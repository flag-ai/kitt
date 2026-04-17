-- name: ListEngineProfiles :many
SELECT * FROM engine_profiles ORDER BY engine, name;

-- name: ListEngineProfilesByEngine :many
SELECT * FROM engine_profiles WHERE engine = $1 ORDER BY name;

-- name: GetEngineProfile :one
SELECT * FROM engine_profiles WHERE id = $1;

-- name: CreateEngineProfile :one
INSERT INTO engine_profiles (
    name, engine, description, build_config, runtime_config, is_default
) VALUES (
    $1, $2, $3, $4, $5, $6
)
RETURNING *;

-- name: UpdateEngineProfile :one
UPDATE engine_profiles
SET name = $2, description = $3, build_config = $4,
    runtime_config = $5, is_default = $6, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeleteEngineProfile :exec
DELETE FROM engine_profiles WHERE id = $1;
