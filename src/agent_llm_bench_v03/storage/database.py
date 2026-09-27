"""SQLite database layer for Agent LLM Bench V0.3.

Provides connection management, schema initialization, and CRUD operations
for all benchmark tables. Thread-safe via per-thread connections.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Schema SQL is bundled with the package
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DatabaseError(Exception):
    """Raised for database operation failures."""
    pass


class Database:
    """Thread-safe SQLite database wrapper for V0.3 benchmarks."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def initialize(self) -> None:
        """Create tables and apply schema if needed."""
        with self._init_lock:
            if self._initialized:
                return
            schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
            with self.conn:
                self.conn.executescript(schema_sql)
                # Record schema version
                self.conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (1,),
                )
            self._initialized = True

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self.conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # --- Suite Runs ---

    def create_suite_run(
        self,
        suite_run_id: str,
        model_name: str,
        node_id: str,
        profile: str = "quick",
    ) -> int:
        """Create a new suite run record. Returns row id."""
        with self.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO suite_runs (suite_run_id, model_name, node_id, profile)
                   VALUES (?, ?, ?, ?)""",
                (suite_run_id, model_name, node_id, profile),
            )
            return cursor.lastrowid

    def complete_suite_run(
        self,
        suite_run_id: str,
        status: str = "completed",
        total_duration_sec: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a suite run as completed."""
        with self.transaction() as conn:
            conn.execute(
                """UPDATE suite_runs SET status=?, completed_at=datetime('now'),
                   total_duration_sec=?, error_message=? WHERE suite_run_id=?""",
                (status, total_duration_sec, error_message, suite_run_id),
            )

    def get_suite_run(self, suite_run_id: str) -> Optional[dict]:
        """Get a suite run by ID."""
        row = self.conn.execute(
            "SELECT * FROM suite_runs WHERE suite_run_id=?", (suite_run_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_suite_runs(
        self,
        limit: int = 50,
        model_name: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> list[dict]:
        """List recent suite runs with optional filters."""
        query = "SELECT * FROM suite_runs WHERE 1=1"
        params: list[Any] = []
        if model_name:
            query += " AND model_name=?"
            params.append(model_name)
        if node_id:
            query += " AND node_id=?"
            params.append(node_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # --- Benchmark Runs ---

    def create_benchmark_run(
        self,
        suite_run_id: str,
        run_id: int,
        model_name: str,
        node_id: str,
        benchmark_name: str,
        variant: Optional[str] = None,
        config_json: Optional[dict] = None,
    ) -> int:
        """Create a new benchmark run record. Returns row id."""
        with self.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO benchmark_runs
                   (suite_run_id, run_id, model_name, node_id, benchmark_name, variant, config_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    suite_run_id,
                    run_id,
                    model_name,
                    node_id,
                    benchmark_name,
                    variant,
                    json.dumps(config_json) if config_json else None,
                ),
            )
            return cursor.lastrowid

    def complete_benchmark_run(
        self,
        benchmark_run_id: int,
        status: str = "completed",
        duration_sec: Optional[float] = None,
        result_json: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a benchmark run as completed."""
        with self.transaction() as conn:
            conn.execute(
                """UPDATE benchmark_runs SET status=?, completed_at=datetime('now'),
                   duration_sec=?, result_json=?, error_message=? WHERE id=?""",
                (
                    status,
                    duration_sec,
                    json.dumps(result_json) if result_json else None,
                    error_message,
                    benchmark_run_id,
                ),
            )

    def get_benchmark_run(self, benchmark_run_id: int) -> Optional[dict]:
        """Get a benchmark run by ID."""
        row = self.conn.execute(
            "SELECT * FROM benchmark_runs WHERE id=?", (benchmark_run_id,)
        ).fetchone()
        if row:
            result = dict(row)
            if result.get("config_json"):
                result["config"] = json.loads(result["config_json"])
            if result.get("result_json"):
                result["result"] = json.loads(result["result_json"])
            return result
        return None

    def list_benchmark_runs(
        self,
        suite_run_id: Optional[str] = None,
        model_name: Optional[str] = None,
        benchmark_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List benchmark runs with optional filters."""
        query = "SELECT * FROM benchmark_runs WHERE 1=1"
        params: list[Any] = []
        if suite_run_id:
            query += " AND suite_run_id=?"
            params.append(suite_run_id)
        if model_name:
            query += " AND model_name=?"
            params.append(model_name)
        if benchmark_name:
            query += " AND benchmark_name=?"
            params.append(benchmark_name)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # --- Suite Parameters ---

    def set_suite_parameters(
        self, suite_run_id: str, parameters: dict[str, Any]
    ) -> None:
        """Store parameters used for a suite run."""
        with self.transaction() as conn:
            for name, value in parameters.items():
                conn.execute(
                    """INSERT INTO suite_parameters (suite_run_id, parameter_name, parameter_value)
                       VALUES (?, ?, ?)""",
                    (suite_run_id, name, str(value)),
                )

    def get_suite_parameters(self, suite_run_id: str) -> dict[str, str]:
        """Retrieve parameters for a suite run."""
        rows = self.conn.execute(
            "SELECT parameter_name, parameter_value FROM suite_parameters WHERE suite_run_id=?",
            (suite_run_id,),
        ).fetchall()
        return {r["parameter_name"]: r["parameter_value"] for r in rows}

    # --- Detailed Results ---

    def insert_llama_benchy_results(
        self, benchmark_run_id: int, results: list[dict]
    ) -> None:
        """Insert llama-benchy performance results."""
        with self.transaction() as conn:
            for r in results:
                conn.execute(
                    """INSERT INTO llama_benchy_results
                       (benchmark_run_id, n_ctx, batch_size, pp_n_threads, tg_n_threads,
                        pp_tps, tg_tps, pp_ms_per_token, tg_ms_per_token, total_duration_sec)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        benchmark_run_id,
                        r.get("n_ctx"),
                        r.get("batch_size"),
                        r.get("pp_n_threads"),
                        r.get("tg_n_threads"),
                        r.get("pp_tps"),
                        r.get("tg_tps"),
                        r.get("pp_ms_per_token"),
                        r.get("tg_ms_per_token"),
                        r.get("total_duration_sec"),
                    ),
                )

    def insert_bfcl_v4_results(
        self, benchmark_run_id: int, variant: str, results: dict
    ) -> None:
        """Insert BFCL-V4 tool calling results."""
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO bfcl_v4_results
                   (benchmark_run_id, variant, total_tasks, correct_tasks, accuracy,
                    tool_call_success_rate, avg_response_time_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    benchmark_run_id,
                    variant,
                    results.get("total_tasks"),
                    results.get("correct_tasks"),
                    results.get("accuracy"),
                    results.get("tool_call_success_rate"),
                    results.get("avg_response_time_sec"),
                ),
            )

    def insert_agent_llm_bench_results(
        self, benchmark_run_id: int, results: dict
    ) -> None:
        """Insert local agent LLM bench results."""
        with self.transaction() as conn:
            task_details = results.pop("task_details", None)
            conn.execute(
                """INSERT INTO agent_llm_bench_results
                   (benchmark_run_id, total_tasks, correct_tasks, accuracy,
                    avg_response_time_sec, task_details_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    benchmark_run_id,
                    results.get("total_tasks"),
                    results.get("correct_tasks"),
                    results.get("accuracy"),
                    results.get("avg_response_time_sec"),
                    json.dumps(task_details) if task_details else None,
                ),
            )

    # --- Aggregation ---

    def get_suite_aggregate(self, suite_run_id: str) -> dict:
        """Get aggregated results for a suite run."""
        suite = self.get_suite_run(suite_run_id)
        if not suite:
            raise DatabaseError(f"Suite run {suite_run_id} not found")

        bench_runs = self.list_benchmark_runs(suite_run_id=suite_run_id, limit=1000)

        # Aggregate by benchmark name
        benchmarks: dict[str, list[dict]] = {}
        for br in bench_runs:
            name = br["benchmark_name"]
            if name not in benchmarks:
                benchmarks[name] = []
            benchmarks[name].append(br)

        # Calculate overall metrics
        total_benchmarks = len(bench_runs)
        completed = sum(1 for br in bench_runs if br["status"] == "completed")
        failed = sum(1 for br in bench_runs if br["status"] == "failed")
        timed_out = sum(1 for br in bench_runs if br["status"] == "timeout")

        # TTFT from llama_benchy_results (use first run's n_ctx=64000)
        ttft_64k = None
        for br in bench_runs:
            if br["benchmark_name"] == "llama_benchy":
                rows = self.conn.execute(
                    """SELECT pp_tps, tg_tps FROM llama_benchy_results
                       WHERE benchmark_run_id=? AND n_ctx=64000 LIMIT 1""",
                    (br["id"],),
                ).fetchone()
                if rows:
                    ttft_64k = {"pp_tps": rows["pp_tps"], "tg_tps": rows["tg_tps"]}
                    break

        # Accuracy from agent benchmarks
        accuracies = []
        for br in bench_runs:
            if br["benchmark_name"] in ("agent_llm_bench", "bfcl_v4", "tau2"):
                if br.get("result_json"):
                    result = json.loads(br["result_json"])
                    acc = result.get("accuracy")
                    if acc is not None:
                        accuracies.append(acc)

        avg_accuracy = (
            sum(accuracies) / len(accuracies) if accuracies else None
        )

        return {
            "suite": suite,
            "total_benchmarks": total_benchmarks,
            "completed": completed,
            "failed": failed,
            "timed_out": timed_out,
            "ttft_64k": ttft_64k,
            "avg_accuracy": avg_accuracy,
            "benchmarks": benchmarks,
        }

    def get_leaderboard(
        self, limit: int = 20, benchmark_name: Optional[str] = None
    ) -> list[dict]:
        """Get leaderboard of best results per model."""
        query = """
            SELECT br.model_name, br.node_id, br.benchmark_name, br.variant,
                   br.result_json, br.started_at
            FROM benchmark_runs br
            INNER JOIN (
                SELECT model_name, benchmark_name, variant, MAX(id) as max_id
                FROM benchmark_runs
                WHERE status='completed' AND result_json IS NOT NULL
        """
        params: list[Any] = []
        if benchmark_name:
            query += " AND benchmark_name=?"
            params.append(benchmark_name)
        query += """
                GROUP BY model_name, benchmark_name, variant
            ) best ON br.id = best.max_id
            ORDER BY br.started_at DESC
            LIMIT ?
        """
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
