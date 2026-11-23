package main

import (
	"context"
	"strings"
	"testing"

	commonpb "go.temporal.io/api/common/v1"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/api/serviceerror"
	workflowpb "go.temporal.io/api/workflow/v1"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"go.temporal.io/server/common/cluster"
	"go.temporal.io/server/common/config"
	"go.temporal.io/server/common/metrics"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/proto"
)

func TestBoundCancellationRequestShape(t *testing.T) {
	const operation = "90ed515f-69af-4c52-b9dd-53a0be99ee8e"
	const run = "759b8a63-f8e7-4d4e-8c15-0ac56c88dbcf"
	const assignment = "9b8d71d6-49c1-4307-aefe-d91ee4b037b9"
	request := &workflowservice.SignalWorkflowExecutionRequest{
		Namespace: namespace, WorkflowExecution: &commonpb.WorkflowExecution{WorkflowId: "operation-" + operation, RunId: run},
		SignalName: "request_cancel", RequestId: assignment,
	}
	got, authorizedShape := exactBoundCancellation(request, namespace)
	if !authorizedShape || got != (boundCancellation{assignment, operation, run, namespace}) {
		t.Fatal("expected exact bound cancellation")
	}
	for name, mutate := range map[string]func(*workflowservice.SignalWorkflowExecutionRequest){
		"no run":        func(r *workflowservice.SignalWorkflowExecutionRequest) { r.WorkflowExecution.RunId = "" },
		"no assignment": func(r *workflowservice.SignalWorkflowExecutionRequest) { r.RequestId = "" },
		"other signal":  func(r *workflowservice.SignalWorkflowExecutionRequest) { r.SignalName = "update" },
		"namespace":     func(r *workflowservice.SignalWorkflowExecutionRequest) { r.Namespace = "elsewhere" },
		"input":         func(r *workflowservice.SignalWorkflowExecutionRequest) { r.Input = &commonpb.Payloads{} },
		"bad workflow":  func(r *workflowservice.SignalWorkflowExecutionRequest) { r.WorkflowExecution.WorkflowId = "other" },
	} {
		t.Run(name, func(t *testing.T) {
			invalid := proto.CloneOf(request)
			mutate(invalid)
			if _, allowed := exactBoundCancellation(invalid, namespace); allowed {
				t.Fatal("invalid cancellation shape permitted")
			}
		})
	}
}

func TestBoundRunStatusOnly(t *testing.T) {
	ctx := context.WithValue(t.Context(), authorization.MappedClaims, &authorization.Claims{Subject: observer})
	run := &commonpb.WorkflowExecution{WorkflowId: "operation-id", RunId: "known-run"}
	request := &workflowservice.DescribeWorkflowExecutionRequest{Execution: run}
	method := &grpc.UnaryServerInfo{FullMethod: workflowRPC + "DescribeWorkflowExecution"}
	info := &workflowpb.WorkflowExecutionInfo{
		Execution: run, Type: &commonpb.WorkflowType{Name: "PlanExecutionWorkflow"},
		TaskQueue: "ai-res-manager", Status: enumspb.WORKFLOW_EXECUTION_STATUS_FAILED,
		Memo: &commonpb.Memo{Fields: map[string]*commonpb.Payload{"sensitive": {Data: []byte("test canary")}}},
	}
	handler := func(context.Context, any) (any, error) {
		return &workflowservice.DescribeWorkflowExecutionResponse{
			WorkflowExecutionInfo: info,
			ExecutionConfig:       &workflowpb.WorkflowExecutionConfig{},
			PendingActivities:     []*workflowpb.PendingActivityInfo{{ActivityId: "fixture"}},
		}, nil
	}
	got, err := boundRunStatusOnly(ctx, request, method, handler)
	want := &workflowservice.DescribeWorkflowExecutionResponse{WorkflowExecutionInfo: &workflowpb.WorkflowExecutionInfo{
		Execution: run, Type: info.Type, TaskQueue: info.TaskQueue, Status: info.Status,
	}}
	if err != nil || !proto.Equal(got.(proto.Message), want) {
		t.Fatalf("status response must contain only allowlisted fields: %v, %v", got, err)
	}
	if _, err := boundRunStatusOnly(t.Context(), request, method, handler); err == nil {
		t.Fatal("response without observer claims was allowed")
	}
	for _, test := range []struct {
		input error
		want  string
	}{
		{serviceerror.NewNotFound("test canary"), "bound execution not found"},
		{serviceerror.NewInternal("test canary"), "bound execution status unavailable"},
	} {
		_, failure := boundRunStatusOnly(ctx, request, method, func(context.Context, any) (any, error) { return nil, test.input })
		if failure == nil || failure.Error() != test.want || strings.Contains(failure.Error(), "test canary") {
			t.Fatalf("unexpected error projection: %v", failure)
		}
	}
	request.Execution = &commonpb.WorkflowExecution{WorkflowId: run.WorkflowId, RunId: "other-run"}
	if _, err := boundRunStatusOnly(ctx, request, method, handler); err == nil {
		t.Fatal("mismatched response execution was allowed")
	}
}

