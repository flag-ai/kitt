-- name: ListRuns :many
SELECT * FROM runs ORDER BY created_at DESC LIMIT $1 OFFSET $2;

-- name: ListRunsByCampaign :many
SELECT * FROM runs WHERE campaign_id = $1 ORDER BY created_at DESC;

-- name: GetRun :one
SELECT * FROM runs WHERE id = $1;

-- name: CreateRun :one
INSERT INTO runs (
    campaign_id, agent_id, hardware_id, model, engine,
    engine_profile_id, status
) VALUES (
    $1, $2, $3, $4, $5, $6, $7
)
RETURNING *;

-- name: UpdateRunStatus :one
UPDATE runs
SET status = $2, error = $3, started_at = $4, finished_at = $5,
    updated_at = now()
WHERE id = $1
RETURNING *;

-- name: ListBenchmarksForRun :many
SELECT * FROM benchmarks WHERE run_id = $1 ORDER BY benchmark;

-- name: CreateBenchmarkResult :one
INSERT INTO benchmarks (
    run_id, benchmark, status, score, duration_ms, raw_json,
    started_at, finished_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8
)
RETURNING *;

-- name: CreateMetric :one
INSERT INTO metrics (run_id, benchmark_id, name, value, unit)
VALUES ($1, $2, $3, $4, $5)
RETURNING *;

-- name: ListMetricsForRun :many
SELECT * FROM metrics WHERE run_id = $1 ORDER BY recorded_at;
