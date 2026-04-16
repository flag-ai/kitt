package engines

import (
	"fmt"
	"sort"
	"sync"
)

// Registry holds every built-in engine plugin. The global registry is
// populated by init() blocks in each engine sub-package, keeping
// compile-in registration local to where the engine is defined.
type Registry struct {
	mu      sync.RWMutex
	engines map[string]Engine
}

// NewRegistry constructs an empty registry.
func NewRegistry() *Registry {
	return &Registry{engines: map[string]Engine{}}
}

// Register adds e to the registry. Panics if an engine with the same
// name is already registered — duplicate names are a programming error
// that must be caught at init-time.
func (r *Registry) Register(e Engine) {
	if e == nil {
		panic("engines: nil engine")
	}
	spec := e.Spec()
	if spec == nil || spec.Name == "" {
		panic("engines: engine has no Spec or empty name")
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.engines[spec.Name]; ok {
		panic(fmt.Sprintf("engines: duplicate registration for %q", spec.Name))
	}
	r.engines[spec.Name] = e
}

// Get returns the engine registered under name, or (nil, false).
func (r *Registry) Get(name string) (Engine, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	e, ok := r.engines[name]
	return e, ok
}

// List returns every registered engine's Spec, sorted by Name.
func (r *Registry) List() []*Spec {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]*Spec, 0, len(r.engines))
	for _, e := range r.engines {
		out = append(out, e.Spec())
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// Default is the process-wide registry populated by init() side-effects
// in the engine sub-packages. Importers of this package should do
// blank imports of the engine packages they want included:
//
//	import (
//	    _ "github.com/flag-ai/kitt/internal/engines/vllm"
//	    _ "github.com/flag-ai/kitt/internal/engines/llamacpp"
//	    ...
//	)
var Default = NewRegistry()