func TestProbeConfigIsolation(t *testing.T) {
	cases := []struct {
		name   string
		change func(*config.Config)
	}{
		{name: "declared loopback storage"},
		{name: "transport without client certificates", change: func(cfg *config.Config) {
			cfg.Global.TLS.Frontend.Server.RequireClientAuth = false
		}},
		{name: "client certificates without active TLS", change: func(cfg *config.Config) {
			cfg.Global.TLS.Frontend.Server.KeyFile = ""
		}},
		{name: "TLS key without server certificate", change: func(cfg *config.Config) {
			cfg.Global.TLS.Frontend.Server.CertFile = ""
		}},
		{name: "TLS without explicit client CA", change: func(cfg *config.Config) {
			cfg.Global.TLS.Frontend.Server.ClientCAFiles = nil
		}},
		{name: "frontend TLS host override", change: func(cfg *config.Config) {
			cfg.Global.TLS.Frontend.PerHostOverrides = map[string]config.ServerTLS{"other.test": {}}
		}},
		{name: "diagnostic pprof", change: func(cfg *config.Config) {
			cfg.Global.PProf.Port = 6060
		}},
		{name: "diagnostic metrics", change: func(cfg *config.Config) {
			cfg.Global.Metrics = &metrics.Config{}
		}},
		{name: "implicit redirection policy", change: func(cfg *config.Config) {
			cfg.DCRedirectionPolicy.Policy = ""
		}},
		{name: "cross-cluster forwarding", change: func(cfg *config.Config) {
			cfg.DCRedirectionPolicy.Policy = "all-apis-forwarding"
		}},
		{name: "global namespace", change: func(cfg *config.Config) {
			cfg.ClusterMetadata.EnableGlobalNamespace = true
		}},
		{name: "second cluster", change: func(cfg *config.Config) {
			cfg.ClusterMetadata.ClusterInformation["remote"] = cluster.ClusterInformation{Enabled: true}
		}},
		{name: "nonloopback frontend", change: func(cfg *config.Config) {
			cfg.Services["frontend"] = config.Service{RPC: config.RPC{BindOnIP: "0.0.0.0"}}
		}},
		{name: "http frontend", change: func(cfg *config.Config) {
			cfg.Services["frontend"] = config.Service{RPC: config.RPC{BindOnIP: "127.0.0.1", HTTPPort: 7243}}
		}},
		{name: "postgresql storage", change: func(cfg *config.Config) {
			cfg.Persistence.DataStores["default"].SQL.PluginName = "postgres12"
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var cfg config.Config
			configureTestLocalCluster(&cfg)
			cfg.Global.Membership.BroadcastAddress = "127.0.0.1"
			cfg.Global.TLS.Frontend.Server.RequireClientAuth = true
			cfg.Global.TLS.Frontend.Server.KeyFile = "fixture.key"
			cfg.Global.TLS.Frontend.Server.CertFile = "fixture.pem"
			cfg.Global.TLS.Frontend.Server.ClientCAFiles = []string{"fixture-ca.pem"}
			cfg.Services = map[string]config.Service{"frontend": {RPC: config.RPC{BindOnIP: "127.0.0.1"}}}
			cfg.Persistence.DataStores = map[string]config.DataStore{"default": {SQL: &config.SQL{PluginName: "sqlite"}}}
			if tc.change != nil {
				tc.change(&cfg)
			}
			if err := validateProbeConfig(&cfg); (err != nil) != (tc.change != nil) {
				t.Fatalf("unexpected isolation validation result: %v", err)
			}
		})
	}
}

func configureTestLocalCluster(cfg *config.Config) {
	cfg.DCRedirectionPolicy.Policy = "noop"
	cfg.ClusterMetadata = &cluster.Config{
		CurrentClusterName: "local", MasterClusterName: "local",
		ClusterInformation: map[string]cluster.ClusterInformation{"local": {Enabled: true}},
	}
}
