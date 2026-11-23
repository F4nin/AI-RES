package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"slices"
	"strings"
	"time"

	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	historypb "go.temporal.io/api/history/v1"
	taskqueuepb "go.temporal.io/api/taskqueue/v1"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

const assignedManagerQueue = "ai-res-manager"

const (
	// Bound the combined poll response below the worker's default 4 MiB receive limit.
	maxAssignedPollHistoryBytes = 3 * 1024 * 1024
	maxAssignedPollHistoryPages = 64
	assignedPollHistoryTimeout  = 3 * time.Second
)

type assignedHistoryReader interface {
	GetWorkflowExecutionHistory(context.Context, *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error)
}

// The matching service supplies the only continuation accepted here. It is
// consumed within the authorized poll, using the exact Run and no public History RPC.
func completeAssignedPollHistory(ctx context.Context, reader assignedHistoryReader, poll *workflowservice.PollWorkflowTaskQueueResponse) bool {
	if reader == nil || poll.GetStartedEventId() < 1 || poll.GetHistory() == nil {
		return false
	}
	size := proto.Size(poll)
	if size > maxAssignedPollHistoryBytes {
		return false
	}
	ctx, cancel := context.WithTimeout(ctx, assignedPollHistoryTimeout)
	defer cancel()
	var events []*historypb.HistoryEvent
	lastID := int64(0)
	appendPage := func(page []*historypb.HistoryEvent) bool {
		for _, event := range page {
			if event.GetEventId() != lastID+1 || event.GetEventId() > poll.GetStartedEventId() {
				return false
			}
			lastID = event.GetEventId()
		}
		events = append(events, page...)
		return true
	}
	if !appendPage(poll.GetHistory().GetEvents()) {
		return false
	}
	token := poll.GetNextPageToken()
	for page := 1; len(token) != 0; page++ {
		if page >= maxAssignedPollHistoryPages || len(token) > 8192 || ctx.Err() != nil {
			return false
		}
		result, err := reader.GetWorkflowExecutionHistory(ctx, &workflowservice.GetWorkflowExecutionHistoryRequest{
			Namespace: namespace, Execution: poll.GetWorkflowExecution(), NextPageToken: token,
			MaximumPageSize: 100, SkipArchival: true, HistoryEventFilterType: enumspb.HISTORY_EVENT_FILTER_TYPE_ALL_EVENT,
		})
		if err != nil || result.GetHistory() == nil || len(result.GetRawHistory()) != 0 {
			return false
		}
		size += proto.Size(result.GetHistory())
		next := result.GetNextPageToken()
		if size > maxAssignedPollHistoryBytes || slices.Equal(token, next) || !appendPage(result.GetHistory().GetEvents()) {
			return false
		}
		token = next
	}
	if ctx.Err() != nil || lastID != poll.GetStartedEventId() || events[len(events)-1].GetEventType() != enumspb.EVENT_TYPE_WORKFLOW_TASK_STARTED {
		return false
	}
	poll.History.Events = events
	poll.NextPageToken = nil
	return true
}

type nativeTaskReceipt struct {
	TokenSHA256   string `json:"tokenSha256"`
	Principal     string `json:"principal"`
	Namespace     string `json:"namespace"`
	Queue         string `json:"queue"`
	TaskKind      string `json:"taskKind"`
	OperationID   string `json:"operationId"`
	WorkflowRunID string `json:"workflowRunId"`
}

func permittedManagerPoll(subject, requestNamespace string, queue *taskqueuepb.TaskQueue) bool {
	return subject == manager && requestNamespace == namespace &&
		queue.GetName() == assignedManagerQueue && queue.GetNormalName() == "" &&
		(queue.GetKind() == enumspb.TASK_QUEUE_KIND_NORMAL || queue.GetKind() == enumspb.TASK_QUEUE_KIND_UNSPECIFIED) &&
		len(queue.ProtoReflect().GetUnknown()) == 0
}

func permittedManagerActivity(workflowType, activityType string) bool {
	switch workflowType {
	case "ManagerIntakeWorkflow", "PlanExecutionWorkflow":
		switch activityType {
		case "acknowledge_bound_start", "confirm_bound_cancellation":
			return true
		case "complete_manager_intake":
			return workflowType == "ManagerIntakeWorkflow"
		case "prepare_plan_tasks":
			return workflowType == "PlanExecutionWorkflow"
		}
	}
	return false
}

func exactPollerVersion(version *commonpb.WorkerVersionCapabilities) bool {
	return version == nil || (version.GetBuildId() == managerBuild && allowedFields(version.ProtoReflect(), "build_id"))
}

func discardPollerCompatibilityFields(message protoreflect.Message) bool {
	raw := message.GetUnknown()
	if len(raw) == 0 {
		return true
	}
	// SDK 1.36 appends worker_instance_key (8) and optional poller_pool_info (11).
	// Validate the instance and bounded target_pollers count before dropping the fields.
	keySize := workerInstanceSize(raw, 8)
	if keySize == 0 {
		return false
	}
	if extras := raw[keySize:]; len(extras) != 0 {
		number, wireType, tagSize := protowire.ConsumeTag(extras)
		if tagSize < 0 || number != 11 || wireType != protowire.BytesType {
			return false
		}
		pool, size := protowire.ConsumeBytes(extras[tagSize:])
		if size < 0 || tagSize+size != len(extras) {
			return false
		}
		field, kind, tag := protowire.ConsumeTag(pool)
		if tag < 0 || field != 1 || kind != protowire.VarintType {
			return false
		}
		count, packed := protowire.ConsumeVarint(pool[tag:])
		if packed < 0 || tag+packed != len(pool) || count < 1 || count > 5 {
			return false
		}
	}
	message.SetUnknown(nil)
	return true
}

