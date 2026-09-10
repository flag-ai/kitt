# Campaigns

Campaigns automate benchmark runs across multiple models, engines, and
quantization variants. Define the matrix in a YAML file and KITT handles
scheduling, state tracking, and failure recovery.

## Campaign YAML Structure

```yaml
campaign_name: my-campaign
description: "Benchmark Llama and Qwen across all engines"

models:
  - name: Llama-3.1-8B-Instruct
    params: "8B"
    safetensors_repo: meta-llama/Llama-3.1-8B-Instruct
    gguf_repo: bartowski/Meta-Llama-3.1-8B-Instruct-GGUF
    ollama_tag: "llama3.1:8b"
    estimated_size_gb: 16.0

  - name: Qwen2.5-7B-Instruct
    params: "7B"
    gguf_repo: Qwen/Qwen2.5-7B-Instruct-GGUF
    ollama_tag: "qwen2.5:7b"
    estimated_size_gb: 14.0

engines:
  - name: llama_cpp
    suite: standard
    formats: [gguf]
  - name: ollama
    suite: standard
    formats: [gguf]

disk:
  reserve_gb: 100.0
  cleanup_after_run: true

notifications:
  desktop: true
  on_complete: true
  on_failure: true

quant_filter:
  skip_patterns: ["IQ1_*", "IQ2_*"]

resource_limits:
  max_model_size_gb: 100.0

parallel: false
devon_managed: true
```

Each model can specify multiple source repositories (safetensors, GGUF, Ollama
tag). KITT automatically matches models to compatible engines based on format.

## Running a Campaign

```bash
kitt campaign run configs/campaigns/example.yaml
```

Use `--dry-run` to preview the planned runs without executing them:

```bash
kitt campaign run configs/campaigns/example.yaml --dry-run
```

## Campaign Wizard

Build a campaign config interactively:

```bash
kitt campaign wizard
```

The wizard walks through model selection, engine configuration, disk limits,
and notification settings, then outputs a YAML file you can save and edit.

## Campaign Lifecycle and State

KITT persists campaign state so you can track progress and resume interrupted
runs.

```bash
# Check latest campaign status
kitt campaign status

# Check a specific campaign
kitt campaign status <campaign-id>

# List all campaigns
kitt campaign list
```

Campaign states: **pending**, **running**, **completed**, **failed**.

## Resuming and Rerunning Failures

If a campaign is interrupted or some runs fail, resume from where it left off:

```bash
kitt campaign run configs/campaigns/example.yaml --resume
kitt campaign run configs/campaigns/example.yaml --resume --campaign-id <id>
```

Only pending and failed runs are re-executed. Successful runs are skipped.

You can also create a dedicated failure-rerun config that targets specific
models and quants. See `configs/campaigns/rerun-failures.yaml` for an example.

## Scheduling

Schedule a campaign to run on a cron expression:

```bash
kitt campaign schedule configs/campaigns/example.yaml --cron "0 2 * * *"
kitt campaign cron-status
kitt campaign unschedule <schedule-id>
```

## Generating a Config from Existing Results

Create a campaign config that replays the model/engine combinations found in an
existing results directory:

```bash
kitt campaign create --from-results ./kitt-results -o replay.yaml
```

## Web UI Campaign Wizard

The web dashboard provides a step-by-step wizard for creating campaigns without writing YAML. Navigate to **Campaigns > Create Campaign** and follow the six steps:

1. **Basics** — enter a campaign name and optional description.
2. **Agent** — select the target agent. The chosen agent's hardware determines which engines are compatible.
3. **Engines** — pick one or more engines. Format badges (safetensors, GGUF) and platform warnings are shown based on the selected agent's CPU architecture.
4. **Models** — a searchable multi-select checklist of models found in the configured model directory, filtered to only show models compatible with the selected engines' supported formats.
5. **Settings** — choose the test suite, toggle Devon-managed model handling, and enable post-run cleanup.
6. **Review** — a compatibility matrix shows which model/engine combinations will actually run. Confirm to create the campaign.

After creation, click **Launch** on the campaign detail page to start execution.

## Agent-Based Dispatch

When a campaign is launched on a remote agent from the web UI, KITT breaks the campaign config into individual quick test rows and queues them one at a time. Each test is picked up by the agent's heartbeat, dispatched for execution, and the campaign executor waits for it to finish before queuing the next.

The campaign detail page streams live progress logs over SSE showing:

- Which model/engine/benchmark combination is running
- Agent status transitions (queued, dispatched, running, completed)
- Success/failure counts and final summary

Campaign logs are persisted to the database, so they survive page refreshes and remain available after the campaign completes. Each test has a 30-minute timeout.

Campaigns launched on a **test agent** use simulated execution instead — see the [Test Agents](agents.md#test-agents) section.

## Key Options Reference

| Option | Description |
|---|---|
| `parallel` | Run models in parallel (requires multiple GPUs) |
| `devon_managed` | Use DEVON for model download management |
| `quant_filter.skip_patterns` | Glob patterns for quantization variants to skip |
| `quant_filter.include_only` | Only include these specific quant names |
| `resource_limits.max_model_size_gb` | Skip models exceeding this size |
| `disk.reserve_gb` | Minimum free disk space to maintain |
| `disk.cleanup_after_run` | Delete downloaded models after each run |
