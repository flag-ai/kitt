-- name: ListCampaigns :many
SELECT * FROM campaigns ORDER BY name;

-- name: GetCampaign :one
SELECT * FROM campaigns WHERE id = $1;

-- name: GetCampaignByName :one
SELECT * FROM campaigns WHERE name = $1;

-- name: CreateCampaign :one
INSERT INTO campaigns (name, description, config, cron_expr, enabled)
VALUES ($1, $2, $3, $4, $5)
RETURNING *;

-- name: UpdateCampaign :one
UPDATE campaigns
SET description = $2, config = $3, cron_expr = $4, enabled = $5,
    updated_at = now()
WHERE id = $1
RETURNING *;

-- name: UpdateCampaignSchedule :one
UPDATE campaigns
SET cron_expr = $2, enabled = $3, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeleteCampaign :exec
DELETE FROM campaigns WHERE id = $1;

-- name: CountCampaignRuns :one
SELECT COUNT(*) FROM campaign_runs WHERE campaign_id = $1;

-- name: ListCampaignRuns :many
SELECT campaign_id, run_id, scheduled_at
FROM campaign_runs
WHERE campaign_id = $1
ORDER BY scheduled_at DESC;
