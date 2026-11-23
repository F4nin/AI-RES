package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	failurepb "go.temporal.io/api/failure/v1"
	"go.temporal.io/api/workflowservice/v1"
	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/reflect/protoreflect"
)

func cleanActivityFailure(failure *failurepb.Failure) (*failurepb.Failure, string) {
	if failure == nil || !allowedFields(failure.ProtoReflect(), "message", "source", "stack_trace", "application_failure_info") ||
		(failure.GetSource() != "" && failure.GetSource() != "PythonSDK") {
		return nil, ""
	}
	application := failure.GetApplicationFailureInfo()
	if application == nil || !allowedFields(application.ProtoReflect(), "type", "non_retryable") {
		return nil, ""
	}
	var message string
	var permanent bool
	switch application.GetType() {
	case "PlatformTransientError":
		message = "platform temporarily unavailable"
	case "PermanentPlatformError":
		message, permanent = "platform rejected the request", true
	case "ManagerActivityFailed":
		message, permanent = "Manager Activity failed", true
	default:
		return nil, ""
	}
	if failure.GetMessage() != message || application.GetNonRetryable() != permanent {
		return nil, ""
	}
	return &failurepb.Failure{Message: message, FailureInfo: &failurepb.Failure_ApplicationFailureInfo{
		ApplicationFailureInfo: &failurepb.ApplicationFailureInfo{Type: application.GetType(), NonRetryable: permanent},
	}}, application.GetType()
}

func (c *nativeAuthorizationClient) allowActivityFailure(ctx context.Context, request *workflowservice.RespondActivityTaskFailedRequest) bool {
	if request == nil || request.GetNamespace() != namespace || request.GetIdentity() != managerRPCIdentity ||
		!exactWorkerVersion(request.GetWorkerVersion()) ||
		!discardSDKActivityFailureCause(request.ProtoReflect()) ||
		!allowedFields(request.ProtoReflect(), "task_token", "failure", "identity", "namespace", "worker_version") {
		return false
	}
	receipt, exact := issuedTaskReceipt(request.GetTaskToken(), "ACTIVITY")
	clean, _ := cleanActivityFailure(request.GetFailure())
	if !exact || clean == nil || !c.authorize(ctx, "check-task", receipt) {
		return false
	}
	request.Failure = clean
	return true
}

func discardSDKActivityFailureCause(message protoreflect.Message) bool {
	raw := message.GetUnknown()
	if len(raw) == 0 {
		return true
	}
	// Python SDK 1.36 reports cause=ACTIVITY_WORKER_UNHANDLED_FAILURE (3) in field 10.
	// The pinned Temporal server predates this field. Remove the one compatible value.
	field, kind, tagSize := protowire.ConsumeTag(raw)
	if tagSize < 0 || field != 10 || kind != protowire.VarintType {
		return false
	}
	value, valueSize := protowire.ConsumeVarint(raw[tagSize:])
	if valueSize < 0 || value != 3 || tagSize+valueSize != len(raw) {
		return false
	}
	message.SetUnknown(nil)
	return true
}

type activityFailureProof struct {
	scheduled, started   int64
	retry                enumspb.RetryState
	activity, kind, code string
}

func (proof activityFailureProof) receipt(token []byte, base nativeTaskReceipt) nativeTaskReceipt {
	// Separate this proof digest from SHA-256(raw task token) when using the existing durable receipt store.
	mac := hmac.New(sha256.New, token)
	fmt.Fprintf(mac, "ai-res/workflow-activity-failure/v1:%d:%d:%d:%s:%s:%s",
		proof.scheduled, proof.started, proof.retry, proof.activity, proof.kind, proof.code)
	base.TokenSHA256 = hex.EncodeToString(mac.Sum(nil))
	return base
}

func cleanFailureCause(failure *failurepb.Failure) (*failurepb.Failure, string) {
	if failure == nil || failure.GetTimeoutFailureInfo() == nil {
		return cleanActivityFailure(failure)
	}
	timeout := failure.GetTimeoutFailureInfo()
	if !allowedFields(failure.ProtoReflect(), "message", "source", "stack_trace", "timeout_failure_info", "cause") ||
		!allowedFields(timeout.ProtoReflect(), "timeout_type") {
		return nil, ""
	}
	kind := timeout.GetTimeoutType()
	switch kind {
	case enumspb.TIMEOUT_TYPE_SCHEDULE_TO_CLOSE, enumspb.TIMEOUT_TYPE_SCHEDULE_TO_START, enumspb.TIMEOUT_TYPE_START_TO_CLOSE:
		return &failurepb.Failure{Message: "Assigned Activity timed out", FailureInfo: &failurepb.Failure_TimeoutFailureInfo{
			TimeoutFailureInfo: &failurepb.TimeoutFailureInfo{TimeoutType: kind},
		}}, kind.String()
	default:
		return nil, ""
	}
}

