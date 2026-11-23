//go:build temporal_runtime

package main

import (
	"context"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.temporal.io/server/common/auth"
	"go.temporal.io/server/common/cluster"
	"go.temporal.io/server/common/config"
	"go.temporal.io/server/common/membership/static"
	"go.temporal.io/server/common/metrics"
	_ "go.temporal.io/server/common/persistence/sql/sqlplugin/postgresql"
	"go.temporal.io/server/common/primitives"
	"go.temporal.io/server/temporal"
)

const (
	namespace                 = "ai-res"
	identityPrefix            = "spiffe://ai-res/temporal/"
	managerBuild              = "ai-res-manager-g02-v1"
	allowFixtureAuthorization = false

	secretDir      = "/run/secrets/"
	activeCertDir  = "/etc/temporal/active-client-certs"
	frontendHost   = "temporal-workflow"
	internodeHost  = "temporal-internode"
	metricsHost    = "temporal-metrics"
	platformURL    = "https://platform-api:8443"
	connectTimeout = 5 * time.Second
)

func main() {
	if len(os.Args) != 1 {
		log.Fatal("temporal-native does not accept command-line configuration")
	}
	if err := runTemporal(); err != nil {
		log.Fatal(err)
	}
}

func runTemporal() error {
	registry, err := os.Stat(activeCertDir)
	if err != nil || !registry.IsDir() {
		return fmt.Errorf("Temporal active identity directory is required")
	}
	frontendIP, err := resolvePrivateIP(frontendHost)
	if err != nil {
		return fmt.Errorf("Temporal requires one private IPv4 workflow address")
	}
	password, err := os.ReadFile(secretDir + "temporal_db_password")
	if err != nil || len(strings.TrimRight(string(password), "\n")) == 0 {
		return fmt.Errorf("Temporal database credential is required")
	}
	ca, caErr := os.ReadFile(secretDir + "temporal_platform_ca")
	signer, readErr := os.ReadFile(secretDir + "temporal_auth_control_signing_key")
	if caErr != nil || readErr != nil {
		return fmt.Errorf("Temporal auth-control credentials are required")
	}
	seed, err := base64.StdEncoding.Strict().DecodeString(strings.TrimSuffix(string(signer), "\n"))
	if err != nil {
		return fmt.Errorf("invalid Temporal auth-control credentials")
	}
	native, err := newBoundNativeAuthorizationClient(platformURL, ca, seed, platformURL)
	if err != nil {
		return fmt.Errorf("invalid Temporal auth-control credentials")
	}
	cfg := runtimeConfig(frontendIP, strings.TrimRight(string(password), "\n"))
	switch os.Getenv("G02_TEMPORAL_METRICS") {
	case "":
	case "1":
		metricsIP, err := resolvePrivateIP(metricsHost)
		if err != nil || metricsIP == frontendIP {
			return fmt.Errorf("Temporal metrics require a separate private observability address")
		}
		cfg.Global.Metrics = &metrics.Config{Prometheus: &metrics.PrometheusConfig{
			ListenAddress: net.JoinHostPort(metricsIP, "9090"),
		}}
	default:
		return fmt.Errorf("invalid Temporal metrics configuration")
	}
	hosts := make(map[primitives.ServiceName]static.Hosts, len(cfg.Services))
	for name, service := range cfg.Services {
		hosts[primitives.ServiceName(name)] = static.SingleLocalHost(
			net.JoinHostPort(service.RPC.BindOnIP, strconv.Itoa(service.RPC.GRPCPort)),
		)
	}
	mapper := verifiedSAN{isActive: activeClientCertificate(activeCertDir)}
	return serveNativeTemporal(cfg, mapper, nil, native, temporal.WithStaticHosts(hosts))
}

func resolvePrivateIP(name string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), connectTimeout)
	defer cancel()
	addresses, err := net.DefaultResolver.LookupIP(ctx, "ip4", name)
	if err != nil || len(addresses) != 1 || !addresses[0].IsPrivate() {
		return "", fmt.Errorf("one private IPv4 address is required")
	}
	return addresses[0].String(), nil
}

