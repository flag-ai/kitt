// Package exllamav2 registers the ExLlamaV2 engine.
package exllamav2

import "github.com/flag-ai/kitt/internal/engines"

var spec = &engines.Spec{
	Name:        "exllamav2",
	DisplayName: "ExLlamaV2",
	DockerImage: "ghcr.io/turboderp/exllamav2",
	APIStyle:    "openai",
	DefaultPort: 8002,
	Formats: []engines.Format{
		engines.FormatGPTQ,
		engines.FormatEXL2,
		engines.FormatGGUF,
	},
	Modes:       []engines.Mode{engines.ModeDocker},
	DefaultMode: engines.ModeDocker,
	Description: "Fast quantized inference for GPTQ/EXL2 weights on consumer GPUs.",
}

// engine implements engines.Engine for ExLlamaV2.
type engine struct{}

// Spec returns the ExLlamaV2 capability description.
func (engine) Spec() *engines.Spec { return spec } //nolint:revive // satisfies engines.Engine

func init() {
	engines.Default.Register(engine{})
}
