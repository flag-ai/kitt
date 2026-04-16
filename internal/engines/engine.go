// Package engines defines the inference-engine plugin interface and
// the compile-in registry for KITT 2.0.
//
// In 1.x engines were discovered at runtime via pkg_resources; in 2.0
// they are compiled in from sub-packages (vllm, llamacpp, ollama,
// exllamav2, mlx) via an init() side-effect registration. This trades
// deploy-time flexibility for type safety and a single binary.
package engines

// Mode is the execution environment an engine supports.
type Mode string

// Supported modes.
const (
	// ModeDocker runs the engine in a container via BONNIE.
	ModeDocker Mode = "docker"
	// ModeNative runs the engine as a host process on the BONNIE agent.
	ModeNative Mode = "native"
)

// Format is a model weight format a given engine can load.
type Format string

// Supported model formats across KITT's engine set.
const (
	FormatSafetensors Format = "safetensors"
	FormatPyTorch     Format = "pytorch"
	FormatGGUF        Format = "gguf"
	FormatGPTQ        Format = "gptq"
	FormatEXL2        Format = "exl2"
	FormatMLX         Format = "mlx"
)

// Spec describes an engine's static capabilities — everything that's
// known without contacting a running instance. Spec is returned by
// Engine.Spec() and serialized by GET /api/v1/engines so the UI can
// populate dropdowns.
type Spec struct {
	// Name is the stable identifier used in URLs, configs, and
	// profiles (e.g., "vllm", "llamacpp").
	Name string `json:"name"`

	// DisplayName is a human-readable label for UI surfaces.
	DisplayName string `json:"display_name"`

	// DockerImage is the default container image reference. Empty for
	// native-only engines.
	DockerImage string `json:"docker_image,omitempty"`

	// APIStyle identifies the request protocol the engine speaks on
	// its HTTP port ("openai" or "ollama").
	APIStyle string `json:"api_style"`

	// DefaultPort is the port the engine binds by default.
	DefaultPort int `json:"default_port"`

	// Formats is the set of model weight formats this engine can load.
	Formats []Format `json:"formats"`

	// Modes lists the execution modes this engine supports.
	Modes []Mode `json:"modes"`

	// DefaultMode is the mode chosen when a profile omits it.
	DefaultMode Mode `json:"default_mode"`

	// Description is a short capability summary for tooltips.
	Description string `json:"description,omitempty"`
}

// Engine is implemented by every built-in engine plugin. 2.0 only
// needs the static Spec — actual container/process lifecycle is
// delegated to BONNIE and exposed via agent commands in a later PR.
// Keeping the interface narrow for now lets us grow it without
// breaking early adopters.
type Engine interface {
	// Spec returns the engine's static description. Implementations
	// should return a pointer to a package-level value so callers can
	// rely on identity comparison for caching.
	Spec() *Spec
}
