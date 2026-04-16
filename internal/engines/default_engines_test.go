package engines_test

import (
	"testing"

	"github.com/flag-ai/kitt/internal/engines"

	// Side-effect imports register each engine with engines.Default.
	_ "github.com/flag-ai/kitt/internal/engines/exllamav2"
	_ "github.com/flag-ai/kitt/internal/engines/llamacpp"
	_ "github.com/flag-ai/kitt/internal/engines/mlx"
	_ "github.com/flag-ai/kitt/internal/engines/ollama"
	_ "github.com/flag-ai/kitt/internal/engines/vllm"
)

func TestDefaultRegistry_AllBuiltInsRegistered(t *testing.T) {
	specs := engines.Default.List()
	want := map[string]bool{
		"vllm":      false,
		"llamacpp":  false,
		"ollama":    false,
		"exllamav2": false,
		"mlx":       false,
	}
	for _, s := range specs {
		if _, ok := want[s.Name]; ok {
			want[s.Name] = true
		}
	}
	for name, seen := range want {
		if !seen {
			t.Errorf("engine %q not registered", name)
		}
	}
}

func TestDefaultRegistry_VLLMSpec(t *testing.T) {
	e, ok := engines.Default.Get("vllm")
	if !ok {
		t.Fatal("vllm not found")
	}
	s := e.Spec()
	if s.DockerImage != "vllm/vllm-openai:latest" {
		t.Errorf("image = %q", s.DockerImage)
	}
	if s.DefaultPort != 8000 {
		t.Errorf("port = %d", s.DefaultPort)
	}
	if s.DefaultMode != engines.ModeDocker {
		t.Errorf("mode = %q", s.DefaultMode)
	}
}
