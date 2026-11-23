package main

import (
	"encoding/json"
	"testing"
	"time"

	commandpb "go.temporal.io/api/command/v1"
	commonpb "go.temporal.io/api/common/v1"
	taskqueuepb "go.temporal.io/api/taskqueue/v1"
	"go.temporal.io/api/workflowservice/v1"
	"google.golang.org/protobuf/encoding/protowire"
	"google.golang.org/protobuf/types/known/durationpb"
)

func commandPayload(t *testing.T, value any) *commonpb.Payloads {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return &commonpb.Payloads{Payloads: []*commonpb.Payload{{
		Data: raw, Metadata: map[string][]byte{"encoding": []byte("json/plain")},
	}}}
}

func TestAssignedActivityPreservesExactInputBinding(t *testing.T) {
	start, ok := exactAssignedStart(newAssignedFixture(), namespace)
	if !ok {
		t.Fatal("invalid start fixture")
	}
	scope := workflowTaskContext{AssignmentID: sampleID, WorkflowType: start.WorkflowType,
		WorkflowContractVersion: start.WorkflowContractVersion, InputSha256: start.InputSha256, OperationStatus: "RUNNING"}
	receipt := nativeTaskReceipt{OperationID: sampleID, WorkflowRunID: sampleID}
	input := boundActivityInput{sampleID, assignedOperation{sampleID, sampleID, sampleID}, start.WorkflowID, sampleID}
	scheduled := &commandpb.ScheduleActivityTaskCommandAttributes{
		ActivityId: "1", ActivityType: &commonpb.ActivityType{Name: "complete_manager_intake"},
		TaskQueue: &taskqueuepb.TaskQueue{Name: assignedManagerQueue}, Input: commandPayload(t, input),
		ScheduleToCloseTimeout: durationpb.New(time.Minute), StartToCloseTimeout: durationpb.New(30 * time.Second),
		RetryPolicy: &commonpb.RetryPolicy{MaximumAttempts: 1},
	}
	if !exactActivity(scheduled, receipt, scope) {
		t.Fatal("exact activity rejected")
	}
	nested := protowire.AppendString(protowire.AppendTag(nil, 20, protowire.BytesType), "fixture")
	for _, duration := range []*durationpb.Duration{scheduled.StartToCloseTimeout, scheduled.ScheduleToCloseTimeout} {
		duration.ProtoReflect().SetUnknown(nested)
		if exactActivity(scheduled, receipt, scope) {
			t.Fatal("activity with unexpected duration metadata accepted")
		}
		duration.ProtoReflect().SetUnknown(nil)
	}
	input.Operation.ProjectID = "22222222-2222-4222-a222-222222222222"
	scheduled.Input = commandPayload(t, input)
	if exactActivity(scheduled, receipt, scope) {
		t.Fatal("activity with a substituted tenant reference accepted")
	}
}

func TestPollDisallowsEmbeddedHeartbeatAndVersioning(t *testing.T) {
	workflow := &workflowservice.PollWorkflowTaskQueueRequest{Identity: managerRPCIdentity, Namespace: namespace,
		TaskQueue:                 &taskqueuepb.TaskQueue{Name: assignedManagerQueue},
		WorkerVersionCapabilities: &commonpb.WorkerVersionCapabilities{BuildId: managerBuild},
	}
	if !exactWorkflowPoll(workflow) {
		t.Fatal("pinned worker build rejected")
	}
	key := protowire.AppendString(protowire.AppendTag(nil, 8, protowire.BytesType), sampleID)
	pool := protowire.AppendVarint(protowire.AppendTag(nil, 1, protowire.VarintType), 5)
	compatibility := protowire.AppendBytes(protowire.AppendTag(key, 11, protowire.BytesType), pool)
	workflow.ProtoReflect().SetUnknown(compatibility)
	if !exactWorkflowPoll(workflow) || len(workflow.ProtoReflect().GetUnknown()) != 0 {
		t.Fatal("known SDK poller metadata was not removed")
	}
	workflow.WorkerVersionCapabilities.UseVersioning = true
	if exactWorkflowPoll(workflow) {
		t.Fatal("workflow poll can change version routing")
	}
	activity := &workflowservice.PollActivityTaskQueueRequest{Identity: managerRPCIdentity, Namespace: namespace,
		TaskQueue:                 &taskqueuepb.TaskQueue{Name: assignedManagerQueue},
		WorkerVersionCapabilities: &commonpb.WorkerVersionCapabilities{BuildId: "unexpected-build"},
	}
	if exactActivityPoll(activity) {
		t.Fatal("activity poll can submit an arbitrary build identity")
	}
	heartbeat := workflow.ProtoReflect().Descriptor().Fields().ByName("worker_heartbeat")
	workflow.WorkerVersionCapabilities.UseVersioning = false
	workflow.ProtoReflect().Mutable(heartbeat)
	if exactWorkflowPoll(workflow) {
		t.Fatal("embedded worker heartbeat reached the frontend")
	}
}

func TestTerminalWorkflowResultMatchesDomainOperation(t *testing.T) {
	result := commandPayload(t, operationState{sampleID, "SUCCEEDED"})
	if !exactTerminalStatus(result, sampleID, "SUCCEEDED") || exactTerminalStatus(result, sampleID, "FAILED") {
		t.Fatal("workflow terminal result does not follow the domain Operation")
	}
	if exactTerminalStatus(commandPayload(t, operationState{sampleID, "RUNNING"}), sampleID, "RUNNING") {
		t.Fatal("workflow completed while its Operation is still running")
	}
}

func TestOnlyTheKnownSdkWorkerInstanceFieldCanBeDiscarded(t *testing.T) {
	request := new(workflowservice.RespondWorkflowTaskCompletedRequest).ProtoReflect()
	key := protowire.AppendString(protowire.AppendTag(nil, 19, protowire.BytesType), sampleID)
	request.SetUnknown(key)
	if !discardWorkerInstanceKey(request, 19) || len(request.GetUnknown()) != 0 {
		t.Fatal("known SDK compatibility field was not removed")
	}
	for _, input := range [][]byte{
		protowire.AppendString(protowire.AppendTag(nil, 20, protowire.BytesType), sampleID),
		protowire.AppendString(protowire.AppendTag(nil, 19, protowire.BytesType), "not-a-uuid"),
		append(append([]byte{}, key...), key...),
	} {
		request.SetUnknown(input)
		if discardWorkerInstanceKey(request, 19) {
			t.Fatal("unexpected compatibility metadata accepted")
		}
	}
}
