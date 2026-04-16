// Package vllm registers the vLLM engine.
package vllm

import "github.com/flag-ai/kitt/internal/engines"

// spec is the static capability description for vLLM.
var spec = &engines.Spec{
	Name:        "vllm",
	DisplayName: "vLLM",
	DockerImage: "vllm/vllm-openai:latest",
	APIStyle:    "openai",
	DefaultPort: 8000,
	Formats:     []engines.Format{engines.FormatSafetensors, engines.FormatPyTorch},
	Modes:       []engines.Mode{engines.ModeDocker, engines.ModeNative},
	DefaultMode: engines.ModeDocker,
	Description: "High-throughput OpenAI-compatible server backed by PagedAttention.",
}

// engine implements engines.Engine for vLLM.
type engine struct{}

// Spec returns the vLLM capability description.
func (engine) Spec() *engines.Spec { return spec } //nolint:revive // satisfies engines.Engine

func init() {
	engines.Default.Register(engine{})
}
