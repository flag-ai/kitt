"""Simulated test execution for virtual test agents.

Runs in a background daemon thread, simulating realistic delays,
log streaming, status transitions, and result persistence — all
through the same pipelines real agents use.
"""

from __future__ import annotations

import logging
import random
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any

from kitt.web.services.event_bus import event_bus
from kitt.web.services.result_generator import generate_fake_result

logger = logging.getLogger(__name__)


def simulate_test_execution(
    test_id: str,
    agent_id: str,
    model_path: str,
    engine_name: str,
    benchmark_name: str,
    suite_name: str,
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    result_service: Any,
    agent: dict[str, Any],
) -> None:
    """Simulate a single quick test execution in the current thread.

    This is meant to be called from a daemon thread. It:
    1. Sleeps briefly (queue delay)
    2. Transitions status to 'running' with log streaming
    3. Generates a fake result and persists it
    4. Transitions status to 'completed'
    """
    try:
        _run_simulation(
            test_id=test_id,
            agent_id=agent_id,
            model_path=model_path,
            engine_name=engine_name,
            benchmark_name=benchmark_name,
            suite_name=suite_name,
            db_conn=db_conn,
            db_write_lock=db_write_lock,
            result_service=result_service,
            agent=agent,
        )
    except Exception:
        logger.exception("Test simulation failed for %s", test_id)
        _update_test_status(
            db_conn, db_write_lock, test_id, "failed", error="Simulation error"
        )


def _run_simulation(
    test_id: str,
    agent_id: str,
    model_path: str,
    engine_name: str,
    benchmark_name: str,
    suite_name: str,
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    result_service: Any,
    agent: dict[str, Any],
) -> None:
    """Inner simulation logic (exceptions propagate to caller)."""
    model_name = model_path.rsplit("/", 1)[-1] if "/" in model_path else model_path

    # 1. Queue delay
    time.sleep(random.uniform(1.0, 2.0))

    # 2. Transition to running
    _update_test_status(db_conn, db_write_lock, test_id, "running")

    # 3. Stream log lines with realistic delays
    log_lines = [
        "Preparing benchmark environment...",
        f"Loading model: {model_path}",
        f"Initializing engine: {engine_name}",
        f"Running {benchmark_name} benchmark...",
        f"Iteration 1/5 complete ({random.uniform(80, 180):.1f} tok/s)",
        f"Iteration 2/5 complete ({random.uniform(80, 180):.1f} tok/s)",
        f"Iteration 3/5 complete ({random.uniform(80, 180):.1f} tok/s)",
        f"Iteration 4/5 complete ({random.uniform(80, 180):.1f} tok/s)",
        f"Iteration 5/5 complete ({random.uniform(80, 180):.1f} tok/s)",
        "Benchmark complete. Saving results...",
    ]

    for line in log_lines:
        time.sleep(random.uniform(0.5, 1.5))
        _persist_log(db_conn, db_write_lock, test_id, line)

    # 4. Generate and save fake result
    result_data = generate_fake_result(
        model_path=model_path,
        engine_name=engine_name,
        benchmark_name=benchmark_name,
        suite_name=suite_name,
        agent=agent,
    )
    result_service.save_result(result_data)

    _persist_log(
        db_conn,
        db_write_lock,
        test_id,
        f"Result saved for {model_name} on {engine_name}",
    )

    # 5. Mark complete
    _update_test_status(db_conn, db_write_lock, test_id, "completed")
    logger.info("Test simulation completed: %s", test_id)


def simulate_campaign_execution(
    campaign_id: str,
    agent_id: str,
    config: dict[str, Any],
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    result_service: Any,
    campaign_service: Any,
    agent_manager: Any,
) -> None:
    """Simulate a full campaign execution in a daemon thread.

    Iterates over all model x engine combinations in the campaign config
    and runs simulate_test_execution() for each.
    """
    try:
        _run_campaign_simulation(
            campaign_id=campaign_id,
            agent_id=agent_id,
            config=config,
            db_conn=db_conn,
            db_write_lock=db_write_lock,
            result_service=result_service,
            campaign_service=campaign_service,
            agent_manager=agent_manager,
        )
    except Exception:
        logger.exception("Campaign simulation failed for %s", campaign_id)
        campaign_service.update_status(campaign_id, "failed", error="Simulation error")


