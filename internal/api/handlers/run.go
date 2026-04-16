package handlers

import (
	"errors"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/flag-ai/kitt/internal/storage"
)

// RunHandler serves /api/v1/results and /api/v1/runs/{id}.
type RunHandler struct {
	store  *storage.Store
	logger *slog.Logger
}

// NewRunHandler constructs a RunHandler.
func NewRunHandler(store *storage.Store, logger *slog.Logger) *RunHandler {
	return &RunHandler{store: store, logger: logger}
}

// List handles GET /api/v1/results. Supports ?limit=&offset= with
// sensible caps (50 default, 500 max).
func (h *RunHandler) List(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	offset, _ := strconv.Atoi(r.URL.Query().Get("offset"))
	runs, err := h.store.ListRuns(r.Context(), storage.ListParams{Limit: limit, Offset: offset})
	if err != nil {
		h.logger.Error("list runs failed", "error", err)
		writeError(w, http.StatusInternalServerError, "list runs failed")
		return
	}
	writeJSON(w, http.StatusOK, runs)
}

// Get handles GET /api/v1/runs/{id}, returning the run plus its
// benchmarks and metrics.
func (h *RunHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	detail, err := h.store.GetRun(r.Context(), id)
	if err != nil {
		if errors.Is(err, storage.ErrNotFound) {
			writeError(w, http.StatusNotFound, "run not found")
			return
		}
		h.logger.Error("get run failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "get run failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}
