# Remote Execution

KITT can run benchmark campaigns on remote GPU servers over SSH. This is useful
when you have multiple machines and want to coordinate work from a single
workstation without deploying the full agent daemon.

---

## How It Works

The `kitt remote` commands manage a registry of remote hosts stored in
`~/.kitt/hosts.yaml`. KITT connects via SSH to upload campaign configs, start
benchmarks, stream logs, and sync results back to your local machine.

---

## Setting Up a Remote Host

```bash
kitt remote setup user@gpu-server-01 --name dgx01
```

This command:

1. Opens an SSH connection to the host.
2. Checks prerequisites -- Python version, Docker availability, GPU info.
3. Optionally installs KITT on the remote host (skip with `--no-install`).
4. Saves the host configuration to `~/.kitt/hosts.yaml`.

You can also supply a specific SSH key:

```bash
kitt remote setup user@gpu-server-01 --name dgx01 --ssh-key ~/.ssh/id_ed25519
```

---

## Host Configuration

Hosts are stored in `~/.kitt/hosts.yaml` with the following structure:

```yaml
hosts:
  dgx01:
    name: dgx01
    hostname: gpu-server-01
    user: user
    ssh_key: ~/.ssh/id_ed25519
    port: 22
    kitt_path: ~/.local/bin/kitt
    storage_path: ~/kitt-results
    gpu_info: NVIDIA GH200
    gpu_count: 1
    python_version: "3.11"
```

List all configured hosts:

```bash
kitt remote list
```

Test connectivity:

```bash
kitt remote test dgx01
```

Remove a host:

```bash
kitt remote remove dgx01
```

---

## Running Campaigns Remotely

Upload a campaign config and start it on a remote host:

```bash
kitt remote run campaign.yaml --host dgx01
```

Add `--wait` to block until the campaign finishes:

```bash
kitt remote run campaign.yaml --host dgx01 --wait
```

Use `--dry-run` to validate the config without executing benchmarks.

---

## Monitoring Remote Campaigns

Check the status of a running campaign:

```bash
kitt remote status --host dgx01
```

View live logs:

```bash
kitt remote logs --host dgx01 --tail 100
```

---

## Syncing Results

After a campaign completes, pull results to your local machine:

```bash
kitt remote sync --host dgx01
```

By default results are saved to the local KITT results directory. Override with
`--output`:

```bash
kitt remote sync --host dgx01 --output ./results/dgx01
```

---

## Coordinating Distributed Benchmarks

To run the same campaign across multiple hosts, script the `kitt remote run`
command for each host:

```bash
for host in dgx01 dgx02 dgx03; do
    kitt remote run campaign.yaml --host "$host" &
done
wait
for host in dgx01 dgx02 dgx03; do
    kitt remote sync --host "$host" --output "./results/$host"
done
```

Then use `kitt results compare` or `kitt compare` to analyze results across
machines.
