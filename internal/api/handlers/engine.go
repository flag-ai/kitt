package handlers

import (
	"errors"
	"log/slog"
	"net/http"

	"github.com/flag-ai/kitt/internal/engines"
	"github.com/flag-ai/kitt/internal/models"
	"github.com/flag-ai/kitt/internal/service"
)

// EngineHandler serves /api/v1/engines — read-only enumeration of the
// compile-in engine registry — and the /api/v1/engines/profiles CRUD
// surface that backs the web UI.
type EngineHandler struct {
	registry   *engines.Registry
	profileSvc service.EngineProfileServicer
	logger     *slog.Logger
}

// NewEngineHandler constructs an EngineHandler. Either dependency may
// be nil: if registry is nil, ListEngines returns an empty set; if
// profileSvc is nil, the profile routes respond 503.
func NewEngineHandler(reg *engines.Registry, profileSvc service.EngineProfileServicer, logger *slog.Logger) *EngineHandler {
	return &EngineHandler{registry: reg, profileSvc: profileSvc, logger: logger}
}

// ListEngines handles GET /api/v1/engines.
func (h *EngineHandler) ListEngines(w http.ResponseWriter, _ *http.Request) {
	if h.registry == nil {
		writeJSON(w, http.StatusOK, []*engines.Spec{})
		return
	}
	writeJSON(w, http.StatusOK, h.registry.List())
}

// profilePayload is the JSON shape accepted by POST/PUT profile routes.
type profilePayload struct {
	Name          string         `json:"name"`
	Engine        string         `json:"engine"`
	Description   string         `json:"description"`
	BuildConfig   map[string]any `json:"build_config"`
	RuntimeConfig map[string]any `json:"runtime_config"`
	IsDefault     bool           `json:"is_default"`
}

// ListProfiles handles GET /api/v1/engines/profiles?engine=NAME.
func (h *EngineHandler) ListProfiles(w http.ResponseWriter, r *http.Request) {
	if h.profileSvc == nil {
		writeError(w, http.StatusServiceUnavailable, "profiles unavailable")
		return
	}
	engine := r.URL.Query().Get("engine")
	profiles, err := h.profileSvc.List(r.Context(), engine)
	if err != nil {
		h.logger.Error("list engine profiles failed", "error", err)
		writeError(w, http.StatusInternalServerError, "list profiles failed")
		return
	}
	writeJSON(w, http.StatusOK, profiles)
}

// CreateProfile handles POST /api/v1/engines/profiles.
func (h *EngineHandler) CreateProfile(w http.ResponseWriter, r *http.Request) {
	if h.profileSvc == nil {
		writeError(w, http.StatusServiceUnavailable, "profiles unavailable")
		return
	}
	var req profilePayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	p := models.EngineProfile{
		Name:          req.Name,
		Engine:        req.Engine,
		Description:   req.Description,
		BuildConfig:   req.BuildConfig,
		RuntimeConfig: req.RuntimeConfig,
		IsDefault:     req.IsDefault,
	}
	created, err := h.profileSvc.Create(r.Context(), &p)
	if err != nil {
		h.logger.Warn("create engine profile rejected", "error", err, "engine", p.Engine, "name", p.Name)
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

// UpdateProfile handles PUT /api/v1/engines/profiles/{id}.
func (h *EngineHandler) UpdateProfile(w http.ResponseWriter, r *http.Request) {
	if h.profileSvc == nil {
		writeError(w, http.StatusServiceUnavailable, "profiles unavailable")
		return
	}
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req profilePayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	p := models.EngineProfile{
		ID:            id,
		Name:          req.Name,
		Description:   req.Description,
		BuildConfig:   req.BuildConfig,
		RuntimeConfig: req.RuntimeConfig,
		IsDefault:     req.IsDefault,
	}
	updated, err := h.profileSvc.Update(r.Context(), &p)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "profile not found")
			return
		}
		h.logger.Error("update engine profile failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "update profile failed")
		return
	}
	writeJSON(w, http.StatusOK, updated)
}

// GetProfile handles GET /api/v1/engines/profiles/{id}.
func (h *EngineHandler) GetProfile(w http.ResponseWriter, r *http.Request) {
	if h.profileSvc == nil {
		writeError(w, http.StatusServiceUnavailable, "profiles unavailable")
		return
	}
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	p, err := h.profileSvc.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, service.ErrNotFound) {
			writeError(w, http.StatusNotFound, "profile not found")
			return
		}
		h.logger.Error("get engine profile failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "get profile failed")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// DeleteProfile handles DELETE /api/v1/engines/profiles/{id}.
func (h *EngineHandler) DeleteProfile(w http.ResponseWriter, r *http.Request) {
	if h.profileSvc == nil {
		writeError(w, http.StatusServiceUnavailable, "profiles unavailable")
		return
	}
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := h.profileSvc.Delete(r.Context(), id); err != nil {
		h.logger.Error("delete engine profile failed", "error", err, "id", id)
		writeError(w, http.StatusInternalServerError, "delete profile failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
