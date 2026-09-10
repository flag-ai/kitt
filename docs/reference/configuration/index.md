# Configuration Files

KITT uses YAML configuration files stored in the `configs/` directory at the
project root. Every configuration file is validated at load time with
**Pydantic v2** models defined in `src/kitt/config/models.py`.

## Directory layout

```
configs/
├── suites/              # Test-suite definitions
│   ├── quick.yaml
│   ├── standard.yaml
│   └── performance.yaml
├── engines/             # Engine parameter overrides
│   ├── vllm.yaml
│   ├── llama_cpp.yaml
│   ├── ollama.yaml
│   └── profiles/        # Named engine profiles
├── campaigns/           # Multi-model, multi-engine campaign configs
│   ├── example.yaml
│   └── scheduled_example.yaml
└── tests/               # Benchmark definitions
    ├── performance/     # Built-in performance benchmarks
    └── quality/
        ├── standard/    # Built-in quality benchmarks (MMLU, GSM8K, ...)
        └── custom/      # User-created custom benchmarks
```

## Configuration types

| Type | Pydantic Model | Reference |
|------|---------------|-----------|
| Suite | `SuiteConfig` | [Suite Configuration](suites.md) |
| Engine | `EngineConfig` | [Engine Configuration](engines.md) |
| Campaign | *(free-form YAML)* | [Campaign Configuration](campaigns.md) |
| Benchmark | `TestConfig` | [Custom Benchmark Configuration](benchmarks.md) |

## Loading pattern

All configs follow the same load pattern:

```python
from kitt.config.loader import load_config
from kitt.config.models import SuiteConfig

suite = load_config("configs/suites/standard.yaml", SuiteConfig)
```

`load_config()` reads the YAML file, passes the resulting dictionary to the
Pydantic model, and raises a validation error if any field is invalid or
missing.
