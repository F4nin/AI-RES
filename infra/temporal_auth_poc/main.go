// Native Temporal frontend authorization shared by the probe and runtime.
package main

import (
	"context"
	"crypto/x509"
	"fmt"

	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/api/serviceerror"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"go.temporal.io/server/common/config"
	"go.temporal.io/server/common/dynamicconfig"
	temporallog "go.temporal.io/server/common/log"
	"go.temporal.io/server/temporal"
	"google.golang.org/grpc"
)

const (
	workflowRPC  = "/temporal.api.workflowservice.v1.WorkflowService/"
	manager      = identityPrefix + "manager"
	worker       = identityPrefix + "worker"
	operator     = identityPrefix + "operator"
	dispatcher   = identityPrefix + "dispatcher"
	observer     = identityPrefix + "reconciliation-observer"
	cancellation = identityPrefix + "backend-cancellation"
	managerQueue = "auth-poc-manager"
	workerQueue  = "auth-poc-worker"
)

type verifiedSAN struct {
	isActive func(*x509.Certificate) bool
}

func (verifiedSAN) AuthInfoRequired() bool { return false }

func (mapper verifiedSAN) GetClaims(info *authorization.AuthInfo) (*authorization.Claims, error) {
	if info == nil {
		return nil, fmt.Errorf("certificate required")
	}
	cert := authorization.PeerCert(info.TLSConnection)
	if cert == nil || len(cert.URIs) != 1 {
		return nil, fmt.Errorf("verified identity required")
	}
	principal := cert.URIs[0].String()
	switch principal {
	case manager, worker, operator, dispatcher, observer, cancellation:
		if mapper.isActive != nil && !mapper.isActive(cert) {
			return nil, fmt.Errorf("inactive identity")
		}
		return &authorization.Claims{Subject: principal}, nil
	default:
		return nil, fmt.Errorf("unknown identity")
	}
}

func (mapper verifiedSAN) checkResponseIdentity(
	ctx context.Context, req any, _ *grpc.UnaryServerInfo, handler grpc.UnaryHandler,
) (any, error) {
	result, err := handler(ctx, req)
	// Long polls and backend lookups can outlive a published leaf's admission.
	if _, authErr := mapper.GetClaims(&authorization.AuthInfo{TLSConnection: authorization.TLSInfoFromContext(ctx)}); authErr != nil {
		return nil, serviceerror.NewPermissionDenied("inactive identity", "")
	}
	return result, err
}

type exactRPC struct {
	receipts *receiptClient
	native   *nativeAuthorizationClient
}

