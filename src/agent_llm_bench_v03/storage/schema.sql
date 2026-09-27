-- Agent LLM Bench V0.3 Database Schema
-- Version: 1

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suite_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_run_id TEXT NOT NULL UNIQUE,
    model_name TEXT NOT NULL,
    node_id TEXT NOT NULL,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    profile TEXT DEFAULT 'quick',
    total_duration_sec REAL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_run_id TEXT NOT NULL REFERENCES suite_runs(suite_run_id),
    run_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    node_id TEXT NOT NULL,
    benchmark_name TEXT NOT NULL,
    variant TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    duration_sec REAL,
    status TEXT NOT NULL DEFAULT 'running',
    config_json TEXT,
    result_json TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS suite_parameters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_run_id TEXT NOT NULL REFERENCES suite_runs(suite_run_id),
    parameter_name TEXT NOT NULL,
    parameter_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT NOT NULL UNIQUE,
    model_name TEXT NOT NULL,
    node_id TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS parameter_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    node_id TEXT NOT NULL,
    benchmark_name TEXT NOT NULL,
    parameter_name TEXT NOT NULL,
    suggested_value TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    evidence_count INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llama_benchy_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id INTEGER NOT NULL REFERENCES benchmark_runs(id),
    n_ctx INTEGER NOT NULL,
    batch_size INTEGER NOT NULL,
    pp_n_threads INTEGER NOT NULL,
    tg_n_threads INTEGER NOT NULL,
    pp_tps REAL,
    tg_tps REAL,
    pp_ms_per_token REAL,
    tg_ms_per_token REAL,
    total_duration_sec REAL
);

CREATE TABLE IF NOT EXISTS bfcl_v4_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id INTEGER NOT NULL REFERENCES benchmark_runs(id),
    variant TEXT NOT NULL,
    total_tasks INTEGER NOT NULL,
    correct_tasks INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    tool_call_success_rate REAL,
    avg_response_time_sec REAL
);

CREATE TABLE IF NOT EXISTS tau2_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id INTEGER NOT NULL REFERENCES benchmark_runs(id),
    domain TEXT NOT NULL,
    total_tasks INTEGER NOT NULL,
    correct_tasks INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    avg_steps_per_task REAL,
    avg_response_time_sec REAL
);

CREATE TABLE IF NOT EXISTS tool_eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id INTEGER NOT NULL REFERENCES benchmark_runs(id),
    total_tasks INTEGER NOT NULL,
    correct_tasks INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    avg_response_time_sec REAL
);

CREATE TABLE IF NOT EXISTS vitabench_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id INTEGER NOT NULL REFERENCES benchmark_runs(id),
    total_tasks INTEGER NOT NULL,
    correct_tasks INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    avg_response_time_sec REAL
);

CREATE TABLE IF NOT EXISTS agent_llm_bench_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id INTEGER NOT NULL REFERENCES benchmark_runs(id),
    total_tasks INTEGER NOT NULL,
    correct_tasks INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    avg_response_time_sec REAL,
    task_details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_suite_runs_model ON suite_runs(model_name);
CREATE INDEX IF NOT EXISTS idx_suite_runs_node ON suite_runs(node_id);
CREATE INDEX IF NOT EXISTS idx_suite_runs_started ON suite_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_bench_runs_suite ON benchmark_runs(suite_run_id);
CREATE INDEX IF NOT EXISTS idx_bench_runs_model ON benchmark_runs(model_name);
CREATE INDEX IF NOT EXISTS idx_bench_runs_benchmark ON benchmark_runs(benchmark_name);
CREATE INDEX IF NOT EXISTS idx_bench_runs_started ON benchmark_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_suite_params_suite ON suite_parameters(suite_run_id);
CREATE INDEX IF NOT EXISTS idx_param_suggestions_model ON parameter_suggestions(model_name, node_id, benchmark_name);
