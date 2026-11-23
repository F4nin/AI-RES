//go:build temporal_runtime

package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"net/url"
	"testing"

	commonpb "go.temporal.io/api/common/v1"
	"go.temporal.io/api/serviceerror"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/peer"
)

func TestRuntimeUsesIsolatedVerifiedTransports(t *testing.T) {
	const frontend = "172.28.100.5"
	cfg := runtimeConfig(frontend, "test-password")
	if err := validateProbeBindings(cfg, frontend); err != nil {
		t.Fatal(err)
	}
	internode := cfg.Global.TLS.Internode
	if !internode.Server.RequireClientAuth || internode.Client.DisableHostVerification ||
		internode.Client.ServerName != internodeHost || len(internode.Client.RootCAFiles) != 1 ||
		internode.Client.RootCAFiles[0] == cfg.Global.TLS.Frontend.Server.ClientCAFiles[0] {
		t.Fatal("internode TLS must verify its own authority")
	}
	if cfg.Persistence.NumHistoryShards != 4 || cfg.Persistence.DefaultStore != "default" || cfg.Persistence.VisibilityStore != "visibility" ||
		len(cfg.Persistence.DataStores) != 2 {
		t.Fatal("runtime stores must match the existing Temporal cluster")
	}
	for key, name := range map[string]string{"default": "temporal_db", "visibility": "temporal_visibility_db"} {
		store := cfg.Persistence.DataStores[key].SQL
		if store == nil || store.PluginName != "postgres12" || store.User != "temporal" || store.DatabaseName != name ||
			store.ConnectAddr != "postgres:5432" || store.ConnectAttributes["connect_timeout"] != "5" ||
			store.TLS == nil || !store.TLS.Enabled || !store.TLS.EnableHostVerification ||
			store.TLS.ServerName != "postgres" || store.TLS.CaFile != secretDir+"postgres_tls_ca_cert" {
			t.Fatalf("unexpected PostgreSQL configuration for %s", key)
		}
	}
}

func TestRuntimeDeniesFixtureAuthorization(t *testing.T) {
	ctx := context.Background()
	mapper := verifiedSAN{isActive: func(*x509.Certificate) bool { return true }}
	if err := serveNativeTemporal(nil, mapper, &receiptClient{}, nil); err == nil {
		t.Fatal("without native auth-control the runtime must not start")
	}
	if err := serveNativeTemporal(nil, verifiedSAN{}, nil, &nativeAuthorizationClient{}); err == nil {
		t.Fatal("without active identity checking the runtime must not start")
	}
	for _, test := range []struct {
		subject string
		target  authorization.CallTarget
	}{
		{operator, authorization.CallTarget{APIName: workflowRPC + "GetWorkflowExecutionHistory",
			Namespace: namespace, Request: &workflowservice.GetWorkflowExecutionHistoryRequest{
				Namespace: namespace, Execution: &commonpb.WorkflowExecution{WorkflowId: "operation-fixture"},
				SkipArchival: true, MaximumPageSize: 1,
			}}},
		{"spiffe://temporal-auth-poc/operator", authorization.CallTarget{APIName: workflowRPC + "GetSystemInfo"}},
		{operator, authorization.CallTarget{APIName: workflowRPC + "RegisterNamespace",
			Namespace: "auth-poc", Request: &workflowservice.RegisterNamespaceRequest{Namespace: "auth-poc"}}},
	} {
		authorizer := exactRPC{native: &nativeAuthorizationClient{observedWorkflowID: "operation-fixture"}}
		result, err := authorizer.Authorize(ctx, &authorization.Claims{Subject: test.subject}, &test.target)
		if err != nil || result.Decision != authorization.DecisionDeny {
			t.Fatalf("fixture identity or RPC was accepted: %s", test.target.APIName)
		}
	}
}

func TestRuntimeWithholdsInFlightPollResponseAfterRevocation(t *testing.T) {
	san, err := url.Parse(manager)
	if err != nil {
		t.Fatal(err)
	}
	cert := &x509.Certificate{URIs: []*url.URL{san}}
	tlsInfo := credentials.TLSInfo{State: tls.ConnectionState{VerifiedChains: [][]*x509.Certificate{{cert}}}}
	ctx := peer.NewContext(context.Background(), &peer.Peer{AuthInfo: tlsInfo})
	active := true
	mapper := verifiedSAN{isActive: func(*x509.Certificate) bool { return active }}
	if _, err := mapper.GetClaims(&authorization.AuthInfo{TLSConnection: &tlsInfo}); err != nil {
		t.Fatal(err)
	}
	response := &workflowservice.PollWorkflowTaskQueueResponse{TaskToken: []byte("fixture")}
	got, err := mapper.checkResponseIdentity(ctx, nil, nil, func(context.Context, any) (any, error) {
		active = false // The leaf is revoked while the RPC is waiting for its result.
		return response, nil
	})
	if _, denied := err.(*serviceerror.PermissionDenied); !denied || got != nil {
		t.Fatal("an in-flight poll returned protected data to an inactive leaf")
	}
}
