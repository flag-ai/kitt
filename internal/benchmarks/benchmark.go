// Package benchmarks defines the benchmark plugin types and the
// database-backed registry.
//
// KITT 2.0 supports two kinds of benchmarks:
//
//   - KindYAML — declarative prompts + grading rules loaded from
//     benchmarks-reference/yaml/. Small, self-contained, ideal for
//     quality (MMLU, GSM8K, HellaSwag, TruthfulQA, prompt-robustness).
//
//   - KindContainer — containerized harnesses published from
//     benchmarks-reference/containers/. Necessary for anything that
//     needs a runtime environment (HumanEval sandboxed execution,
//     VLM image handling, RAG pipelines, performance/streaming
//     measurements that need low-level instrumentation).
//
// Both kinds are recorded in the same `benchmark_registry` table; the
// `kind` column tells the campaign runner how to dispatch the run.
package benchmarks

// Kind names the dispatch strategy for a benchmark.
type Kind string

// Supported benchmark kinds.
const (
	// KindYAML means the server interprets the config map as prompts +
	// grading rules and runs the benchmark against the engine directly.
	KindYAML Kind = "yaml"

	// KindContainer means KITT asks BONNIE to pull and run the named
	// container image; the benchmark emits its own results over SSE.
	KindContainer Kind = "container"
)

// Category is a loose grouping used for UI filtering.
type Category string

// Common categories. New categories can be added freely — the registry
// doesn't enforce a closed set because operators author their own
// benchmarks.
const (
	CategoryQuality     Category = "quality"
	CategoryPerformance Category = "performance"
	CategoryRobustness  Category = "robustness"
	CategoryCoding      Category = "coding"
	CategoryRAG         Category = "rag"
	CategoryMultimodal  Category = "multimodal"
)
