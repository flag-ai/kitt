// Package bonnie wraps the flag-commons BONNIE client for KITT-specific
// use cases. Everything in this package ultimately calls into
// github.com/flag-ai/commons/bonnie — we keep a KITT-owned seam so
// later refactors (custom retry policies, KITT-specific telemetry,
// etc.) can be applied in one place.
package bonnie

import (
	"log/slog"
	"time"

	commons "github.com/flag-ai/commons/bonnie"
)

// Client is re-exported so callers can import a single "bonnie"
// package rather than distinguishing KITT and commons variants.
type Client = commons.Client

// Agent is the minimal agent record the registry knows about.
type Agent = commons.Agent

// RegistryStore abstracts agent persistence. KITT's service layer
// implements this against its sqlc queries.
type RegistryStore = commons.RegistryStore

// Registry is the shared BONNIE agent registry.
type Registry = commons.Registry

// Option is a commons.Client option re-exported for convenience.
type Option = commons.Option

// DefaultPollInterval is the poll cadence used by KITT when callers
// don't specify one. 30 seconds matches KARR and keeps agent status
// fresh without flooding the network.
const DefaultPollInterval = 30 * time.Second

// NewRegistry constructs a KITT-configured BONNIE registry. logger
// must be non-nil; pass slog.Default if no domain logger is available.
func NewRegistry(store RegistryStore, logger *slog.Logger, opts ...Option) *Registry {
	return commons.NewRegistry(store, DefaultPollInterval, logger, opts...)
}

// NewClient constructs a BONNIE client pointing at baseURL.
func NewClient(baseURL, token string, opts ...Option) Client {
	return commons.New(baseURL, token, opts...)
}
