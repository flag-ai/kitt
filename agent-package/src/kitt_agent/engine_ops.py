"""Agent-side native engine lifecycle management.

Handles discovery, installation, startup, shutdown, and status
queries for inference engines running as native host processes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shlex
import shutil
import subprocess as sp
import sys
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Dedicated venv for vLLM with CUDA-matched wheels.
_VLLM_VENV_DIR = Path.home() / ".kitt" / "vllm-venv"

# Engine binary names to search for during discovery.
_ENGINE_BINARIES: dict[str, list[str]] = {
    "ollama": ["ollama"],
    "llama_cpp": ["llama-server"],
    "vllm": [],  # Python module — no standalone binary
}

# Default ports used by native engine servers.
_ENGINE_PORTS: dict[str, int] = {
    "ollama": 11434,
    "llama_cpp": 8081,
    "vllm": 8000,
}


class EngineOps:
    """Agent-side engine lifecycle operations.

    All methods are designed to be called from the daemon's command
    dispatch, either synchronously or in a background thread.
    """

    # Active engine processes tracked by engine name.
    _processes: dict[str, sp.Popen[str]] = {}
    _lock = threading.Lock()

    @staticmethod
    def find_engine(name: str) -> dict[str, Any]:
        """Discover whether an engine is available on the host.

        Returns a dict with:
            installed (bool), binary_path (str), version (str)
        """
        result: dict[str, Any] = {
            "engine": name,
            "installed": False,
            "binary_path": "",
            "version": "",
        }

        if name == "vllm":
            # vLLM is a Python module, not a standalone binary.
            # Check the dedicated vLLM venv first (has CUDA-matched wheels),
            # then fall back to the current interpreter (agent venv).
            python = _find_vllm_python()
            try:
                out = sp.run(
                    [python, "-c", "import vllm; print(vllm.__version__)"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if out.returncode == 0:
                    result["installed"] = True
                    result["binary_path"] = f"{python} -m vllm"
                    result["version"] = out.stdout.strip()
            except (FileNotFoundError, sp.TimeoutExpired):
                pass
            return result

        binaries = _ENGINE_BINARIES.get(name, [])
        for binary in binaries:
            path = shutil.which(binary)
            if path:
                result["installed"] = True
                result["binary_path"] = path
                result["version"] = _get_version(binary, path)
                break

        return result

    @staticmethod
    def engine_status(name: str) -> dict[str, Any]:
        """Get current status of an engine.

        Returns a dict with:
            engine, installed, binary_path, version, running, pid, port
        """
        info = EngineOps.find_engine(name)
        info["running"] = False
        info["pid"] = 0
        info["port"] = _ENGINE_PORTS.get(name, 0)

        # Check for tracked process.
        with EngineOps._lock:
            proc = EngineOps._processes.get(name)
        if proc and proc.poll() is None:
            info["running"] = True
            info["pid"] = proc.pid
            return info

        # Check if Ollama systemd service is running.
        if name == "ollama" and _is_systemd_active("ollama"):
            info["running"] = True
            pid = _get_systemd_pid("ollama")
            if pid:
                info["pid"] = pid
            return info

        return info

    @staticmethod
    def start_engine(
        name: str,
        runtime_config: dict[str, Any],
        model_path: str = "",
        on_log: Any = None,
    ) -> dict[str, Any]:
        """Start a native engine process.

        Returns a dict with: success, pid, port, error
        """
        log = on_log or logger.info
        port = runtime_config.get("port", _ENGINE_PORTS.get(name, 0))

        # Check if already running.
        status = EngineOps.engine_status(name)
        if status["running"]:
            log(f"{name} is already running (PID {status['pid']})")
            return {
                "success": True,
                "pid": status["pid"],
                "port": port,
                "error": "",
            }

        if not status["installed"]:
            return {
                "success": False,
                "pid": 0,
                "port": port,
                "error": f"{name} is not installed",
            }

        try:
            if name == "ollama":
                proc = _start_ollama(port, runtime_config, log)
            elif name == "llama_cpp":
                proc = _start_llama_cpp(
                    status["binary_path"], port, model_path, runtime_config, log
                )
            elif name == "vllm":
                proc = _start_vllm(port, model_path, runtime_config, log)
            else:
                return {
                    "success": False,
                    "pid": 0,
                    "port": port,
                    "error": f"Unknown engine: {name}",
                }

            # Verify the process started.
            time.sleep(0.5)
            if proc.poll() is not None:
                output = ""
                if proc.stderr:
                    output = proc.stderr.read()
                elif proc.stdout:
                    output = proc.stdout.read()
                return {
                    "success": False,
                    "pid": 0,
                    "port": port,
                    "error": f"Process exited immediately: {output}",
                }

            with EngineOps._lock:
                EngineOps._processes[name] = proc
            log(f"{name} started (PID {proc.pid}, port {port})")
            return {"success": True, "pid": proc.pid, "port": port, "error": ""}

        except Exception as e:
            return {"success": False, "pid": 0, "port": port, "error": str(e)}

    @staticmethod
    def stop_engine(name: str) -> dict[str, Any]:
        """Stop a running engine process.

        Returns a dict with: success, error
        """
        with EngineOps._lock:
            proc = EngineOps._processes.pop(name, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except sp.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                return {"success": True, "error": ""}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Try systemd for Ollama.
        if name == "ollama" and _is_systemd_active("ollama"):
            try:
                sp.run(
                    ["systemctl", "stop", "ollama"],
                    capture_output=True,
                    timeout=15,
                )
                return {"success": True, "error": ""}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": f"{name} is not running"}

    @staticmethod
    def install_engine(
        name: str,
        on_log: Any = None,
    ) -> dict[str, Any]:
        """Install a native engine on the host.

        Returns a dict with: success, version, error
        """
        log = on_log or logger.info

        # Check if already installed.
        info = EngineOps.find_engine(name)
        if info["installed"]:
            log(f"{name} already installed (version {info['version']})")
            return {
                "success": True,
                "version": info["version"],
                "already_installed": True,
                "error": "",
            }

        try:
            if name == "ollama":
                return _install_ollama(log)
            elif name == "llama_cpp":
                return _install_llama_cpp(log)
            elif name == "vllm":
                return _install_vllm(log)
            else:
                return {
                    "success": False,
                    "version": "",
                    "error": f"No installer for engine: {name}",
                }
        except Exception as e:
            log(f"Installation failed: {e}")
            return {"success": False, "version": "", "error": str(e)}

    @staticmethod
    def all_engine_status() -> list[dict[str, Any]]:
        """Get status of all known engines. Used for heartbeat payload."""
        results = []
        for name in _ENGINE_BINARIES:
            results.append(EngineOps.engine_status(name))
        return results


# -------------------------------------------------------------------
# Engine installers
# -------------------------------------------------------------------


def _install_ollama(log: Any) -> dict[str, Any]:
    """Install Ollama via the official install script."""
    log("Installing Ollama via https://ollama.com/install.sh ...")
    result = sp.run(
        ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        log(f"Ollama install failed: {error}")
        return {"success": False, "version": "", "error": error}

    # Verify installation.
    info = EngineOps.find_engine("ollama")
    if info["installed"]:
        log(f"Ollama installed successfully (version {info['version']})")
        return {"success": True, "version": info["version"], "error": ""}

    return {
        "success": False,
        "version": "",
        "error": "Install script succeeded but ollama binary not found",
    }


def _install_llama_cpp(log: Any) -> dict[str, Any]:
    """Install llama.cpp llama-server from source or package manager."""
    # Method 1: Build from source with CUDA (most reliable on ARM64/Blackwell).
    if shutil.which("cmake") and shutil.which("git"):
        log("Building llama.cpp from source with CUDA support...")
        nvcc = shutil.which("nvcc") or "/usr/local/cuda/bin/nvcc"
        cuda_arch = os.environ.get("CUDA_ARCHITECTURES", "native")
        build_script = (
            "cd /tmp && rm -rf llama.cpp"
            " && git clone --depth 1 https://github.com/ggml-org/llama.cpp.git"
            " && cd llama.cpp"
            f" && cmake -B build -DGGML_CUDA=ON"
            f" -DCMAKE_CUDA_ARCHITECTURES={shlex.quote(cuda_arch)}"
            f" -DCMAKE_CUDA_COMPILER={shlex.quote(nvcc)}"
            " && cmake --build build --config Release -j$(nproc) --target llama-server"
            " && sudo cp build/bin/llama-server /usr/local/bin/"
            " && rm -rf /tmp/llama.cpp"
        )
        result = sp.run(
            ["bash", "-c", build_script],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            info = EngineOps.find_engine("llama_cpp")
            if info["installed"]:
                log(f"llama-server built and installed (version {info['version']})")
                return {"success": True, "version": info["version"], "error": ""}
        log(f"Source build failed: {result.stderr.strip()[-200:]}")

    # Method 2: Try pip into the current venv.
    log("Trying pip install llama-cpp-python[server]...")
    result = sp.run(
        [sys.executable, "-m", "pip", "install", "llama-cpp-python[server]"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode == 0:
        info = EngineOps.find_engine("llama_cpp")
        if info["installed"]:
            log(f"llama-server installed via pip (version {info['version']})")
            return {"success": True, "version": info["version"], "error": ""}

    return {
        "success": False,
        "version": "",
        "error": "Could not install llama-server from source or pip",
    }


def _install_vllm(log: Any) -> dict[str, Any]:
    """Install vLLM into a dedicated venv with CUDA-matched wheels.

    Standard pip installs pull CPU-only PyTorch on platforms like DGX Spark
    (CUDA 13 + ARM64).  A dedicated venv lets us pin the correct torch+cu130
    wheels without disturbing the agent venv.
    """
    venv_python = str(_VLLM_VENV_DIR / "bin" / "python")

    # Create the dedicated venv if it doesn't exist.
    if not _VLLM_VENV_DIR.exists():
        log(f"Creating dedicated vLLM venv at {_VLLM_VENV_DIR}...")
        result = sp.run(
            [sys.executable, "-m", "venv", str(_VLLM_VENV_DIR)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {"success": False, "version": "", "error": result.stderr.strip()}
        # Upgrade pip.
        sp.run(
            [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    # Detect CUDA version for index selection.
    cuda_ver = _detect_cuda_major()
    if cuda_ver and cuda_ver >= 13:
        log(f"Detected CUDA {cuda_ver} — installing PyTorch cu130 wheels...")
        result = sp.run(
            [
                venv_python, "-m", "pip", "install",
                "torch", "torchvision", "torchaudio",
                "--index-url", "https://download.pytorch.org/whl/cu130",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            log(f"PyTorch cu130 install warning: {result.stderr.strip()[-200:]}")

        log("Installing vLLM cu130 nightly...")
        result = sp.run(
            [
                venv_python, "-m", "pip", "install",
                "--force-reinstall", "--no-deps",
                "vllm",
                "-i", "https://wheels.vllm.ai/nightly/cu130",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            log(f"vLLM cu130 nightly failed: {result.stderr.strip()[-200:]}")
            # Fall back to standard install with deps.
            log("Falling back to standard vLLM install...")
            result = sp.run(
                [venv_python, "-m", "pip", "install", "vllm"],
                capture_output=True,
                text=True,
                timeout=600,
            )

        # Install remaining vLLM deps that --no-deps skipped.
        sp.run(
            [
                venv_python, "-m", "pip", "install",
                "vllm", "--extra-index-url", "https://wheels.vllm.ai/nightly/cu130",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    else:
        log("Installing vLLM via pip...")
        result = sp.run(
            [venv_python, "-m", "pip", "install", "vllm"],
            capture_output=True,
            text=True,
            timeout=600,
        )

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        log(f"vLLM install failed: {error}")
        return {"success": False, "version": "", "error": error}

    info = EngineOps.find_engine("vllm")
    if info["installed"]:
        log(f"vLLM installed (version {info['version']})")
        return {"success": True, "version": info["version"], "error": ""}

    return {
        "success": False,
        "version": "",
        "error": "pip install succeeded but vllm module not importable",
    }


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


def _find_vllm_python() -> str:
    """Return the Python interpreter that has vLLM installed.

    Search order:
    1. Dedicated vLLM venv (~/.kitt/vllm-venv/bin/python) — preferred
       because it can carry CUDA-matched wheels independent of the
       agent venv.
    2. Current interpreter (sys.executable) — the agent venv.
    """
    venv_python = str(_VLLM_VENV_DIR / "bin" / "python")
    if _VLLM_VENV_DIR.exists() and os.path.isfile(venv_python):
        try:
            out = sp.run(
                [venv_python, "-c", "import vllm"],
                capture_output=True,
                timeout=10,
            )
            if out.returncode == 0:
                return venv_python
        except (FileNotFoundError, sp.TimeoutExpired):
            pass
    return sys.executable


def _detect_cuda_major() -> int | None:
    """Detect the major CUDA toolkit version from nvcc."""
    nvcc = shutil.which("nvcc") or "/usr/local/cuda/bin/nvcc"
    try:
        out = sp.run(
            [nvcc, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in out.stdout.split("\n"):
            if "release" in line.lower():
                # e.g. "Cuda compilation tools, release 13.0, V13.0.96"
                parts = line.split("release")[-1].strip().split(",")[0].strip()
                return int(parts.split(".")[0])
    except (FileNotFoundError, sp.TimeoutExpired, ValueError, IndexError):
        pass
    return None


def _get_version(binary_name: str, binary_path: str) -> str:
    """Try to get the version string from an engine binary."""
    try:
        if binary_name == "ollama":
            out = sp.run(
                [binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Ollama outputs: "ollama version 0.x.y"
            return out.stdout.strip().replace("ollama version ", "")
        elif binary_name in ("llama-server",):
            out = sp.run(
                [binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return out.stdout.strip().split("\n")[0]
    except (FileNotFoundError, sp.TimeoutExpired):
        pass
    return ""


def _is_systemd_active(service: str) -> bool:
    """Check if a systemd service is active."""
    try:
        result = sp.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "active"
    except (FileNotFoundError, sp.TimeoutExpired):
        return False


def _get_systemd_pid(service: str) -> int:
    """Get the main PID of a systemd service."""
    try:
        result = sp.run(
            ["systemctl", "show", "--property=MainPID", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            if line.startswith("MainPID="):
                pid = int(line.split("=", 1)[1])
                return pid if pid > 0 else 0
    except (FileNotFoundError, sp.TimeoutExpired, ValueError):
        pass
    return 0


def _start_ollama(
    port: int,
    runtime_config: dict[str, Any],
    log: Any,
) -> sp.Popen[str]:
    """Start an Ollama server process."""
    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"0.0.0.0:{port}"

    # Forward runtime config as environment variables.
    for key in (
        "OLLAMA_NUM_PARALLEL",
        "OLLAMA_MAX_LOADED_MODELS",
        "OLLAMA_GPU_OVERHEAD",
    ):
        if key.lower() in runtime_config:
            env[key] = str(runtime_config[key.lower()])
        elif key in runtime_config:
            env[key] = str(runtime_config[key])

    log(f"Starting ollama serve on port {port}")
    return sp.Popen(
        ["ollama", "serve"],
        stdout=sp.PIPE,
        stderr=sp.STDOUT,
        text=True,
        env=env,
    )


def _start_llama_cpp(
    binary_path: str,
    port: int,
    model_path: str,
    runtime_config: dict[str, Any],
    log: Any,
) -> sp.Popen[str]:
    """Start a llama-server process."""
    args = [
        binary_path,
        "--port",
        str(port),
        "--host",
        "0.0.0.0",
    ]

    if model_path:
        args.extend(["--model", model_path])

    # Map runtime config to CLI flags.
    flag_map = {
        "n_gpu_layers": "--n-gpu-layers",
        "n_ctx": "--ctx-size",
        "n_batch": "--batch-size",
        "threads": "--threads",
        "flash_attn": "--flash-attn",
    }
    for key, flag in flag_map.items():
        if key in runtime_config:
            val = runtime_config[key]
            if isinstance(val, bool):
                if val:
                    args.append(flag)
            else:
                args.extend([flag, str(val)])

    log(f"Starting llama-server on port {port}: {' '.join(args[:6])}...")
    return sp.Popen(
        args,
        stdout=sp.PIPE,
        stderr=sp.STDOUT,
        text=True,
    )


def _start_vllm(
    port: int,
    model_path: str,
    runtime_config: dict[str, Any],
    log: Any,
) -> sp.Popen[str]:
    """Start a vLLM OpenAI-compatible server."""
    python = _find_vllm_python()
    args = [
        python,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--port",
        str(port),
        "--host",
        "0.0.0.0",
    ]

    if model_path:
        args.extend(["--model", model_path])

    # Map runtime config to CLI flags.
    flag_map = {
        "tensor_parallel_size": "--tensor-parallel-size",
        "gpu_memory_utilization": "--gpu-memory-utilization",
        "max_model_len": "--max-model-len",
        "dtype": "--dtype",
        "quantization": "--quantization",
    }
    for key, flag in flag_map.items():
        if key in runtime_config:
            args.extend([flag, str(runtime_config[key])])

    log(f"Starting vLLM server on port {port}")
    return sp.Popen(
        args,
        stdout=sp.PIPE,
        stderr=sp.STDOUT,
        text=True,
    )
