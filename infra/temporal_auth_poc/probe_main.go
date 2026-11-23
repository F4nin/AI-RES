//go:build !temporal_runtime

package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"go.temporal.io/server/common/config"
	_ "go.temporal.io/server/common/persistence/sql/sqlplugin/sqlite"
	"go.temporal.io/server/temporal"
)

const (
	namespace                 = "auth-poc"
	identityPrefix            = "spiffe://temporal-auth-poc/"
	managerBuild              = "ai-res-manager-probe-1"
	allowFixtureAuthorization = true
)

func main() {
	if len(os.Args) != 2 {
		log.Fatal("usage: temporal-auth-poc <isolated config directory>")
	}
	cfg, err := config.LoadConfig("poc", os.Args[1], "")
	if err != nil {
		log.Fatal("invalid isolated configuration")
	}
	if err := validateProbeConfig(cfg); err != nil {
		log.Fatal(err)
	}
	if err := serveNativeProbe(cfg, os.Args[1], false); err != nil {
		log.Fatal(err)
	}
}

func serveNativeProbe(cfg *config.Config, root string, requireNative bool) error {
	return serveNativeProbeWith(cfg, root, requireNative, "")
}

func serveNativeProbeWith(cfg *config.Config, root string, requireNative bool, platformOrigin string, options ...temporal.ServerOption) error {
	receipts, err := newReceiptClient(root)
	if err != nil {
		return fmt.Errorf("invalid fixture receipt configuration")
	}
	native, err := loadNativeAuthorization(root, platformOrigin)
	if err != nil || (requireNative && native == nil) {
		return fmt.Errorf("invalid loopback authorization configuration")
	}
	return serveNativeTemporal(cfg, verifiedSAN{}, receipts, native, options...)
}

func loadNativeAuthorization(root string, platformOrigin string) (*nativeAuthorizationClient, error) {
	origin, err := os.ReadFile(filepath.Join(root, "native-auth-origin"))
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	ca, err := os.ReadFile(filepath.Join(root, "native-auth-ca"))
	if err != nil {
		return nil, err
	}
	seed, err := os.ReadFile(filepath.Join(root, "native-auth-seed"))
	if err != nil {
		return nil, err
	}
	native, err := newBoundNativeAuthorizationClient(strings.TrimSpace(string(origin)), ca, seed, platformOrigin)
	if err != nil {
		return nil, err
	}
	observed, err := os.ReadFile(filepath.Join(root, "observe-fixture-operation"))
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	if err == nil {
		id := strings.TrimSpace(string(observed))
		if !uuidForm.MatchString(id) {
			return nil, fmt.Errorf("invalid fixture operation")
		}
		native.observedWorkflowID = "operation-" + id
	}
	return native, nil
}
