# Concepts

This section explains the key ideas, design decisions, and internal architecture behind KITT. These pages are intended to help you understand **why** KITT works the way it does, not just **how** to use it.

If you are looking for step-by-step instructions, see the [Guides](../guides/index.md) section. If you need command-line reference, see the [CLI Reference](../reference/cli/index.md).

## Topics

### [Architecture](architecture.md)

How KITT is structured: the engine plugin system, Docker-based container management, the sibling container pattern, and the overall project layout.

### [Hardware Fingerprinting](hardware-fingerprinting.md)

How KITT uniquely identifies the hardware it runs on, the fingerprint format, detection methods for GPUs, CPUs, RAM, and storage, and the supported environment types.

### [KARR — Results Storage](karr.md)

KARR (Kitt's AI Results Repository) is KITT's results storage system. Covers the database backend (SQLite / PostgreSQL), the hybrid data model, schema migrations, and the evolution from flat files through Git-backed storage to the current database architecture.

### [Engine Lifecycle](engine-lifecycle.md)

The full lifecycle of an inference engine container: image pull, container creation, health checking with exponential backoff, benchmark execution, GPU memory tracking, and cleanup.

### [Benchmark System](benchmark-system.md)

The benchmark plugin architecture, built-in performance and quality benchmarks, YAML-defined custom benchmarks, checkpoint recovery, and suite orchestration.

### [Security](security.md)

Mutual TLS for agent-server communication, automatic certificate generation, bearer token authentication, and development-mode options.
