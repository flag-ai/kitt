// Package mlx registers the MLX engine (Apple Silicon).
package mlx

import "github.com/flag-ai/kitt/internal/engines"

var spec = &engines.Spec{
	Name:        "mlx",
	DisplayName: "MLX",
	DockerImage: "",
	APIStyle:    "openai",
	DefaultPort: 8082,
	Formats:     []engines.Format{engines.FormatMLX, engines.FormatSafetensors},
	Modes:       []engines.Mode{engines.ModeNative},
	DefaultMode: engines.ModeNative,
	Description: "Apple Silicon inference runtime (native-only — no Docker image).",
}

// engine implements engines.Engine for MLX.
type engine struct{}

// Spec returns the MLX capability description.
func (engine) Spec() *engines.Spec { return spec } //nolint:revive // satisfies engines.Engine

func init() {
	engines.Default.Register(engine{})
}
