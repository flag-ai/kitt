"""Shared database schema definitions for KITT storage backends."""

# SQLite schema — version-tracked for migrations.
SCHEMA_VERSION = 11

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    engine TEXT NOT NULL,
    suite_name TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    total_benchmarks INTEGER NOT NULL DEFAULT 0,
    passed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    total_time_seconds REAL NOT NULL DEFAULT 0.0,
    kitt_version TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    test_version TEXT NOT NULL DEFAULT '1.0.0',
    run_number INTEGER NOT NULL DEFAULT 1,
    passed INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_id INTEGER NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value REAL
);

CREATE TABLE IF NOT EXISTS hardware (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    gpu_model TEXT,
    gpu_vram_gb INTEGER,
    gpu_count INTEGER DEFAULT 1,
    cpu_model TEXT,
    cpu_cores INTEGER,
    ram_gb INTEGER,
    environment_type TEXT,
    fingerprint TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_runs_engine ON runs(engine);
CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp);
CREATE INDEX IF NOT EXISTS idx_runs_suite ON runs(suite_name);
CREATE INDEX IF NOT EXISTS idx_benchmarks_run_id ON benchmarks(run_id);
CREATE INDEX IF NOT EXISTS idx_benchmarks_test_name ON benchmarks(test_name);
CREATE INDEX IF NOT EXISTS idx_metrics_benchmark_id ON metrics(benchmark_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_hardware_run_id ON hardware(run_id);
"""

# PostgreSQL equivalent (uses SERIAL, BOOLEAN, JSONB)
# NOTE: This schema must include ALL tables through SCHEMA_VERSION because
# fresh Postgres installs apply this schema and set the version directly,
# skipping migrations.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    engine TEXT NOT NULL,
    suite_name TEXT NOT NULL DEFAULT '',
    timestamp TIMESTAMPTZ NOT NULL,
    passed BOOLEAN NOT NULL DEFAULT FALSE,
    total_benchmarks INTEGER NOT NULL DEFAULT 0,
    passed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    total_time_seconds REAL NOT NULL DEFAULT 0.0,
    kitt_version TEXT NOT NULL DEFAULT '',
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    test_version TEXT NOT NULL DEFAULT '1.0.0',
    run_number INTEGER NOT NULL DEFAULT 1,
    passed BOOLEAN NOT NULL DEFAULT FALSE,
    timestamp TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    id SERIAL PRIMARY KEY,
    benchmark_id INTEGER NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS hardware (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    gpu_model TEXT,
    gpu_vram_gb INTEGER,
    gpu_count INTEGER DEFAULT 1,
    cpu_model TEXT,
    cpu_cores INTEGER,
    ram_gb INTEGER,
    environment_type TEXT,
    fingerprint TEXT
);

-- v2: agents, web_campaigns, quick_tests, events
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    hostname TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 8090,
    token TEXT NOT NULL DEFAULT '',
    token_hash TEXT DEFAULT '',
    token_prefix TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'offline',
    gpu_info TEXT DEFAULT '',
    gpu_count INTEGER DEFAULT 0,
    cpu_info TEXT DEFAULT '',
    ram_gb INTEGER DEFAULT 0,
    environment_type TEXT DEFAULT '',
    fingerprint TEXT DEFAULT '',
    kitt_version TEXT DEFAULT '',
    hardware_details TEXT DEFAULT '',
    last_heartbeat TEXT DEFAULT '',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    cpu_arch TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS web_campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    config_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    agent_id TEXT REFERENCES agents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TEXT DEFAULT '',
    completed_at TEXT DEFAULT '',
    total_runs INTEGER DEFAULT 0,
    succeeded INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quick_tests (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    model_path TEXT NOT NULL,
    engine_name TEXT NOT NULL,
    benchmark_name TEXT NOT NULL,
    suite_name TEXT DEFAULT 'quick',
    status TEXT NOT NULL DEFAULT 'queued',
    command_id TEXT DEFAULT '',
    engine_mode TEXT DEFAULT 'docker',
    profile_id TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TEXT DEFAULT '',
    completed_at TEXT DEFAULT '',
    result_id TEXT REFERENCES runs(id),
    error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- v3: web_settings
CREATE TABLE IF NOT EXISTS web_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- v7: quick_test_logs
CREATE TABLE IF NOT EXISTS quick_test_logs (
    id SERIAL PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES quick_tests(id),
    line TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_runs_engine ON runs(engine);
CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp);
CREATE INDEX IF NOT EXISTS idx_runs_suite ON runs(suite_name);
CREATE INDEX IF NOT EXISTS idx_benchmarks_run_id ON benchmarks(run_id);
CREATE INDEX IF NOT EXISTS idx_benchmarks_test_name ON benchmarks(test_name);
CREATE INDEX IF NOT EXISTS idx_metrics_benchmark_id ON metrics(benchmark_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_hardware_run_id ON hardware(run_id);
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_web_campaigns_status ON web_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_web_campaigns_agent ON web_campaigns(agent_id);
CREATE INDEX IF NOT EXISTS idx_quick_tests_agent ON quick_tests(agent_id);
CREATE INDEX IF NOT EXISTS idx_quick_tests_status ON quick_tests(status);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source_id);
CREATE INDEX IF NOT EXISTS idx_quick_test_logs_test ON quick_test_logs(test_id);

-- v10: campaign_logs
CREATE TABLE IF NOT EXISTS campaign_logs (
    id SERIAL PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES web_campaigns(id),
    line TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_campaign_logs_campaign ON campaign_logs(campaign_id);

-- v11: engine_profiles and agent_engines
CREATE TABLE IF NOT EXISTS engine_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    engine TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'docker',
    description TEXT DEFAULT '',
    build_config TEXT DEFAULT '{}',
    runtime_config TEXT DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_engines (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    engine TEXT NOT NULL,
    mode TEXT NOT NULL,
    version TEXT DEFAULT '',
    binary_path TEXT DEFAULT '',
    status TEXT DEFAULT 'unknown',
    last_checked TEXT DEFAULT '',
    UNIQUE(agent_id, engine, mode)
);

CREATE INDEX IF NOT EXISTS idx_engine_profiles_engine ON engine_profiles(engine);
CREATE INDEX IF NOT EXISTS idx_agent_engines_agent ON agent_engines(agent_id);

-- v8: agent_settings
CREATE TABLE IF NOT EXISTS agent_settings (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    UNIQUE(agent_id, key)
);
CREATE INDEX IF NOT EXISTS idx_agent_settings_agent ON agent_settings(agent_id);
"""
