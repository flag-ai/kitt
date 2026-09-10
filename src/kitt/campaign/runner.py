"""Campaign runner — core orchestration engine."""

import logging
import subprocess
import threading
import time
from datetime import datetime

from .gguf_discovery import (
    discover_gguf_quants,
    discover_ollama_tags,
    filter_quants,
    find_model_path,
)
from .metrics_exporter import CampaignMetricsExporter
from .models import CampaignConfig, CampaignRunSpec
from .notifications import NotificationDispatcher
from .result import CampaignResult, CampaignRunResult
from .scheduler import CampaignScheduler, estimate_quant_size_gb, parse_params
from .state_manager import CampaignState, CampaignStateManager, RunState

logger = logging.getLogger(__name__)


def _run_subprocess_with_heartbeat(
    args: list[str],
    timeout: int,
    label: str,
    heartbeat_interval: int = 300,
) -> subprocess.CompletedProcess:
    """Run a subprocess with periodic heartbeat logging."""
    stop_event = threading.Event()

    def _heartbeat():
        elapsed = 0
        while not stop_event.wait(heartbeat_interval):
            elapsed += heartbeat_interval
            logger.info(
                f"[heartbeat] {label} still running ({elapsed}s / {timeout}s timeout)"
            )

    monitor = threading.Thread(target=_heartbeat, daemon=True)
    monitor.start()
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result
    finally:
        stop_event.set()
        monitor.join(timeout=5)


