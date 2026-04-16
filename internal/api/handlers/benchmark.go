package handlers

import (
	"errors"
	"log/slog"
	"net/http"

	"github.com/flag-ai/kitt/internal/benchmarks"
	"github.com/flag-ai/kitt/internal/models"
	"github.com/flag-ai/kitt/internal/service"
)

// BenchmarkHandler serves /api/v1/benchmarks.
type BenchmarkHandler struct {
	svc    service.BenchmarkRegistryServicer
	logger *slog.Logger
}

// NewBenchmarkHandler constructs a BenchmarkHandler.
func NewBenchmarkHandler(svc service.BenchmarkRegistryServicer, logger *slog.Logger) *BenchmarkHandler {
	return &BenchmarkHandler{svc: svc, logger: logger}
}

type benchmarkPayload struct {
	Name        string         `json:"name"`
	Kind        string         `json:"kind"`
	Category    string         `json:"category"`
	Description string         `json:"description"`
	Source      string         `json:"source"`
	Config      map[string]any `json:"config"`
	Enabled     bool           `json:"enabled"`
}

// List handles GET /api/v1/benchmarks?kind=KIND.
func (h *BenchmarkHandler) List(w http.ResponseWriter, r *http.Request) {
	kind := benchmarks.Kind(r.URL.Query().Get("kind"))
	entries, err := h.svc.List(r.Context(), kind)
	if err != nil {
		h.logger.Error("list benchmarks failed", "error", err)
		writeError(w, http.StatusInternalServerError, "list benchmarks failed")
		return
	}
	writeJSON(w, http.StatusOK, entries)
}

// Create handles POST /api/v1/benchmarks.
func (h *BenchmarkHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req benchmarkPayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	entry := models.BenchmarkRegistryEntry{
		Name:        req.Name,
		Kind:        benchmarks.Kind(req.Kind),
		Category:    benchmarks.Category(req.Category),
		Description: req.Description,
		Source:      req.Source,
		Config:      req.Config,
		Enabled:     req.Enabled,
	}
	created, err := h.svc.Create(r.Context(), &entry)
	if err != nil {
		h.logger.Warn("create benchmark rejected", "error", err, "name", entry.Name)
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

// Get handles GET /api/v1/benchmarks/{id}.
func (h *BenchmarkHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	entry, err := h.svc.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "benchmark not found")
			return
		}
		h.logger.Error("get benchmark failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "get benchmark failed")
		return
	}
	writeJSON(w, http.StatusOK, entry)
}

// Update handles PUT /api/v1/benchmarks/{id}.
func (h *BenchmarkHandler) Update(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req benchmarkPayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	// Name remains as stored — we use the existing row's name by
	// forcing the service to ignore the payload's name during update.
	entry := models.BenchmarkRegistryEntry{
		ID:          id,
		Name:        req.Name, // non-zero so validation passes; UPDATE query does not set name.
		Kind:        benchmarks.Kind(req.Kind),
		Category:    benchmarks.Category(req.Category),
		Description: req.Description,
		Source:      req.Source,
		Config:      req.Config,
		Enabled:     req.Enabled,
	}
	updated, err := h.svc.Update(r.Context(), &entry)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "benchmark not found")
			return
		}
		h.logger.Warn("update benchmark failed", "error", err, "id", id)
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, updated)
}

// Delete handles DELETE /api/v1/benchmarks/{id}.
func (h *BenchmarkHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := h.svc.Delete(r.Context(), id); err != nil {
		h.logger.Error("delete benchmark failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "delete benchmark failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
