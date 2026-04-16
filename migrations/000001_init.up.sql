-- KITT 2.0 initial schema.
--
-- KITT 2.0 starts fresh — 1.x data is not migrated. Operators who need
-- historical results must keep their old database or export JSON with
-- the 1.x CLI before upgrading.

-- =============================================================================
-- BONNIE agent registry (KITT-scoped)
-- =============================================================================
-- Mirrors the shape of karr_agents so the shared flag-commons BONNIE
-- client package can back its registry with a KITT-owned store. The
-- kitt_ prefix keeps the table from colliding if KITT and KARR ever
-- share a database.
CREATE TABLE kitt_bonnie_agents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    url          TEXT NOT NULL,
    token        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'offline',
    last_seen_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Hardware fingerprints
-- =============================================================================
-- Each BONNIE agent reports its hardware once; subsequent runs reference
-- the fingerprint so results remain comparable across days. fingerprint
-- is a compact stable string (e.g. rtx4090-24gb_i9-13900k-24c_...).
CREATE TABLE hardware (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint     TEXT NOT NULL UNIQUE,
    gpu             TEXT NOT NULL DEFAULT '',
    cpu             TEXT NOT NULL DEFAULT '',
    ram_gb          INTEGER NOT NULL DEFAULT 0,
    storage         TEXT NOT NULL DEFAULT '',
    cuda_version    TEXT NOT NULL DEFAULT '',
    driver_version  TEXT NOT NULL DEFAULT '',
    os              TEXT NOT NULL DEFAULT '',
    environment     TEXT NOT NULL DEFAULT '',
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX hardware_environment_idx ON hardware (environment);

-- =============================================================================
-- Engine profiles
-- =============================================================================
-- Named build + runtime configurations for each inference engine. Used
-- by quicktests, campaigns, and agent commands to pick a consistent
-- engine setup.
CREATE TABLE engine_profiles (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL,
    engine         TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    build_config   JSONB NOT NULL DEFAULT '{}'::jsonb,
    runtime_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_default     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (engine, name)
);

CREATE INDEX engine_profiles_engine_idx ON engine_profiles (engine);

-- =============================================================================
-- Benchmark registry
-- =============================================================================
-- KITT 2.0 supports hybrid benchmarks: some are declarative YAML
-- (prompts + grading rules) loaded at boot, others are containerized
-- harnesses published from benchmarks-reference/. Both kinds are
-- recorded here with their resolved config so a run is reproducible.
CREATE TABLE benchmark_registry (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    category    TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT '',
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX benchmark_registry_kind_idx ON benchmark_registry (kind);
CREATE INDEX benchmark_registry_category_idx ON benchmark_registry (category);

-- =============================================================================
-- Campaigns
-- =============================================================================
-- A campaign is a reproducible named bundle of (models × engines ×
-- benchmarks) that runs on one or more agents. Campaigns can be
-- scheduled via cron_expr (evaluated by the in-app robfig/cron
-- scheduler).
CREATE TABLE campaigns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL DEFAULT '',
    config       JSONB NOT NULL DEFAULT '{}'::jsonb,
    cron_expr    TEXT NOT NULL DEFAULT '',
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX campaigns_enabled_idx ON campaigns (enabled);

-- =============================================================================
-- Runs
-- =============================================================================
-- A run is a single invocation of a model × engine × benchmark set.
-- campaign_id is nullable so ad-hoc quicktests (no campaign) still
-- land in the same table. agent_id is nullable for server-side
-- simulated runs during development.
CREATE TABLE runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id  UUID REFERENCES campaigns (id) ON DELETE SET NULL,
    agent_id     UUID REFERENCES kitt_bonnie_agents (id) ON DELETE SET NULL,
    hardware_id  UUID REFERENCES hardware (id) ON DELETE SET NULL,
    model        TEXT NOT NULL,
    engine       TEXT NOT NULL,
    engine_profile_id UUID REFERENCES engine_profiles (id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT NOT NULL DEFAULT '',
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX runs_campaign_id_idx ON runs (campaign_id);
CREATE INDEX runs_agent_id_idx    ON runs (agent_id);
CREATE INDEX runs_status_idx      ON runs (status);
CREATE INDEX runs_model_idx       ON runs (model);
CREATE INDEX runs_engine_idx      ON runs (engine);

-- =============================================================================
-- Campaign run pivot
-- =============================================================================
-- Many runs per campaign invocation (N models × M benchmarks). The
-- scheduled_at timestamp groups runs triggered by a single cron fire so
-- the UI can show per-invocation rollups.
CREATE TABLE campaign_runs (
    campaign_id  UUID NOT NULL REFERENCES campaigns (id) ON DELETE CASCADE,
    run_id       UUID NOT NULL REFERENCES runs (id)      ON DELETE CASCADE,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campaign_id, run_id)
);

CREATE INDEX campaign_runs_scheduled_at_idx ON campaign_runs (scheduled_at);

-- =============================================================================
-- Benchmarks (run results)
-- =============================================================================
-- One row per (run, benchmark) pair. raw_json holds the complete
-- harness output so no information is lost even when flag-commons
-- evolves the normalized columns.
CREATE TABLE benchmarks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    benchmark    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    score        DOUBLE PRECISION,
    duration_ms  BIGINT,
    raw_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX benchmarks_run_id_idx    ON benchmarks (run_id);
CREATE INDEX benchmarks_benchmark_idx ON benchmarks (benchmark);

-- =============================================================================
-- Metrics
-- =============================================================================
-- Fine-grained metric rows — throughput tokens/s, latency ms, GPU
-- memory, power, etc. Separating these from benchmarks lets us run
-- time-series queries without JSONB unpacking, and lets a single
-- benchmark row yield many metrics.
CREATE TABLE metrics (
    id           BIGSERIAL PRIMARY KEY,
    run_id       UUID NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    benchmark_id UUID REFERENCES benchmarks (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    unit         TEXT NOT NULL DEFAULT '',
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX metrics_run_id_idx       ON metrics (run_id);
CREATE INDEX metrics_benchmark_id_idx ON metrics (benchmark_id);
CREATE INDEX metrics_name_idx         ON metrics (name);

-- =============================================================================
-- Notification configs
-- =============================================================================
-- Tenants may configure multiple Slack / Discord destinations (one per
-- team, one per campaign category, etc.). target is the webhook URL
-- or channel identifier; config holds channel-specific knobs.
CREATE TABLE notification_configs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    channel     TEXT NOT NULL,
    target      TEXT NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX notification_configs_channel_idx ON notification_configs (channel);
