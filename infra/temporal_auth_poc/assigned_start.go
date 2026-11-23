package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/api/serviceerror"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"google.golang.org/grpc"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

var uuidForm = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)

const dispatcherRPCIdentity = "ai-res-outbox-dispatcher"

type assignedOperation struct {
	OperationID    string `json:"operation_id"`
	OrganizationID string `json:"organization_id"`
	ProjectID      string `json:"project_id"`
}

// Verify an initial execution witness inside the authenticated Start RPC. The
// caller receives the ordinary Start reply, with no History read privilege.
func checkAssignedStartResult(ctx context.Context, reader assignedHistoryReader, intent startIntent, runID string) bool {
	if reader == nil || !uuidForm.MatchString(runID) {
		return false
	}
	ctx, cancel := context.WithTimeout(ctx, assignedPollHistoryTimeout)
	defer cancel()
	result, err := reader.GetWorkflowExecutionHistory(ctx, &workflowservice.GetWorkflowExecutionHistoryRequest{
		Namespace: intent.Namespace, Execution: &commonpb.WorkflowExecution{WorkflowId: intent.WorkflowID, RunId: runID},
		MaximumPageSize: 1, SkipArchival: true,
	})
	if err != nil || ctx.Err() != nil || result == nil || len(result.GetRawHistory()) != 0 || proto.Size(result) > 8192 {
		return false
	}
	events := result.GetHistory().GetEvents()
	// Temporal can return the full first storage batch even for page size one.
	if len(events) == 0 || events[0].GetEventId() != 1 || events[0].GetEventType() != enumspb.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED {
		return false
	}
	started := events[0].GetWorkflowExecutionStartedEventAttributes()
	if started.GetWorkflowId() != intent.WorkflowID || started.GetOriginalExecutionRunId() != runID || started.GetFirstExecutionRunId() != runID ||
		started.GetWorkflowType().GetName() != intent.WorkflowType || started.GetTaskQueue().GetName() != intent.TaskQueue ||
		len(started.GetInput().GetPayloads()) != 1 {
		return false
	}
	payload := started.GetInput().GetPayloads()[0]
	if len(payload.GetData()) > 512 || len(payload.GetMetadata()) != 1 || string(payload.GetMetadata()["encoding"]) != "json/plain" {
		return false
	}
	digest := sha256.Sum256(payload.GetData())
	return hex.EncodeToString(digest[:]) == intent.InputSha256
}

func interceptAssignedStartResult(ctx context.Context, raw any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	if info.FullMethod != workflowRPC+"StartWorkflowExecution" {
		return handler(ctx, raw)
	}
	claims, _ := ctx.Value(authorization.MappedClaims).(*authorization.Claims)
	request, ok := raw.(*workflowservice.StartWorkflowExecutionRequest)
	if !ok || claims == nil || claims.Subject != dispatcher {
		return nil, serviceerror.NewPermissionDenied("assigned Start required", "")
	}
	intent, exact := exactAssignedStart(request, namespace)
	if !exact {
		return nil, serviceerror.NewPermissionDenied("assigned Start required", "")
	}
	result, err := handler(ctx, request)
	response, _ := result.(*workflowservice.StartWorkflowExecutionResponse)
	var runID string
	if err != nil {
		var existing *serviceerror.WorkflowExecutionAlreadyStarted
		if !errors.As(err, &existing) {
			return nil, status.Error(serviceerror.ToStatus(err).Code(), "assigned Start failed")
		}
		runID = existing.RunId
	} else {
		runID = response.GetRunId()
	}
	reader, _ := info.Server.(assignedHistoryReader)
	if !checkAssignedStartResult(ctx, reader, intent, runID) {
		return nil, serviceerror.NewUnavailable("assigned Start result unavailable")
	}
	if err != nil {
		return nil, serviceerror.NewWorkflowExecutionAlreadyStarted("assigned execution already exists", "", runID)
	}
	return &workflowservice.StartWorkflowExecutionResponse{RunId: runID, Started: response.GetStarted()}, nil
}

// Field order matches Python's sorted, compact JSON representation.
type assignedInput struct {
	AssignmentID    string            `json:"assignment_id"`
	ContractVersion int               `json:"contract_version"`
	Operation       assignedOperation `json:"operation"`
}

type startIntent struct {
	Caller                  string `json:"caller"`
	AssignmentID            string `json:"assignmentId"`
	WorkflowID              string `json:"workflowId"`
	WorkflowType            string `json:"workflowType"`
	Namespace               string `json:"namespace"`
	TaskQueue               string `json:"taskQueue"`
	WorkflowContractVersion int    `json:"workflowContractVersion"`
	InputSha256             string `json:"inputSha256"`
}

