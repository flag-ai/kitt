# REST API

KITT exposes a REST API through the `kitt web` command. The API is served
by Flask and provides endpoints for managing results, agents, campaigns,
models, quick tests, and real-time event streaming.

## Base URL

```
https://<host>:<port>/api/v1/
```

Default: `https://0.0.0.0:8080/api/v1/`

TLS is enabled by default. Pass `--insecure` to disable it during
development. Pass `--legacy` for the read-only v1 dashboard which does
not require TLS.

## Authentication

Protected endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <token>
```

Set the token with `--auth-token` on the CLI or the `KITT_AUTH_TOKEN`
environment variable. Agent registration, heartbeat, and result-reporting
endpoints all require authentication.

## Endpoints

### Health and version

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | No | Health check (returns `{"status": "ok"}`) |
| GET | `/api/v1/version` | No | Version info |
| GET | `/api/health` | No | Legacy health endpoint |

### Results

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/results/` | No | List results (query: `model`, `engine`, `suite_name`, `page`, `per_page`) |
| GET | `/api/v1/results/<id>` | No | Get a single result |
| DELETE | `/api/v1/results/<id>` | Yes | Delete a result |
| GET | `/api/v1/results/aggregate` | Yes | Aggregate results (query: `group_by`, `metric`) |
| POST | `/api/v1/results/compare` | Yes | Compare results (body: `{"ids": [...]}`) |

### Agents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/agents/` | No | List all agents |
| GET | `/api/v1/agents/<id>` | No | Get agent details |
| POST | `/api/v1/agents/register` | Yes | Register a new agent |
| POST | `/api/v1/agents/<id>/heartbeat` | Yes | Agent heartbeat (response includes `settings`) |
| POST | `/api/v1/agents/<id>/results` | Yes | Report benchmark result |
| PATCH | `/api/v1/agents/<id>` | Yes | Update agent fields |
| DELETE | `/api/v1/agents/<id>` | Yes | Remove an agent |
| GET | `/api/v1/agents/<id>/settings` | Yes | Get agent settings |
| PUT | `/api/v1/agents/<id>/settings` | Yes | Update agent settings (body: `{"key": "value", ...}`) |
| POST | `/api/v1/agents/<id>/cleanup` | Yes | Queue storage cleanup command |
| GET | `/api/v1/agent/install.sh` | No | Agent bootstrap install script |
| GET | `/api/v1/agent/package` | No | Agent package tarball |
| GET | `/api/v1/agent/package/sha256` | No | SHA-256 of agent package |
| GET | `/api/v1/agent/build-context` | No | Docker build context tarball |
| GET | `/api/v1/agent/build-context/sha256` | No | SHA-256 of build context |

### Campaigns

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/campaigns/` | No | List campaigns (query: `status`, `page`, `per_page`) |
| POST | `/api/v1/campaigns/` | Yes | Create a campaign |
| GET | `/api/v1/campaigns/<id>` | No | Get campaign details |
| DELETE | `/api/v1/campaigns/<id>` | Yes | Delete a campaign |
| POST | `/api/v1/campaigns/<id>/launch` | Yes | Launch a campaign |
| POST | `/api/v1/campaigns/<id>/cancel` | Yes | Cancel a running campaign |
| PUT | `/api/v1/campaigns/<id>/config` | Yes | Update campaign config (draft only) |
| GET | `/api/v1/campaigns/<id>/logs` | No | Get stored log lines for a campaign |

### Models

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/models/search` | No | Search models via Devon (query: `q`, `limit`) |
| GET | `/api/v1/models/local` | No | List locally available models |
| POST | `/api/v1/models/download` | Yes | Download a model (body: `{"repo_id": "..."}`) |
| DELETE | `/api/v1/models/<repo_id>` | Yes | Remove a local model |

### Quick tests

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/quicktest/models` | No | List available models from Devon manifest |
| GET | `/api/v1/quicktest/agent-capabilities` | No | Get per-engine compatibility for an agent (query: `agent_id`) |
| GET | `/api/v1/quicktest/` | No | List quick tests (query: `status`, `agent_name`, `page`, `per_page`) |
| POST | `/api/v1/quicktest/` | Yes | Launch a quick test (body: `agent_id`, `model_path`, `engine_name`) |
| GET | `/api/v1/quicktest/<id>` | No | Get quick test status |
| GET | `/api/v1/quicktest/<id>/logs` | No | Get stored log lines for a test |
| POST | `/api/v1/quicktest/<id>/logs` | Yes | Post a log line from the agent (body: `line`) |
| POST | `/api/v1/quicktest/<id>/status` | Yes | Update test status (body: `status`: `running`/`completed`/`failed`) |

### Events (SSE)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/events/stream` | No | Global SSE event stream |
| GET | `/api/v1/events/stream/<source_id>` | No | Filtered SSE stream by source |

## Response format

All endpoints return JSON. List endpoints support pagination with `page`
and `per_page` query parameters and return results in an envelope:

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "per_page": 25
}
```

Error responses use a standard structure:

```json
{
  "error": "Description of the problem"
}
```

HTTP status codes follow REST conventions: 200 for success, 201 for
created, 202 for accepted (async), 400 for bad request, 401 for
unauthorized, 403 for forbidden, 404 for not found.
