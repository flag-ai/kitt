# Plugin System

KITT uses a plugin architecture for both inference engines and benchmarks. The
built-in engines and benchmarks are registered the same way external plugins
are, so the extension mechanism is consistent throughout the codebase.

---

## Engine Plugins

Every engine extends the `InferenceEngine` abstract base class and is registered
with `@register_engine`:

```python
from kitt.engines.base import InferenceEngine
from kitt.engines.registry import register_engine


@register_engine
class MyEngine(InferenceEngine):
    @classmethod
    def name(cls) -> str:
        return "my-engine"

    @classmethod
    def supported_formats(cls) -> list[str]:
        return ["safetensors"]

    @classmethod
    def default_image(cls) -> str:
        return "myorg/my-engine:latest"

    @classmethod
    def default_port(cls) -> int:
        return 8000

    @classmethod
    def container_port(cls) -> int:
        return 8000

    @classmethod
    def health_endpoint(cls) -> str:
        return "/health"

    def initialize(self, model_path: str, config: dict) -> None:
        ...

    def generate(self, prompt: str, **kwargs) -> "GenerationResult":
        ...
```

The `InferenceEngine` ABC requires you to implement:

- `name()` -- unique engine identifier
- `supported_formats()` -- model file formats the engine can load
- `default_image()` / `default_port()` / `container_port()` -- Docker settings
- `health_endpoint()` -- path the health check probes
- `initialize()` -- start the Docker container and wait for health
- `generate()` -- send a prompt and return a `GenerationResult`

The `cleanup()` method is provided by the base class and stops the container.

---

## Benchmark Plugins

Benchmarks extend `LLMBenchmark` and register with `@register_benchmark`:

```python
from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark


@register_benchmark
class MyBenchmark(LLMBenchmark):
    name = "my-benchmark"
    version = "1.0.0"
    category = "quality_custom"
    description = "Measures something useful."

    def _execute(self, engine, config: dict) -> BenchmarkResult:
        result = engine.generate(prompt="Hello", max_tokens=50)
        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=True,
            metrics={"tokens_generated": result.completion_tokens},
            outputs=[result.output],
        )
```

The base class provides the `run()` method which handles warmup iterations
before calling your `_execute()` implementation.

---

## Plugin Discovery

KITT discovers external plugins through Python entry points. Declare your
plugin in `pyproject.toml`:

```toml
[project.entry-points."kitt.engines"]
my-engine = "my_package.engine:MyEngine"

[project.entry-points."kitt.benchmarks"]
my-benchmark = "my_package.benchmark:MyBenchmark"
```

Supported entry point groups:

| Group | Class Base |
|-------|------------|
| `kitt.engines` | `InferenceEngine` |
| `kitt.benchmarks` | `LLMBenchmark` |
| `kitt.reporters` | Reporter classes |

When KITT calls `EngineRegistry.auto_discover()` or
`BenchmarkRegistry.auto_discover()`, it first registers all built-in
implementations and then scans entry points for external plugins.

---

## Managing Plugins with the CLI

Install a third-party plugin package:

```bash
kitt plugin install kitt-engine-triton
```

List installed plugins and discovered classes:

```bash
kitt plugin list
```

Remove a plugin:

```bash
kitt plugin remove kitt-engine-triton
```

After installation, the new engine or benchmark is immediately available in
`kitt run`, `kitt engines list`, and `kitt test list`.

---

## Plugin File Locations

| Location | Purpose |
|----------|---------|
| `src/kitt/engines/` | Built-in engine implementations |
| `src/kitt/benchmarks/performance/` | Built-in performance benchmarks |
| `src/kitt/benchmarks/quality/standard/` | Built-in quality benchmarks |
| `src/kitt/plugins/discovery.py` | Entry point scanning logic |
| `src/kitt/plugins/installer.py` | `pip install` / `pip uninstall` wrapper |
| `src/kitt/plugins/validator.py` | Plugin compatibility checks |

---

## Tips for Plugin Authors

1. Always subclass the ABC (`InferenceEngine` or `LLMBenchmark`) so KITT can
   validate your plugin at registration time.
2. Use the decorator (`@register_engine` / `@register_benchmark`) if your
   module will be imported directly, or declare an entry point if the plugin
   is distributed as a separate package.
3. Test your plugin in isolation with `kitt engines check <name>` or
   `kitt test list --category quality_custom` before running full suites.
