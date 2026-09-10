"""Campaign executor for real agents.

Breaks a campaign config into individual quick_test rows and queues
them one at a time so the heartbeat mechanism dispatches them to the
agent. Polls for completion between runs and tracks overall progress.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from kitt.web.services.event_bus import event_bus

logger = logging.getLogger(__name__)

# How often to poll for test completion (seconds).
_POLL_INTERVAL = 5
# Maximum time to wait for a single test to finish (seconds).
_TEST_TIMEOUT = 1800  # 30 minutes


def execute_campaign(
    campaign_id: str,
    agent_id: str,
    config: dict[str, Any],
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    campaign_service: Any,
) -> None:
    """Execute a campaign on a real agent in a daemon thread.

    Creates quick_test rows one at a time and waits for the agent to
    complete each before queuing the next.
    """
    try:
        _run_campaign(
            campaign_id=campaign_id,
            agent_id=agent_id,
            config=config,
            db_conn=db_conn,
            db_write_lock=db_write_lock,
            campaign_service=campaign_service,
        )
    except Exception:
        logger.exception("Campaign execution failed for %s", campaign_id)
        _publish_campaign_log(
            db_conn, db_write_lock, campaign_id, "Campaign failed: unexpected error"
        )
        campaign_service.update_status(
            campaign_id, "failed", error="Unexpected error during campaign execution"
        )


def _run_campaign(
    campaign_id: str,
    agent_id: str,
    config: dict[str, Any],
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    campaign_service: Any,
) -> None:
    """Inner campaign execution logic."""
    models = config.get("models", [])
    engines = config.get("engines", [])
    benchmarks = config.get("benchmarks", ["throughput"])
    suite_name = config.get("suite_name", "quick")

    total_runs = len(models) * len(engines) * len(benchmarks)
    if total_runs == 0:
        campaign_service.update_status(
            campaign_id, "failed", error="No test combinations in campaign config"
        )
        return

    succeeded = 0
    failed = 0

    campaign_service.update_status(campaign_id, "running", total_runs=total_runs)
    _publish_campaign_log(
        db_conn, db_write_lock, campaign_id, f"Campaign started: {total_runs} runs"
    )

    run_index = 0
    cancelled = False
    for model in models:
        model_path = model.get("path", model.get("name", "unknown"))
        model_name = model_path.rsplit("/", 1)[-1] if "/" in model_path else model_path
        for engine in engines:
            engine_name = engine.get("name", "unknown")
            engine_mode = engine.get("mode", "docker")
            profile_id = engine.get("profile_id", "")
            for benchmark_name in benchmarks:
                # Check for cancellation
                if _is_cancelled(db_conn, campaign_id):
                    _publish_campaign_log(
                        db_conn,
                        db_write_lock,
                        campaign_id,
                        "Campaign cancelled by user",
                    )
                    logger.info("Campaign %s cancelled", campaign_id)
                    cancelled = True
                    break

                run_index += 1
                _publish_campaign_log(
                    db_conn,
                    db_write_lock,
                    campaign_id,
                    f"[{run_index}/{total_runs}] Queuing: {model_name} / {engine_name} / {benchmark_name}",
                )

                # Create a quick_test row — the heartbeat will dispatch it
                test_id = uuid.uuid4().hex[:16]
                command_id = uuid.uuid4().hex[:16]
                now = datetime.now().isoformat()

                with db_write_lock:
                    db_conn.execute(
                        """INSERT INTO quick_tests
                           (id, agent_id, model_path, engine_name,
                            benchmark_name, suite_name, status,
                            command_id, engine_mode, profile_id, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                        (
                            test_id,
                            agent_id,
                            model_path,
                            engine_name,
                            benchmark_name,
                            suite_name,
                            command_id,
                            engine_mode,
                            profile_id,
                            now,
                        ),
                    )
                    db_conn.commit()

                _publish_campaign_log(
                    db_conn,
                    db_write_lock,
                    campaign_id,
                    f"[{run_index}/{total_runs}] Waiting for agent to pick up test...",
                )

                # Wait for the test to complete
                final_status = _wait_for_test(
                    db_conn, db_write_lock, campaign_id, test_id, run_index, total_runs
                )

                if final_status == "completed":
                    succeeded += 1
                    _publish_campaign_log(
                        db_conn,
                        db_write_lock,
                        campaign_id,
                        f"[{run_index}/{total_runs}] Completed successfully",
                    )
                elif final_status == "cancelled":
                    cancelled = True
                    break
                else:
                    failed += 1
                    _publish_campaign_log(
                        db_conn,
                        db_write_lock,
                        campaign_id,
                        f"[{run_index}/{total_runs}] Failed ({final_status})",
                    )
            if cancelled:
                break
        if cancelled:
            break

    if not cancelled:
        _publish_campaign_log(
            db_conn,
            db_write_lock,
            campaign_id,
            f"Campaign finished: {succeeded} succeeded, {failed} failed",
        )
        campaign_service.update_status(
            campaign_id, "completed", succeeded=succeeded, failed=failed
        )

    logger.info(
        "Campaign %s done: %d succeeded, %d failed, cancelled=%s",
        campaign_id,
        succeeded,
        failed,
        cancelled,
    )


