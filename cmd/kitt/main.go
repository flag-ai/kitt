// Package main is the entrypoint for the KITT server.
//
// KITT (Kirizan's Inference Testing Tools) is an end-to-end testing
// and benchmarking suite for LLM inference engines. It measures quality
// consistency and performance across vLLM, llama.cpp, Ollama,
// ExLlamaV2, and MLX.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/flag-ai/commons/database"
	"github.com/flag-ai/commons/health"
	"github.com/flag-ai/commons/secrets"
	"github.com/flag-ai/commons/version"

	"github.com/flag-ai/kitt/internal/api"
	"github.com/flag-ai/kitt/internal/bonnie"
	"github.com/flag-ai/kitt/internal/campaign"
	"github.com/flag-ai/kitt/internal/config"
	"github.com/flag-ai/kitt/internal/db"
	"github.com/flag-ai/kitt/internal/db/sqlc"
	"github.com/flag-ai/kitt/internal/engines"
	"github.com/flag-ai/kitt/internal/service"

	// Side-effect imports — each engine package registers itself with
	// engines.Default on init().
	_ "github.com/flag-ai/kitt/internal/engines/exllamav2"
	_ "github.com/flag-ai/kitt/internal/engines/llamacpp"
	_ "github.com/flag-ai/kitt/internal/engines/mlx"
	_ "github.com/flag-ai/kitt/internal/engines/ollama"
	_ "github.com/flag-ai/kitt/internal/engines/vllm"
)

func main() {
	if err := run(); err != nil {
		slog.Error("fatal", "error", err)
		os.Exit(1)
	}
}

func run() error {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: kitt <command>\n\nCommands:\n  serve     Start the KITT server\n  migrate   Run database migrations\n")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "serve":
		return serve()
	case "migrate":
		return migrate()
	default:
		return fmt.Errorf("unknown command: %s", os.Args[1])
	}
}

// newProviderAndConfig resolves a secrets provider (OpenBao first, env
// fallback) and loads the KITT configuration.
func newProviderAndConfig(ctx context.Context) (*config.Config, *slog.Logger, error) {
	provider, err := secrets.NewProvider(secrets.ProviderOpenBao, nil)
	if err != nil {
		slog.Warn("OpenBao unavailable, falling back to environment variables for secrets", "error", err)
		provider, _ = secrets.NewProvider(secrets.ProviderEnv, nil)
	}

	cfg, err := config.Load(ctx, provider)
	if err != nil {
		return nil, nil, err
	}

	logger := cfg.Logger()
	return cfg, logger, nil
}

func migrate() error {
	ctx := context.Background()
	cfg, logger, err := newProviderAndConfig(ctx)
	if err != nil {
		return err
	}

	if len(os.Args) < 3 || os.Args[2] != "up" {
		return fmt.Errorf("usage: kitt migrate up")
	}

	logger.Info("running migrations")
	return database.RunMigrations(migrationsSourcePath(), cfg.DatabaseURL, logger)
}

func serve() error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	cfg, logger, err := newProviderAndConfig(ctx)
	if err != nil {
		return err
	}

	logger.Info("starting kitt", "version", version.Info(), "addr", cfg.ListenAddr)

	// Database pool
	pool, err := db.NewPool(ctx, cfg.DatabaseURL, logger)
	if err != nil {
		return err
	}
	defer pool.Close()

	// Run migrations on boot so a freshly-deployed image is usable
	// without a separate migrate step.
	if err := db.RunMigrations(migrationsSourcePath(), cfg.DatabaseURL, logger); err != nil {
		return err
	}

	// sqlc queries.
	queries := sqlc.New(pool)

	// BONNIE agent registry — shared flag-commons implementation
	// backed by the kitt_bonnie_agents table.
	store := service.NewBonnieRegistryStore(queries)
	registry := bonnie.NewRegistry(store, logger)
	registry.Start(ctx)

	// Domain services.
	agentSvc := service.NewAgentService(queries, registry, logger)
	engineProfileSvc := service.NewEngineProfileService(queries, engines.Default, logger)
	benchmarkSvc := service.NewBenchmarkRegistryService(queries, logger)

	// Campaign control plane: state is shared between the runner
	// (producer) and the /campaigns/{id}/status SSE endpoint (consumer).
	campaignState := campaign.NewState()
	campaignRunner := campaign.NewRunner(registry, campaignState, logger)
	// Two-phase wiring: service needs the scheduler (for reload on
	// mutations), scheduler needs the service (to fetch campaigns).
	// We construct the service with a nil reloader, build the
	// scheduler with the service as fetcher, then hand the scheduler
	// back to the service via a setter. This avoids an initialization
	// cycle without giving either side a god-reference.
	campaignSvc := service.NewCampaignService(queries, nil, logger)
	campaignScheduler := campaign.NewScheduler(campaignSvc, campaignRunner, logger)
	campaignSvc.SetScheduler(campaignScheduler)
	if err := campaignScheduler.Start(ctx); err != nil {
		return fmt.Errorf("campaign scheduler start: %w", err)
	}
	defer campaignScheduler.Stop()

	// Health registry — database check is mandatory. Devon reachability
	// is registered in PR F when the recommender consumes it.
	healthRegistry := health.NewRegistry()
	healthRegistry.Register(health.NewDatabaseChecker(pool))

	// Build router.
	router := api.NewRouter(&api.RouterConfig{
		Logger:               logger,
		HealthRegistry:       healthRegistry,
		AdminToken:           cfg.AdminToken,
		CORSOrigins:          cfg.CORSOrigins,
		AgentService:         agentSvc,
		EngineRegistry:       engines.Default,
		EngineProfileService: engineProfileSvc,
		BenchmarkService:     benchmarkSvc,
		CampaignService:      campaignSvc,
		CampaignRunner:       campaignRunner,
		CampaignState:        campaignState,
	})

	srv := &http.Server{
		Handler:           router,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      60 * time.Second, // Allows SSE streaming for up to 60s per flush cycle.
		IdleTimeout:       120 * time.Second,
	}

	errCh := make(chan error, 1)
	go func() {
		ln, listenErr := net.Listen("tcp", cfg.ListenAddr)
		if listenErr != nil {
			errCh <- listenErr
			return
		}
		logger.Info("server listening", "addr", ln.Addr().String())
		if serveErr := srv.Serve(ln); serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
			errCh <- serveErr
		}
		close(errCh)
	}()

	select {
	case <-ctx.Done():
		logger.Info("shutdown signal received")
	case err := <-errCh:
		if err != nil {
			logger.Error("server error", "error", err)
		}
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		return err
	}

	logger.Info("kitt stopped")
	return nil
}

// migrationsSourcePath resolves the migrations directory — preferring
// ./migrations relative to cwd (dev) and falling back to the binary's
// directory (container).
func migrationsSourcePath() string {
	if _, err := os.Stat("migrations"); err == nil {
		abs, _ := filepath.Abs("migrations")
		return "file://" + abs
	}
	exe, _ := os.Executable()
	return "file://" + filepath.Join(filepath.Dir(exe), "migrations")
}
