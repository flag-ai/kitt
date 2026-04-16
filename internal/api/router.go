// Package api provides the HTTP API layer for the KITT server.
package api

import (
	"log/slog"

	"github.com/go-chi/chi/v5"

	"github.com/flag-ai/commons/health"

	"github.com/flag-ai/kitt/internal/api/handlers"
	"github.com/flag-ai/kitt/internal/api/middleware"
	"github.com/flag-ai/kitt/internal/service"
)

// RouterConfig holds all dependencies needed to build the HTTP router.
//
// Later PRs will add service fields (EngineRegistry, BenchmarkRegistry,
// CampaignRunner, Storage, Notifier, Recommender) as each layer lands.
type RouterConfig struct {
	Logger         *slog.Logger
	HealthRegistry *health.Registry

	// AdminToken protects every /api/v1 route. Required.
	AdminToken string

	// CORSOrigins is a comma-separated list of allowed origins.
	CORSOrigins string

	// AgentService handles BONNIE agent CRUD. May be nil in early
	// bring-up; the agent routes are only registered when non-nil.
	AgentService service.AgentServicer
}

// NewRouter builds a chi.Mux with the KITT scaffold routes registered.
// This is the foundation: health/ready endpoints are public, the
// /api/v1 namespace requires a bearer token matching AdminToken.
// Subsequent PRs layer domain routes (engines, benchmarks, campaigns,
// etc.) into the /api/v1 group.
func NewRouter(cfg *RouterConfig) *chi.Mux {
	r := chi.NewRouter()

	// Global middleware — order matters: recover first so panics in any
	// later layer are caught; security headers before logging so they
	// are present even on panicking responses; CORS last so preflights
	// are handled cheaply.
	r.Use(middleware.Recovery(cfg.Logger))
	r.Use(middleware.SecurityHeaders())
	r.Use(middleware.Logging(cfg.Logger))
	r.Use(middleware.CORS(cfg.CORSOrigins))

	// Health (no auth — Kubernetes/Docker probes must reach these).
	healthH := handlers.NewHealthHandler(cfg.HealthRegistry, cfg.Logger)
	r.Get("/health", healthH.Health)
	r.Get("/ready", healthH.Ready)

	// API v1 — all authenticated behind the admin bearer token.
	r.Route("/api/v1", func(r chi.Router) {
		r.Use(middleware.Auth(cfg.AdminToken))

		// BONNIE agent registry.
		if cfg.AgentService != nil {
			agentH := handlers.NewAgentHandler(cfg.AgentService, cfg.Logger)
			r.Get("/bonnie-agents", agentH.List)
			r.Post("/bonnie-agents", agentH.Create)
			r.Get("/bonnie-agents/{id}", agentH.Get)
			r.Delete("/bonnie-agents/{id}", agentH.Delete)
		}
	})

	return r
}
