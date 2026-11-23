//go:build temporal_postgres_probe

package main

import (
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"go.temporal.io/server/common/auth"
	"go.temporal.io/server/common/config"
	"go.temporal.io/server/common/dynamicconfig"
	"go.temporal.io/server/common/membership/static"
	_ "go.temporal.io/server/common/persistence/sql/sqlplugin/postgresql"
	"go.temporal.io/server/common/primitives"
	"go.temporal.io/server/temporal"
)

// This entry point is available only in a test binary and accepts only the disposable fixture profile.
func TestServeNativePostgresProbe(t *testing.T) {
	root := os.Getenv("G02_NATIVE_POSTGRES_FIXTURE_DIR")
	if root == "" {
		t.Skip("started explicitly by the integration fixture")
	}
	candidate := os.Getenv("G02_NATIVE_COMPOSE_CANDIDATE") == "1"
	networked := candidate && os.Getenv("G02_NATIVE_COMPOSE_NETWORK") == "1"
	if candidate {
		deadline := time.Now().Add(90 * time.Second)
		for {
			if _, err := os.Stat(filepath.Join(root, "ready")); err == nil {
				break
			} else if !errors.Is(err, os.ErrNotExist) || time.Now().After(deadline) {
				t.Fatal("the isolated Compose fixture did not supply a configuration")
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	cfg, err := config.LoadConfig("poc", root, "")
	if err != nil {
		t.Fatal("invalid PostgreSQL probe fixture configuration")
	}
	frontendIP := "127.0.0.1"
	if networked {
		frontendIP = privateFixtureIP(t, "temporal-workflow")
	}
	if err := validateBoundPostgresProbe(cfg, candidate, frontendIP); err != nil {
		t.Fatal(err)
	}
	if networked {
		privateFixtureIP(t, "postgres")
		privateFixtureIP(t, "platform-api")
		hosts := make(map[primitives.ServiceName]static.Hosts, len(cfg.Services))
		for name, service := range cfg.Services {
			address := net.JoinHostPort(service.RPC.BindOnIP, strconv.Itoa(service.RPC.GRPCPort))
			hosts[primitives.ServiceName(name)] = static.SingleLocalHost(address)
		}
		options := []temporal.ServerOption{temporal.WithStaticHosts(hosts)}
		if os.Getenv("G02_PROBE_PAGINATE_HISTORY") == "1" {
			options = append(options, temporal.WithDynamicConfigClient(dynamicconfig.StaticClient{
				dynamicconfig.ExposeAuthorizerErrors.Key(): true,
				dynamicconfig.HistoryMaxPageSize.Key():     1,
			}))
		}
		if err := serveNativeProbeWith(cfg, root, true, "https://platform-api:8443", options...); err != nil {
			t.Fatal(err)
		}
		return
	}
	if candidate {
		addresses, err := net.LookupIP("postgres")
		if err != nil || len(addresses) == 0 {
			t.Fatal("could not resolve the isolated PostgreSQL fixture")
		}
		for _, addr := range addresses {
			if !addr.Equal(net.IPv4(127, 0, 0, 1)) {
				t.Fatal("the Compose candidate database must resolve to IPv4 loopback")
			}
		}
	}
	if err := serveNativeProbe(cfg, root, true); err != nil {
		t.Fatal(err)
	}
}

func privateFixtureIP(t *testing.T, name string) string {
	t.Helper()
	addresses, err := net.LookupIP(name)
	if err != nil || len(addresses) != 1 || addresses[0].To4() == nil || !addresses[0].IsPrivate() {
		t.Fatalf("the networked candidate requires one private IPv4 address for %s", name)
	}
	return addresses[0].String()
}

func validatePostgresProbe(cfg *config.Config, candidate bool) error {
	return validateBoundPostgresProbe(cfg, candidate, "127.0.0.1")
}

func validateBoundPostgresProbe(cfg *config.Config, candidate bool, frontendIP string) error {
	if err := validateProbeBindings(cfg, frontendIP); err != nil {
		return err
	}
	for _, service := range cfg.Services {
		if service.RPC.GRPCPort < 1 || service.RPC.GRPCPort > 32767 ||
			service.RPC.MembershipPort < 1 || service.RPC.MembershipPort > 32767 {
			return fmt.Errorf("the PostgreSQL probe requires RPC ports within the signed SMALLINT range")
		}
	}
	tls := cfg.Global.TLS.Internode
	if !tls.Server.RequireClientAuth || tls.Server.CertFile == "" || tls.Server.KeyFile == "" || len(tls.Server.ClientCAFiles) != 1 ||
		len(tls.PerHostOverrides) != 0 || tls.Client.DisableHostVerification || tls.Client.ServerName == "" || len(tls.Client.RootCAFiles) != 1 {
		return fmt.Errorf("the PostgreSQL probe requires internode mTLS and hostname verification")
	}
	persistence := cfg.Persistence
	if persistence.DefaultStore != "default" || persistence.VisibilityStore != "visibility" ||
		persistence.SecondaryVisibilityStore != "" || len(persistence.DataStores) != 2 {
		return fmt.Errorf("the PostgreSQL probe requires separate fixture history and visibility stores")
	}
	names := map[string]string{"default": "temporal_probe_history", "visibility": "temporal_probe_visibility"}
	user, expectedHost := "temporal_probe", "127.0.0.1"
	if candidate {
		names = map[string]string{"default": "temporal_db", "visibility": "temporal_visibility_db"}
		user, expectedHost = "temporal", "postgres"
	}
	for key, name := range names {
		store := persistence.DataStores[key]
		sql := store.SQL
		if sql == nil || sql.PluginName != "postgres12" || sql.DatabaseName != name || sql.User != user ||
			len(sql.ConnectAttributes) != 0 || store.Cassandra != nil || store.Elasticsearch != nil || store.CustomDataStoreConfig != nil {
			return fmt.Errorf("the PostgreSQL probe requires its disposable databases and role")
		}
		if candidate {
			if sql.TLS == nil || *sql.TLS != (auth.TLS{
				Enabled: true, EnableHostVerification: true, CaFile: "/run/secrets/postgres_tls_ca_cert", ServerName: "postgres",
			}) {
				return fmt.Errorf("the Compose candidate requires verified PostgreSQL TLS for both databases")
			}
		} else if sql.TLS != nil {
			return fmt.Errorf("the loopback fixture only accepts its declared database transport")
		}
		host, rawPort, splitErr := net.SplitHostPort(sql.ConnectAddr)
		port, portErr := strconv.Atoi(rawPort)
		if splitErr != nil || portErr != nil || port < 1 || port > 65535 || strconv.Itoa(port) != rawPort ||
			host != expectedHost || sql.ConnectProtocol != "tcp" || (candidate && port != 5432) {
			return fmt.Errorf("the PostgreSQL probe requires its declared fixture address")
		}
	}
	return nil
}

func TestPostgresProbeRejectsUnsafeConfiguration(t *testing.T) {
	for _, test := range []struct {
		name           string
		address        string
		attributes     map[string]string
		membershipPort int
	}{
		{name: "host attribute override", address: "127.0.0.1:20000", attributes: map[string]string{"host": "another.test"}},
		{name: "database attribute override", address: "127.0.0.1:20000", attributes: map[string]string{"dbname": "another_db"}},
		{name: "address with query suffix", address: "127.0.0.1:20000?host=another.test"},
		{name: "membership port too large for PostgreSQL", address: "127.0.0.1:20000", membershipPort: 40000},
	} {
		t.Run(test.name, func(t *testing.T) {
			cfg := probeTransportConfig()
			for key, name := range map[string]string{"default": "temporal_probe_history", "visibility": "temporal_probe_visibility"} {
				cfg.Persistence.DataStores[key] = config.DataStore{SQL: &config.SQL{
					PluginName: "postgres12", DatabaseName: name, User: "temporal_probe", ConnectAddr: "127.0.0.1:20000", ConnectProtocol: "tcp",
				}}
			}
			if err := validatePostgresProbe(&cfg, false); err != nil {
				t.Fatal(err)
			}
			cfg.Persistence.DataStores["default"].SQL.ConnectAddr = test.address
			cfg.Persistence.DataStores["default"].SQL.ConnectAttributes = test.attributes
			if test.membershipPort != 0 {
				frontend := cfg.Services["frontend"]
				frontend.RPC.MembershipPort = test.membershipPort
				cfg.Services["frontend"] = frontend
			}
			if err := validatePostgresProbe(&cfg, false); err == nil {
				t.Fatal("unsafe fixture configuration was accepted")
			}
		})
	}
}

func TestComposeProbeRejectsUnverifiedDatastores(t *testing.T) {
	for _, test := range []struct {
		name   string
		modify func(*config.SQL)
	}{
		{"missing TLS", func(store *config.SQL) { store.TLS = nil }},
		{"TLS disabled", func(store *config.SQL) { store.TLS.Enabled = false }},
		{"hostname verification disabled", func(store *config.SQL) { store.TLS.EnableHostVerification = false }},
		{"unapproved CA", func(store *config.SQL) { store.TLS.CaFile = "other.pem" }},
		{"unexpected destination", func(store *config.SQL) { store.ConnectAddr = "127.0.0.1:5432" }},
		{"privileged database role", func(store *config.SQL) { store.User = "postgres" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			cfg := probeTransportConfig()
			for key, name := range map[string]string{"default": "temporal_db", "visibility": "temporal_visibility_db"} {
				cfg.Persistence.DataStores[key] = config.DataStore{SQL: &config.SQL{
					PluginName: "postgres12", DatabaseName: name, User: "temporal", ConnectAddr: "postgres:5432", ConnectProtocol: "tcp",
					TLS: &auth.TLS{Enabled: true, EnableHostVerification: true, CaFile: "/run/secrets/postgres_tls_ca_cert", ServerName: "postgres"},
				}}
			}
			if err := validatePostgresProbe(&cfg, true); err != nil {
				t.Fatal(err)
			}
			test.modify(cfg.Persistence.DataStores["visibility"].SQL)
			if err := validatePostgresProbe(&cfg, true); err == nil {
				t.Fatal("unsafe Compose datastore was accepted")
			}
		})
	}
}

func probeTransportConfig() config.Config {
	var cfg config.Config
	configureTestLocalCluster(&cfg)
	cfg.Global.Membership.BroadcastAddress = "127.0.0.1"
	cfg.Global.TLS.Frontend.Server = config.ServerTLS{RequireClientAuth: true, CertFile: "fixture.pem",
		KeyFile: "fixture.key", ClientCAFiles: []string{"fixture-ca.pem"}}
	cfg.Global.TLS.Internode.Server = cfg.Global.TLS.Frontend.Server
	cfg.Global.TLS.Internode.Client = config.ClientTLS{ServerName: "internode.test", RootCAFiles: []string{"fixture-ca.pem"}}
	cfg.Services = map[string]config.Service{"frontend": {
		RPC: config.RPC{BindOnIP: "127.0.0.1", GRPCPort: 20001, MembershipPort: 20002},
	}}
	cfg.Persistence.DefaultStore, cfg.Persistence.VisibilityStore = "default", "visibility"
	cfg.Persistence.DataStores = map[string]config.DataStore{}
	return cfg
}
