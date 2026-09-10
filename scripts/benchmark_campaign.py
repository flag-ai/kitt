#!/usr/bin/env python3
"""Multi-model benchmark campaign on DGX Spark.

Runs comprehensive benchmarks across 5 models with all available
quantization levels on vLLM, llama.cpp, and Ollama engines.

Uses a download-benchmark-delete pipeline to manage disk space:
  - Downloads one model/quant at a time
  - Runs the standard benchmark suite
  - Removes the model before downloading the next

Usage:
    python scripts/benchmark_campaign.py [--dry-run] [--resume-from MODEL ENGINE QUANT]
"""
import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("campaign.log"),
    ],
)
log = logging.getLogger("campaign")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISK_RESERVE_GB = 100
SUITE = "standard"
DEVON = "devon"
KITT = "kitt"

# Devon storage path (must match ~/.config/devon/config.yaml)
DEVON_STORAGE = Path.home() / "models"


@dataclass
class ModelSpec:
    name: str
    params: str
    safetensors_repo: Optional[str]  # None = skip vLLM
    gguf_repo: Optional[str]
    ollama_tag: Optional[str]


MODELS = [
    ModelSpec(
        name="Llama-3.1-8B-Instruct",
        params="8B",
        safetensors_repo="meta-llama/Llama-3.1-8B-Instruct",
        gguf_repo="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        ollama_tag="llama3.1:8b",
    ),
    ModelSpec(
        name="Qwen2.5-7B-Instruct",
        params="7B",
        safetensors_repo="Qwen/Qwen2.5-7B-Instruct",
        gguf_repo="Qwen/Qwen2.5-7B-Instruct-GGUF",
        ollama_tag="qwen2.5:7b",
    ),
    ModelSpec(
        name="Mistral-7B-Instruct-v0.3",
        params="7B",
        safetensors_repo="mistralai/Mistral-7B-Instruct-v0.3",
        gguf_repo="bartowski/Mistral-7B-Instruct-v0.3-GGUF",
        ollama_tag="mistral:7b",
    ),
    ModelSpec(
        name="Llama-3.3-70B-Instruct",
        params="70B",
        safetensors_repo=None,  # Skip vLLM — too large for GPU memory
        gguf_repo="bartowski/Llama-3.3-70B-Instruct-GGUF",
        ollama_tag="llama3.3:70b",
    ),
    ModelSpec(
        name="Phi-4",
        params="14B",
        safetensors_repo="microsoft/Phi-4",
        gguf_repo="bartowski/Phi-4-GGUF",
        ollama_tag="phi4:latest",
    ),
]

# ---------------------------------------------------------------------------
# Campaign tracking
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    model: str
    engine: str
    quant: str
    status: str  # "success", "failed", "skipped"
    duration_s: float = 0.0
    output_dir: str = ""
    error: str = ""