func (a exactRPC) Authorize(ctx context.Context, claims *authorization.Claims, target *authorization.CallTarget) (authorization.Result, error) {
	deny := authorization.Result{Decision: authorization.DecisionDeny}
	allow := authorization.Result{Decision: authorization.DecisionAllow}
	if claims == nil || target == nil || (!allowFixtureAuthorization && a.native == nil) {
		return deny, nil
	}
	switch target.APIName {
	case workflowRPC + "GetSystemInfo":
		if claims.Subject == manager || claims.Subject == worker || claims.Subject == operator || claims.Subject == dispatcher ||
			(a.native != nil && (claims.Subject == observer || claims.Subject == cancellation)) {
			return allow, nil
		}
	case workflowRPC + "RegisterNamespace":
		if request, ok := target.Request.(*workflowservice.RegisterNamespaceRequest); ok && claims.Subject == operator &&
			request.GetNamespace() == namespace && !request.GetIsGlobalNamespace() &&
			(allowFixtureAuthorization || allowedFields(request.ProtoReflect(), "namespace", "workflow_execution_retention_period")) {
			return allow, nil
		}
	case workflowRPC + "DescribeNamespace":
		if request, ok := target.Request.(*workflowservice.DescribeNamespaceRequest); ok &&
			(claims.Subject == operator || (a.native != nil && claims.Subject == manager)) &&
			request.GetNamespace() == namespace && allowedFields(request.ProtoReflect(), "namespace") {
			return allow, nil
		}
	case workflowRPC + "GetWorkflowExecutionHistory":
		// Synthetic loopback evidence for one fixture. Product observers use a separate scoped authority.
		if request, ok := target.Request.(*workflowservice.GetWorkflowExecutionHistoryRequest); ok &&
			allowFixtureAuthorization && claims.Subject == operator && a.native != nil && a.native.observedWorkflowID != "" && request.GetNamespace() == namespace &&
			request.GetExecution().GetWorkflowId() == a.native.observedWorkflowID && exactFixtureHistory(request) {
			return allow, nil
		}
	case workflowRPC + "DescribeWorkflowExecution":
		if request, ok := target.Request.(*workflowservice.DescribeWorkflowExecutionRequest); ok && a.native != nil &&
			claims.Subject == observer && target.Namespace == namespace {
			intent, exact := exactReconciliationDescribe(request, namespace)
			if exact {
				accepted, available := a.native.canDescribeReconciliationRun(ctx, intent)
				if !available {
					return deny, serviceerror.NewUnavailable("reconciliation authorization unavailable")
				}
				if accepted {
					return allow, nil
				}
			}
		}
	case workflowRPC + "StartWorkflowExecution":
		if a.native != nil {
			request, ok := target.Request.(*workflowservice.StartWorkflowExecutionRequest)
			if !ok || claims.Subject != dispatcher || target.Namespace != namespace {
				return deny, nil
			}
			intent, exact := exactAssignedStart(request, namespace)
			if exact {
				accepted, available := a.native.checkExecutionAuthority(ctx, "authorize-start", intent)
				if !available {
					return deny, serviceerror.NewUnavailable("start authorization unavailable")
				}
				if accepted {
					return allow, nil
				}
			}
			return deny, nil
		}
		if request, ok := target.Request.(*workflowservice.StartWorkflowExecutionRequest); ok && claims.Subject == dispatcher &&
			target.Namespace == namespace && request.GetWorkflowId() == "auth-poc-fixture" &&
			request.GetWorkflowType().GetName() == "AuthPocFixture" && request.GetTaskQueue().GetName() == managerQueue &&
			request.GetInput() == nil && !request.GetRequestEagerExecution() {
			return allow, nil
		}
	case workflowRPC + "SignalWorkflowExecution":
		if request, ok := target.Request.(*workflowservice.SignalWorkflowExecutionRequest); ok && a.native != nil &&
			claims.Subject == cancellation && target.Namespace == namespace {
			intent, exact := exactBoundCancellation(request, namespace)
			if exact {
				accepted, available := a.native.checkExecutionAuthority(ctx, "authorize-bound-cancel", intent)
				if !available {
					return deny, serviceerror.NewUnavailable("cancellation authorization unavailable")
				}
				if accepted {
					return allow, nil
				}
			}
		}
	case workflowRPC + "RespondWorkflowTaskCompleted":
		if a.native != nil {
			if request, ok := target.Request.(*workflowservice.RespondWorkflowTaskCompletedRequest); ok &&
				claims.Subject == manager && target.Namespace == namespace && a.native.allowWorkflowCompletion(ctx, request) {
				return allow, nil
			}
			return deny, nil
		}
		request, ok := target.Request.(*workflowservice.RespondWorkflowTaskCompletedRequest)
		if !ok || claims.Subject != manager || target.Namespace != namespace || request.GetReturnNewWorkflowTask() ||
			request.GetForceCreateNewWorkflowTask() || request.GetStickyAttributes() != nil || len(request.GetCommands()) != 1 ||
			request.GetCommands()[0].GetCommandType() != enumspb.COMMAND_TYPE_COMPLETE_WORKFLOW_EXECUTION ||
			request.GetCommands()[0].GetCompleteWorkflowExecutionCommandAttributes() == nil {
			return deny, nil
		}
		verified, err := a.receipts.check(ctx, "check", request.GetTaskToken())
		if err == nil && verified {
			return allow, nil
		}
	case workflowRPC + "RespondActivityTaskCompleted":
		if a.native != nil {
			if request, ok := target.Request.(*workflowservice.RespondActivityTaskCompletedRequest); ok &&
				claims.Subject == manager && target.Namespace == namespace && a.native.allowActivityCompletion(ctx, request) {
				return allow, nil
			}
		}
	case workflowRPC + "RespondActivityTaskFailed":
		if request, ok := target.Request.(*workflowservice.RespondActivityTaskFailedRequest); ok && a.native != nil &&
			claims.Subject == manager && a.native.allowActivityFailure(ctx, request) {
			return allow, nil
		}
	case workflowRPC + "PollWorkflowTaskQueue":
		if a.native != nil {
			if request, ok := target.Request.(*workflowservice.PollWorkflowTaskQueueRequest); ok &&
				permittedManagerPoll(claims.Subject, target.Namespace, request.GetTaskQueue()) {
				return allow, nil
			}
			return deny, nil
		}
		if request, ok := target.Request.(*workflowservice.PollWorkflowTaskQueueRequest); ok && claims.Subject == manager &&
			target.Namespace == namespace && request.GetTaskQueue().GetName() == managerQueue {
			return allow, nil
		}
	case workflowRPC + "PollActivityTaskQueue":
		if a.native != nil {
			if request, ok := target.Request.(*workflowservice.PollActivityTaskQueueRequest); ok &&
				permittedManagerPoll(claims.Subject, target.Namespace, request.GetTaskQueue()) {
				return allow, nil
			}
			return deny, nil
		}
		if request, ok := target.Request.(*workflowservice.PollActivityTaskQueueRequest); ok && claims.Subject == worker &&
			target.Namespace == namespace && request.GetTaskQueue().GetName() == workerQueue {
			return allow, nil
		}
	}
	return deny, nil
}

