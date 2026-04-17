package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/flag-ai/kitt/internal/models"
	"github.com/flag-ai/kitt/internal/service"
)

// fakeAgentService is a test double implementing service.AgentServicer.
type fakeAgentService struct {
	list   []models.Agent
	get    models.Agent
	create models.Agent
	err    error
}

func (f *fakeAgentService) List(_ context.Context) ([]models.Agent, error) {
	return f.list, f.err
}

func (f *fakeAgentService) Get(_ context.Context, _ uuid.UUID) (models.Agent, error) {
	return f.get, f.err
}

func (f *fakeAgentService) Create(_ context.Context, _, _, _ string) (models.Agent, error) {
	return f.create, f.err
}

func (f *fakeAgentService) Delete(_ context.Context, _ uuid.UUID) error {
	return f.err
}

func newTestHandler(svc service.AgentServicer) *AgentHandler {
	return NewAgentHandler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
}

func TestAgentHandler_List(t *testing.T) {
	agents := []models.Agent{{ID: uuid.New(), Name: "a1", URL: "http://a1"}}
	h := newTestHandler(&fakeAgentService{list: agents})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bonnie-agents", http.NoBody)
	w := httptest.NewRecorder()
	h.List(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	var got []models.Agent
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(got) != 1 || got[0].Name != "a1" {
		t.Fatalf("got %v", got)
	}
}

func TestAgentHandler_Create(t *testing.T) {
	created := models.Agent{ID: uuid.New(), Name: "a1", URL: "http://a1"}
	h := newTestHandler(&fakeAgentService{create: created})

	body := bytes.NewBufferString(`{"name":"a1","url":"http://a1","token":"t"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bonnie-agents", body)
	w := httptest.NewRecorder()
	h.Create(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("status = %d, want 201", w.Code)
	}
}

func TestAgentHandler_CreateValidation(t *testing.T) {
	h := newTestHandler(&fakeAgentService{})
	cases := []string{
		`{}`,
		`{"name":"a"}`,
		`{"name":"a","url":"u"}`,
	}
	for _, body := range cases {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/bonnie-agents", bytes.NewBufferString(body))
		w := httptest.NewRecorder()
		h.Create(w, req)
		if w.Code != http.StatusBadRequest {
			t.Fatalf("body %q: status = %d, want 400", body, w.Code)
		}
	}
}

func TestAgentHandler_GetNotFound(t *testing.T) {
	h := newTestHandler(&fakeAgentService{err: service.ErrNotFound})

	id := uuid.New()
	r := chi.NewRouter()
	r.Get("/bonnie-agents/{id}", h.Get)
	req := httptest.NewRequest(http.MethodGet, "/bonnie-agents/"+id.String(), http.NoBody)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", w.Code)
	}
}

func TestAgentHandler_DeleteSuccess(t *testing.T) {
	h := newTestHandler(&fakeAgentService{})

	id := uuid.New()
	r := chi.NewRouter()
	r.Delete("/bonnie-agents/{id}", h.Delete)
	req := httptest.NewRequest(http.MethodDelete, "/bonnie-agents/"+id.String(), http.NoBody)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want 204", w.Code)
	}
}

func TestAgentHandler_DeleteError(t *testing.T) {
	h := newTestHandler(&fakeAgentService{err: errors.New("boom")})

	id := uuid.New()
	r := chi.NewRouter()
	r.Delete("/bonnie-agents/{id}", h.Delete)
	req := httptest.NewRequest(http.MethodDelete, "/bonnie-agents/"+id.String(), http.NoBody)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", w.Code)
	}
}
