# Guides

How-to guides for specific tasks in KITT. Each guide walks through a
particular workflow -- from engine setup to production deployment -- with
commands you can copy and adapt.

If you are new to KITT, start with the
[Getting Started](../getting-started/index.md) section first.

---

## Engine & Benchmark Workflows

- **[Engines](engines.md)** -- Set up, inspect, and configure inference engines.
- **[Benchmarks](benchmarks.md)** -- Run test suites, create custom benchmarks, and interpret results.
- **[Results & KARR](results.md)** -- Store, compare, import, and export benchmark results through KARR.
- **[Campaigns](campaigns.md)** -- Automate multi-model, multi-engine benchmark runs with campaign configs.

## Deployment & Infrastructure

- **[Docker Deployment](deployment.md)** -- Generate composable Docker stacks with `kitt stack`.
- **[Web Dashboard](web-dashboard.md)** -- Launch the web UI, configure TLS, and use the REST API.
- **[Monitoring](monitoring.md)** -- Deploy Prometheus + Grafana + InfluxDB monitoring stacks locally or remotely.

## Distributed Execution

- **[Agent Daemon](agents.md)** -- Run a KITT agent on GPU servers for remote benchmark execution.
- **[Remote Execution](remote-execution.md)** -- Set up remote hosts and run campaigns over SSH.

## Automation & Integration

- **[CI Integration](ci-integration.md)** -- Generate reports and post results to GitHub PRs from CI pipelines.
- **[Plugins](plugins.md)** -- Install, list, and remove third-party KITT plugins.
- **[Bot Integration](bots.md)** -- Run a Slack or Discord bot that responds to benchmark commands.

## Visualization & Hardware

- **[Charts](charts.md)** -- Generate quantization quality tradeoff curves and export data.
- **[DGX Spark](dgx-spark.md)** -- Notes for running KITT on NVIDIA DGX Spark hardware.
