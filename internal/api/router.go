// Package api provides the HTTP API layer for the KITT server.
package api

import (
	"io/fs"
	"log/slog"

	"github.com/go-chi/chi/v5"

	"github.com/flag-ai/commons/health"

	"github.com/flag-ai/kitt/internal/api/handlers"
	"github.com/flag-ai/kitt/internal/api/middleware"
	"github.com/flag-ai/kitt/internal/campaign"
	"github.com/flag-ai/kitt/internal/engines"
	"github.com/flag-ai/kitt/internal/notifications"
	"github.com/flag-ai/kitt/internal/recommendation"
	"github.com/flag-ai/kitt/internal/service"
	"github.com/flag-ai/kitt/internal/storage"
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

	// EngineRegistry is the compile-in engine plugin registry. When
	// nil the engine enumeration route returns an empty list.
	EngineRegistry *engines.Registry

	// EngineProfileService backs the /engines/profiles CRUD routes.
	EngineProfileService service.EngineProfileServicer

	// BenchmarkService backs /benchmarks CRUD. May be nil during
	// early bring-up.
	BenchmarkService service.BenchmarkRegistryServicer

	// CampaignService, CampaignRunner, and CampaignState power the
	// /campaigns routes. All three must be non-nil for the routes to
	// be registered.
	CampaignService service.CampaignServicer
	CampaignRunner  handlers.CampaignRunner
	CampaignState   *campaign.State

	// Storage backs the /results and /runs routes.
	Storage *storage.Store

	// Notifier backs /notifications/test.
	Notifier *notifications.Notifier

	// Recommender backs /recommend. May be nil to omit the route.
	Recommender *recommendation.Recommender

	// SPAFS is the embedded React SPA filesystem. When nil, no SPA
	// fallback handler is registered (useful for API-only deploys).
	SPAFS fs.FS
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

		// Engine registry + engine profiles.
		engineH := handlers.NewEngineHandler(cfg.EngineRegistry, cfg.EngineProfileService, cfg.Logger)
		r.Get("/engines", engineH.ListEngines)
		r.Get("/engines/profiles", engineH.ListProfiles)
		r.Post("/engines/profiles", engineH.CreateProfile)
		r.Get("/engines/profiles/{id}", engineH.GetProfile)
		r.Put("/engines/profiles/{id}", engineH.UpdateProfile)
		r.Delete("/engines/profiles/{id}", engineH.DeleteProfile)

		// Benchmark registry.
		if cfg.BenchmarkService != nil {
			benchH := handlers.NewBenchmarkHandler(cfg.BenchmarkService, cfg.Logger)
			r.Get("/benchmarks", benchH.List)
			r.Post("/benchmarks", benchH.Create)
			r.Get("/benchmarks/{id}", benchH.Get)
			r.Put("/benchmarks/{id}", benchH.Update)
			r.Delete("/benchmarks/{id}", benchH.Delete)
		}

		// Campaigns.
		if cfg.CampaignService != nil && cfg.CampaignRunner != nil && cfg.CampaignState != nil {
			campH := handlers.NewCampaignHandler(cfg.CampaignService, cfg.CampaignRunner, cfg.CampaignState, cfg.Logger)
			r.Get("/campaigns", campH.List)
			r.Post("/campaigns", campH.Create)
			r.Get("/campaigns/{id}", campH.Get)
			r.Delete("/campaigns/{id}", campH.Delete)
			r.Post("/campaigns/{id}/run", campH.RunNow)
			r.Get("/campaigns/{id}/schedule", campH.GetSchedule)
			r.Put("/campaigns/{id}/schedule", campH.UpdateSchedule)
			r.Get("/campaigns/{id}/status", campH.Status)
		}

		// Results + quicktest.
		if cfg.Storage != nil {
			runH := handlers.NewRunHandler(cfg.Storage, cfg.Logger)
			r.Get("/results", runH.List)
			r.Get("/runs/{id}", runH.Get)
		}
		quickH := handlers.NewQuickTestHandler(cfg.Logger)
		r.Get("/quicktest/{id}/logs", quickH.Logs)

		// Notifications.
		if cfg.Notifier != nil {
			notifH := handlers.NewNotificationHandler(cfg.Notifier, cfg.Logger)
			r.Post("/notifications/test", notifH.Test)
		}

		// Recommendations.
		if cfg.Recommender != nil {
			recH := handlers.NewRecommendationHandler(cfg.Recommender, cfg.Logger)
			r.Get("/recommend", recH.Recommend)
			r.Post("/recommend", recH.Recommend)
		}
	})

	// SPA fallback — must be registered last so API routes take
	// precedence over the wildcard match.
	if cfg.SPAFS != nil {
		r.Get("/*", SPAHandler(cfg.SPAFS))
	}

	return r
}
