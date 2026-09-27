"""Tests for the V0.3 database layer."""

import json
import tempfile
from pathlib import Path

import pytest

from agent_llm_bench_v03.storage.database import Database, DatabaseError


@pytest.fixture
def db():
    """Create a temporary in-memory-like database for testing."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_bench.db"
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


def test_initialize_creates_tables(db):
    """Schema initialization creates all required tables."""
    conn = db.conn
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected = {
        "schema_version",
        "suite_runs",
        "benchmark_runs",
        "suite_parameters",
        "model_profiles",
        "parameter_suggestions",
        "llama_benchy_results",
        "bfcl_v4_results",
        "tau2_results",
        "tool_eval_results",
        "vitabench_results",
        "agent_llm_bench_results",
    }
    assert expected.issubset(tables)


def test_create_and_get_suite_run(db):
    """Create a suite run and retrieve it."""
    run_id = db.create_suite_run(
        suite_run_id="test-run-001",
        model_name="Qwen2.5-Coder-0.5B-Instruct-Q8_0.gguf",
        node_id="node-2",
        profile="quick",
    )
    assert run_id > 0

    suite = db.get_suite_run("test-run-001")
    assert suite is not None
    assert suite["model_name"] == "Qwen2.5-Coder-0.5B-Instruct-Q8_0.gguf"
    assert suite["node_id"] == "node-2"
    assert suite["profile"] == "quick"
    assert suite["status"] == "running"


def test_complete_suite_run(db):
    """Mark a suite run as completed."""
    db.create_suite_run("test-run-002", "model-x.gguf", "node-1")
    db.complete_suite_run(
        "test-run-002", status="completed", total_duration_sec=123.45
    )

    suite = db.get_suite_run("test-run-002")
    assert suite["status"] == "completed"
    assert suite["total_duration_sec"] == 123.45
    assert suite["completed_at"] is not None


def test_create_and_complete_benchmark_run(db):
    """Create and complete a benchmark run within a suite."""
    db.create_suite_run("test-run-003", "model-y.gguf", "node-2")

    bench_id = db.create_benchmark_run(
        suite_run_id="test-run-003",
        run_id=1,
        model_name="model-y.gguf",
        node_id="node-2",
        benchmark_name="llama_benchy",
        variant="n_ctx=64000,batch_size=512",
        config_json={"n_ctx": 64000, "batch_size": 512},
    )
    assert bench_id > 0

    db.complete_benchmark_run(
        bench_id,
        status="completed",
        duration_sec=45.2,
        result_json={"pp_tps": 95.0, "tg_tps": 100.0},
    )

    bench = db.get_benchmark_run(bench_id)
    assert bench["status"] == "completed"
    assert bench["duration_sec"] == 45.2
    assert bench["result"]["pp_tps"] == 95.0
    assert bench["config"]["n_ctx"] == 64000


def test_llama_benchy_results(db):
    """Insert and query llama-benchy detailed results."""
    db.create_suite_run("test-run-004", "model-z.gguf", "node-1")
    bench_id = db.create_benchmark_run(
        "test-run-004", 1, "model-z.gguf", "node-1", "llama_benchy"
    )

    results = [
        {
            "n_ctx": 64000,
            "batch_size": 512,
            "pp_n_threads": 8,
            "tg_n_threads": 8,
            "pp_tps": 95.0,
            "tg_tps": 100.0,
            "pp_ms_per_token": 10.5,
            "tg_ms_per_token": 10.0,
            "total_duration_sec": 30.0,
        }
    ]
    db.insert_llama_benchy_results(bench_id, results)

    rows = db.conn.execute(
        "SELECT * FROM llama_benchy_results WHERE benchmark_run_id=?",
        (bench_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["tg_tps"] == 100.0


def test_suite_parameters(db):
    """Store and retrieve suite parameters."""
    db.create_suite_run("test-run-005", "model-a.gguf", "node-2")
    params = {
        "n_ctx": "64000",
        "batch_size": "512",
        "flash_attn": "on",
        "gpu": "0",
    }
    db.set_suite_parameters("test-run-005", params)

    retrieved = db.get_suite_parameters("test-run-005")
    assert retrieved == params


def test_list_suite_runs(db):
    """List suite runs with filters."""
    db.create_suite_run("run-1", "model-a.gguf", "node-1")
    db.create_suite_run("run-2", "model-b.gguf", "node-2")

    all_runs = db.list_suite_runs(limit=10)
    assert len(all_runs) == 2

    filtered = db.list_suite_runs(model_name="model-a.gguf")
    assert len(filtered) == 1
    assert filtered[0]["model_name"] == "model-a.gguf"


def test_get_suite_aggregate(db):
    """Aggregate results for a complete suite run."""
    db.create_suite_run("test-run-006", "model-bench.gguf", "node-2")

    # Add llama_benchy with results
    bench1 = db.create_benchmark_run(
        "test-run-006", 1, "model-bench.gguf", "node-2", "llama_benchy"
    )
    db.insert_llama_benchy_results(
        bench1,
        [
            {
                "n_ctx": 64000,
                "batch_size": 512,
                "pp_n_threads": 8,
                "tg_n_threads": 8,
                "pp_tps": 95.0,
                "tg_tps": 100.0,
                "pp_ms_per_token": 10.5,
                "tg_ms_per_token": 10.0,
                "total_duration_sec": 30.0,
            }
        ],
    )
    db.complete_benchmark_run(bench1, status="completed", duration_sec=30.0)

    # Add agent benchmark with accuracy
    bench2 = db.create_benchmark_run(
        "test-run-006", 2, "model-bench.gguf", "node-2", "agent_llm_bench"
    )
    db.complete_benchmark_run(
        bench2,
        status="completed",
        duration_sec=120.0,
        result_json={"total_tasks": 17, "correct_tasks": 15, "accuracy": 0.882},
    )

    aggregate = db.get_suite_aggregate("test-run-006")
    assert aggregate["total_benchmarks"] == 2
    assert aggregate["completed"] == 2
    assert aggregate["ttft_64k"]["tg_tps"] == 100.0
    assert aggregate["avg_accuracy"] == pytest.approx(0.882)


def test_bfcl_v4_results(db):
    """Insert and verify BFCL-V4 results."""
    db.create_suite_run("test-run-007", "model-tool.gguf", "node-1")
    bench_id = db.create_benchmark_run(
        "test-run-007", 1, "model-tool.gguf", "node-1", "bfcl_v4"
    )

    db.insert_bfcl_v4_results(
        bench_id,
        variant="simple_python",
        results={
            "total_tasks": 60,
            "correct_tasks": 50,
            "accuracy": 0.833,
            "tool_call_success_rate": 0.9,
            "avg_response_time_sec": 2.5,
        },
    )

    rows = db.conn.execute(
        "SELECT * FROM bfcl_v4_results WHERE benchmark_run_id=?",
        (bench_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["variant"] == "simple_python"
    assert rows[0]["accuracy"] == pytest.approx(0.833)


def test_database_error_on_missing_suite(db):
    """get_suite_aggregate raises for non-existent suite."""
    with pytest.raises(DatabaseError):
        db.get_suite_aggregate("nonexistent-run")