func exactFixtureHistory(request *workflowservice.GetWorkflowExecutionHistoryRequest) bool {
	execution := request.GetExecution()
	if !request.GetSkipArchival() || !allowedFields(execution.ProtoReflect(), "workflow_id", "run_id") {
		return false
	}
	if execution.GetRunId() == "" {
		return request.GetMaximumPageSize() == 1 &&
			allowedFields(request.ProtoReflect(), "namespace", "execution", "maximum_page_size", "skip_archival")
	}
	return uuidForm.MatchString(execution.GetRunId()) &&
		request.GetHistoryEventFilterType() == enumspb.HISTORY_EVENT_FILTER_TYPE_ALL_EVENT &&
		allowedFields(request.ProtoReflect(), "namespace", "execution", "history_event_filter_type", "skip_archival")
}

func validateProbeTransport(cfg *config.Config) error {
	return validateProbeBindings(cfg, "127.0.0.1")
}

func validateProbeBindings(cfg *config.Config, frontendIP string) error {
	_, ok := cfg.Services["frontend"]
	frontendTLS := cfg.Global.TLS.Frontend
	serverTLS := frontendTLS.Server
	if !ok || cfg.Global.Membership.BroadcastAddress != "127.0.0.1" {
		return fmt.Errorf("the native PoC requires a frontend and IPv4 loopback membership")
	}
	if !frontendTLS.IsServerEnabled() || !serverTLS.RequireClientAuth || (serverTLS.CertFile == "" && serverTLS.CertData == "") ||
		(len(serverTLS.ClientCAFiles) == 0 && len(serverTLS.ClientCAData) == 0) {
		return fmt.Errorf("the native PoC requires a frontend certificate, key and explicit client CA")
	}
	if cfg.Global.PProf.Port != 0 || cfg.Global.Metrics != nil {
		return fmt.Errorf("diagnostic listeners are disabled in the native PoC")
	}
	if len(cfg.Global.TLS.Frontend.PerHostOverrides) != 0 {
		return fmt.Errorf("frontend TLS host overrides are disabled in the native PoC")
	}
	// Temporal's redirection interceptor runs before the status-only response filter.
	metadata := cfg.ClusterMetadata
	if cfg.DCRedirectionPolicy.Policy != "noop" || metadata == nil || metadata.EnableGlobalNamespace ||
		len(metadata.ClusterInformation) != 1 || metadata.CurrentClusterName == "" ||
		metadata.MasterClusterName != metadata.CurrentClusterName || !metadata.ClusterInformation[metadata.CurrentClusterName].Enabled {
		return fmt.Errorf("the native PoC requires one local cluster without redirection")
	}
	for name, service := range cfg.Services {
		expectedIP := "127.0.0.1"
		if name == "frontend" {
			expectedIP = frontendIP
		}
		if service.RPC.BindOnIP != expectedIP || service.RPC.BindOnLocalHost || service.RPC.HTTPPort != 0 {
			return fmt.Errorf("all PoC listeners must bind to their declared addresses with HTTP disabled")
		}
	}
	return nil
}

