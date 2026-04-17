// Package ollama registers the Ollama engine.
package ollama

import "github.com/flag-ai/kitt/internal/engines"

var spec = &engines.Spec{
	Name:        "ollama",
	DisplayName: "Ollama",
	DockerImage: "ollama/ollama:latest",
	APIStyle:    "ollama",
	DefaultPort: 11434,
	Formats:     []engines.Format{engines.FormatGGUF},
	Modes:       []engines.Mode{engines.ModeDocker, engines.ModeNative},
	DefaultMode: engines.ModeDocker,
	Description: "Ergonomic runtime for GGUF models with a native API.",
}

// engine implements engines.Engine for Ollama.
type engine struct{}

// Spec returns the Ollama capability description.
func (engine) Spec() *engines.Spec { return spec } //nolint:revive // satisfies engines.Engine

func init() {
	engines.Default.Register(engine{})
}
