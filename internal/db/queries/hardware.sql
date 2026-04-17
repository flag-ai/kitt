-- Seed query set — exercises sqlc codegen so the repo stays buildable
-- before domain queries arrive in later PRs. Replace/extend these as
-- the storage layer grows.

-- name: GetHardwareByFingerprint :one
SELECT id, fingerprint, gpu, cpu, ram_gb, storage, cuda_version,
       driver_version, os, environment, details, created_at
FROM hardware
WHERE fingerprint = $1;

-- name: ListHardware :many
SELECT id, fingerprint, gpu, cpu, ram_gb, storage, cuda_version,
       driver_version, os, environment, details, created_at
FROM hardware
ORDER BY created_at DESC;

-- name: CreateHardware :one
INSERT INTO hardware (
    fingerprint, gpu, cpu, ram_gb, storage, cuda_version,
    driver_version, os, environment, details
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
)
RETURNING id, fingerprint, gpu, cpu, ram_gb, storage, cuda_version,
          driver_version, os, environment, details, created_at;
