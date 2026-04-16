// Package recommendation produces engine + model suggestions given a
// hardware profile and a set of registered engines.
//
// The 2.0 recommender is rule-based: VRAM in GiB, GPU capability tags,
// and the requested task (quality, performance, coding, multimodal)
// pick a short ranked list of (engine, suggested_quantization) pairs
// along with human-readable rationale strings. This is a direct port
// of the 1.x recommender's decision tree — intentionally conservative
// so operators can see why a suggestion was made.
package recommendation

import (
	"sort"

	"github.com/flag-ai/kitt/internal/engines"
)

// Request narrows the recommendation space.
type Request struct {
	// GPUVRAMGiB is the target GPU's VRAM in GiB. Zero means "unknown"
	// and the recommender falls back to conservative suggestions only.
	GPUVRAMGiB int `json:"gpu_vram_gib"`

	// UnifiedMemory is true for Apple Silicon / DGX Spark systems
	// where host RAM backs the GPU. When true, MLX is preferred over
	// CUDA-only engines.
	UnifiedMemory bool `json:"unified_memory"`

	// Task is "quality" (accuracy-focused), "performance"
	// (throughput), "coding", or "multimodal". Empty defaults to
	// "quality".
	Task string `json:"task"`

	// DesiredFormats constrains the recommender to engines that can
	// load at least one of the listed weight formats. Empty means no
	// format constraint.
	DesiredFormats []engines.Format `json:"desired_formats,omitempty"`
}

// Suggestion is a single recommender output.
type Suggestion struct {
	Engine       string `json:"engine"`
	Quantization string `json:"quantization,omitempty"`
	Rationale    string `json:"rationale"`
	Score        int    `json:"score"`
}

// Recommender produces Suggestions for a Request.
type Recommender struct {
	registry *engines.Registry
}

// NewRecommender constructs a Recommender. registry must be non-nil.
func NewRecommender(r *engines.Registry) *Recommender {
	return &Recommender{registry: r}
}

// Recommend returns a ranked slice of Suggestions. The returned slice
// is always non-nil; an empty Request yields the default
// "quality on a CPU" suggestions.
func (r *Recommender) Recommend(req *Request) []Suggestion {
	task := req.Task
	if task == "" {
		task = "quality"
	}

	specs := r.registry.List()
	suggestions := make([]Suggestion, 0, len(specs))

	for _, spec := range specs {
		// Apply hardware eligibility rules first — skip engines that
		// can't run on the requested box at all.
		if !eligible(spec, req) {
			continue
		}
		score, rationale, quant := scoreEngine(spec, task, req)
		if score <= 0 {
			continue
		}
		suggestions = append(suggestions, Suggestion{
			Engine:       spec.Name,
			Quantization: quant,
			Rationale:    rationale,
			Score:        score,
		})
	}

	sort.SliceStable(suggestions, func(i, j int) bool {
		if suggestions[i].Score != suggestions[j].Score {
			return suggestions[i].Score > suggestions[j].Score
		}
		return suggestions[i].Engine < suggestions[j].Engine
	})
	return suggestions
}

// eligible filters engines that cannot run on the requested hardware.
func eligible(spec *engines.Spec, req *Request) bool {
	// MLX is native-only and requires unified memory (Apple Silicon
	// or DGX Spark). Reject it on traditional discrete GPUs.
	if spec.Name == "mlx" && !req.UnifiedMemory {
		return false
	}
	// ExLlamaV2 is a CUDA-only quantized runtime; rule it out on
	// unified memory / CPU-only hosts.
	if spec.Name == "exllamav2" && req.UnifiedMemory {
		return false
	}
	if len(req.DesiredFormats) > 0 {
		if !anyFormatMatches(spec.Formats, req.DesiredFormats) {
			return false
		}
	}
	return true
}

// scoreEngine returns a relative preference score for a given engine
// under the requested task + hardware, plus a short rationale and a
// suggested quantization string.
func scoreEngine(spec *engines.Spec, task string, req *Request) (score int, rationale, quant string) {
	vram := req.GPUVRAMGiB

	switch spec.Name {
	case "vllm":
		score = 70
		rationale = "High-throughput OpenAI-compatible server; ideal for production-like performance runs."
		switch {
		case vram >= 48:
			quant = "fp16"
			score += 10
		case vram >= 24:
			quant = "fp16 or awq-int4"
			score += 5
		case vram >= 16:
			quant = "awq-int4"
		default:
			// vLLM's memory overhead makes it a poor fit for <16 GiB
			// cards; downweight heavily.
			score -= 30
		}
		if task == "performance" {
			score += 15
		}

	case "llamacpp":
		score = 60
		rationale = "Lightweight GGUF runtime; strong fit across VRAM tiers and a safe default for small GPUs."
		switch {
		case vram >= 24:
			quant = "Q6_K or Q8_0"
			score += 5
		case vram >= 12:
			quant = "Q5_K_M"
		case vram >= 6:
			quant = "Q4_K_M"
		default:
			quant = "Q4_K_S (CPU offload)"
		}

	case "ollama":
		score = 55
		rationale = "Opinionated wrapper around llama.cpp with a friendly model pull UX."
		quant = "Q4_K_M (default)"

	case "exllamav2":
		if vram >= 12 {
			score = 75
			rationale = "Fast quantized inference for GPTQ/EXL2 weights on consumer GPUs."
			quant = "EXL2 4.0 bpw"
			if task == "performance" {
				score += 10
			}
		}

	case "mlx":
		score = 65
		rationale = "Native Apple Silicon / DGX Spark runtime using unified memory efficiently."
		quant = "MLX 4-bit"
		if task == "quality" {
			quant = "MLX 8-bit"
			score += 5
		}
	}

	// Task-specific nudges. These compound with the per-engine scores
	// above to surface task-relevant engines at the top of the list.
	switch task {
	case "quality":
		if spec.Name == "vllm" {
			score += 5
		}
	case "coding":
		if spec.Name == "vllm" || spec.Name == "exllamav2" {
			score += 8
		}
	case "multimodal":
		if spec.Name == "vllm" {
			score += 12
		} else {
			score -= 10
		}
	}
	return score, rationale, quant
}

// anyFormatMatches returns true when spec supports any format in want.
func anyFormatMatches(have, want []engines.Format) bool {
	set := make(map[engines.Format]struct{}, len(have))
	for _, f := range have {
		set[f] = struct{}{}
	}
	for _, f := range want {
		if _, ok := set[f]; ok {
			return true
		}
	}
	return false
}
