package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"

	commandpb "go.temporal.io/api/command/v1"
	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	failurepb "go.temporal.io/api/failure/v1"
	historypb "go.temporal.io/api/history/v1"
	"go.temporal.io/api/workflowservice/v1"
	tokenspb "go.temporal.io/server/api/token/v1"
	"go.temporal.io/server/common/authorization"
	"go.temporal.io/server/common/tasktoken"
	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/proto"
)

type assignedHistoryReadFunc func(context.Context, *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error)

func (read assignedHistoryReadFunc) GetWorkflowExecutionHistory(ctx context.Context, request *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error) {
	return read(ctx, request)
}

func TestAssignedPollHistoryBounds(t *testing.T) {
	for _, tc := range []struct {
		name          string
		initialCursor []byte
		read          func(int) *workflowservice.GetWorkflowExecutionHistoryResponse
		calls         int
	}{
		{"cursor size", make([]byte, 8193), nil, 0},
		{"total history size", []byte("first"), func(int) *workflowservice.GetWorkflowExecutionHistoryResponse {
			return &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{{
				EventId: 1, Attributes: &historypb.HistoryEvent_WorkflowExecutionStartedEventAttributes{
					WorkflowExecutionStartedEventAttributes: &historypb.WorkflowExecutionStartedEventAttributes{
						Input: &commonpb.Payloads{Payloads: []*commonpb.Payload{{Data: make([]byte, maxAssignedPollHistoryBytes)}}},
					},
				}}}}}
		}, 1},
		{"page count", []byte("first"), func(calls int) *workflowservice.GetWorkflowExecutionHistoryResponse {
			return &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{}, NextPageToken: []byte(strconv.Itoa(calls))}
		}, maxAssignedPollHistoryPages - 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			poll := &workflowservice.PollWorkflowTaskQueueResponse{
				StartedEventId: 1,
				History:        &historypb.History{},
				NextPageToken:  bytes.Clone(tc.initialCursor),
			}
			calls := 0
			read := assignedHistoryReadFunc(func(context.Context, *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error) {
				calls++
				if tc.read == nil {
					t.Fatal("history read allowed past the continuation bound")
				}
				return tc.read(calls), nil
			})
			if completeAssignedPollHistory(context.Background(), read, poll) || calls != tc.calls || len(poll.History.Events) != 0 {
				t.Fatalf("expected bounded rejection without a modified poll, got %d continuation reads", calls)
			}
		})
	}
}

func TestCompleteAssignedPollHistory(t *testing.T) {
	execution := &commonpb.WorkflowExecution{WorkflowId: "operation-" + sampleID, RunId: sampleID}
	first := &historypb.HistoryEvent{EventId: 1, EventType: enumspb.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED}
	last := &historypb.HistoryEvent{EventId: 2, EventType: enumspb.EVENT_TYPE_WORKFLOW_TASK_STARTED}
	for _, tc := range []struct {
		name string
		page *workflowservice.GetWorkflowExecutionHistoryResponse
		ok   bool
	}{
		{"exact", &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{last}}}, true},
		{"gap", &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{{EventId: 3}}}}, false},
		{"overlap", &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{first, last}}}, false},
		{"future event", &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{last, {EventId: 3}}}}, false},
		{"truncated", &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{}}, false},
		{"repeated continuation", &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{}, NextPageToken: []byte("server continuation")}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			poll := &workflowservice.PollWorkflowTaskQueueResponse{WorkflowExecution: execution, StartedEventId: 2,
				History: &historypb.History{Events: []*historypb.HistoryEvent{first}}, NextPageToken: []byte("server continuation")}
			read := assignedHistoryReadFunc(func(ctx context.Context, request *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error) {
				if _, bounded := ctx.Deadline(); !bounded || request.GetNamespace() != namespace || !proto.Equal(request.GetExecution(), execution) ||
					!bytes.Equal(request.GetNextPageToken(), poll.GetNextPageToken()) || !request.GetSkipArchival() || request.GetWaitNewEvent() {
					t.Fatal("history continuation escaped the exact poll scope")
				}
				return tc.page, nil
			})
			if completeAssignedPollHistory(context.Background(), read, poll) != tc.ok {
				t.Fatal("unexpected history continuation decision")
			}
			if tc.ok && (len(poll.History.Events) != 2 || len(poll.NextPageToken) != 0) {
				t.Fatal("successful poll did not include the complete history")
			}
			if !tc.ok && (len(poll.History.Events) != 1 || len(poll.NextPageToken) == 0) {
				t.Fatal("failed history completion modified the original poll")
			}
		})
	}
}

