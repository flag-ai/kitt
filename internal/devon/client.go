// Package devon is KITT's typed client for the DEVON model-management
// service.
//
// DEVON (Developer Environment for On-prem AI) owns model discovery,
// download, and local storage. KITT uses the /api/v1/models/ensure
// endpoint to broker downloads — when a campaign references a model
// that isn't yet present on a BONNIE host, KITT asks DEVON to stage
// it, then hands the resolved path to the benchmark runner.
package devon

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client talks to a DEVON server over HTTP.
type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

// Option configures a Client at construction time.
type Option func(*Client)

// WithHTTPClient overrides the default http.Client. Use this in tests
// to inject a custom transport.
func WithHTTPClient(h *http.Client) Option {
	return func(c *Client) { c.http = h }
}

// New constructs a DEVON client. baseURL should be the service's root
// (e.g., "https://devon.local:8443"). token is the bearer credential.
func New(baseURL, token string, opts ...Option) *Client {
	c := &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		http:    &http.Client{Timeout: 30 * time.Second},
	}
	for _, opt := range opts {
		opt(c)
	}
	return c
}

// EnsureRequest asks DEVON to stage a model. Exactly one of ModelID or
// HuggingFaceID must be set. Target is optional — when empty DEVON
// picks a storage location.
type EnsureRequest struct {
	// ModelID is a DEVON-owned model identifier (e.g.,
	// "meta/llama-3-8b-instruct"). Preferred when the model is already
	// cataloged in DEVON.
	ModelID string `json:"model_id,omitempty"`

	// HuggingFaceID triggers a fresh pull from Hugging Face (e.g.,
	// "meta-llama/Meta-Llama-3-8B-Instruct").
	HuggingFaceID string `json:"huggingface_id,omitempty"`

	// Revision pins a Git revision or tag; empty means "latest".
	Revision string `json:"revision,omitempty"`

	// Target is an optional storage preference (NFS share name, local
	// path, etc.). Interpreted by DEVON.
	Target string `json:"target,omitempty"`
}

// EnsureResponse is the body DEVON returns on a successful ensure.
type EnsureResponse struct {
	// ModelID echoes the resolved DEVON model id.
	ModelID string `json:"model_id"`

	// Path is the filesystem path (or share URI) where the model is
	// staged — this is what KITT hands to the engine.
	Path string `json:"path"`

	// Ready is true when the model is fully staged. When false, Status
	// is a progress hint (e.g., "downloading").
	Ready bool `json:"ready"`

	// Status is an optional human-readable status string.
	Status string `json:"status,omitempty"`
}

// Error is returned on non-2xx responses.
type Error struct {
	Op         string
	StatusCode int
	Body       string
}

func (e *Error) Error() string {
	return fmt.Sprintf("devon: %s: status %d: %s", e.Op, e.StatusCode, e.Body)
}

// ErrEmptyBaseURL is returned when a Client is constructed with no URL.
// Surfaced so callers can treat "devon not configured" as a friendly
// no-op rather than a runtime error.
var ErrEmptyBaseURL = errors.New("devon: base URL is not configured")

// EnsureModel POSTs to /api/v1/models/ensure and returns the resolved
// model staging info.
//
// TODO: update once DEVON PR #N lands and the endpoint spec is
// finalized; contract here matches the KITT-Devon-Go-Migration plan.
func (c *Client) EnsureModel(ctx context.Context, req *EnsureRequest) (*EnsureResponse, error) {
	if c.baseURL == "" {
		return nil, ErrEmptyBaseURL
	}
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("devon: marshal request: %w", err)
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+"/api/v1/models/ensure", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("devon: build request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "application/json")
	if c.token != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.token)
	}
	resp, err := c.http.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("devon: ensure: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return nil, &Error{Op: "ensure", StatusCode: resp.StatusCode, Body: string(raw)}
	}

	var out EnsureResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("devon: decode ensure response: %w", err)
	}
	return &out, nil
}

// Health returns nil when the DEVON server's /health endpoint responds 2xx.
func (c *Client) Health(ctx context.Context) error {
	if c.baseURL == "" {
		return ErrEmptyBaseURL
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/health", http.NoBody)
	if err != nil {
		return err
	}
	if c.token != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.token)
	}
	resp, err := c.http.Do(httpReq)
	if err != nil {
		return fmt.Errorf("devon: health: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &Error{Op: "health", StatusCode: resp.StatusCode}
	}
	return nil
}
