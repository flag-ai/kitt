"""Parallel campaign runner — overlaps download and benchmark execution."""

import logging
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from .models import CampaignConfig, CampaignRunSpec
from .result import CampaignResult, CampaignRunResult
from .runner import CampaignRunner
from .state_manager import CampaignState, CampaignStateManager

logger = logging.getLogger(__name__)


class ParallelCampaignRunner:
    """Campaign runner that overlaps model downloads with benchmark execution.

    Uses two worker pools:
    - benchmark_worker: executes benchmarks (GPU-bound, 1 at a time)
    - download_worker: pre-downloads next model (network-bound)

    This allows downloading the next model while the current benchmark runs,
    reducing total campaign time.
    """

    def __init__(
        self,
        config: CampaignConfig,
        state_manager: CampaignStateManager | None = None,
        dry_run: bool = False,
        max_download_workers: int = 1,
    ) -> None:
        self.config = config
        self.state_manager = state_manager or CampaignStateManager()
        self.dry_run = dry_run
        self.max_download_workers = max_download_workers

        # Delegate single-run execution to CampaignRunner
        self._runner = CampaignRunner(
            config=config,
            state_manager=state_manager,
            dry_run=dry_run,
        )

        # Thread safety
        self._state_lock = Lock()
        self._download_cache: dict = {}  # key -> model_path

    def run(
        self,
        campaign_id: str | None = None,
        resume: bool = False,
    ) -> CampaignResult:
        """Execute the campaign with parallel download/benchmark overlap."""
        campaign_id = campaign_id or self._runner._generate_id()

        # Load or create state
        state: CampaignState | None = None
        if resume:
            state = self.state_manager.load(campaign_id)

        if state is None:
            state = self.state_manager.create(campaign_id, self.config.campaign_name)

        # Plan and expand
        planned = self._runner.scheduler.plan_runs(self.config)
        expanded = self._runner._expand_runs(planned)
        self._runner._register_runs(state, expanded)
        self.state_manager.save(state)

        remaining = [
            r for r in expanded if not self.state_manager.is_run_done(state, r.key)
        ]

        logger.info(
            f"Parallel campaign '{self.config.campaign_name}' — "
            f"{len(expanded)} total, {len(remaining)} remaining"
        )

        result = CampaignResult(
            campaign_id=campaign_id,
            campaign_name=self.config.campaign_name,
            started_at=state.started_at,
        )

        # Execute with download prefetch
        with ThreadPoolExecutor(
            max_workers=self.max_download_workers,
            thread_name_prefix="kitt-download",
        ) as download_pool:
            # Submit first download
            pending_download: Future | None = None
            if len(remaining) > 0:
                pending_download = download_pool.submit(
                    self._safe_download, remaining[0]
                )

            for i, run_spec in enumerate(remaining):
                # Check disk space
                if not self._check_disk_space():
                    logger.warning("Disk space low — pausing downloads")

                # Wait for current download
                if pending_download is not None:
                    model_path = pending_download.result(timeout=7200)
                    if model_path:
                        self._download_cache[run_spec.key] = model_path

                # Start prefetching next model
                if i + 1 < len(remaining):
                    next_spec = remaining[i + 1]
                    pending_download = download_pool.submit(
                        self._safe_download, next_spec
                    )
                else:
                    pending_download = None

                # Execute benchmark (sequential — GPU bound)
                run_result = self._execute_with_cached_download(run_spec, state)
                result.runs.append(run_result)

                # Update metrics exporter if present
                if self._runner.metrics_exporter:
                    self._runner.metrics_exporter.update_campaign_progress(
                        total_runs=len(expanded),
                        completed=result.succeeded + result.failed + result.skipped,
                        succeeded=result.succeeded,
                        failed=result.failed,
                        skipped=result.skipped,
                        duration_s=result.total_duration_s,
                    )

                if run_result.status == "failed":
                    self._runner.notifier.notify_failure(
                        self.config.campaign_name,
                        run_spec.key,
                        run_result.error,
                    )

        # Finalize
        from datetime import datetime

        with self._state_lock:
            state.status = "completed"
            state.completed_at = datetime.now().isoformat()
            self.state_manager.save(state)

        result.completed_at = state.completed_at
        summary = (
            f"Total: {result.total}, "
            f"Succeeded: {result.succeeded}, "
            f"Failed: {result.failed}, "
            f"Skipped: {result.skipped}"
        )
        logger.info(f"Parallel campaign complete: {summary}")
        self._runner.notifier.notify_complete(self.config.campaign_name, summary)

        return result

    def _safe_download(self, run_spec: CampaignRunSpec) -> str | None:
        """Download model with error handling (runs in download thread)."""
        try:
            return self._runner._download_model(run_spec)
        except Exception as e:
            logger.error(f"Pre-download failed for {run_spec.key}: {e}")
            return None

    def _execute_with_cached_download(
        self,
        run_spec: CampaignRunSpec,
        state: CampaignState,
    ) -> CampaignRunResult:
        """Execute a run, using cached download path if available."""
        # Use the standard runner's _execute_run
        run_result = self._runner._execute_run(run_spec, state)

        # Clean up download cache
        self._download_cache.pop(run_spec.key, None)

        return run_result

    def _check_disk_space(self) -> bool:
        """Check if there's enough disk space to continue."""
        try:
            disk = shutil.disk_usage(Path.home())
            free_gb = disk.free / (1024**3)
            min_free = self.config.disk.reserve_gb if self.config.disk else 20
            return free_gb >= min_free
        except Exception:
            return True  # Assume OK if we can't check
