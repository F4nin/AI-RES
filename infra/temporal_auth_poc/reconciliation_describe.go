package main

import (
	"context"
	"errors"
	"net/http"
	"strings"

	commonpb "go.temporal.io/api/common/v1"
	"go.temporal.io/api/serviceerror"
	workflowpb "go.temporal.io/api/workflow/v1"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"google.golang.org/grpc"
)

func (c *nativeAuthorizationClient) canDescribeReconciliationRun(ctx context.Context, intent reconciliationDescribe) (accepted, available bool) {
	return c.checkExecutionAuthority(ctx, "authorize-bound-status", intent)
}

func (c *nativeAuthorizationClient) checkExecutionAuthority(ctx context.Context, action string, intent any) (accepted, available bool) {
	response := c.post(ctx, action, intent)
	if response == nil {
		return false, false
	}
	defer response.Body.Close()
	switch response.StatusCode {
	case http.StatusNoContent:
		return true, true
	case http.StatusForbidden:
		return false, true
	default:
		return false, false
	}
}

type boundCancellation struct {
	AssignmentID  string `json:"assignmentId"`
	OperationID   string `json:"operationId"`
	WorkflowRunID string `json:"workflowRunId"`
	Namespace     string `json:"namespace"`
}

func exactBoundCancellation(request *workflowservice.SignalWorkflowExecutionRequest, expectedNamespace string) (boundCancellation, bool) {
	if request == nil || expectedNamespace == "" || request.GetNamespace() != expectedNamespace ||
		request.GetSignalName() != "request_cancel" || !uuidForm.MatchString(request.GetRequestId()) ||
		!allowedFields(request.ProtoReflect(), "namespace", "workflow_execution", "signal_name", "request_id") {
		return boundCancellation{}, false
	}
	execution := request.GetWorkflowExecution()
	if execution == nil || !allowedFields(execution.ProtoReflect(), "workflow_id", "run_id") {
		return boundCancellation{}, false
	}
	operation, assigned := strings.CutPrefix(execution.GetWorkflowId(), "operation-")
	if !assigned || !uuidForm.MatchString(operation) || !uuidForm.MatchString(execution.GetRunId()) {
		return boundCancellation{}, false
	}
	return boundCancellation{request.GetRequestId(), operation, execution.GetRunId(), expectedNamespace}, true
}

// Return a new response so current and future Temporal metadata are excluded
// even when the task queue, workflow type and execution match the assignment.
func boundRunStatusOnly(ctx context.Context, req any, method *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	if method.FullMethod != workflowRPC+"DescribeWorkflowExecution" {
		return handler(ctx, req)
	}
	claims, _ := ctx.Value(authorization.MappedClaims).(*authorization.Claims)
	request, ok := req.(*workflowservice.DescribeWorkflowExecutionRequest)
	if !ok || claims == nil || claims.Subject != observer {
		return nil, serviceerror.NewPermissionDenied("reconciliation observer required", "")
	}
	raw, err := handler(ctx, req)
	if err != nil {
		var missing *serviceerror.NotFound
		if errors.As(err, &missing) {
			return nil, serviceerror.NewNotFound("bound execution not found")
		}
		return nil, serviceerror.NewUnavailable("bound execution status unavailable")
	}
	result, ok := raw.(*workflowservice.DescribeWorkflowExecutionResponse)
	if !ok {
		return nil, serviceerror.NewUnavailable("bound execution status unavailable")
	}
	info := result.GetWorkflowExecutionInfo()
	execution := info.GetExecution()
	kind := info.GetType().GetName()
	if execution.GetWorkflowId() != request.GetExecution().GetWorkflowId() ||
		execution.GetRunId() != request.GetExecution().GetRunId() || info.GetTaskQueue() != "ai-res-manager" ||
		(kind != "ManagerIntakeWorkflow" && kind != "PlanExecutionWorkflow") {
		return nil, serviceerror.NewUnavailable("bound execution status unavailable")
	}
	return &workflowservice.DescribeWorkflowExecutionResponse{WorkflowExecutionInfo: &workflowpb.WorkflowExecutionInfo{
		Execution: &commonpb.WorkflowExecution{WorkflowId: execution.GetWorkflowId(), RunId: execution.GetRunId()},
		Type:      &commonpb.WorkflowType{Name: kind},
		TaskQueue: info.GetTaskQueue(),
		Status:    info.GetStatus(),
	}}, nil
}

type reconciliationDescribe struct {
	OperationID   string `json:"operationId"`
	WorkflowRunID string `json:"workflowRunId"`
	Namespace     string `json:"namespace"`
}

func exactReconciliationDescribe(request *workflowservice.DescribeWorkflowExecutionRequest, expectedNamespace string) (reconciliationDescribe, bool) {
	if request == nil || expectedNamespace == "" || request.GetNamespace() != expectedNamespace ||
		!allowedFields(request.ProtoReflect(), "namespace", "execution") {
		return reconciliationDescribe{}, false
	}
	execution := request.GetExecution()
	if execution == nil || !allowedFields(execution.ProtoReflect(), "workflow_id", "run_id") {
		return reconciliationDescribe{}, false
	}
	operation, assigned := strings.CutPrefix(execution.GetWorkflowId(), "operation-")
	if !assigned || !uuidForm.MatchString(operation) || !uuidForm.MatchString(execution.GetRunId()) {
		return reconciliationDescribe{}, false
	}
	return reconciliationDescribe{OperationID: operation, WorkflowRunID: execution.GetRunId(), Namespace: expectedNamespace}, true
}
