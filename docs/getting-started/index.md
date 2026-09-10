# Getting Started

Everything you need to install KITT, run your first benchmark, and deploy with
Docker.

---

## What's in This Section

### [Installation](installation.md)

Install KITT using Docker (recommended) or from source with Poetry. Covers
prerequisites, optional extras, and GPU setup.

### [Tutorial: First Benchmark](first-benchmark.md)

A step-by-step walkthrough from hardware fingerprinting through benchmark
execution to storing results in KARR.

### [Tutorial: Docker Quickstart](docker-quickstart.md)

Run KITT entirely from a container -- build the image, mount models and results,
use Docker Compose, and generate production deployment stacks.

---

## Prerequisites at a Glance

| Requirement | Why |
|---|---|
| Docker | All inference engines run as containers |
| NVIDIA GPU + drivers | Required for GPU-accelerated inference |
| NVIDIA Container Toolkit | Lets Docker containers access the GPU |
| A model on disk | GGUF, safetensors, or PyTorch format depending on engine |

!!! tip
    The fastest path to your first result is the Docker method described in the
    [Installation](installation.md) guide -- no Python environment needed on the
    host.
