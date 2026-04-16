package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/flag-ai/kitt/internal/campaign"
	"github.com/flag-ai/kitt/internal/models"
	"github.com/flag-ai/kitt/internal/service"
)

// CampaignRunner is the subset of campaign.Runner the handler needs.
// Exposed as an interface so handler tests can replace it.
type CampaignRunner interface {
	Run(ctx context.Context, c *models.Campaign) error
}

// CampaignHandler serves /api/v1/campaigns.
type CampaignHandler struct {
	svc    service.CampaignServicer
	runner CampaignRunner
	state  *campaign.State
	logger *slog.Logger
}

// NewCampaignHandler constructs a CampaignHandler.
func NewCampaignHandler(svc service.CampaignServicer, runner CampaignRunner, state *campaign.State, logger *slog.Logger) *CampaignHandler {
	return &CampaignHandler{svc: svc, runner: runner, state: state, logger: logger}
}

type campaignPayload struct {
	Name        string                `json:"name"`
	Description string                `json:"description"`
	Config      models.CampaignConfig `json:"config"`
	CronExpr    string                `json:"cron_expr"`
	Enabled     bool                  `json:"enabled"`
}

type schedulePayload struct {
	CronExpr string `json:"cron_expr"`
	Enabled  bool   `json:"enabled"`
}

// List handles GET /api/v1/campaigns.
func (h *CampaignHandler) List(w http.ResponseWriter, r *http.Request) {
	items, err := h.svc.List(r.Context())
	if err != nil {
		h.logger.Error("list campaigns failed", "error", err)
		writeError(w, http.StatusInternalServerError, "list campaigns failed")
		return
	}
	writeJSON(w, http.StatusOK, items)
}

// Create handles POST /api/v1/campaigns.
func (h *CampaignHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req campaignPayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	c := models.Campaign{
		Name:        req.Name,
		Description: req.Description,
		Config:      req.Config,
		CronExpr:    req.CronExpr,
		Enabled:     req.Enabled,
	}
	created, err := h.svc.Create(r.Context(), &c)
	if err != nil {
		h.logger.Warn("create campaign rejected", "error", err)
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

// Get handles GET /api/v1/campaigns/{id}.
func (h *CampaignHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	c, err := h.svc.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "campaign not found")
			return
		}
		h.logger.Error("get campaign failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "get campaign failed")
		return
	}
	writeJSON(w, http.StatusOK, c)
}

// GetSchedule handles GET /api/v1/campaigns/{id}/schedule.
func (h *CampaignHandler) GetSchedule(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	c, err := h.svc.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "campaign not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "get schedule failed")
		return
	}
	writeJSON(w, http.StatusOK, schedulePayload{CronExpr: c.CronExpr, Enabled: c.Enabled})
}

// UpdateSchedule handles PUT /api/v1/campaigns/{id}/schedule.
func (h *CampaignHandler) UpdateSchedule(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req schedulePayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	updated, err := h.svc.UpdateSchedule(r.Context(), id, req.CronExpr, req.Enabled)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "campaign not found")
			return
		}
		h.logger.Error("update schedule failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "update schedule failed")
		return
	}
	writeJSON(w, http.StatusOK, schedulePayload{CronExpr: updated.CronExpr, Enabled: updated.Enabled})
}

// RunNow handles POST /api/v1/campaigns/{id}/run. The run executes on
// a background goroutine; the response returns 202 immediately. Status
// is observable via GET .../status (SSE).
func (h *CampaignHandler) RunNow(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	c, err := h.svc.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "campaign not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "get campaign failed")
		return
	}
	// Detach from the request context — the request returns 202 as
	// soon as the run is dispatched, and the run may outlive it. The
	// explicit 6h cap prevents a stuck run from leaking a goroutine.
	// The cancel func is owned by the goroutine so it survives the
	// handler return.
	go func(cc models.Campaign) {
		runCtx, cancel := context.WithTimeout(context.WithoutCancel(r.Context()), 6*time.Hour)
		defer cancel()
		if rerr := h.runner.Run(runCtx, &cc); rerr != nil {
			h.logger.Warn("manual campaign run failed", "id", cc.ID, "error", rerr)
		}
	}(c)
	w.WriteHeader(http.StatusAccepted)
}

// Status handles GET /api/v1/campaigns/{id}/status (SSE stream).
func (h *CampaignHandler) Status(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming not supported")
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	// Send the current snapshot immediately so clients that connect
	// mid-run see the latest state without waiting for the next
	// update.
	if cur, ok := h.state.Get(id); ok {
		writeSSEEvent(w, flusher, cur)
	}

	ch, cancel := h.state.Subscribe(id)
	defer cancel()

	// Keep-alive ping every 30s so reverse proxies don't tear down the
	// idle connection.
	ping := time.NewTicker(30 * time.Second)
	defer ping.Stop()

	for {
		select {
		case <-r.Context().Done():
			return
		case st, ok := <-ch:
			if !ok {
				return
			}
			writeSSEEvent(w, flusher, st)
		case <-ping.C:
			_, _ = fmt.Fprint(w, ": ping\n\n")
			flusher.Flush()
		}
	}
}

// Delete handles DELETE /api/v1/campaigns/{id}.
func (h *CampaignHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := h.svc.Delete(r.Context(), id); err != nil {
		h.logger.Error("delete campaign failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "delete campaign failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// writeSSEEvent serializes v as JSON and writes it as an SSE `data:`
// frame, flushing immediately.
func writeSSEEvent(w http.ResponseWriter, flusher http.Flusher, v any) {
	body, err := json.Marshal(v)
	if err != nil {
		return
	}
	_, _ = fmt.Fprintf(w, "data: %s\n\n", body)
	flusher.Flush()
}