// Read one published leaf fingerprint per RPC. A directory mount lets the
// identity operator publish replacements atomically and revoke a live connection.
func activeClientCertificate(root string) func(*x509.Certificate) bool {
	return func(cert *x509.Certificate) bool {
		now := time.Now()
		if now.Before(cert.NotBefore) || !now.Before(cert.NotAfter) {
			return false
		}
		role := strings.TrimPrefix(cert.URIs[0].String(), identityPrefix)
		file, err := os.Open(filepath.Join(root, role+".sha256"))
		if err != nil {
			return false
		}
		defer file.Close()
		fingerprint, err := io.ReadAll(io.LimitReader(file, 67))
		digest := sha256.Sum256(cert.Raw)
		return err == nil && strings.TrimSuffix(string(fingerprint), "\n") == hex.EncodeToString(digest[:])
	}
}

func runtimeConfig(frontendIP, password string) *config.Config {
	serverTLS := func(name string) config.ServerTLS {
		return config.ServerTLS{
			CertFile:          secretDir + "temporal_" + name + "_cert",
			KeyFile:           secretDir + "temporal_" + name + "_key",
			RequireClientAuth: true,
			ClientCAFiles:     []string{secretDir + "temporal_" + name + "_ca"},
		}
	}
	database := func(name string, connections int) config.DataStore {
		return config.DataStore{SQL: &config.SQL{
			PluginName: "postgres12", ConnectAddr: "postgres:5432", ConnectProtocol: "tcp",
			DatabaseName: name, User: "temporal", Password: password,
			MaxConns: connections, MaxIdleConns: connections, MaxConnLifetime: time.Hour,
			ConnectAttributes: map[string]string{"connect_timeout": strconv.Itoa(int(connectTimeout / time.Second))},
			TLS: &auth.TLS{Enabled: true, EnableHostVerification: true,
				CaFile: secretDir + "postgres_tls_ca_cert", ServerName: "postgres"},
		}}
	}
	cfg := &config.Config{
		Services: map[string]config.Service{
			"frontend": {RPC: config.RPC{BindOnIP: frontendIP, GRPCPort: 7233}},
			"history":  {RPC: config.RPC{BindOnIP: "127.0.0.1", GRPCPort: 7234}},
			"matching": {RPC: config.RPC{BindOnIP: "127.0.0.1", GRPCPort: 7235}},
			// The static resolver requires an entry even though this process does not start a system worker.
			"worker": {RPC: config.RPC{BindOnIP: "127.0.0.1", GRPCPort: 7239}},
		},
		Persistence: config.Persistence{
			DefaultStore: "default", VisibilityStore: "visibility", NumHistoryShards: 4,
			DataStores: map[string]config.DataStore{
				"default": database("temporal_db", 20), "visibility": database("temporal_visibility_db", 10),
			},
		},
		ClusterMetadata: &cluster.Config{
			CurrentClusterName: "active", MasterClusterName: "active", FailoverVersionIncrement: 10,
			ClusterInformation: map[string]cluster.ClusterInformation{
				"active": {Enabled: true, InitialFailoverVersion: 1, RPCAddress: frontendHost + ":7233"},
			},
		},
	}
	cfg.Log.Stdout, cfg.Log.Level = true, "info"
	cfg.DCRedirectionPolicy.Policy = "noop"
	cfg.Global.Membership.BroadcastAddress = "127.0.0.1"
	cfg.Global.TLS.Frontend.Server = serverTLS("frontend")
	cfg.Global.TLS.Internode.Server = serverTLS("internode")
	cfg.Global.TLS.Internode.Client = config.ClientTLS{
		ServerName: internodeHost, RootCAFiles: []string{secretDir + "temporal_internode_ca"},
	}
	return cfg
}