func platformRejectedFixture() *failurepb.Failure {
	return &failurepb.Failure{Message: "platform rejected the request", Source: "PythonSDK", StackTrace: "fixture canary", FailureInfo: &failurepb.Failure_ApplicationFailureInfo{
		ApplicationFailureInfo: &failurepb.ApplicationFailureInfo{Type: "PermanentPlatformError", NonRetryable: true},
	}}
}

func TestOnlyKnownActivityFailuresCanEnterHistory(t *testing.T) {
	clean, code := cleanActivityFailure(platformRejectedFixture())
	if code != "PermanentPlatformError" || clean.GetStackTrace() != "" || clean.GetSource() != "" || !clean.GetApplicationFailureInfo().GetNonRetryable() {
		t.Fatal("failure was not reduced to its fixed, nonretryable outcome")
	}
	for _, mutate := range []func(*failurepb.Failure){
		func(f *failurepb.Failure) { f.Message = "fixture canary" },
		func(f *failurepb.Failure) { f.Cause = &failurepb.Failure{Message: "fixture canary"} },
		func(f *failurepb.Failure) { f.EncodedAttributes = &commonpb.Payload{Data: []byte("fixture canary")} },
		func(f *failurepb.Failure) { f.GetApplicationFailureInfo().Details = &commonpb.Payloads{} },
		func(f *failurepb.Failure) { f.GetApplicationFailureInfo().NonRetryable = false },
		func(f *failurepb.Failure) { f.GetApplicationFailureInfo().Type = "UnknownFailure" },
		func(f *failurepb.Failure) { f.ProtoReflect().SetUnknown([]byte{0xf8, 0x01, 0x01}) },
	} {
		fixture := platformRejectedFixture()
		mutate(fixture)
		if clean, _ := cleanActivityFailure(fixture); clean != nil {
			t.Fatal("unapproved failure shape was accepted")
		}
	}
}

func TestActivityFailureRequiresAnIssuedTaskAndCurrentManagerAuthority(t *testing.T) {
	token, err := tasktoken.NewSerializer().Serialize(&tokenspb.Task{WorkflowId: "operation-" + sampleID, RunId: sampleID, ActivityId: "2", ScheduledEventId: 3})
	if err != nil {
		t.Fatal(err)
	}
	receipt, _ := issuedTaskReceipt(token, "ACTIVITY")
	var revoked atomic.Bool
	backend := httptest.NewTLSServer(http.HandlerFunc(func(res http.ResponseWriter, req *http.Request) {
		var supplied nativeTaskReceipt
		if json.NewDecoder(req.Body).Decode(&supplied) == nil && strings.HasSuffix(req.URL.Path, "/check-task") && supplied == receipt && !revoked.Load() {
			res.WriteHeader(http.StatusNoContent)
			return
		}
		res.WriteHeader(http.StatusForbidden)
	}))
	defer backend.Close()
	client := &nativeAuthorizationClient{origin: backend.URL, http: backend.Client(), key: ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize))}
	for _, check := range []struct {
		principal string
		ns        string
		revoked   bool
		cause     uint64
		allowed   bool
	}{
		{manager, namespace, false, 3, true},
		{manager, namespace, false, 1, false},
		{worker, namespace, false, 3, false},
		{manager, "other", false, 3, false},
		{manager, namespace, true, 3, false},
	} {
		revoked.Store(check.revoked)
		request := &workflowservice.RespondActivityTaskFailedRequest{Namespace: check.ns, Identity: managerRPCIdentity, TaskToken: token, Failure: platformRejectedFixture()}
		request.ProtoReflect().SetUnknown(protowire.AppendVarint(protowire.AppendTag(nil, 10, protowire.VarintType), check.cause))
		result, err := (exactRPC{native: client}).Authorize(t.Context(), &authorization.Claims{Subject: check.principal}, &authorization.CallTarget{
			APIName: workflowRPC + "RespondActivityTaskFailed", Namespace: check.ns, Request: request,
		})
		if err != nil || (result.Decision == authorization.DecisionAllow) != check.allowed ||
			check.allowed && (request.Failure.GetStackTrace() != "" || len(request.ProtoReflect().GetUnknown()) != 0) {
			t.Fatal("failure reply did not respect the task receipt and current authority")
		}
	}
}

