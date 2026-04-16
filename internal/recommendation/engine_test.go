package recommendation_test

import (
	"testing"

	"github.com/flag-ai/kitt/internal/engines"
	"github.com/flag-ai/kitt/internal/recommendation"

	// Register all built-in engines for the test registry.
	_ "github.com/flag-ai/kitt/internal/engines/exllamav2"
	_ "github.com/flag-ai/kitt/internal/engines/llamacpp"
	_ "github.com/flag-ai/kitt/internal/engines/mlx"
	_ "github.com/flag-ai/kitt/internal/engines/ollama"
	_ "github.com/flag-ai/kitt/internal/engines/vllm"
)

func TestRecommend_24GiBQualityPrefersVLLM(t *testing.T) {
	r := recommendation.NewRecommender(engines.Default)
	out := r.Recommend(&recommendation.Request{GPUVRAMGiB: 24, Task: "quality"})
	if len(out) == 0 {
		t.Fatal("expected suggestions")
	}
	if out[0].Engine != "vllm" {
		t.Errorf("top = %q (all = %v)", out[0].Engine, names(out))
	}
}

func TestRecommend_UnifiedMemoryPreferMLX(t *testing.T) {
	r := recommendation.NewRecommender(engines.Default)
	out := r.Recommend(&recommendation.Request{UnifiedMemory: true, Task: "quality"})
	found := false
	for _, s := range out {
		if s.Engine == "mlx" {
			found = true
		}
		if s.Engine == "exllamav2" {
			t.Errorf("exllamav2 should be filtered out on unified memory")
		}
	}
	if !found {
		t.Errorf("mlx not recommended; got %v", names(out))
	}
}

func TestRecommend_SmallVRAMPrefersLlamaCpp(t *testing.T) {
	r := recommendation.NewRecommender(engines.Default)
	out := r.Recommend(&recommendation.Request{GPUVRAMGiB: 8, Task: "quality"})
	if len(out) == 0 {
		t.Fatal("expected suggestions")
	}
	// Small VRAM should rank llamacpp ahead of vllm because vllm is
	// penalised below 16 GiB.
	llamacppIdx := indexOf(out, "llamacpp")
	vllmIdx := indexOf(out, "vllm")
	if llamacppIdx == -1 {
		t.Fatalf("llamacpp missing; got %v", names(out))
	}
	if vllmIdx != -1 && vllmIdx < llamacppIdx {
		t.Errorf("vllm should rank below llamacpp at 8 GiB (got vllm=%d llamacpp=%d)", vllmIdx, llamacppIdx)
	}
}

func TestRecommend_FormatFilter(t *testing.T) {
	r := recommendation.NewRecommender(engines.Default)
	out := r.Recommend(&recommendation.Request{
		GPUVRAMGiB:     24,
		Task:           "quality",
		DesiredFormats: []engines.Format{engines.FormatGGUF},
	})
	for _, s := range out {
		if s.Engine == "vllm" {
			t.Errorf("vllm should not match when only GGUF is acceptable")
		}
	}
}

func names(ss []recommendation.Suggestion) []string {
	out := make([]string, len(ss))
	for i, s := range ss {
		out[i] = s.Engine
	}
	return out
}

func indexOf(ss []recommendation.Suggestion, name string) int {
	for i, s := range ss {
		if s.Engine == name {
			return i
		}
	}
	return -1
}
