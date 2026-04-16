package devon

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClient_EnsureModel(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer tok" {
			t.Errorf("auth header = %q", got)
		}
		if r.URL.Path != "/api/v1/models/ensure" {
			t.Errorf("path = %q", r.URL.Path)
		}
		var req EnsureRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("decode: %v", err)
		}
		if req.HuggingFaceID != "meta-llama/Llama-3" {
			t.Errorf("hf id = %q", req.HuggingFaceID)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(EnsureResponse{
			ModelID: "meta/llama-3",
			Path:    "/models/llama-3",
			Ready:   true,
		})
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	got, err := c.EnsureModel(context.Background(), &EnsureRequest{
		HuggingFaceID: "meta-llama/Llama-3",
	})
	if err != nil {
		t.Fatalf("ensure: %v", err)
	}
	if got.Path != "/models/llama-3" {
		t.Fatalf("path = %q", got.Path)
	}
	if !got.Ready {
		t.Fatalf("ready = false")
	}
}

func TestClient_EnsureModelError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":"bad request"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	_, err := c.EnsureModel(context.Background(), &EnsureRequest{ModelID: "x"})
	if err == nil {
		t.Fatal("want error")
	}
	var de *Error
	if !errors.As(err, &de) {
		t.Fatalf("want *Error, got %T", err)
	}
	if de.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d", de.StatusCode)
	}
}

func TestClient_EmptyBaseURL(t *testing.T) {
	c := New("", "")
	if _, err := c.EnsureModel(context.Background(), &EnsureRequest{}); !errors.Is(err, ErrEmptyBaseURL) {
		t.Fatalf("want ErrEmptyBaseURL, got %v", err)
	}
	if err := c.Health(context.Background()); !errors.Is(err, ErrEmptyBaseURL) {
		t.Fatalf("want ErrEmptyBaseURL, got %v", err)
	}
}
