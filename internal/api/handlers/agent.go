package handlers

import (
	"errors"
	"log/slog"
	"net/http"
	"net/url"

	"github.com/flag-ai/kitt/internal/service"
)

// AgentHandler serves /api/v1/bonnie-agents.
type AgentHandler struct {
	svc    service.AgentServicer
	logger *slog.Logger
}

// NewAgentHandler constructs an AgentHandler.
func NewAgentHandler(svc service.AgentServicer, logger *slog.Logger) *AgentHandler {
	return &AgentHandler{svc: svc, logger: logger}
}

// agentCreateRequest is the JSON body accepted by POST
// /api/v1/bonnie-agents. Token is required so the registry can
// authenticate against the BONNIE host; empty-token registration is
// rejected to avoid accidentally trusting unauthenticated hosts.
type agentCreateRequest struct {
	Name  string `json:"name"`
	URL   string `json:"url"`
	Token string `json:"token"`
}

// List handles GET /api/v1/bonnie-agents.
func (h *AgentHandler) List(w http.ResponseWriter, r *http.Request) {
	agents, err := h.svc.List(r.Context())
	if err != nil {
		h.logger.Error("list bonnie agents failed", "error", err)
		writeError(w, http.StatusInternalServerError, "list agents failed")
		return
	}
	writeJSON(w, http.StatusOK, agents)
}

// Create handles POST /api/v1/bonnie-agents.
func (h *AgentHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req agentCreateRequest
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	if req.Name == "" || req.URL == "" || req.Token == "" {
		writeError(w, http.StatusBadRequest, "name, url, and token are required")
		return
	}
	parsed, err := url.ParseRequestURI(req.URL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		writeError(w, http.StatusBadRequest, "url must use http or https scheme")
		return
	}
	agent, err := h.svc.Create(r.Context(), req.Name, req.URL, req.Token)
	if err != nil {
		h.logger.Error("create bonnie agent failed", "error", err)
		writeError(w, http.StatusInternalServerError, "create agent failed")
		return
	}
	writeJSON(w, http.StatusCreated, agent)
}

// Delete handles DELETE /api/v1/bonnie-agents/{id}.
func (h *AgentHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := h.svc.Delete(r.Context(), id); err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "agent not found")
			return
		}
		h.logger.Error("delete bonnie agent failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "delete agent failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// Get handles GET /api/v1/bonnie-agents/{id}.
func (h *AgentHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	agent, err := h.svc.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "agent not found")
			return
		}
		h.logger.Error("get bonnie agent failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "get agent failed")
		return
	}
	writeJSON(w, http.StatusOK, agent)
}
