# Monitoring

KITT includes a Prometheus + Grafana + InfluxDB monitoring stack for tracking
benchmark and system metrics over time. You can run the built-in stack locally,
generate customized stacks with specific scrape targets, and deploy them to
remote hosts.

## Local Stack

Start the built-in monitoring stack from the `docker/monitoring/` directory:

```bash
kitt monitoring start
kitt monitoring status
kitt monitoring stop
```

Target a named generated stack instead of the built-in one:

```bash
kitt monitoring start --name lab
kitt monitoring stop --name lab
```

## Generating a Custom Stack

Create a monitoring stack with custom Prometheus scrape targets:

```bash
kitt monitoring generate <name> -t <host:port> [-t <host:port> ...] [OPTIONS]
```

Generated stacks are stored at `~/.kitt/monitoring/<name>/`.

| Option | Default | Description |
|---|---|---|
| `-t` / `--target` | (required) | Scrape target `host:port` (repeatable) |
| `--grafana-port` | 3000 | Grafana dashboard port |
| `--prometheus-port` | 9090 | Prometheus port |
| `--influxdb-port` | 8086 | InfluxDB port |
| `--grafana-password` | kitt | Grafana admin password |
| `--influxdb-token` | (auto) | InfluxDB admin token |

Example:

```bash
kitt monitoring generate lab -t 192.168.1.10:9100 -t 192.168.1.11:9100
```

## Port Configuration

Override default ports when generating a stack:

```bash
kitt monitoring generate lab \
  -t 10.0.0.5:9100 \
  --grafana-port 3001 \
  --prometheus-port 9091 \
  --influxdb-port 8087
```

## Credentials

Set custom Grafana and InfluxDB credentials at generation time:

```bash
kitt monitoring generate lab \
  -t 10.0.0.5:9100 \
  --grafana-password my-secret \
  --influxdb-token my-influx-token
```

## Remote Deployment

Deploy a generated stack to a remote host and manage its lifecycle over SSH.
Remote hosts are configured in `~/.kitt/hosts.yaml`.

### Deploy

Upload the generated stack to a remote host:

```bash
kitt monitoring deploy lab --host dgx01
```

You can also deploy immediately after generation:

```bash
kitt monitoring generate lab -t 10.0.0.5:9100 --deploy --host dgx01
```

### Remote Start / Stop / Status

```bash
kitt monitoring remote-start lab --host dgx01
kitt monitoring remote-stop lab --host dgx01
kitt monitoring remote-status lab --host dgx01
```

## Stack Management

### List Stacks

```bash
kitt monitoring list-stacks
```

### Remove a Stack

```bash
kitt monitoring remove-stack lab
kitt monitoring remove-stack lab --delete-files
```

## Example Workflow

A complete workflow from generation to remote teardown:

```bash
# Generate a stack targeting two hosts
kitt monitoring generate lab -t 192.168.1.10:9100 -t 192.168.1.11:9100

# Deploy to a remote DGX host
kitt monitoring deploy lab --host dgx01

# Check status on the remote host
kitt monitoring remote-status lab --host dgx01

# View Grafana dashboards
# Open http://dgx01:3000 in your browser (admin / kitt)

# Stop when done
kitt monitoring remote-stop lab --host dgx01

# Clean up
kitt monitoring remove-stack lab --delete-files
```
