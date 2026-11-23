package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/server/common/authorization"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// The fixture service is started on loopback by check.py and owns its disposable PG connection.
type receiptClient struct {
	url    string
	secret string
	http   *http.Client
}

func newReceiptClient(root string) (*receiptClient, error) {
	raw, err := os.ReadFile(filepath.Join(root, "receipt-address"))
	if err != nil {
		return nil, err
	}
	address := strings.TrimSpace(string(raw))
	host, _, err := net.SplitHostPort(address)
	if err != nil || host != "127.0.0.1" {
		return nil, fmt.Errorf("fixture receipt address must be loopback")
	}
	key, err := os.ReadFile(filepath.Join(root, "receipt-key"))
	if err != nil || len(key) != 64 {
		return nil, fmt.Errorf("missing fixture receipt key")
	}
	return &receiptClient{
		url:    "http://" + address,
		secret: string(key),
		http: &http.Client{
			Timeout:       2 * time.Second,
			Transport:     &http.Transport{},
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
	}, nil
}

func (r *receiptClient) check(ctx context.Context, action string, token []byte) (bool, error) {
	if len(token) == 0 || len(token) > 8192 {
		return false, nil
	}
	digest := sha256.Sum256(token)
	payload, err := json.Marshal(map[string]string{
		"digest": hex.EncodeToString(digest[:]), "principal": manager, "namespace": namespace,
		"queue": managerQueue, "kind": "workflow",
	})
	if err != nil {
		return false, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, r.url+"/"+action, bytes.NewReader(payload))
	if err != nil {
		return false, err
	}
	req.Header.Set("Authorization", "Bearer "+r.secret)
	req.Header.Set("Content-Type", "application/json")
	response, err := r.http.Do(req)
	if err != nil {
		return false, fmt.Errorf("receipt service unavailable")
	}
	defer response.Body.Close()
	switch response.StatusCode {
	case http.StatusNoContent:
		return true, nil
	case http.StatusForbidden:
		return false, nil
	default:
		return false, fmt.Errorf("receipt service unavailable")
	}
}

func (r *receiptClient) intercept(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	if info.FullMethod != workflowRPC+"PollWorkflowTaskQueue" {
		return handler(ctx, req)
	}
	claims, _ := ctx.Value(authorization.MappedClaims).(*authorization.Claims)
	request, ok := req.(*workflowservice.PollWorkflowTaskQueueRequest)
	if claims == nil || claims.Subject != manager || !ok || request.GetNamespace() != namespace ||
		request.GetTaskQueue().GetName() != managerQueue {
		return nil, status.Error(codes.PermissionDenied, "fixture poll scope denied")
	}
	result, err := handler(ctx, req)
	if err != nil {
		return nil, err
	}
	task, ok := result.(*workflowservice.PollWorkflowTaskQueueResponse)
	if !ok {
		return nil, status.Error(codes.Unavailable, "unexpected fixture poll response")
	}
	if len(task.GetTaskToken()) > 0 {
		registered, registerErr := r.check(ctx, "register", task.GetTaskToken())
		if registerErr != nil || !registered {
			return nil, status.Error(codes.Unavailable, "fixture receipt registration failed")
		}
	}
	return result, nil
}
