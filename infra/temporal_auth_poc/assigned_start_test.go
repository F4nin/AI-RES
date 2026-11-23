package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	historypb "go.temporal.io/api/history/v1"
	"go.temporal.io/api/serviceerror"
	taskqueuepb "go.temporal.io/api/taskqueue/v1"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

const sampleID = "11111111-1111-4111-a111-111111111111"

func newAssignedFixture() *workflowservice.StartWorkflowExecutionRequest {
	value := assignedInput{sampleID, 1, assignedOperation{sampleID, sampleID, sampleID}}
	payload, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	return &workflowservice.StartWorkflowExecutionRequest{
		Namespace: namespace, WorkflowId: "operation-" + sampleID,
		WorkflowType: &commonpb.WorkflowType{Name: "ManagerIntakeWorkflow"},
		TaskQueue:    &taskqueuepb.TaskQueue{Name: "ai-res-manager"}, RequestId: sampleID, Identity: dispatcherRPCIdentity,
		WorkflowIdReusePolicy:    enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
		WorkflowIdConflictPolicy: enumspb.WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING,
		Input:                    &commonpb.Payloads{Payloads: []*commonpb.Payload{{Metadata: map[string][]byte{"encoding": []byte("json/plain")}, Data: payload}}},
	}
}

func TestAssignedStartResultRequiresMatchingInitialEvent(t *testing.T) {
	request := newAssignedFixture()
	intent, ok := exactAssignedStart(request, namespace)
	if !ok {
		t.Fatal("invalid Start fixture")
	}
	const runID = "ba125e09-6348-42a2-8d26-b8356d80039b"
	started := &historypb.WorkflowExecutionStartedEventAttributes{
		WorkflowId: request.WorkflowId, WorkflowType: request.WorkflowType, TaskQueue: request.TaskQueue, Input: request.Input,
		OriginalExecutionRunId: runID, FirstExecutionRunId: runID,
	}
	for _, tc := range []struct {
		name   string
		change func(*historypb.WorkflowExecutionStartedEventAttributes)
		want   bool
	}{
		{"exact", func(*historypb.WorkflowExecutionStartedEventAttributes) {}, true},
		{"different workflow", func(event *historypb.WorkflowExecutionStartedEventAttributes) {
			event.WorkflowType.Name = "OperationWorkflow"
		}, false},
		{"different initial Run", func(event *historypb.WorkflowExecutionStartedEventAttributes) { event.FirstExecutionRunId = sampleID }, false},
		{"different workflow ID", func(event *historypb.WorkflowExecutionStartedEventAttributes) { event.WorkflowId = "other" }, false},
		{"different queue", func(event *historypb.WorkflowExecutionStartedEventAttributes) { event.TaskQueue.Name = "other" }, false},
		{"different payload", func(event *historypb.WorkflowExecutionStartedEventAttributes) {
			event.Input.Payloads[0].Data = []byte("other")
		}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			reader := assignedHistoryReadFunc(func(_ context.Context, req *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error) {
				if req.Namespace != namespace || req.Execution.WorkflowId != request.WorkflowId || req.Execution.RunId != runID ||
					req.MaximumPageSize != 1 || !req.SkipArchival {
					t.Fatal("start proof broadened the internal History request")
				}
				attributes := proto.CloneOf(started)
				tc.change(attributes)
				return &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{{
					EventId: 1, EventType: enumspb.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED,
					Attributes: &historypb.HistoryEvent_WorkflowExecutionStartedEventAttributes{WorkflowExecutionStartedEventAttributes: attributes},
				}, {EventId: 2, EventType: enumspb.EVENT_TYPE_WORKFLOW_TASK_SCHEDULED}}}}, nil
			})
			if got := checkAssignedStartResult(t.Context(), reader, intent, runID); got != tc.want {
				t.Fatalf("assigned Start witness result = %v, want %v", got, tc.want)
			}
		})
	}
}