func activityFailureFromHistory(polled *workflowservice.PollWorkflowTaskQueueResponse) (activityFailureProof, bool) {
	var proof activityFailureProof
	if len(polled.GetNextPageToken()) != 0 {
		return proof, false
	}
	events := polled.GetHistory().GetEvents()
	for index := len(events) - 1; index >= 0; index-- {
		event := events[index]
		switch event.GetEventType() {
		case enumspb.EVENT_TYPE_WORKFLOW_TASK_SCHEDULED, enumspb.EVENT_TYPE_WORKFLOW_TASK_STARTED,
			enumspb.EVENT_TYPE_WORKFLOW_TASK_FAILED, enumspb.EVENT_TYPE_WORKFLOW_TASK_TIMED_OUT,
			enumspb.EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED:
			continue
		case enumspb.EVENT_TYPE_ACTIVITY_TASK_FAILED:
			failed := event.GetActivityTaskFailedEventAttributes()
			_, code := cleanActivityFailure(failed.GetFailure())
			proof = activityFailureProof{scheduled: failed.GetScheduledEventId(), started: failed.GetStartedEventId(), retry: failed.GetRetryState(), code: code}
		case enumspb.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT:
			timedOut := event.GetActivityTaskTimedOutEventAttributes()
			_, code := cleanFailureCause(timedOut.GetFailure())
			proof = activityFailureProof{scheduled: timedOut.GetScheduledEventId(), started: timedOut.GetStartedEventId(), retry: timedOut.GetRetryState(), code: code}
		default:
			return proof, false
		}
		if proof.code == "" || proof.scheduled < 1 {
			return proof, false
		}
		for _, scheduled := range events[:index] {
			if scheduled.GetEventId() == proof.scheduled {
				attributes := scheduled.GetActivityTaskScheduledEventAttributes()
				proof.kind, proof.activity = attributes.GetActivityType().GetName(), attributes.GetActivityId()
				return proof, proof.activity != "" && permittedManagerActivity(polled.GetWorkflowType().GetName(), proof.kind)
			}
		}
		return proof, false
	}
	return proof, false
}

func cleanWorkflowFailure(failure *failurepb.Failure, scope workflowTaskContext) (*failurepb.Failure, activityFailureProof) {
	var proof activityFailureProof
	if failure == nil || !allowedFields(failure.ProtoReflect(), "message", "source", "stack_trace", "cause", "activity_failure_info") {
		return nil, proof
	}
	info := failure.GetActivityFailureInfo()
	if info == nil || !allowedFields(info.ProtoReflect(), "scheduled_event_id", "started_event_id", "identity", "activity_type", "activity_id", "retry_state") ||
		!allowedFields(info.GetActivityType().ProtoReflect(), "name") || !permittedManagerActivity(scope.WorkflowType, info.GetActivityType().GetName()) ||
		info.GetScheduledEventId() < 1 || info.GetActivityId() == "" {
		return nil, proof
	}
	cause, code := cleanFailureCause(failure.GetCause())
	if cause == nil {
		return nil, proof
	}
	proof = activityFailureProof{scheduled: info.GetScheduledEventId(), started: info.GetStartedEventId(), retry: info.GetRetryState(),
		activity: info.GetActivityId(), kind: info.GetActivityType().GetName(), code: code}
	return &failurepb.Failure{Message: "Assigned Activity did not complete", Cause: cause, FailureInfo: &failurepb.Failure_ActivityFailureInfo{
		ActivityFailureInfo: &failurepb.ActivityFailureInfo{ScheduledEventId: proof.scheduled, StartedEventId: proof.started, RetryState: proof.retry,
			ActivityType: &commonpb.ActivityType{Name: proof.kind}, ActivityId: proof.activity},
	}}, proof
}
