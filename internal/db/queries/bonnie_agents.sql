-- name: ListBonnieAgents :many
SELECT * FROM kitt_bonnie_agents ORDER BY name;

-- name: GetBonnieAgent :one
SELECT * FROM kitt_bonnie_agents WHERE id = $1;

-- name: GetBonnieAgentByName :one
SELECT * FROM kitt_bonnie_agents WHERE name = $1;

-- name: CreateBonnieAgent :one
INSERT INTO kitt_bonnie_agents (name, url, token, status)
VALUES ($1, $2, $3, $4)
RETURNING *;

-- name: UpdateBonnieAgent :one
UPDATE kitt_bonnie_agents
SET name = $2, url = $3, token = $4, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeleteBonnieAgent :exec
DELETE FROM kitt_bonnie_agents WHERE id = $1;

-- name: UpdateBonnieAgentStatus :exec
UPDATE kitt_bonnie_agents
SET status = $2, last_seen_at = $3, updated_at = now()
WHERE id = $1;