func TestAssignedStartResultExcludesUnverifiedResponseFields(t *testing.T) {
	request := newAssignedFixture()
	const runID = "ba125e09-6348-42a2-8d26-b8356d80039b"
	reader := assignedHistoryReadFunc(func(_ context.Context, _ *workflowservice.GetWorkflowExecutionHistoryRequest) (*workflowservice.GetWorkflowExecutionHistoryResponse, error) {
		return &workflowservice.GetWorkflowExecutionHistoryResponse{History: &historypb.History{Events: []*historypb.HistoryEvent{{
			EventId: 1, EventType: enumspb.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED,
			Attributes: &historypb.HistoryEvent_WorkflowExecutionStartedEventAttributes{WorkflowExecutionStartedEventAttributes: &historypb.WorkflowExecutionStartedEventAttributes{
				WorkflowId: request.WorkflowId, WorkflowType: request.WorkflowType, TaskQueue: request.TaskQueue, Input: request.Input,
				OriginalExecutionRunId: runID, FirstExecutionRunId: runID,
			}},
		}}}}, nil
	})
	metadata := &grpc.UnaryServerInfo{Server: reader, FullMethod: workflowRPC + "StartWorkflowExecution"}
	ctx := context.WithValue(t.Context(), authorization.MappedClaims, &authorization.Claims{Subject: dispatcher})
	response := &workflowservice.StartWorkflowExecutionResponse{RunId: runID, Started: true, Status: enumspb.WORKFLOW_EXECUTION_STATUS_RUNNING}
	result, err := interceptAssignedStartResult(ctx, request, metadata, func(context.Context, any) (any, error) { return response, nil })
	if err != nil || !proto.Equal(result.(*workflowservice.StartWorkflowExecutionResponse), &workflowservice.StartWorkflowExecutionResponse{RunId: runID, Started: true}) {
		t.Fatal("Start returned fields outside the verified receipt")
	}
	_, err = interceptAssignedStartResult(ctx, request, metadata, func(context.Context, any) (any, error) {
		return nil, serviceerror.NewWorkflowExecutionAlreadyStarted("fixture detail", "internal-request", runID)
	})
	var existing *serviceerror.WorkflowExecutionAlreadyStarted
	if !errors.As(err, &existing) || existing.RunId != runID || existing.StartRequestId != "" || strings.Contains(err.Error(), "fixture detail") {
		t.Fatal("closed Start did not return the minimal verified Run")
	}
	_, err = interceptAssignedStartResult(ctx, request, metadata, func(context.Context, any) (any, error) {
		return nil, serviceerror.NewWorkflowExecutionAlreadyStarted("fixture detail", "internal-request", sampleID)
	})
	var unavailable *serviceerror.Unavailable
	if !errors.As(err, &unavailable) {
		t.Fatal("conflicting Start returned an unverified existing Run")
	}
	_, err = interceptAssignedStartResult(ctx, request, metadata, func(context.Context, any) (any, error) {
		return nil, status.Error(codes.InvalidArgument, "private diagnostic detail")
	})
	if status.Code(err) != codes.InvalidArgument || strings.Contains(err.Error(), "private diagnostic detail") {
		t.Fatal("Start exposed the upstream diagnostic or changed its status")
	}
}

func TestAssignedStartRequiresExactMetadata(t *testing.T) {
	request := newAssignedFixture()
	// The Python SDK includes its empty default priority on the wire.
	request.Priority = &commonpb.Priority{}
	intent, ok := exactAssignedStart(request, namespace)
	if !ok || intent.AssignmentID != sampleID || len(intent.InputSha256) != 64 {
		t.Fatal("exact input was not admitted")
	}
	request.Priority.PriorityKey = 1
	if _, ok := exactAssignedStart(request, namespace); ok {
		t.Fatal("the dispatcher cannot override priority")
	}
	request.Priority = nil
	request.WorkflowIdReusePolicy = enumspb.WORKFLOW_ID_REUSE_POLICY_ALLOW_DUPLICATE
	if _, ok := exactAssignedStart(request, namespace); ok {
		t.Fatal("only reject-duplicate executions can be assigned")
	}
}