func validateProbeConfig(cfg *config.Config) error {
	if err := validateProbeTransport(cfg); err != nil {
		return err
	}
	for _, store := range cfg.Persistence.DataStores {
		if store.SQL == nil || store.SQL.PluginName != "sqlite" || store.Cassandra != nil || store.Elasticsearch != nil || store.CustomDataStoreConfig != nil {
			return fmt.Errorf("the native PoC requires SQLite Temporal storage")
		}
	}
	return nil
}

func serveNativeTemporal(cfg *config.Config, mapper verifiedSAN, receipts *receiptClient, native *nativeAuthorizationClient, options ...temporal.ServerOption) error {
	if native == nil && (!allowFixtureAuthorization || receipts == nil) {
		return fmt.Errorf("native authorization is required")
	}
	if !allowFixtureAuthorization && mapper.isActive == nil {
		return fmt.Errorf("active Temporal identities are required")
	}
	interceptors := []grpc.UnaryServerInterceptor{}
	if !allowFixtureAuthorization {
		interceptors = append(interceptors, mapper.checkResponseIdentity)
	}
	interceptors = append(interceptors, boundRunStatusOnly)
	if native != nil {
		interceptors = append(interceptors, interceptAssignedStartResult, native.interceptPoll)
	} else {
		interceptors = append(interceptors, receipts.intercept)
	}
	dynamic := dynamicconfig.StaticClient{dynamicconfig.ExposeAuthorizerErrors.Key(): true}
	if !allowFixtureAuthorization {
		dynamic[dynamicconfig.EnableActivityEagerExecution.Key()] = false
		dynamic[dynamicconfig.EnableEagerWorkflowStart.Key()] = false
	}
	options = append([]temporal.ServerOption{
		temporal.WithConfig(cfg),
		temporal.ForServices([]string{"frontend", "history", "matching"}),
		temporal.WithLogger(temporallog.NewZapLogger(temporallog.BuildZapLogger(cfg.Log))),
		temporal.WithAuthorizer(exactRPC{receipts: receipts, native: native}),
		// Expose the fixed availability errors returned by the authorizer.
		temporal.WithDynamicConfigClient(dynamic),
		temporal.WithChainedFrontendGrpcInterceptors(interceptors...),
		temporal.WithClaimMapper(func(*config.Config) authorization.ClaimMapper { return mapper }),
		temporal.InterruptOn(temporal.InterruptCh()),
	}, options...)
	server, err := temporal.NewServer(options...)
	if err != nil {
		return fmt.Errorf("could not compose native server")
	}
	if err := server.Start(); err != nil {
		return fmt.Errorf("native server stopped")
	}
	return nil
}