def _wait_for_test(
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    campaign_id: str,
    test_id: str,
    run_index: int,
    total_runs: int,
) -> str:
    """Poll until a quick_test reaches a terminal status.

    Returns the final status string ('completed', 'failed', 'cancelled',
    or 'timeout').
    """
    start = time.monotonic()
    last_status = ""

    while time.monotonic() - start < _TEST_TIMEOUT:
        # Check for campaign cancellation
        if _is_cancelled(db_conn, campaign_id):
            _publish_campaign_log(
                db_conn,
                db_write_lock,
                campaign_id,
                "Campaign cancelled by user",
            )
            return "cancelled"

        row = db_conn.execute(
            "SELECT status FROM quick_tests WHERE id = ?", (test_id,)
        ).fetchone()

        if row is None:
            return "failed"

        status = row["status"]
        if status != last_status:
            if status in ("dispatched", "running"):
                _publish_campaign_log(
                    db_conn,
                    db_write_lock,
                    campaign_id,
                    f"[{run_index}/{total_runs}] Agent status: {status}",
                )
            last_status = status

        if status in ("completed", "failed"):
            return status

        time.sleep(_POLL_INTERVAL)

    # Timeout
    _publish_campaign_log(
        db_conn,
        db_write_lock,
        campaign_id,
        f"[{run_index}/{total_runs}] Timed out after {_TEST_TIMEOUT}s",
    )
    return "timeout"


def _is_cancelled(db_conn: sqlite3.Connection, campaign_id: str) -> bool:
    """Check if the campaign has been cancelled."""
    row = db_conn.execute(
        "SELECT status FROM web_campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()
    return row is not None and row["status"] == "cancelled"


def _publish_campaign_log(
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    campaign_id: str,
    line: str,
) -> None:
    """Persist a campaign log line and publish to SSE."""
    with db_write_lock:
        db_conn.execute(
            "INSERT INTO campaign_logs (campaign_id, line) VALUES (?, ?)",
            (campaign_id, line),
        )
        db_conn.commit()

    event_bus.publish("log", campaign_id, {"line": line, "campaign_id": campaign_id})


def spawn_campaign_execution(
    campaign_id: str,
    agent_id: str,
    config: dict[str, Any],
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    campaign_service: Any,
) -> None:
    """Spawn a daemon thread to execute a campaign on a real agent."""
    t = threading.Thread(
        target=execute_campaign,
        kwargs={
            "campaign_id": campaign_id,
            "agent_id": agent_id,
            "config": config,
            "db_conn": db_conn,
            "db_write_lock": db_write_lock,
            "campaign_service": campaign_service,
        },
        daemon=True,
        name=f"campaign-exec-{campaign_id}",
    )
    t.start()
