# Reference

Technical reference material for KITT. This section provides detailed
specifications for the CLI, configuration file schemas, Docker setup,
REST API, and environment variables.

Use these pages when you need exact field names, endpoint paths, or
default values. For guided walkthroughs, see the
[Getting Started](../getting-started/index.md) section instead.

## Contents

- **[CLI Reference](cli/index.md)** -- Complete command and option listing,
  auto-generated from Click decorators.

- **[Configuration Files](configuration/index.md)** -- YAML schema reference
  for suites, engines, campaigns, and custom benchmarks.

    - [Suite Configuration](configuration/suites.md)
    - [Engine Configuration](configuration/engines.md)
    - [Campaign Configuration](configuration/campaigns.md)
    - [Custom Benchmark Configuration](configuration/benchmarks.md)

- **[Docker Files](docker-files.md)** -- Dockerfile stages, docker-compose
  services, GPU passthrough, and network requirements.

- **[REST API](api.md)** -- Endpoints exposed by `kitt web`, including
  authentication, request/response formats, and SSE streaming.

- **[Environment Variables](environment.md)** -- Every environment variable
  KITT reads, with descriptions and default values.