func exactWorkflowPoll(poll *workflowservice.PollWorkflowTaskQueueRequest) bool {
	return poll.GetIdentity() == managerRPCIdentity &&
		(poll.GetBinaryChecksum() == "" || poll.GetBinaryChecksum() == managerBuild) && exactPollerVersion(poll.GetWorkerVersionCapabilities()) &&
		discardPollerCompatibilityFields(poll.ProtoReflect()) &&
		allowedFields(poll.ProtoReflect(), "namespace", "task_queue", "identity", "binary_checksum", "worker_version_capabilities")
}

func exactActivityPoll(poll *workflowservice.PollActivityTaskQueueRequest) bool {
	return poll.GetIdentity() == managerRPCIdentity && exactPollerVersion(poll.GetWorkerVersionCapabilities()) &&
		(poll.GetTaskQueueMetadata() == nil || allowedFields(poll.GetTaskQueueMetadata().ProtoReflect())) &&
		discardPollerCompatibilityFields(poll.ProtoReflect()) &&
		allowedFields(poll.ProtoReflect(), "namespace", "task_queue", "identity", "task_queue_metadata", "worker_version_capabilities")
}

func (c *nativeAuthorizationClient) registerPolledTask(
	ctx context.Context, ref *commonpb.WorkflowExecution, token []byte, kind string,
) bool {
	receipt, exact := taskReceipt(ref, token, kind)
	return exact && c.authorize(ctx, "register-task", receipt)
}

func taskReceipt(ref *commonpb.WorkflowExecution, token []byte, kind string) (nativeTaskReceipt, bool) {
	if len(token) == 0 || len(token) > 8192 {
		return nativeTaskReceipt{}, false
	}
	operation, exact := strings.CutPrefix(ref.GetWorkflowId(), "operation-")
	if !exact || !uuidForm.MatchString(operation) || !uuidForm.MatchString(ref.GetRunId()) {
		return nativeTaskReceipt{}, false
	}
	digest := sha256.Sum256(token)
	return nativeTaskReceipt{
		TokenSHA256: hex.EncodeToString(digest[:]), Principal: "MANAGER_RUNTIME",
		Namespace: namespace, Queue: assignedManagerQueue, TaskKind: kind,
		OperationID: operation, WorkflowRunID: ref.GetRunId(),
	}, true
}

func (c *nativeAuthorizationClient) interceptPoll(ctx context.Context, request any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	if info.FullMethod != workflowRPC+"PollWorkflowTaskQueue" && info.FullMethod != workflowRPC+"PollActivityTaskQueue" {
		return handler(ctx, request)
	}
	claims, _ := ctx.Value(authorization.MappedClaims).(*authorization.Claims)
	if claims == nil {
		return nil, status.Error(codes.PermissionDenied, "task scope denied")
	}
	switch poll := request.(type) {
	case *workflowservice.PollWorkflowTaskQueueRequest:
		if !permittedManagerPoll(claims.Subject, poll.GetNamespace(), poll.GetTaskQueue()) || !exactWorkflowPoll(poll) {
			return nil, status.Error(codes.PermissionDenied, "task scope denied")
		}
	case *workflowservice.PollActivityTaskQueueRequest:
		if !permittedManagerPoll(claims.Subject, poll.GetNamespace(), poll.GetTaskQueue()) || !exactActivityPoll(poll) {
			return nil, status.Error(codes.PermissionDenied, "task scope denied")
		}
	default:
		return nil, status.Error(codes.PermissionDenied, "task scope denied")
	}
	result, err := handler(ctx, request)
	if err != nil {
		return nil, err
	}
	switch polled := result.(type) {
	case *workflowservice.PollWorkflowTaskQueueResponse:
		if len(polled.GetTaskToken()) == 0 {
			return result, nil
		}
		kind := polled.GetWorkflowType().GetName()
		if kind == "ManagerIntakeWorkflow" || kind == "PlanExecutionWorkflow" {
			receipt, exact := taskReceipt(polled.GetWorkflowExecution(), polled.GetTaskToken(), "WORKFLOW")
			if exact && c.authorize(ctx, "register-task", receipt) {
				if len(polled.GetNextPageToken()) != 0 {
					reader, _ := info.Server.(assignedHistoryReader)
					if !completeAssignedPollHistory(ctx, reader, polled) || !c.authorize(ctx, "check-task", receipt) {
						return nil, status.Error(codes.Unavailable, "task issuance unavailable")
					}
				}
				proof, witnessed := activityFailureFromHistory(polled)
				if !witnessed || c.authorize(ctx, "register-task", proof.receipt(polled.GetTaskToken(), receipt)) {
					return result, nil
				}
			}
		}
	case *workflowservice.PollActivityTaskQueueResponse:
		if len(polled.GetTaskToken()) == 0 {
			return result, nil
		}
		if permittedManagerActivity(polled.GetWorkflowType().GetName(), polled.GetActivityType().GetName()) &&
			c.registerPolledTask(ctx, polled.GetWorkflowExecution(), polled.GetTaskToken(), "ACTIVITY") {
			return result, nil
		}
	}
	return nil, status.Error(codes.Unavailable, "task issuance unavailable")
}
