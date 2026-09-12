"""Preflight prerequisite checks for KITT agent."""

import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    passed: bool
    required: bool
    message: str


def check_python_version() -> CheckResult:
    """Check Python >= 3.10."""
    version = sys.version_info
    ok = version >= (3, 10)
    return CheckResult(
        name="Python >= 3.10",
        passed=ok,
        required=True,
        message=f"{version.major}.{version.minor}.{version.micro}"
        if ok
        else f"Found {version.major}.{version.minor} — need 3.10+",
    )


def check_docker_available() -> CheckResult:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0
        return CheckResult(
            name="Docker available",
            passed=ok,
            required=True,
            message="Available" if ok else result.stderr.strip()[:80],
        )
    except FileNotFoundError:
        return CheckResult(
            name="Docker available",
            passed=False,
            required=True,
            message="docker not found in PATH",
        )
    except Exception as e:
        return CheckResult(
            name="Docker available",
            passed=False,
            required=True,
            message=str(e)[:80],
        )


def check_docker_gpu() -> CheckResult:
    """Check if Docker has GPU access."""
    try:
        import platform as _platform

        from kitt_agent.docker_ops import normalize_arch

        arch = normalize_arch(_platform.machine())
        docker_platform = f"linux/{arch}" if arch else None

        cmd = [
            "docker",
            "run",
            "--rm",
        ]
        if docker_platform:
            cmd.extend(["--platform", docker_platform])
        cmd.extend(
            [
                "--gpus",
                "all",
                "nvidia/cuda:12.0.0-base-ubuntu22.04",
                "nvidia-smi",
            ]
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
        return CheckResult(
            name="Docker GPU access",
            passed=ok,
            required=True,
            message="GPU accessible in containers"
            if ok
            else "No GPU access — check nvidia-container-toolkit",
        )
    except FileNotFoundError:
        return CheckResult(
            name="Docker GPU access",
            passed=False,
            required=True,
            message="docker not found",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Docker GPU access",
            passed=False,
            required=True,
            message="Timed out pulling/running CUDA image",
        )
    except Exception as e:
        return CheckResult(
            name="Docker GPU access",
            passed=False,
            required=True,
            message=str(e)[:80],
        )


def check_nvidia_drivers() -> CheckResult:
    """Check if NVIDIA drivers are installed."""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ok = result.returncode == 0
        # Extract driver version from first line
        driver_info = ""
        if ok and result.stdout:
            for line in result.stdout.splitlines():
                if "Driver Version" in line:
                    driver_info = line.strip()
                    break
        return CheckResult(
            name="NVIDIA drivers",
            passed=ok,
            required=True,
            message=driver_info or ("Installed" if ok else "nvidia-smi failed"),
        )
    except FileNotFoundError:
        return CheckResult(
            name="NVIDIA drivers",
            passed=False,
            required=True,
            message="nvidia-smi not found — install NVIDIA drivers",
        )
    except Exception as e:
        return CheckResult(
            name="NVIDIA drivers",
            passed=False,
            required=True,
            message=str(e)[:80],
        )


def check_nfs_utilities() -> CheckResult:
    """Check if NFS mount utilities are available."""
    has_nfs = shutil.which("mount.nfs") is not None
    return CheckResult(
        name="NFS utilities",
        passed=has_nfs,
        required=False,
        message="mount.nfs available"
        if has_nfs
        else "mount.nfs not found — install nfs-common",
    )


def check_disk_space(path: str = "") -> CheckResult:
    """Check if sufficient disk space is available."""
    check_path = path or str(Path.home() / ".kitt" / "models")
    # Create the directory if it doesn't exist so disk_usage works
    Path(check_path).mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(check_path)
        free_gb = usage.free / (1024**3)
        ok = free_gb >= 50
        return CheckResult(
            name="Disk space (>= 50GB free)",
            passed=ok,
            required=False,
            message=f"{free_gb:.1f}GB free at {check_path}",
        )
    except OSError as e:
        return CheckResult(
            name="Disk space (>= 50GB free)",
            passed=False,
            required=False,
            message=str(e)[:80],
        )


def check_server_reachable(server_url: str) -> CheckResult:
    """Check if the KITT server is reachable."""
    if not server_url:
        return CheckResult(
            name="Server reachable",
            passed=False,
            required=True,
            message="No server URL provided",
        )
    url = f"{server_url.rstrip('/')}/api/v1/health"
    import ssl

    req = urllib.request.Request(url, method="GET")
    # Try with TLS verification first, fall back to insecure for self-signed certs
    for verify in (True, False):
        try:
            ctx = ssl.create_default_context()
            if not verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                ok = resp.status == 200
                suffix = " (self-signed)" if not verify else ""
                return CheckResult(
                    name="Server reachable",
                    passed=ok,
                    required=True,
                    message=f"{server_url} — OK{suffix}"
                    if ok
                    else f"HTTP {resp.status}",
                )
        except ssl.SSLError:
            if verify:
                continue  # retry without verification
            return CheckResult(
                name="Server reachable",
                passed=False,
                required=True,
                message=f"{server_url} — SSL error",
            )
        except urllib.error.URLError as e:
            # URLError can wrap an SSL error on some platforms
            if verify and isinstance(e.reason, ssl.SSLError):
                continue  # retry without verification
            return CheckResult(
                name="Server reachable",
                passed=False,
                required=True,
                message=f"{server_url} — {e}",
            )
        except Exception as e:
            return CheckResult(
                name="Server reachable",
                passed=False,
                required=True,
                message=f"{server_url} — {e}",
            )
    # Should not reach here, but handle gracefully
    return CheckResult(
        name="Server reachable",
        passed=False,
        required=True,
        message=f"{server_url} — connection failed",
    )


def check_kitt_image(image: str = "kitt:latest") -> CheckResult:
    """Check if the KITT Docker image is available locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return CheckResult(
                name="KITT Docker image",
                passed=False,
                required=False,
                message=f"Image '{image}' not found — run 'kitt-agent build'",
            )

        # Extract architecture from inspect JSON
        import json

        inspect_data = json.loads(result.stdout)
        arch = "unknown"
        if inspect_data and isinstance(inspect_data, list):
            arch = inspect_data[0].get("Architecture", "unknown")

        return CheckResult(
            name="KITT Docker image",
            passed=True,
            required=False,
            message=f"{image} ({arch})",
        )
    except FileNotFoundError:
        return CheckResult(
            name="KITT Docker image",
            passed=False,
            required=False,
            message="docker not found",
        )
    except Exception as e:
        return CheckResult(
            name="KITT Docker image",
            passed=False,
            required=False,
            message=str(e)[:80],
        )


def check_port_available(port: int) -> CheckResult:
    """Check if the agent port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
        return CheckResult(
            name=f"Port {port} available",
            passed=True,
            required=False,
            message=f"Port {port} is free",
        )
    except OSError:
        return CheckResult(
            name=f"Port {port} available",
            passed=False,
            required=False,
            message=f"Port {port} is in use",
        )


def run_all_checks(
    server_url: str = "",
    port: int = 8090,
    model_storage_dir: str = "",
) -> list[CheckResult]:
    """Run all preflight checks and return results."""
    results = [
        check_python_version(),
        check_docker_available(),
        check_docker_gpu(),
        check_kitt_image(),
        check_nvidia_drivers(),
        check_nfs_utilities(),
        check_disk_space(model_storage_dir),
    ]
    if server_url:
        results.append(check_server_reachable(server_url))
    if port:
        results.append(check_port_available(port))
    return results


def print_results(results: list[CheckResult]) -> bool:
    """Print check results as a formatted table.

    Returns True if all required checks passed.
    """
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="KITT Agent Preflight Checks")
        table.add_column("Check", style="bold")
        table.add_column("Required")
        table.add_column("Status")
        table.add_column("Details")

        for r in results:
            if r.passed:
                status = "[green]PASS[/green]"
            elif r.required:
                status = "[red]FAIL[/red]"
            else:
                status = "[yellow]WARN[/yellow]"

            req = "Yes" if r.required else "No"
            table.add_row(r.name, req, status, r.message)

        console.print(table)
    except ImportError:
        # Fallback without Rich
        print("\nKITT Agent Preflight Checks")
        print("-" * 70)
        for r in results:
            status = "PASS" if r.passed else ("FAIL" if r.required else "WARN")
            req = "Req" if r.required else "Opt"
            print(f"  [{status}] [{req}] {r.name}: {r.message}")
        print()

    all_required_passed = all(r.passed for r in results if r.required)
    return all_required_passed
