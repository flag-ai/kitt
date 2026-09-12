# CLI Reference

Complete reference for all KITT commands. This page is auto-generated from
the Click decorators in the source code, so it always reflects the current
state of the CLI.

KITT exposes **18 command groups** through a single entry point:

| Group | Purpose |
|-------|---------|
| `run` | Execute benchmarks against an engine |
| `test` | List benchmarks, create custom tests |
| `engines` | List, check, and set up inference engines |
| `results` | KARR result management, listing, and comparison |
| `campaign` | Run multi-model, multi-engine campaigns |
| `monitoring` | Generate and deploy monitoring stacks |
| `stack` | Generate and manage composable Docker stacks |
| `agent` | Manage distributed benchmark agents |
| `remote` | Remote deployment commands |
| `ci` | CI/CD integration helpers |
| `bot` | Chat-bot testing utilities |
| `plugin` | Manage engine and benchmark plugins |
| `charts` | Generate result charts and visualizations |
| `recommend` | Hardware and configuration recommendations |
| `storage` | Manage result storage backends |
| `compare` | Launch interactive TUI for comparing runs |
| `fingerprint` | Display hardware fingerprint |
| `web` | Launch the web dashboard and REST API |

::: mkdocs-click
    :module: kitt.cli.main
    :command: cli
    :prog_name: kitt
    :depth: 2
    :style: table