class CampaignRunner:
    """Orchestrate a multi-model benchmark campaign.

    Main loop:
    1. Plan runs from campaign config
    2. Expand discovery placeholders (GGUF quants, Ollama tags)
    3. For each run: download → init engine → run suite → save → cleanup
    4. Per-run error isolation — one failure doesn't stop the campaign
    5. Resume support — skip completed runs
    """

    def __init__(
        self,
        config: CampaignConfig,
        state_manager: CampaignStateManager | None = None,
        dry_run: bool = False,
        metrics_exporter: CampaignMetricsExporter | None = None,
    ) -> None:
        self.config = config
        self.state_manager = state_manager or CampaignStateManager()
        self.dry_run = dry_run
        self.scheduler = CampaignScheduler(config.disk, config.resource_limits)
        self.notifier = NotificationDispatcher(config.notifications)
        self.metrics_exporter = metrics_exporter

    def run(
        self,
        campaign_id: str | None = None,
        resume: bool = False,
    ) -> CampaignResult:
        """Execute the campaign.

        Args:
            campaign_id: Unique identifier. Generated if not provided.
            resume: If True, load existing state and skip completed runs.

        Returns:
            CampaignResult with all run outcomes.
        """
        campaign_id = campaign_id or self._generate_id()

        # Load or create state
        state: CampaignState | None = None
        if resume:
            state = self.state_manager.load(campaign_id)

        if state is None:
            state = self.state_manager.create(campaign_id, self.config.campaign_name)

        # Plan and expand runs
        planned = self.scheduler.plan_runs(self.config)
        expanded = self._expand_runs(planned)

        # Register all runs in state
        self._register_runs(state, expanded)
        self.state_manager.save(state)

        # Filter out completed runs
        remaining = [
            r for r in expanded if not self.state_manager.is_run_done(state, r.key)
        ]

        logger.info(
            f"Campaign '{self.config.campaign_name}' — "
            f"{len(expanded)} total runs, {len(remaining)} remaining"
        )

        # Execute
        result = CampaignResult(
            campaign_id=campaign_id,
            campaign_name=self.config.campaign_name,
            started_at=state.started_at,
        )

        for run_spec in remaining:
            run_result = self._execute_run(run_spec, state)
            result.runs.append(run_result)

            # Update metrics exporter
            if self.metrics_exporter:
                self.metrics_exporter.update_campaign_progress(
                    total_runs=len(expanded),
                    completed=result.succeeded + result.failed + result.skipped,
                    succeeded=result.succeeded,
                    failed=result.failed,
                    skipped=result.skipped,
                    duration_s=result.total_duration_s,
                )

            if run_result.status == "failed":
                self.notifier.notify_failure(
                    self.config.campaign_name,
                    run_spec.key,
                    run_result.error,
                )

        # Finalize
        state.status = "completed"
        state.completed_at = datetime.now().isoformat()
        self.state_manager.save(state)

        result.completed_at = state.completed_at

        summary = (
            f"Total: {result.total}, "
            f"Succeeded: {result.succeeded}, "
            f"Failed: {result.failed}, "
            f"Skipped: {result.skipped}, "
            f"Duration: {result.total_duration_s / 3600:.1f}h"
        )
        logger.info(f"Campaign complete: {summary}")
        self.notifier.notify_complete(self.config.campaign_name, summary)

        return result

    def _execute_run(
        self,
        run_spec: CampaignRunSpec,
        state: CampaignState,
    ) -> CampaignRunResult:
        """Execute a single benchmark run with error isolation."""
        logger.info(f"Starting: {run_spec.key}")

        # Check size limit first
        if self.scheduler.should_skip_for_size(run_spec):
            skip_reason = (
                f"Estimated size {run_spec.estimated_size_gb:.1f}GB exceeds "
                f"limit of {self.scheduler.resource_limits.max_model_size_gb:.1f}GB"
            )
            self.state_manager.update_run(
                state, run_spec.key, "skipped", error=skip_reason
            )
            return CampaignRunResult(
                model_name=run_spec.model_name,
                engine_name=run_spec.engine_name,
                quant=run_spec.quant,
                status="skipped",
                error=skip_reason,
            )

        # Check disk space
        if not self.scheduler.check_disk_space(
            run_spec, self.scheduler.disk_config.storage_path
        ):
            self.state_manager.update_run(
                state, run_spec.key, "skipped", error="Insufficient disk space"
            )
            return CampaignRunResult(
                model_name=run_spec.model_name,
                engine_name=run_spec.engine_name,
                quant=run_spec.quant,
                status="skipped",
                error="Insufficient disk space",
            )

        # Check gated model access (skip in dry-run mode)
        if (
            not self.dry_run
            and self.config.skip_gated
            and run_spec.repo_id
            and run_spec.engine_name != "ollama"
        ):
            try:
                from .gated_model_checker import GatedModelChecker

                checker = GatedModelChecker(hf_token=self.config.hf_token)
                if checker.is_gated(run_spec.repo_id):
                    skip_reason = (
                        f"Model {run_spec.repo_id} is gated (requires access approval)"
                    )
                    logger.info(f"Skipping gated model: {run_spec.key}")
                    self.state_manager.update_run(
                        state, run_spec.key, "skipped", error=skip_reason
                    )
                    return CampaignRunResult(
                        model_name=run_spec.model_name,
                        engine_name=run_spec.engine_name,
                        quant=run_spec.quant,
                        status="skipped",
                        error=skip_reason,
                    )
            except Exception as e:
                logger.debug(f"Gated model check failed: {e}")

        self.state_manager.update_run(state, run_spec.key, "running")
        start_time = time.time()

        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would run: {run_spec.key}")
                duration = 0.0
                output_dir = "dry-run"
            else:
                # Download model if needed
                model_path = self._download_model(run_spec)
                if not model_path:
                    raise RuntimeError("Model path not found after download")

                # Run benchmark via kitt CLI
                output_dir = self._run_benchmark(
                    model_path, run_spec.engine_name, run_spec.suite
                )
                duration = time.time() - start_time

                # Cleanup model
                if self.config.disk.cleanup_after_run and run_spec.repo_id:
                    self._cleanup_model(run_spec.repo_id)

            self.state_manager.update_run(
                state,
                run_spec.key,
                "success",
                duration_s=duration,
                output_dir=output_dir,
            )

            return CampaignRunResult(
                model_name=run_spec.model_name,
                engine_name=run_spec.engine_name,
                quant=run_spec.quant,
                status="success",
                duration_s=duration,
                output_dir=output_dir,
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Run failed: {run_spec.key}: {error_msg}")

            self.state_manager.update_run(
                state,
                run_spec.key,
                "failed",
                duration_s=duration,
                error=error_msg,
            )

            # Clean up Docker containers
            self._cleanup_docker()

            # Try to clean up model
            if run_spec.repo_id:
                self._cleanup_model(run_spec.repo_id)

            return CampaignRunResult(
                model_name=run_spec.model_name,
                engine_name=run_spec.engine_name,
                quant=run_spec.quant,
                status="failed",
                duration_s=duration,
                error=error_msg,
            )

    def _expand_runs(self, planned: list[CampaignRunSpec]) -> list[CampaignRunSpec]:
        """Expand discovery placeholders into concrete runs.

        Sets estimated_size_gb on each expanded run based on the quant
        name and model parameter count for size-based skip rules.
        """
        expanded: list[CampaignRunSpec] = []

        # Build a lookup from model name to params string
        model_params: dict[str, str] = {m.name: m.params for m in self.config.models}

        for run in planned:
            params_b = parse_params(model_params.get(run.model_name, ""))

            if run.quant == "__discover_gguf__" and run.repo_id:
                quants = discover_gguf_quants(run.repo_id)
                quants = filter_quants(
                    quants,
                    skip_patterns=self.config.quant_filter.skip_patterns,
                    include_only=self.config.quant_filter.include_only or None,
                )
                for q in quants:
                    est_size = estimate_quant_size_gb(params_b, q.quant_name)
                    expanded.append(
                        CampaignRunSpec(
                            model_name=run.model_name,
                            engine_name=run.engine_name,
                            quant=q.quant_name,
                            repo_id=run.repo_id,
                            include_pattern=q.include_pattern,
                            estimated_size_gb=est_size or run.estimated_size_gb,
                            suite=run.suite,
                            engine_config=run.engine_config,
                        )
                    )

            elif run.quant == "__discover_ollama__" and run.repo_id:
                tags = discover_ollama_tags(run.repo_id)
                for tag in tags:
                    quant = tag.split(":")[-1] if ":" in tag else tag
                    est_size = estimate_quant_size_gb(params_b, quant)
                    expanded.append(
                        CampaignRunSpec(
                            model_name=run.model_name,
                            engine_name=run.engine_name,
                            quant=quant,
                            repo_id=tag,
                            estimated_size_gb=est_size or run.estimated_size_gb,
                            suite=run.suite,
                            engine_config=run.engine_config,
                        )
                    )

            else:
                # For non-discovery runs (e.g. vllm bf16), estimate size
                if run.estimated_size_gb <= 0 and params_b > 0:
                    est_size = estimate_quant_size_gb(params_b, run.quant)
                    if est_size > 0:
                        run = run.model_copy(update={"estimated_size_gb": est_size})
                expanded.append(run)

        return expanded

    def _register_runs(self, state: CampaignState, runs: list[CampaignRunSpec]) -> None:
        """Register all planned runs in state (skipping already-registered)."""
        existing_keys = {r.key for r in state.runs}
        for run in runs:
            if run.key not in existing_keys:
                state.runs.append(
                    RunState(
                        model_name=run.model_name,
                        engine_name=run.engine_name,
                        quant=run.quant,
                        status="pending",
                    )
                )

    def _download_model(self, run_spec: CampaignRunSpec) -> str | None:
        """Download model via Devon or return path for Ollama.

        Resolution order:
        1. Remote Devon (HTTP) — when devon_url is configured
        2. Local DevonBridge — when Devon is installed as a Python package
        3. Devon CLI — subprocess fallback
        """
        if run_spec.engine_name == "ollama":
            return run_spec.repo_id  # Ollama pulls inside container

        if not run_spec.repo_id:
            return run_spec.model_path

        # 1. Try remote Devon client
        if self.config.devon_url and self.config.devon_managed:
            try:
                from kitt.devon import DevonConnectionConfig, RemoteDevonClient

                remote_config = DevonConnectionConfig(
                    url=self.config.devon_url,
                    api_key=self.config.devon_api_key,
                )
                client = RemoteDevonClient(remote_config)
                patterns = None
                if run_spec.include_pattern:
                    patterns = [run_spec.include_pattern]
                path = client.download(run_spec.repo_id, allow_patterns=patterns)
                logger.info(f"Downloaded {run_spec.repo_id} via remote Devon: {path}")
                return str(path)
            except ImportError:
                logger.debug("httpx not available, skipping remote Devon")
            except Exception as e:
                logger.warning(f"Remote Devon download failed: {e}")

        # 2. Try local DevonBridge
        try:
            from .devon_bridge import DevonBridge, is_devon_available

            if is_devon_available() and self.config.devon_managed:
                bridge = DevonBridge()
                patterns = None
                if run_spec.include_pattern:
                    patterns = [run_spec.include_pattern]
                path = bridge.download(run_spec.repo_id, allow_patterns=patterns)

                # For GGUF files, find the specific file
                if run_spec.engine_name in ("llama_cpp", "exllamav2"):
                    gguf_path = find_model_path(
                        run_spec.repo_id,
                        run_spec.include_pattern,
                        storage_root=bridge.storage_root,
                    )
                    return gguf_path
                return str(path)
        except ImportError:
            pass

        # 3. Fallback: use Devon CLI via subprocess
        return self._download_via_cli(run_spec)

    def _download_via_cli(self, run_spec: CampaignRunSpec) -> str | None:
        """Download model using Devon CLI as fallback."""
        if not run_spec.repo_id:
            raise RuntimeError("Cannot download: repo_id is not set")
        args: list[str] = ["devon", "download", run_spec.repo_id, "-y"]
        if run_spec.include_pattern:
            args.extend(["--include", run_spec.include_pattern])

        result = _run_subprocess_with_heartbeat(
            args, timeout=7200, label="devon download"
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            error_detail = stderr[-500:] if stderr else stdout[-500:]
            if not error_detail:
                error_detail = f"Process exited with code {result.returncode}"
            raise RuntimeError(f"Devon download failed: {error_detail}")

        return find_model_path(run_spec.repo_id, run_spec.include_pattern)  # type: ignore[arg-type]

    def _run_benchmark(self, model_path: str, engine: str, suite: str) -> str:
        """Run a KITT benchmark and return the output directory."""
        args = ["kitt", "run", "-m", model_path, "-e", engine, "-s", suite]
        logger.info(f"Running: {' '.join(args)}")

        result = _run_subprocess_with_heartbeat(args, timeout=14400, label="kitt run")

        output_dir = ""
        for line in (result.stdout or "").splitlines():
            if "kitt-results" in line.lower():
                for word in line.split():
                    if "kitt-results" in word:
                        output_dir = word.strip()
                        break

        if result.returncode != 0:
            # Capture both stderr and stdout for diagnostics
            stderr = (result.stderr or "").strip()
            stdout_tail = (result.stdout or "").strip()[-500:] if result.stdout else ""
            error_detail = stderr[-500:] if stderr else stdout_tail
            if not error_detail:
                error_detail = (
                    f"Process exited with code {result.returncode} (no output captured)"
                )
            raise RuntimeError(
                f"kitt run failed (exit {result.returncode}): {error_detail}"
            )

        return output_dir

    def _cleanup_model(self, repo_id: str) -> None:
        """Remove a downloaded model.

        Resolution order mirrors _download_model:
        1. Remote Devon (HTTP) → 2. Local DevonBridge → 3. CLI fallback
        """
        # 1. Try remote Devon client
        if self.config.devon_url and self.config.devon_managed:
            try:
                from kitt.devon import DevonConnectionConfig, RemoteDevonClient

                remote_config = DevonConnectionConfig(
                    url=self.config.devon_url,
                    api_key=self.config.devon_api_key,
                )
                client = RemoteDevonClient(remote_config)
                client.remove(repo_id)
                return
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Failed to clean up model via remote Devon: {e}")

        # 2. Try local DevonBridge
        try:
            from .devon_bridge import DevonBridge, is_devon_available

            if is_devon_available() and self.config.devon_managed:
                bridge = DevonBridge()
                bridge.remove(repo_id)
                return
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to clean up model via Devon bridge: {e}")

        # 3. Fallback: CLI
        try:
            subprocess.run(
                ["devon", "remove", repo_id, "-y"],
                capture_output=True,
                timeout=60,
            )
        except Exception as e:
            logger.warning(f"Failed to clean up model via CLI: {e}")

    def _cleanup_docker(self) -> None:
        """Clean up leftover kitt Docker containers."""
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    "name=kitt-",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            containers = [c.strip() for c in result.stdout.splitlines() if c.strip()]
            if containers:
                subprocess.run(
                    ["docker", "rm", "-f"] + containers,
                    capture_output=True,
                    timeout=30,
                )
        except Exception:
            pass

    def _generate_id(self) -> str:
        """Generate a campaign ID from name and timestamp."""
        name_slug = self.config.campaign_name.lower().replace(" ", "-")[:20]
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{name_slug}-{ts}"
