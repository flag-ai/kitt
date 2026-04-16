package models

import (
	"time"

	"github.com/google/uuid"
)

// EngineProfile is a named engine configuration (build + runtime
// settings) used by campaigns and quicktests. Both config blocks are
// free-form JSON since each engine has its own knobs.
type EngineProfile struct {
	ID            uuid.UUID      `json:"id"`
	Name          string         `json:"name"`
	Engine        string         `json:"engine"`
	Description   string         `json:"description,omitempty"`
	BuildConfig   map[string]any `json:"build_config"`
	RuntimeConfig map[string]any `json:"runtime_config"`
	IsDefault     bool           `json:"is_default"`
	CreatedAt     time.Time      `json:"created_at"`
	UpdatedAt     time.Time      `json:"updated_at"`
}