func TestNativeBridgeSendsVerifiableRequestToItsPrivateCA(t *testing.T) {
	pub, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal("generate fixture key")
	}
	var unavailable atomic.Bool
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if unavailable.Load() {
			writer.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		fields := strings.Split(strings.TrimPrefix(request.Header.Get("Authorization"), "Bearer "), ".")
		if request.URL.Path != "/internal/auth-control/v1/authorize-start" || len(fields) != 3 || fields[0] != "ar2" {
			writer.WriteHeader(http.StatusBadRequest)
			return
		}
		claimsBytes, claimsErr := base64.RawURLEncoding.DecodeString(fields[1])
		signature, signatureErr := base64.RawURLEncoding.DecodeString(fields[2])
		claims := map[string]any{}
		if claimsErr != nil || signatureErr != nil || json.Unmarshal(claimsBytes, &claims) != nil ||
			claims["iss"] != "TEMPORAL_AUTH_CONTROL" || claims["aud"] != "PLATFORM_AUTH_CONTROL" ||
			!ed25519.Verify(pub, []byte("ai-res-platform-request-v2\x00ar2."+fields[1]), signature) {
			writer.WriteHeader(http.StatusUnauthorized)
			return
		}
		var intent startIntent
		if json.NewDecoder(request.Body).Decode(&intent) != nil || intent.AssignmentID != sampleID {
			writer.WriteHeader(http.StatusForbidden)
			return
		}
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()
	ca := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw})
	bridge, err := newNativeAuthorizationClient(server.URL, ca, private.Seed())
	if err != nil {
		t.Fatal("construct private TLS bridge")
	}
	authorizer := exactRPC{native: bridge}
	target := &authorization.CallTarget{APIName: workflowRPC + "StartWorkflowExecution", Namespace: namespace, Request: newAssignedFixture()}
	allowed, err := authorizer.Authorize(context.Background(), &authorization.Claims{Subject: dispatcher}, target)
	if err != nil || allowed.Decision != authorization.DecisionAllow {
		t.Fatal("assigned Start was not authorized")
	}
	rejected, err := authorizer.Authorize(context.Background(), &authorization.Claims{Subject: manager}, target)
	if err != nil || rejected.Decision != authorization.DecisionDeny {
		t.Fatal("Manager cannot originate Start")
	}
	unavailable.Store(true)
	result, err := authorizer.Authorize(t.Context(), &authorization.Claims{Subject: dispatcher}, target)
	var outage *serviceerror.Unavailable
	if result.Decision != authorization.DecisionDeny || !errors.As(err, &outage) {
		t.Fatal("transient auth-control outage was not represented as unavailable")
	}
}

func TestNativeBridgeRestrictsPlatformOrigin(t *testing.T) {
	certificateServer := httptest.NewTLSServer(nil)
	defer certificateServer.Close()
	ca := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certificateServer.Certificate().Raw})
	seed := make([]byte, ed25519.SeedSize)
	const privateOrigin = "https://platform-api:8443"
	for _, tc := range []struct {
		name, origin, allowed string
		want                  bool
	}{
		{"default loopback", certificateServer.URL, "", true},
		{"default rejects private alias", privateOrigin, "", false},
		{"network admits its declared origin", privateOrigin, privateOrigin, true},
		{"network rejects plaintext", "http://platform-api:8443", privateOrigin, false},
		{"network rejects altered port", "https://platform-api:8444", privateOrigin, false},
		{"network rejects loopback override", certificateServer.URL, privateOrigin, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			bridge, err := newBoundNativeAuthorizationClient(tc.origin, ca, seed, tc.allowed)
			if (err == nil) != tc.want {
				t.Fatal("unexpected Platform origin admission")
			}
			if tc.want && bridge.http.CheckRedirect(nil, nil) != http.ErrUseLastResponse {
				t.Fatal("the bridge must not follow a redirect")
			}
		})
	}
}