def _run_campaign_simulation(
    campaign_id: str,
    agent_id: str,
    config: dict[str, Any],
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    result_service: Any,
    campaign_service: Any,
    agent_manager: Any,
) -> None:
    """Inner campaign simulation logic."""
    import uuid

    models = config.get("models", [])
    engines = config.get("engines", [])
    benchmarks = config.get("benchmarks", ["throughput"])
    suite_name = config.get("suite_name", "quick")

    agent = agent_manager.get_agent(agent_id)
    if agent is None:
        campaign_service.update_status(campaign_id, "failed", error="Agent not found")
        return

    total_runs = len(models) * len(engines) * len(benchmarks)
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
            for benchmark_name in benchmarks:
                # Check for cancellation before each run
                row = db_conn.execute(
                    "SELECT status FROM web_campaigns WHERE id = ?",
                    (campaign_id,),
                ).fetchone()
                if row and row["status"] == "cancelled":
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
                    f"[{run_index}/{total_runs}] {model_name} / {engine_name} / {benchmark_name}",
                )

                # Create a quick_test row for each combo
                test_id = uuid.uuid4().hex[:16]
                command_id = uuid.uuid4().hex[:16]
                now = datetime.now().isoformat()

                with db_write_lock:
                    db_conn.execute(
                        """INSERT INTO quick_tests
                           (id, agent_id, model_path, engine_name,
                            benchmark_name, suite_name, status,
                            command_id, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)""",
                        (
                            test_id,
                            agent_id,
                            model_path,
                            engine_name,
                            benchmark_name,
                            suite_name,
                            command_id,
                            now,
                        ),
                    )
                    db_conn.commit()

                simulate_test_execution(
                    test_id=test_id,
                    agent_id=agent_id,
                    model_path=model_path,
                    engine_name=engine_name,
                    benchmark_name=benchmark_name,
                    suite_name=suite_name,
                    db_conn=db_conn,
                    db_write_lock=db_write_lock,
                    result_service=result_service,
                    agent=agent,
                )

                # Check actual test outcome
                row = db_conn.execute(
                    "SELECT status FROM quick_tests WHERE id = ?",
                    (test_id,),
                ).fetchone()
                if row and row["status"] == "completed":
                    succeeded += 1
                    _publish_campaign_log(
                        db_conn,
                        db_write_lock,
                        campaign_id,
                        f"[{run_index}/{total_runs}] Completed successfully",
                    )
                else:
                    failed += 1
                    _publish_campaign_log(
                        db_conn,
                        db_write_lock,
                        campaign_id,
                        f"[{run_index}/{total_runs}] Failed",
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
        "Campaign simulation completed: %s (%d succeeded, %d failed)",
        campaign_id,
        succeeded,
        failed,
    )


def spawn_test_simulation(
    test_id: str,
    agent_id: str,
    model_path: str,
    engine_name: str,
    benchmark_name: str,
    suite_name: str,
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    result_service: Any,
    agent: dict[str, Any],
) -> None:
    """Spawn a daemon thread to simulate a quick test."""
    t = threading.Thread(
        target=simulate_test_execution,
        kwargs={
            "test_id": test_id,
            "agent_id": agent_id,
            "model_path": model_path,
            "engine_name": engine_name,
            "benchmark_name": benchmark_name,
            "suite_name": suite_name,
            "db_conn": db_conn,
            "db_write_lock": db_write_lock,
            "result_service": result_service,
            "agent": agent,
        },
        daemon=True,
        name=f"test-sim-{test_id}",
    )
    t.start()


def spawn_campaign_simulation(
    campaign_id: str,
    agent_id: str,
    config: dict[str, Any],
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    result_service: Any,
    campaign_service: Any,
    agent_manager: Any,
) -> None:
    """Spawn a daemon thread to simulate a campaign."""
    t = threading.Thread(
        target=simulate_campaign_execution,
        kwargs={
            "campaign_id": campaign_id,
            "agent_id": agent_id,
            "config": config,
            "db_conn": db_conn,
            "db_write_lock": db_write_lock,
            "result_service": result_service,
            "campaign_service": campaign_service,
            "agent_manager": agent_manager,
        },
        daemon=True,
        name=f"campaign-sim-{campaign_id}",
    )
    t.start()


# --- Helpers ---


def _publish_campaign_log(
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    campaign_id: str,
    line: str,
) -> None:
    """Persist a campaign log line to the database and publish to SSE."""
    with db_write_lock:
        db_conn.execute(
            "INSERT INTO campaign_logs (campaign_id, line) VALUES (?, ?)",
            (campaign_id, line),
        )
        db_conn.commit()

    event_bus.publish("log", campaign_id, {"line": line, "campaign_id": campaign_id})


def _update_test_status(
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    test_id: str,
    status: str,
    error: str = "",
) -> None:
    """Update quick_test status and publish SSE event."""
    now = datetime.now().isoformat()
    with db_write_lock:
        if status == "running":
            db_conn.execute(
                "UPDATE quick_tests SET status = ?, started_at = ? WHERE id = ?",
                (status, now, test_id),
            )
        elif status in ("completed", "failed"):
            db_conn.execute(
                "UPDATE quick_tests SET status = ?, completed_at = ?, error = ? WHERE id = ?",
                (status, now, error, test_id),
            )
        else:
            db_conn.execute(
                "UPDATE quick_tests SET status = ? WHERE id = ?",
                (status, test_id),
            )
        db_conn.commit()

    event_bus.publish("status", test_id, {"status": status, "test_id": test_id})


def _persist_log(
    db_conn: sqlite3.Connection,
    db_write_lock: threading.Lock,
    test_id: str,
    line: str,
) -> None:
    """Persist a log line to the database and publish to SSE."""
    with db_write_lock:
        db_conn.execute(
            "INSERT INTO quick_test_logs (test_id, line) VALUES (?, ?)",
            (test_id, line),
        )
        db_conn.commit()

    event_bus.publish("log", test_id, {"line": line, "test_id": test_id})
