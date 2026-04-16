package models

import (
	"time"

	"github.com/google/uuid"
)

// CampaignConfig is the JSON body of a campaign — the declarative
// bundle that says "run these models on these engines against these
// benchmarks on these agents". Each slice is validated by the runner;
// empty slices are rejected so a campaign always has something to do.
type CampaignConfig struct {
	Models     []string `json:"models"`
	Engines    []string `json:"engines"`
	Benchmarks []string `json:"benchmarks"`
	AgentNames []string `json:"agents,omitempty"` // empty = all registered agents
	Suite      string   `json:"suite,omitempty"`  // optional named suite (quick/standard/performance).
}

// Campaign is the API representation of a campaigns row.
type Campaign struct {
	ID          uuid.UUID      `json:"id"`
	Name        string         `json:"name"`
	Description string         `json:"description,omitempty"`
	Config      CampaignConfig `json:"config"`
	CronExpr    string         `json:"cron_expr,omitempty"`
	Enabled     bool           `json:"enabled"`
	CreatedAt   time.Time      `json:"created_at"`
	UpdatedAt   time.Time      `json:"updated_at"`
}

// CampaignRunStatus represents the high-level state of a campaign
// invocation. It is not yet persisted — PR F adds runs/benchmarks
// storage; this type is surfaced over SSE so the UI can render the
// current invocation's progress.
type CampaignRunStatus struct {
	CampaignID uuid.UUID `json:"campaign_id"`
	State      string    `json:"state"` // queued, running, succeeded, failed, cancelled
	Message    string    `json:"message,omitempty"`
	StartedAt  time.Time `json:"started_at,omitempty"`
	UpdatedAt  time.Time `json:"updated_at"`
}
