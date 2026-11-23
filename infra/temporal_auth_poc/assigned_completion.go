package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"slices"
	"strconv"
	"time"

	commandpb "go.temporal.io/api/command/v1"
	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	sdkpb "go.temporal.io/api/sdk/v1"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/tasktoken"
	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/known/durationpb"
)

const managerRPCIdentity = "ai-res-manager-runtime"

type workflowTaskContext struct {
	AssignmentID            string `json:"assignmentId"`
	WorkflowContractVersion int    `json:"workflowContractVersion"`
	WorkflowType            string `json:"workflowType"`
	InputSha256             string `json:"inputSha256"`
	OperationStatus         string `json:"operationStatus"`
}

type boundActivityInput struct {
	AssignmentID  string            `json:"assignment_id"`
	Operation     assignedOperation `json:"operation"`
	WorkflowID    string            `json:"workflow_id"`
	WorkflowRunID string            `json:"workflow_run_id"`
}

type operationState struct {
	OperationID string `json:"operation_id"`
	Status      string `json:"status"`
}

func issuedTaskReceipt(token []byte, kind string) (nativeTaskReceipt, bool) {
	if len(token) == 0 || len(token) > 8192 {
		return nativeTaskReceipt{}, false
	}
	facts, err := tasktoken.NewSerializer().Deserialize(token)
	if err != nil || facts.GetScheduledEventId() < 1 || (facts.GetActivityId() != "") != (kind == "ACTIVITY") {
		return nativeTaskReceipt{}, false
	}
	return taskReceipt(&commonpb.WorkflowExecution{WorkflowId: facts.GetWorkflowId(), RunId: facts.GetRunId()}, token, kind)
}

func (c *nativeAuthorizationClient) workflowTaskScope(ctx context.Context, receipt nativeTaskReceipt) (workflowTaskContext, bool) {
	result := c.post(ctx, "workflow-task-context", receipt)
	if result == nil {
		return workflowTaskContext{}, false
	}
	defer result.Body.Close()
	if result.StatusCode != http.StatusOK {
		return workflowTaskContext{}, false
	}
	raw, err := io.ReadAll(io.LimitReader(result.Body, 513))
	if err != nil || len(raw) > 512 {
		return workflowTaskContext{}, false
	}
	var scope workflowTaskContext
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&scope) != nil || decoder.Decode(new(any)) != io.EOF {
		return workflowTaskContext{}, false
	}
	if scope.WorkflowContractVersion != 1 || !uuidForm.MatchString(scope.AssignmentID) ||
		(scope.WorkflowType != "ManagerIntakeWorkflow" && scope.WorkflowType != "PlanExecutionWorkflow") {
		return workflowTaskContext{}, false
	}
	digest, err := hex.DecodeString(scope.InputSha256)
	return scope, err == nil && len(digest) == sha256.Size && validStatus(scope.OperationStatus)
}

func exactTaskPayload[T any](input *commonpb.Payloads, target *T) bool {
	if len(input.GetPayloads()) != 1 || len(input.ProtoReflect().GetUnknown()) != 0 {
		return false
	}
	payload := input.GetPayloads()[0]
	if len(payload.GetData()) > 512 || len(payload.GetMetadata()) != 1 || string(payload.GetMetadata()["encoding"]) != "json/plain" ||
		len(payload.ProtoReflect().GetUnknown()) != 0 || json.Unmarshal(payload.GetData(), target) != nil {
		return false
	}
	canonical, err := json.Marshal(target)
	return err == nil && bytes.Equal(payload.GetData(), canonical)
}

func exactStatus(input *commonpb.Payloads, operationID string) bool {
	var state operationState
	return exactTaskPayload(input, &state) && state.OperationID == operationID && validStatus(state.Status)
}

func validStatus(status string) bool {
	switch status {
	case "ACCEPTED", "QUEUED", "RUNNING", "WAITING_FOR_HUMAN", "WAITING_FOR_DEPENDENCY", "RETRYING",
		"CANCEL_REQUESTED", "SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED":
		return true
	}
	return false
}

func exactTerminalStatus(input *commonpb.Payloads, operationID, expectedStatus string) bool {
	var state operationState
	if !exactTaskPayload(input, &state) || state.OperationID != operationID || state.Status != expectedStatus {
		return false
	}
	return slices.Contains([]string{"SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED"}, state.Status)
}

func allowedFields(message protoreflect.Message, fields ...protoreflect.Name) bool {
	if len(message.GetUnknown()) != 0 {
		return false
	}
	allowed := true
	message.Range(func(field protoreflect.FieldDescriptor, _ protoreflect.Value) bool {
		allowed = slices.Contains(fields, field.Name())
		return allowed
	})
	return allowed
}

func exactWorkerVersion(stamp *commonpb.WorkerVersionStamp) bool {
	return stamp == nil || (stamp.GetBuildId() == managerBuild && allowedFields(stamp.ProtoReflect(), "build_id"))
}

