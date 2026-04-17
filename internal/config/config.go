// Package config provides KITT-specific configuration loading.
package config

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/flag-ai/commons/config"
	"github.com/flag-ai/commons/logging"
	"github.com/flag-ai/commons/secrets"
)

// Config holds all KITT configuration, embedding the commons Base
// config so standard FLAG env vars (DATABASE_URL, LOG_LEVEL, LOG_FORMAT,
// LISTEN_ADDR) are available on every binary without restating them.
type Config struct {
	config.Base

	// AdminToken is the bearer token required by privileged API routes
	// (/api/v1/*). When empty, the API layer must refuse to start to
	// avoid an accidental open server.
	AdminToken string

	// DevonURL is the base URL for the Devon model-management service
	// (e.g., "https://devon.local:8443"). Used by the /api/v1/models
	// endpoints to broker model downloads.
	DevonURL string

	// DevonToken is the bearer token presented to Devon.
	DevonToken string

	// SlackWebhook is the optional Slack Incoming Webhook URL for
	// campaign and benchmark notifications.
	SlackWebhook string

	// DiscordWebhook is the optional Discord Webhook URL for campaign
	// and benchmark notifications.
	DiscordWebhook string

	// CORSOrigins is a comma-separated list of allowed CORS origins.
	// When empty, CORS headers are omitted (same-origin only).
	CORSOrigins string
}

// Load builds a KITT Config by reading environment variables via the
// secrets provider.
func Load(ctx context.Context, provider secrets.Provider) (*Config, error) {
	if provider == nil {
		return nil, fmt.Errorf("config: secrets provider is required")
	}

	base, err := config.LoadBase(ctx, "kitt", provider)
	if err != nil {
		return nil, err
	}

	adminToken, err := provider.Get(ctx, "KITT_ADMIN_TOKEN")
	if err != nil {
		return nil, fmt.Errorf("config: KITT_ADMIN_TOKEN is required: %w", err)
	}

	return &Config{
		Base:           *base,
		AdminToken:     adminToken,
		DevonURL:       provider.GetOrDefault(ctx, "KITT_DEVON_URL", ""),
		DevonToken:     provider.GetOrDefault(ctx, "KITT_DEVON_TOKEN", ""),
		SlackWebhook:   provider.GetOrDefault(ctx, "KITT_SLACK_WEBHOOK", ""),
		DiscordWebhook: provider.GetOrDefault(ctx, "KITT_DISCORD_WEBHOOK", ""),
		CORSOrigins:    provider.GetOrDefault(ctx, "KITT_CORS_ORIGINS", ""),
	}, nil
}

// Logger creates a configured logger from the config.
func (c *Config) Logger() *slog.Logger {
	return logging.New(c.Component,
		logging.WithLevel(logging.ParseLevel(c.LogLevel)),
		logging.WithFormat(logging.Format(c.LogFormat)),
	)
}