func TestTimeoutFailureDropsPreviousAttemptAndHeartbeatPayloads(t *testing.T) {
	info := &failurepb.TimeoutFailureInfo{TimeoutType: enumspb.TIMEOUT_TYPE_SCHEDULE_TO_CLOSE}
	failure := &failurepb.Failure{Message: "fixture canary", Cause: platformRejectedFixture(),
		FailureInfo: &failurepb.Failure_TimeoutFailureInfo{TimeoutFailureInfo: info}}
	clean, code := cleanFailureCause(failure)
	if code != info.TimeoutType.String() || clean.GetCause() != nil || clean.GetMessage() == failure.GetMessage() {
		t.Fatal("timeout was not reduced to its approved outcome")
	}
	info.LastHeartbeatDetails = &commonpb.Payloads{}
	if clean, _ := cleanFailureCause(failure); clean != nil {
		t.Fatal("unexpected heartbeat details were accepted")
	}
}

func TestWorkflowFailureRequiresExactHistoryReceipt(t *testing.T) {
	const kind, activityID = "prepare_plan_tasks", "2"
	const workflowType = "PlanExecutionWorkflow"
	const retry = enumspb.RETRY_STATE_NON_RETRYABLE_FAILURE
	execution := &commonpb.WorkflowExecution{WorkflowId: "operation-" + sampleID, RunId: sampleID}
	token, err := tasktoken.NewSerializer().Serialize(&tokenspb.Task{WorkflowId: execution.WorkflowId, RunId: sampleID, ScheduledEventId: 7})
	if err != nil {
		t.Fatal(err)
	}
	events := []*historypb.HistoryEvent{
		{EventId: 3, EventType: enumspb.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED, Attributes: &historypb.HistoryEvent_ActivityTaskScheduledEventAttributes{
			ActivityTaskScheduledEventAttributes: &historypb.ActivityTaskScheduledEventAttributes{ActivityId: activityID, ActivityType: &commonpb.ActivityType{Name: kind}},
		}},
		{EventId: 6, EventType: enumspb.EVENT_TYPE_ACTIVITY_TASK_FAILED, Attributes: &historypb.HistoryEvent_ActivityTaskFailedEventAttributes{
			ActivityTaskFailedEventAttributes: &historypb.ActivityTaskFailedEventAttributes{ScheduledEventId: 3, StartedEventId: 4, RetryState: retry, Failure: platformRejectedFixture()},
		}},
		{EventId: 7, EventType: enumspb.EVENT_TYPE_WORKFLOW_TASK_SCHEDULED},
		{EventId: 8, EventType: enumspb.EVENT_TYPE_WORKFLOW_TASK_STARTED},
	}
	polled := &workflowservice.PollWorkflowTaskQueueResponse{WorkflowType: &commonpb.WorkflowType{Name: workflowType}, History: &historypb.History{Events: events}}
	proof, witnessed := activityFailureFromHistory(polled)
	base, exact := issuedTaskReceipt(token, "WORKFLOW")
	if !witnessed || !exact {
		t.Fatal("failed Activity or exact workflow receipt was not recognized")
	}
	proofReceipt := proof.receipt(token, base)
	if proofReceipt.TokenSHA256 == base.TokenSHA256 {
		t.Fatal("technical failure acquired the ordinary task receipt digest")
	}
	polled.NextPageToken = []byte("fixture pagination")
	if _, witnessed := activityFailureFromHistory(polled); witnessed {
		t.Fatal("partial history could authorize a stale failure")
	}
	polled.NextPageToken = nil
	polled.History.Events = append(events[:2:2], &historypb.HistoryEvent{EventId: 7, EventType: enumspb.EVENT_TYPE_ACTIVITY_TASK_COMPLETED})
	if _, witnessed := activityFailureFromHistory(polled); witnessed {
		t.Fatal("an earlier failure survived a newer Activity result")
	}
	backend := httptest.NewTLSServer(http.HandlerFunc(func(res http.ResponseWriter, req *http.Request) {
		var receipt nativeTaskReceipt
		if json.NewDecoder(req.Body).Decode(&receipt) != nil {
			res.WriteHeader(http.StatusBadRequest)
			return
		}
		switch {
		case strings.HasSuffix(req.URL.Path, "/workflow-task-context") && receipt == base:
			_ = json.NewEncoder(res).Encode(workflowTaskContext{AssignmentID: sampleID, WorkflowContractVersion: 1,
				WorkflowType: workflowType, InputSha256: strings.Repeat("0", 64), OperationStatus: "RUNNING"})
		case strings.HasSuffix(req.URL.Path, "/check-task") && receipt == proofReceipt:
			res.WriteHeader(http.StatusNoContent)
		default:
			res.WriteHeader(http.StatusForbidden)
		}
	}))
	defer backend.Close()
	client := &nativeAuthorizationClient{origin: backend.URL, http: backend.Client(), key: ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize))}
	request := func(eventID int64) *workflowservice.RespondWorkflowTaskCompletedRequest {
		failure := &failurepb.Failure{Message: "fixture canary", StackTrace: "fixture canary", Cause: platformRejectedFixture(), FailureInfo: &failurepb.Failure_ActivityFailureInfo{
			ActivityFailureInfo: &failurepb.ActivityFailureInfo{ScheduledEventId: eventID, StartedEventId: 4, RetryState: retry,
				ActivityId: activityID, ActivityType: &commonpb.ActivityType{Name: kind}, Identity: "fixture canary"},
		}}
		return &workflowservice.RespondWorkflowTaskCompletedRequest{Namespace: namespace, Identity: managerRPCIdentity, TaskToken: token,
			Commands: []*commandpb.Command{{CommandType: enumspb.COMMAND_TYPE_FAIL_WORKFLOW_EXECUTION, Attributes: &commandpb.Command_FailWorkflowExecutionCommandAttributes{
				FailWorkflowExecutionCommandAttributes: &commandpb.FailWorkflowExecutionCommandAttributes{Failure: failure},
			}}},
		}
	}
	if client.allowWorkflowCompletion(t.Context(), request(2)) {
		t.Fatal("unwitnessed failure was allowed with only a real workflow task receipt")
	}
	allowed := request(3)
	if !client.allowWorkflowCompletion(t.Context(), allowed) {
		t.Fatal("witnessed failure was rejected")
	}
	encoded, err := proto.Marshal(allowed)
	if err != nil || bytes.Contains(encoded, []byte("fixture canary")) {
		t.Fatal("worker-provided strings survived the server-side normalization")
	}
	if result, err := (exactRPC{native: client}).Authorize(t.Context(), &authorization.Claims{Subject: worker}, &authorization.CallTarget{
		APIName: workflowRPC + "RespondWorkflowTaskCompleted", Namespace: namespace, Request: request(3),
	}); err != nil || result.Decision != authorization.DecisionDeny {
		t.Fatal("a worker principal was allowed to process a Manager workflow task")
	}
}