func discardWorkerInstanceKey(message protoreflect.Message, workerInstanceKey protowire.Number) bool {
	// Python SDK 1.36 sends a worker-instance ID for tracking in newer frontends.
	// Validate the identifier and drop it before core handling on the pinned frontend.
	unknown := message.GetUnknown()
	if len(unknown) == 0 {
		return true
	}
	if workerInstanceSize(unknown, workerInstanceKey) != len(unknown) {
		return false
	}
	message.SetUnknown(nil)
	return true
}

func workerInstanceSize(raw []byte, field protowire.Number) int {
	number, wireType, tagSize := protowire.ConsumeTag(raw)
	if tagSize < 0 || number != field || wireType != protowire.BytesType {
		return 0
	}
	key, valueSize := protowire.ConsumeString(raw[tagSize:])
	if valueSize < 0 || !uuidForm.MatchString(key) {
		return 0
	}
	return tagSize + valueSize
}

func exactSDKMetadata(metadata *sdkpb.WorkflowTaskCompletedMetadata) bool {
	if metadata == nil {
		return true
	}
	if !allowedFields(metadata.ProtoReflect(), "core_used_flags", "lang_used_flags", "sdk_name", "sdk_version") ||
		(metadata.GetSdkName() != "" && metadata.GetSdkName() != "temporal-python") ||
		(metadata.GetSdkVersion() != "" && metadata.GetSdkVersion() != "1.36.0") {
		return false
	}
	return exactSDKFlags(metadata.GetCoreUsedFlags()) && exactSDKFlags(metadata.GetLangUsedFlags())
}

func exactSDKFlags(flags []uint32) bool {
	var seen uint16
	for _, flag := range flags {
		if flag < 1 || flag > 8 || seen&(1<<flag) != 0 {
			return false
		}
		seen |= 1 << flag
	}
	return true
}

func boundedDuration(value *durationpb.Duration, max time.Duration) bool {
	return value != nil && value.IsValid() && allowedFields(value.ProtoReflect(), "seconds", "nanos") &&
		value.AsDuration() > 0 && value.AsDuration() <= max
}

func exactActivity(
	attributes *commandpb.ScheduleActivityTaskCommandAttributes, receipt nativeTaskReceipt, scope workflowTaskContext,
) bool {
	if attributes == nil || attributes.GetRequestEagerExecution() || attributes.GetTaskQueue().GetName() != assignedManagerQueue ||
		attributes.GetTaskQueue().GetNormalName() != "" ||
		(attributes.GetTaskQueue().GetKind() != enumspb.TASK_QUEUE_KIND_NORMAL && attributes.GetTaskQueue().GetKind() != enumspb.TASK_QUEUE_KIND_UNSPECIFIED) ||
		!allowedFields(attributes.ProtoReflect(), "activity_id", "activity_type", "task_queue", "input", "header",
			"schedule_to_close_timeout", "start_to_close_timeout", "retry_policy", "use_workflow_build_id", "priority") ||
		!permittedManagerActivity(scope.WorkflowType, attributes.GetActivityType().GetName()) {
		return false
	}
	if !boundedDuration(attributes.GetScheduleToCloseTimeout(), 15*time.Minute) ||
		!boundedDuration(attributes.GetStartToCloseTimeout(), 30*time.Second) ||
		(attributes.GetHeader() != nil && !allowedFields(attributes.GetHeader().ProtoReflect())) ||
		(attributes.GetPriority() != nil && !allowedFields(attributes.GetPriority().ProtoReflect())) ||
		!allowedFields(attributes.GetTaskQueue().ProtoReflect(), "name", "kind") ||
		!allowedFields(attributes.GetActivityType().ProtoReflect(), "name") {
		return false
	}
	retry := attributes.GetRetryPolicy()
	if retry == nil || !allowedFields(retry.ProtoReflect(), "maximum_attempts", "initial_interval", "maximum_interval", "backoff_coefficient", "non_retryable_error_types") {
		return false
	}
	maxRetryInterval := 30 * time.Second
	if retry.GetMaximumAttempts() == 1 {
		maxRetryInterval = 100 * time.Second // Pinned SDK default. The Activity has only one attempt.
	}
	if (retry.GetInitialInterval() != nil && !boundedDuration(retry.GetInitialInterval(), time.Second)) ||
		(retry.GetMaximumInterval() != nil && !boundedDuration(retry.GetMaximumInterval(), maxRetryInterval)) ||
		(retry.GetBackoffCoefficient() != 0 && retry.GetBackoffCoefficient() != 2) {
		return false
	}
	if attributes.GetActivityType().GetName() == "complete_manager_intake" {
		if retry.GetMaximumAttempts() != 1 || len(retry.GetNonRetryableErrorTypes()) != 0 {
			return false
		}
	} else if retry.GetMaximumAttempts() != 0 || !slices.Equal(retry.GetNonRetryableErrorTypes(), []string{"PermanentPlatformError"}) {
		return false
	}
	activityID, err := strconv.Atoi(attributes.GetActivityId())
	if err != nil || activityID < 1 || strconv.Itoa(activityID) != attributes.GetActivityId() {
		return false
	}
	var input boundActivityInput
	if !exactTaskPayload(attributes.GetInput(), &input) || input.AssignmentID != scope.AssignmentID ||
		input.Operation.OperationID != receipt.OperationID || input.WorkflowID != "operation-"+receipt.OperationID ||
		input.WorkflowRunID != receipt.WorkflowRunID {
		return false
	}
	canonical, err := json.Marshal(assignedInput{input.AssignmentID, scope.WorkflowContractVersion, input.Operation})
	digest := sha256.Sum256(canonical)
	return err == nil && hex.EncodeToString(digest[:]) == scope.InputSha256
}

