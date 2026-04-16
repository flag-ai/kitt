package models

import (
	"time"

	"github.com/google/uuid"
)

// RunStatus is a benchmark-run lifecycle state.
type RunStatus string

// Known run statuses.
const (
	RunStatusPending   RunStatus = "pending"
	RunStatusRunning   RunStatus = "running"
	RunStatusSucceeded RunStatus = "succeeded"
	RunStatusFailed    RunStatus = "failed"
	RunStatusCancelled RunStatus = "cancelled"
)

// Run is the API representation of a runs row — one execution of
// (model, engine, engine_profile) against an agent. Campaign_id is
// nullable because quicktests don't belong to a campaign.
type Run struct {
	ID              uuid.UUID  `json:"id"`
	CampaignID      *uuid.UUID `json:"campaign_id,omitempty"`
	AgentID         *uuid.UUID `json:"agent_id,omitempty"`
	HardwareID      *uuid.UUID `json:"hardware_id,omitempty"`
	Model           string     `json:"model"`
	Engine          string     `json:"engine"`
	EngineProfileID *uuid.UUID `json:"engine_profile_id,omitempty"`
	Status          RunStatus  `json:"status"`
	Error           string     `json:"error,omitempty"`
	StartedAt       *time.Time `json:"started_at,omitempty"`
	FinishedAt      *time.Time `json:"finished_at,omitempty"`
	CreatedAt       time.Time  `json:"created_at"`
	UpdatedAt       time.Time  `json:"updated_at"`
}

// BenchmarkResult is the API shape of a single (run, benchmark) row.
type BenchmarkResult struct {
	ID         uuid.UUID      `json:"id"`
	RunID      uuid.UUID      `json:"run_id"`
	Benchmark  string         `json:"benchmark"`
	Status     string         `json:"status"`
	Score      *float64       `json:"score,omitempty"`
	DurationMS *int64         `json:"duration_ms,omitempty"`
	RawJSON    map[string]any `json:"raw_json,omitempty"`
	StartedAt  *time.Time     `json:"started_at,omitempty"`
	FinishedAt *time.Time     `json:"finished_at,omitempty"`
	CreatedAt  time.Time      `json:"created_at"`
}

// Metric is the API shape of a metrics row.
type Metric struct {
	ID          int64      `json:"id"`
	RunID       uuid.UUID  `json:"run_id"`
	BenchmarkID *uuid.UUID `json:"benchmark_id,omitempty"`
	Name        string     `json:"name"`
	Value       float64    `json:"value"`
	Unit        string     `json:"unit,omitempty"`
	RecordedAt  time.Time  `json:"recorded_at"`
}

// RunDetail bundles a run with its benchmarks and metrics for the
// /api/v1/runs/{id} endpoint.
type RunDetail struct {
	Run        Run               `json:"run"`
	Benchmarks []BenchmarkResult `json:"benchmarks"`
	Metrics    []Metric          `json:"metrics"`
}
