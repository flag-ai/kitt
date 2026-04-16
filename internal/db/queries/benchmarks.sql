-- name: ListBenchmarkRegistry :many
SELECT * FROM benchmark_registry ORDER BY category, name;

-- name: ListBenchmarkRegistryByKind :many
SELECT * FROM benchmark_registry WHERE kind = $1 ORDER BY name;

-- name: GetBenchmarkRegistry :one
SELECT * FROM benchmark_registry WHERE id = $1;

-- name: GetBenchmarkRegistryByName :one
SELECT * FROM benchmark_registry WHERE name = $1;

-- name: CreateBenchmarkRegistry :one
INSERT INTO benchmark_registry (
    name, kind, category, description, source, config, enabled
) VALUES (
    $1, $2, $3, $4, $5, $6, $7
)
RETURNING *;

-- name: UpdateBenchmarkRegistry :one
UPDATE benchmark_registry
SET kind = $2, category = $3, description = $4, source = $5,
    config = $6, enabled = $7, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeleteBenchmarkRegistry :exec
DELETE FROM benchmark_registry WHERE id = $1;