func (c *nativeAuthorizationClient) allowWorkflowCompletion(ctx context.Context, request *workflowservice.RespondWorkflowTaskCompletedRequest) bool {
	if request == nil || request.GetReturnNewWorkflowTask() || request.GetForceCreateNewWorkflowTask() ||
		request.GetStickyAttributes() != nil || len(request.GetCommands()) > 1 || request.GetIdentity() != managerRPCIdentity ||
		!discardWorkerInstanceKey(request.ProtoReflect(), 19) || !allowedFields(
		request.ProtoReflect(), "task_token", "commands", "identity", "namespace", "worker_version_stamp", "sdk_metadata", "metering_metadata", "capabilities",
	) {
		return false
	}
	if !exactWorkerVersion(request.GetWorkerVersionStamp()) || !exactSDKMetadata(request.GetSdkMetadata()) ||
		(request.GetMeteringMetadata() != nil && !allowedFields(request.GetMeteringMetadata().ProtoReflect())) ||
		(request.GetCapabilities() != nil && !allowedFields(request.GetCapabilities().ProtoReflect(), "discard_speculative_workflow_task_with_events")) {
		return false
	}
	receipt, exact := issuedTaskReceipt(request.GetTaskToken(), "WORKFLOW")
	if !exact {
		return false
	}
	scope, authorized := c.workflowTaskScope(ctx, receipt)
	if !authorized {
		return false
	}
	for _, command := range request.GetCommands() {
		if !allowedFields(command.ProtoReflect(), "command_type", "schedule_activity_task_command_attributes",
			"complete_workflow_execution_command_attributes", "fail_workflow_execution_command_attributes", "start_timer_command_attributes") {
			return false
		}
		switch command.GetCommandType() {
		case enumspb.COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK:
			if !exactActivity(command.GetScheduleActivityTaskCommandAttributes(), receipt, scope) {
				return false
			}
		case enumspb.COMMAND_TYPE_COMPLETE_WORKFLOW_EXECUTION:
			attributes := command.GetCompleteWorkflowExecutionCommandAttributes()
			if attributes == nil || !allowedFields(attributes.ProtoReflect(), "result") ||
				!exactTerminalStatus(attributes.GetResult(), receipt.OperationID, scope.OperationStatus) {
				return false
			}
		case enumspb.COMMAND_TYPE_FAIL_WORKFLOW_EXECUTION:
			attributes := command.GetFailWorkflowExecutionCommandAttributes()
			if attributes == nil || !allowedFields(attributes.ProtoReflect(), "failure") {
				return false
			}
			clean, proof := cleanWorkflowFailure(attributes.GetFailure(), scope)
			if clean == nil || !c.authorize(ctx, "check-task", proof.receipt(request.GetTaskToken(), receipt)) {
				return false
			}
			attributes.Failure = clean
		case enumspb.COMMAND_TYPE_START_TIMER:
			timer := command.GetStartTimerCommandAttributes()
			timerID, err := strconv.Atoi(timer.GetTimerId())
			if timer == nil || !allowedFields(timer.ProtoReflect(), "timer_id", "start_to_fire_timeout") ||
				err != nil || timerID < 1 || strconv.Itoa(timerID) != timer.GetTimerId() ||
				!boundedDuration(timer.GetStartToFireTimeout(), 30*time.Second) || timer.GetStartToFireTimeout().AsDuration() != 30*time.Second {
				return false
			}
		default:
			return false
		}
	}
	return true
}

func (c *nativeAuthorizationClient) allowActivityCompletion(ctx context.Context, request *workflowservice.RespondActivityTaskCompletedRequest) bool {
	if request == nil || request.GetIdentity() != managerRPCIdentity || !exactWorkerVersion(request.GetWorkerVersion()) ||
		!allowedFields(request.ProtoReflect(), "task_token", "result", "identity", "namespace", "worker_version") {
		return false
	}
	receipt, exact := issuedTaskReceipt(request.GetTaskToken(), "ACTIVITY")
	return exact && exactStatus(request.GetResult(), receipt.OperationID) && c.authorize(ctx, "check-task", receipt)
}
