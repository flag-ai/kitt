// Package llamacpp registers the llama.cpp engine.
package llamacpp

import "github.com/flag-ai/kitt/internal/engines"

var spec = &engines.Spec{
	Name:        "llamacpp",
	DisplayName: "llama.cpp",
	DockerImage: "ghcr.io/ggerganov/llama.cpp:server",
	APIStyle:    "openai",
	DefaultPort: 8081,
	Formats:     []engines.Format{engines.FormatGGUF},
	Modes:       []engines.Mode{engines.ModeDocker, engines.ModeNative},
	DefaultMode: engines.ModeDocker,
	Description: "Lightweight CPU/GPU inference with broad quantization support.",
}

// engine implements engines.Engine for llama.cpp.
type engine struct{}

// Spec returns the llama.cpp capability description.
func (engine) Spec() *engines.Spec { return spec } //nolint:revive // satisfies engines.Engine

func init() {
	engines.Default.Register(engine{})
}
