package models

import (
	"time"

	"github.com/google/uuid"

	"github.com/flag-ai/kitt/internal/benchmarks"
)

// BenchmarkRegistryEntry is the API representation of a registered
// benchmark.
type BenchmarkRegistryEntry struct {
	ID          uuid.UUID           `json:"id"`
	Name        string              `json:"name"`
	Kind        benchmarks.Kind     `json:"kind"`
	Category    benchmarks.Category `json:"category"`
	Description string              `json:"description,omitempty"`

	// Source is a free-form hint that tells the runner where to find
	// the benchmark definition — a YAML path, a container image
	// reference, etc. The runner interprets this based on Kind.
	Source string `json:"source,omitempty"`

	// Config holds kind-specific settings (prompts + grading rules for
	// YAML benchmarks, cmd/env/volumes for container benchmarks).
	Config  map[string]any `json:"config"`
	Enabled bool           `json:"enabled"`

	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}