func exactAssignedStart(request *workflowservice.StartWorkflowExecutionRequest, expectedNamespace string) (startIntent, bool) {
	if request == nil || request.GetNamespace() != expectedNamespace || expectedNamespace == "" {
		return startIntent{}, false
	}
	queue := request.GetTaskQueue()
	if queue.GetName() != "ai-res-manager" || (queue.GetKind() != enumspb.TASK_QUEUE_KIND_UNSPECIFIED &&
		queue.GetKind() != enumspb.TASK_QUEUE_KIND_NORMAL) || queue.GetNormalName() != "" {
		return startIntent{}, false
	}
	workflowType := request.GetWorkflowType().GetName()
	if workflowType != "ManagerIntakeWorkflow" && workflowType != "PlanExecutionWorkflow" {
		return startIntent{}, false
	}
	if request.GetWorkflowIdReusePolicy() != enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE ||
		request.GetWorkflowIdConflictPolicy() != enumspb.WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING ||
		!uuidForm.MatchString(request.GetRequestId()) || request.GetIdentity() != dispatcherRPCIdentity {
		return startIntent{}, false
	}
	// For this slice, all optional execution, routing and metadata overrides are denied.
	allowed := map[protoreflect.Name]bool{
		"namespace": true, "workflow_id": true, "workflow_type": true, "task_queue": true, "input": true,
		"identity": true, "request_id": true, "workflow_id_reuse_policy": true, "workflow_id_conflict_policy": true,
		"priority": true,
	}
	wire := request.ProtoReflect()
	exact := len(wire.GetUnknown()) == 0
	wire.Range(func(field protoreflect.FieldDescriptor, _ protoreflect.Value) bool {
		exact = exact && allowed[field.Name()]
		return exact
	})
	if !exact || len(queue.ProtoReflect().GetUnknown()) != 0 || len(request.GetWorkflowType().ProtoReflect().GetUnknown()) != 0 ||
		(request.GetPriority() != nil && !allowedFields(request.GetPriority().ProtoReflect())) {
		return startIntent{}, false
	}
	input := request.GetInput()
	if len(input.GetPayloads()) != 1 || len(input.ProtoReflect().GetUnknown()) != 0 {
		return startIntent{}, false
	}
	payload := input.GetPayloads()[0]
	if len(payload.GetData()) > 512 || len(payload.GetMetadata()) != 1 ||
		string(payload.GetMetadata()["encoding"]) != "json/plain" || len(payload.ProtoReflect().GetUnknown()) != 0 {
		return startIntent{}, false
	}
	var parsed assignedInput
	if err := json.Unmarshal(payload.GetData(), &parsed); err != nil {
		return startIntent{}, false
	}
	if parsed.ContractVersion != 1 || !uuidForm.MatchString(parsed.AssignmentID) ||
		!uuidForm.MatchString(parsed.Operation.OperationID) || !uuidForm.MatchString(parsed.Operation.OrganizationID) ||
		!uuidForm.MatchString(parsed.Operation.ProjectID) || request.GetWorkflowId() != "operation-"+parsed.Operation.OperationID {
		return startIntent{}, false
	}
	canonical, err := json.Marshal(parsed)
	if err != nil || !bytes.Equal(payload.GetData(), canonical) {
		return startIntent{}, false
	}
	digest := sha256.Sum256(canonical)
	return startIntent{"OUTBOX_DISPATCHER", parsed.AssignmentID, request.GetWorkflowId(), workflowType,
		expectedNamespace, queue.GetName(), parsed.ContractVersion, hex.EncodeToString(digest[:])}, true
}

// The bridge is permitted only in the isolated native probe. Release composition provides its own key and origin.
type nativeAuthorizationClient struct {
	origin             string
	key                ed25519.PrivateKey
	http               *http.Client
	observedWorkflowID string
}

func newNativeAuthorizationClient(origin string, caPEM, seed []byte) (*nativeAuthorizationClient, error) {
	return newBoundNativeAuthorizationClient(origin, caPEM, seed, "")
}

func newBoundNativeAuthorizationClient(origin string, caPEM, seed []byte, platformOrigin string) (*nativeAuthorizationClient, error) {
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Scheme != "https" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" ||
		parsed.Path != "" || len(seed) != ed25519.SeedSize {
		return nil, fmt.Errorf("native probe needs a trusted HTTPS origin and frontend key")
	}
	if (platformOrigin == "" && !net.ParseIP(parsed.Hostname()).IsLoopback()) || (platformOrigin != "" && origin != platformOrigin) {
		return nil, fmt.Errorf("native probe origin is outside its declared transport")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("native probe has no trusted Platform CA")
	}
	return &nativeAuthorizationClient{
		origin: origin,
		key:    ed25519.NewKeyFromSeed(seed),
		http: &http.Client{
			Timeout: 2 * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12},
			},
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
	}, nil
}

func (c *nativeAuthorizationClient) authorize(ctx context.Context, action string, parameters any) bool {
	response := c.post(ctx, action, parameters)
	if response == nil {
		return false
	}
	defer response.Body.Close()
	return response.StatusCode == http.StatusNoContent
}

func (c *nativeAuthorizationClient) post(ctx context.Context, action string, parameters any) *http.Response {
	raw, err := json.Marshal(parameters)
	if err != nil {
		return nil
	}
	digest := sha256.Sum256(raw)
	nonce, err := freshNonce()
	if err != nil {
		return nil
	}
	path := "/internal/auth-control/v1/" + action
	now := time.Now().Unix()
	claims, err := json.Marshal(map[string]any{
		"iss": "TEMPORAL_AUTH_CONTROL", "aud": "PLATFORM_AUTH_CONTROL",
		"iat": now, "exp": now + 20, "nonce": nonce, "action": action, "method": "POST", "path": path,
		"bodySha256": hex.EncodeToString(digest[:]),
	})
	if err != nil {
		return nil
	}
	signed := "ar2." + base64.RawURLEncoding.EncodeToString(claims)
	signature := ed25519.Sign(c.key, []byte("ai-res-platform-request-v2\x00"+signed))
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.origin+path, bytes.NewReader(raw))
	if err != nil {
		return nil
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+signed+"."+base64.RawURLEncoding.EncodeToString(signature))
	result, err := c.http.Do(request)
	if err != nil {
		return nil
	}
	return result
}

func freshNonce() (string, error) {
	var id [16]byte
	if _, err := rand.Read(id[:]); err != nil {
		return "", err
	}
	id[6], id[8] = id[6]&0x0f|0x40, id[8]&0x3f|0x80
	encoded := hex.EncodeToString(id[:])
	return strings.Join([]string{encoded[:8], encoded[8:12], encoded[12:16], encoded[16:20], encoded[20:]}, "-"), nil
}