@dataclass
class CampaignState:
    started_at: str = ""
    results: list = field(default_factory=list)
    completed_keys: set = field(default_factory=set)

    def add(self, result: RunResult):
        self.results.append(result)
        self.completed_keys.add(f"{result.model}|{result.engine}|{result.quant}")

    def is_done(self, model: str, engine: str, quant: str) -> bool:
        return f"{model}|{engine}|{quant}" in self.completed_keys

    def save(self, path: Path):
        data = {
            "started_at": self.started_at,
            "results": [vars(r) for r in self.results],
            "completed_keys": list(self.completed_keys),
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "CampaignState":
        if not path.exists():
            return cls(started_at=datetime.now().isoformat())
        data = json.loads(path.read_text())
        state = cls(
            started_at=data["started_at"],
            results=[RunResult(**r) for r in data["results"]],
            completed_keys=set(data["completed_keys"]),
        )
        return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def free_space_gb() -> float:
    usage = shutil.disk_usage(str(Path.home()))
    return usage.free / (1024 ** 3)


def check_disk_space(min_gb: float = DISK_RESERVE_GB) -> bool:
    avail = free_space_gb()
    if avail < min_gb:
        log.warning(f"Low disk space: {avail:.1f}GB free (need {min_gb}GB reserve)")
        return False
    return True


def run_cmd(args: list[str], timeout: int = 14400, dry_run: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command with logging."""
    cmd_str = " ".join(args)
    log.info(f"$ {cmd_str}")
    if dry_run:
        log.info("[DRY RUN] Skipped")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        log.error(f"Command timed out after {timeout}s: {cmd_str}")
        return subprocess.CompletedProcess(args, -1, stdout=e.stdout or "", stderr=f"TIMEOUT after {timeout}s")
    except Exception as e:
        log.error(f"Command raised exception: {cmd_str}: {e}")
        return subprocess.CompletedProcess(args, -1, stdout="", stderr=str(e))


def devon_download(repo_id: str, include: Optional[str] = None, dry_run: bool = False) -> tuple[bool, str]:
    """Download a model via devon. Returns (success, error_message)."""
    args = [DEVON, "download", repo_id, "-y"]
    if include:
        args.extend(["--include", include])
    result = run_cmd(args, timeout=7200, dry_run=dry_run)
    if result.returncode != 0:
        error = _extract_error(result, "devon download")
        log.error(f"Download failed: {error}")
        return False, error
    return True, ""


def devon_remove(repo_id: str, dry_run: bool = False) -> bool:
    """Remove a model via devon."""
    result = run_cmd([DEVON, "remove", repo_id, "-y"], dry_run=dry_run)
    if result.returncode != 0:
        log.warning(f"Remove failed (may already be gone): {result.stderr}")
    return True


def kitt_run(model_path: str, engine: str, suite: str = SUITE, dry_run: bool = False) -> tuple[bool, str, str]:
    """Run a KITT benchmark. Returns (success, output_dir, error_message)."""
    args = [KITT, "run", "-m", model_path, "-e", engine, "-s", suite]
    result = run_cmd(args, timeout=14400, dry_run=dry_run)
    if dry_run:
        return True, "dry-run", ""

    # Parse output dir from kitt output
    output_dir = ""
    for line in (result.stdout or "").splitlines():
        if "Results saved" in line or "kitt-results" in line.lower():
            # Try to extract path
            for word in line.split():
                if "kitt-results" in word:
                    output_dir = word.strip()
                    break

    if result.returncode != 0:
        error = _extract_error(result, "kitt run")
        log.error(f"KITT run failed: {error}")
        return False, output_dir, error

    return True, output_dir, ""


def _extract_error(result: subprocess.CompletedProcess, label: str) -> str:
    """Build a concise error string from a failed subprocess result."""
    parts = [f"exit_code={result.returncode}"]

    stderr = (result.stderr or "").strip()
    if stderr:
        # Keep last 1000 chars of stderr — most useful info is at the end
        parts.append(f"stderr={stderr[-1000:]}")

    stdout = (result.stdout or "").strip()
    if stdout and not stderr:
        # If no stderr, check stdout for error lines
        error_lines = [l for l in stdout.splitlines() if any(
            kw in l.lower() for kw in ("error", "traceback", "exception", "failed", "oom", "killed")
        )]
        if error_lines:
            parts.append(f"stdout_errors={'; '.join(error_lines[-5:])}")
        else:
            # Last 500 chars of stdout as fallback context
            parts.append(f"stdout_tail={stdout[-500:]}")

    return f"[{label}] {' | '.join(parts)}"


def cleanup_docker(dry_run: bool = False):
    """Clean up any leftover kitt containers."""
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=kitt-", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    containers = [c.strip() for c in result.stdout.splitlines() if c.strip()]
    if containers:
        log.info(f"Cleaning up {len(containers)} leftover kitt containers")
        if not dry_run:
            subprocess.run(["docker", "rm", "-f"] + containers, capture_output=True)


@dataclass
class GGUFQuant:
    """A single quantization variant, which may consist of multiple shard files."""
    quant_name: str
    files: list[str]  # All files for this quant (1 file, or multiple shards)
    include_pattern: str  # Pattern for devon --include


def discover_gguf_quants(repo_id: str) -> list[GGUFQuant]:
    """List available GGUF quantization variants in a HuggingFace repo.

    Groups split/sharded files (e.g., model-00001-of-00002.gguf) into a
    single quant entry and creates appropriate include patterns.
    """
    import re

    try:
        from huggingface_hub import list_repo_files
        all_files = list(list_repo_files(repo_id))
        gguf_files = sorted([f for f in all_files if f.endswith(".gguf")])
    except Exception as e:
        log.error(f"Failed to list GGUF files for {repo_id}: {e}")
        return []

    if not gguf_files:
        return []

    # Group by quant name — shards share the same prefix/quant
    # Patterns: "Model-Q4_K_M.gguf" (single) or "model-q4_k_m/model-q4_k_m-00001-of-00002.gguf" (split)
    quant_groups: dict[str, list[str]] = {}

    for f in gguf_files:
        # Extract quant name from the filename part only, not directory path
        filename = Path(f).name
        # Check if this is a shard file (contains -NNNNN-of-NNNNN)
        shard_match = re.search(r'-(\d{5})-of-(\d{5})\.gguf$', filename)
        if shard_match:
            # Group key: everything before the shard numbering
            base = re.sub(r'-\d{5}-of-\d{5}\.gguf$', '', filename)
            quant_name = extract_quant_name(base)
            key = quant_name
        else:
            quant_name = extract_quant_name(filename)
            key = quant_name

        quant_groups.setdefault(key, []).append(f)

    quants = []
    for quant_name, files in quant_groups.items():
        if len(files) == 1:
            # Single file — include the exact filename
            include_pattern = files[0]
        else:
            # Multiple shards — use a glob pattern to get all of them
            # Find common prefix/directory
            common_dir = str(Path(files[0]).parent)
            if common_dir and common_dir != ".":
                include_pattern = f"{common_dir}/*.gguf"
            else:
                # Files are at root level with shared prefix
                prefix = _common_prefix(files)
                include_pattern = f"{prefix}*.gguf"

        quants.append(GGUFQuant(quant_name=quant_name, files=files, include_pattern=include_pattern))

    log.info(f"Found {len(quants)} GGUF quant variants ({len(gguf_files)} files) in {repo_id}")
    return quants


def _common_prefix(strings: list[str]) -> str:
    """Find the longest common prefix of a list of strings."""
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def discover_ollama_tags(base_tag: str) -> list[str]:
    """Discover available Ollama tags for a model.

    Scrapes the Ollama library page and filters to instruct quant variants
    matching the base tag's parameter size.
    Falls back to the base tag if scraping fails.
    """
    import re

    model_name = base_tag.split(":")[0]
    # Extract target size from base_tag (e.g., "8b" from "llama3.1:8b")
    target_size = base_tag.split(":")[-1] if ":" in base_tag else None

    try:
        import requests
        resp = requests.get(
            f"https://ollama.com/library/{model_name}/tags",
            timeout=15,
        )
        if resp.status_code == 200:
            # Parse tags from HTML href patterns like /library/llama3.1:8b-instruct-q4_0
            raw_tags = re.findall(
                rf'/library/{re.escape(model_name)}:([^"&\s]+)',
                resp.text,
            )
            # Deduplicate preserving order
            seen = set()
            unique_tags = []
            for tag in raw_tags:
                if tag not in seen:
                    seen.add(tag)
                    unique_tags.append(tag)

            if unique_tags:
                # Filter: keep tags matching target size, instruct only, latest version
                filtered = []
                for tag in unique_tags:
                    # Match the target parameter size
                    if target_size and target_size != "latest":
                        if not tag.startswith(target_size.replace("b", "b")):
                            continue
                    # Skip "text" variants (non-instruct base models)
                    if "-text-" in tag or tag.endswith("-text"):
                        continue
                    # For models with versioned tags (e.g., mistral v0.2/v0.3),
                    # prefer the latest version and skip older ones.
                    # If a tag has no version, skip it if versioned equivalents exist.
                    if re.search(r'-v\d+\.\d+-', tag):
                        # This is a versioned tag — keep it (we'll dedup later)
                        pass
                    elif re.search(r'-instruct-[qf]', tag):
                        # Unversioned instruct+quant tag — skip if versioned exists
                        quant_part = tag.split("-instruct-")[-1]
                        versioned_exists = any(
                            re.search(rf'-instruct-v[\d.]+-{re.escape(quant_part)}$', t)
                            for t in unique_tags
                        )
                        if versioned_exists:
                            continue
                    filtered.append(f"{model_name}:{tag}")

                # Among versioned tags, keep only the highest version per quant
                if any(re.search(r'-v\d+\.\d+-', t.split(":")[-1]) for t in filtered):
                    deduped = {}
                    non_versioned = []
                    for full_tag in filtered:
                        tag = full_tag.split(":")[-1]
                        ver_match = re.search(r'-v(\d+\.\d+)-(.+)$', tag)
                        if ver_match:
                            version, quant = ver_match.group(1), ver_match.group(2)
                            base = re.sub(r'-v\d+\.\d+-', '-', tag)
                            if base not in deduped or version > deduped[base][0]:
                                deduped[base] = (version, full_tag)
                        else:
                            non_versioned.append(full_tag)
                    filtered = non_versioned + [v[1] for v in deduped.values()]

                if filtered:
                    log.info(f"Found {len(filtered)} Ollama tags for {base_tag}")
                    return sorted(filtered)
    except Exception as e:
        log.warning(f"Ollama tag discovery failed for {model_name}: {e}")

    # Fallback: return only the base tag provided
    log.info(f"Using base tag only for {model_name}: {base_tag}")
    return [base_tag]


def find_model_path(repo_id: str, gguf_filename: Optional[str] = None) -> Optional[str]:
    """Find the local path for a downloaded model."""
    base = DEVON_STORAGE / "huggingface" / repo_id
    if not base.exists():
        log.warning(f"Model directory not found: {base}")
        return None

    if gguf_filename:
        # For GGUF: look for the specific file
        gguf_path = base / gguf_filename
        if gguf_path.exists():
            return str(gguf_path)
        # Some repos nest files in subdirectories
        for p in base.rglob(gguf_filename):
            return str(p)
        log.warning(f"GGUF file not found: {gguf_filename} in {base}")
        return None

    # For safetensors: return the directory
    return str(base)


def extract_quant_name(gguf_filename: str) -> str:
    """Extract quantization name from GGUF filename.

    Examples:
        Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf -> Q4_K_M
        qwen2.5-7b-instruct-q4_k_m.gguf -> q4_k_m
    """
    stem = Path(gguf_filename).stem
    # Common quant patterns
    import re
    match = re.search(
        r'(IQ[1-4]_[A-Za-z]+|[Qq][2-8]_[Kk0](?:_[SMLsml])?|[Ff][Pp]16|[Bb][Ff]16|[Ff]32)',
        stem,
    )
    return match.group(0) if match else stem


# ---------------------------------------------------------------------------
# Campaign runners
# ---------------------------------------------------------------------------

def run_vllm_benchmark(
    model: ModelSpec,
    state: CampaignState,
    dry_run: bool = False,
) -> Optional[RunResult]:
    """Run vLLM benchmark with safetensors (bf16)."""
    if not model.safetensors_repo:
        log.info(f"Skipping vLLM for {model.name} (no safetensors repo)")
        return None

    quant = "bf16"
    if state.is_done(model.name, "vllm", quant):
        log.info(f"Already done: {model.name} / vllm / {quant}")
        return None

    log.info(f"=== vLLM: {model.name} ({quant}) ===")
    cleanup_docker(dry_run)

    if not check_disk_space():
        return RunResult(model.name, "vllm", quant, "skipped", error="Low disk space")

    # Download safetensors model
    start = time.time()
    dl_ok, dl_err = devon_download(model.safetensors_repo, dry_run=dry_run)
    if not dl_ok:
        return RunResult(model.name, "vllm", quant, "failed", error=dl_err)

    # Find model path
    model_path = find_model_path(model.safetensors_repo)
    if not model_path and not dry_run:
        devon_remove(model.safetensors_repo, dry_run=dry_run)
        return RunResult(model.name, "vllm", quant, "failed", error="Model path not found after download")

    # Run benchmark
    success, output_dir, run_err = kitt_run(model_path or "dry-run", "vllm", dry_run=dry_run)
    duration = time.time() - start

    # Clean up
    devon_remove(model.safetensors_repo, dry_run=dry_run)

    status = "success" if success else "failed"
    return RunResult(model.name, "vllm", quant, status, duration, output_dir, error=run_err)


def run_llamacpp_benchmarks(
    model: ModelSpec,
    state: CampaignState,
    dry_run: bool = False,
) -> list[RunResult]:
    """Run llama.cpp benchmarks for all available GGUF quants."""
    results = []
    if not model.gguf_repo:
        return results

    quants = discover_gguf_quants(model.gguf_repo)
    if not quants:
        log.warning(f"No GGUF quants found for {model.name}")
        return results

    log.info(f"=== llama.cpp: {model.name} — {len(quants)} quants ===")

    for quant_info in quants:
        quant = quant_info.quant_name

        if state.is_done(model.name, "llama_cpp", quant):
            log.info(f"Already done: {model.name} / llama_cpp / {quant}")
            continue

        log.info(f"--- llama.cpp: {model.name} / {quant} ({len(quant_info.files)} file(s)) ---")
        cleanup_docker(dry_run)

        if not check_disk_space():
            results.append(RunResult(model.name, "llama_cpp", quant, "skipped", error="Low disk space"))
            continue

        start = time.time()

        # Download the GGUF file(s) for this quant
        dl_ok, dl_err = devon_download(model.gguf_repo, include=quant_info.include_pattern, dry_run=dry_run)
        if not dl_ok:
            results.append(RunResult(model.name, "llama_cpp", quant, "failed", error=dl_err))
            continue

        # Find the GGUF file path — use the first file (for single files) or
        # the first shard (llama.cpp loads sharded models from the first shard)
        primary_file = quant_info.files[0]
        model_path = find_model_path(model.gguf_repo, primary_file)
        if not model_path and not dry_run:
            devon_remove(model.gguf_repo, dry_run=dry_run)
            results.append(RunResult(model.name, "llama_cpp", quant, "failed", error="GGUF not found after download"))
            continue

        # Run benchmark
        success, output_dir, run_err = kitt_run(model_path or "dry-run", "llama_cpp", dry_run=dry_run)
        duration = time.time() - start

        # Clean up — remove the entire repo entry so next quant downloads fresh
        devon_remove(model.gguf_repo, dry_run=dry_run)

        status = "success" if success else "failed"
        results.append(RunResult(model.name, "llama_cpp", quant, status, duration, output_dir, error=run_err))

    return results


def run_ollama_benchmarks(
    model: ModelSpec,
    state: CampaignState,
    dry_run: bool = False,
) -> list[RunResult]:
    """Run Ollama benchmarks for all available tags."""
    results = []
    if not model.ollama_tag:
        return results

    tags = discover_ollama_tags(model.ollama_tag)
    if not tags:
        log.warning(f"No Ollama tags found for {model.name}")
        return results

    log.info(f"=== Ollama: {model.name} — {len(tags)} tags ===")

    for tag in tags:
        quant = tag.split(":")[-1] if ":" in tag else tag

        if state.is_done(model.name, "ollama", quant):
            log.info(f"Already done: {model.name} / ollama / {quant}")
            continue

        log.info(f"--- Ollama: {model.name} / {quant} ({tag}) ---")
        cleanup_docker(dry_run)

        start = time.time()

        # Ollama pulls models inside the container, no devon download needed
        success, output_dir, run_err = kitt_run(tag, "ollama", dry_run=dry_run)
        duration = time.time() - start

        # Container cleanup removes pulled model automatically
        status = "success" if success else "failed"
        results.append(RunResult(model.name, "ollama", quant, status, duration, output_dir, error=run_err))

    return results


# ---------------------------------------------------------------------------
# Main campaign
# ---------------------------------------------------------------------------

def run_campaign(dry_run: bool = False, resume_from: Optional[tuple] = None):
    """Run the full benchmark campaign."""
    state_file = Path("campaign_state.json")
    state = CampaignState.load(state_file)
    if not state.started_at:
        state.started_at = datetime.now().isoformat()

    log.info("=" * 60)
    log.info("BENCHMARK CAMPAIGN — DGX Spark")
    log.info(f"Models: {len(MODELS)}")
    log.info(f"Engines: vLLM, llama.cpp, Ollama")
    log.info(f"Suite: {SUITE}")
    log.info(f"Disk free: {free_space_gb():.1f}GB")
    log.info(f"Dry run: {dry_run}")
    if state.completed_keys:
        log.info(f"Resuming: {len(state.completed_keys)} runs already completed")
    log.info("=" * 60)

    # Process resume_from — skip models/engines until we reach the resume point
    reached_resume = resume_from is None

    for model in MODELS:
        log.info(f"\n{'#' * 50}")
        log.info(f"# MODEL: {model.name} ({model.params})")
        log.info(f"{'#' * 50}")

        # --- vLLM ---
        if not reached_resume:
            if resume_from[0] == model.name and resume_from[1] == "vllm":
                reached_resume = True
            else:
                log.info(f"Skipping vLLM {model.name} (before resume point)")
        if reached_resume:
            result = run_vllm_benchmark(model, state, dry_run)
            if result:
                state.add(result)
                state.save(state_file)

        # --- llama.cpp ---
        if not reached_resume:
            if resume_from[0] == model.name and resume_from[1] == "llama_cpp":
                reached_resume = True
            else:
                log.info(f"Skipping llama_cpp {model.name} (before resume point)")
        if reached_resume:
            results = run_llamacpp_benchmarks(model, state, dry_run)
            for result in results:
                state.add(result)
                state.save(state_file)

        # --- Ollama ---
        if not reached_resume:
            if resume_from[0] == model.name and resume_from[1] == "ollama":
                reached_resume = True
            else:
                log.info(f"Skipping ollama {model.name} (before resume point)")
        if reached_resume:
            results = run_ollama_benchmarks(model, state, dry_run)
            for result in results:
                state.add(result)
                state.save(state_file)

    # --- Summary ---
    log.info("\n" + "=" * 60)
    log.info("CAMPAIGN COMPLETE")
    log.info("=" * 60)

    total = len(state.results)
    succeeded = sum(1 for r in state.results if r.status == "success")
    failed = sum(1 for r in state.results if r.status == "failed")
    skipped = sum(1 for r in state.results if r.status == "skipped")

    log.info(f"Total runs: {total}")
    log.info(f"  Succeeded: {succeeded}")
    log.info(f"  Failed:    {failed}")
    log.info(f"  Skipped:   {skipped}")

    if failed > 0:
        log.info("\nFailed runs:")
        for r in state.results:
            if r.status == "failed":
                log.info(f"  {r.model} / {r.engine} / {r.quant}: {r.error}")

    total_duration = sum(r.duration_s for r in state.results)
    hours = total_duration / 3600
    log.info(f"\nTotal duration: {hours:.1f} hours")
    log.info(f"Disk free: {free_space_gb():.1f}GB")

    state.save(state_file)
    log.info(f"State saved to {state_file}")


def main():
    parser = argparse.ArgumentParser(description="Multi-model benchmark campaign")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument(
        "--resume-from",
        nargs=3,
        metavar=("MODEL", "ENGINE", "QUANT"),
        help="Resume from a specific model/engine/quant",
    )
    args = parser.parse_args()

    resume = None
    if args.resume_from:
        resume = tuple(args.resume_from)

    try:
        run_campaign(dry_run=args.dry_run, resume_from=resume)
    except KeyboardInterrupt:
        log.info("\nCampaign interrupted. State saved — resume with --resume-from.")
        sys.exit(1)


if __name__ == "__main__":
    main()
