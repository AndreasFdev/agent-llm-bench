#!/usr/bin/env python3
"""Agent LLM Bench V0.3 Dashboard — MetriLLM-style Leaderboard on port 8083.

Stdlib-only (http.server + sqlite3). Reads LIVE from the V0.3 SQLite database
(bench.db next to this project), so results of the first benchmark run appear
in the leaderboard automatically as soon as they are committed.

Routes:
    /                    -> MetriLLM-style Leaderboard (SPA, client-side filter/sort/pagination)
    /methodology         -> Methodology page (placeholder)
    /blog                -> Blog (placeholder)
    /contributors        -> Contributors (placeholder)
    /founding            -> Founding (placeholder)
    /my-benchmarks       -> My Benchmarks (placeholder)
    /legal /privacy /terms -> Legal pages (placeholder)
    /api/leaderboard     -> All leaderboard rows (joined v03 data + computed scores)
    /api/trending        -> Top models / machines / CPUs (last 7 days)
    /api/stats           -> Aggregate counters (runs, models, families, CPUs)
    /api/filters         -> Distinct values for all filter dropdowns
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Database: V0.3 bench.db (same dir as project root, one level above dashboard/)
DB_PATH = Path(__file__).resolve().parent.parent / "bench.db"

# ---------------------------------------------------------------------------
# Scoring (MetriLLM methodology, simplified to available v03 data)
# ---------------------------------------------------------------------------
# Global = 30% HW-Fit + 70% Quality
# HW-Fit = 50% speed(tok/s) + 20% TTFT + 30% memory-efficiency (placeholder 50 if unknown)
# Verdict: EXCELLENT >= 80, GOOD >= 60, MARGINAL >= 40, NOT RECOMMENDED < 40

VERDICTS = [
    ("EXCELLENT", 80),
    ("GOOD", 60),
    ("MARGINAL", 40),
    ("NOT RECOMMENDED", 0),
]


def _interp(x: float, pts) -> float:
    """Piecewise-linear interpolation over sorted (x, y) points."""
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def speed_score(tg_tps: float | None) -> float:
    if tg_tps is None:
        return 50.0
    return _interp(tg_tps, [(3, 5), (5, 20), (10, 45), (20, 70), (45, 90), (80, 100)])


def ttft_score(ttft_s: float | None) -> float:
    if ttft_s is None or ttft_s <= 0:
        return 50.0
    return _interp(ttft_s, [(0.7, 100), (1.0, 90), (2.0, 70), (5.0, 45), (12.0, 20), (20.0, 5)])


def compute_hw_fit(tg_tps: float | None, ttft_s: float | None) -> float:
    mem_eff = 50.0  # placeholder until RAM-delta tracking lands in the DB
    return round(0.5 * speed_score(tg_tps) + 0.2 * ttft_score(ttft_s) + 0.3 * mem_eff, 1)


def compute_global(hw_fit: float, quality: float | None) -> float:
    q = quality if quality is not None else 0.0
    return round(0.3 * hw_fit + 0.7 * q, 1)


def verdict_for(score: float | None) -> str:
    s = score if score is not None else 0.0
    for name, threshold in VERDICTS:
        if s >= threshold:
            return name
    return "NOT RECOMMENDED"


# ---------------------------------------------------------------------------
# Model-name parsing (family / size / quant) — best effort, placeholders ok
# ---------------------------------------------------------------------------
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)([BM])\b", re.IGNORECASE)
_QUANT_RE = re.compile(
    r"\b(Q\d{1,2}(?:_[A-Z0-9]+)?|MXFP4|NVFP4|FP8|BF16|F16|IQ\d{1,2}[A-Z_]?)\b", re.IGNORECASE
)


def parse_model_name(name: str) -> tuple[str, str | None, str | None]:
    """Return (family, size, quant) parsed from a model name."""
    n = name.split("/")[-1]  # strip org prefix
    m_size = _SIZE_RE.search(n)
    size = None
    if m_size:
        val, unit = m_size.group(1), m_size.group(2).upper()
        if unit == "B":
            size = f"{val}B"
        else:
            size = f"{float(val):g}M"
    m_q = _QUANT_RE.search(n)
    quant = m_q.group(1).upper() if m_q else None
    # family: first token before a digit or '-'
    fam = re.split(r"[\d\-]", n, 1)[0]
    return fam.lower() or "unknown", size, quant


def derive_flags(tg_tps: float | None, quality: float | None) -> list[str]:
    flags = []
    if quality is not None and quality >= 75:
        flags.append("THINK")
    if tg_tps is not None and tg_tps >= 25:
        flags.append("ECO")
    if "THINK" in flags and "ECO" in flags:
        flags.append("ECOTHINK")
    if tg_tps is not None and tg_tps < 5:
        flags.append("SLOW")
    return flags


# ---------------------------------------------------------------------------
# DB access
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _acc_from_result_json(rj: dict | None) -> float | None:
    if not rj:
        return None
    a = rj.get("accuracy")
    if isinstance(a, (int, float)):
        return a
    # fallback: correct/total
    try:
        c, t = rj.get("correct_tasks"), rj.get("total_tasks")
        if c is not None and t:
            return c / t
    except (TypeError, ZeroDivisionError):
        pass
    return None


def _row_get(row, key):
    """Safe column access — returns None if the column doesn't exist."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def build_leaderboard_rows() -> list[dict]:
    """Join suite_runs + benchmark_runs + result tables into leaderboard rows.

    One row per completed suite run (the unit a user compares). Live: any new
    committed run shows up immediately on next page load / auto-refresh.
    """
    conn = get_conn()
    try:
        suites = conn.execute(
            "SELECT * FROM suite_runs WHERE status='completed' ORDER BY started_at DESC"
        ).fetchall()
        if not suites:
            return []

        # Pre-fetch per-suite aggregates
        rows = []
        for s in suites:
            sid = s["suite_run_id"]

            # llama_benchy: best tg_tps (throughput) + pp_tps (prompt processing -> TTFT proxy)
            lb = conn.execute(
                """SELECT lbr.tg_tps, lbr.pp_tps FROM llama_benchy_results lbr
                   JOIN benchmark_runs br ON lbr.benchmark_run_id = br.id
                   WHERE br.suite_run_id=? AND lbr.tg_tps IS NOT NULL
                   ORDER BY lbr.tg_tps DESC LIMIT 1""",
                (sid,),
            ).fetchone()
            tg_tps = lb["tg_tps"] if lb else None
            pp_tps = lb["pp_tps"] if lb else None
            # TTFT proxy: prompt-processing phase duration per token (sec/token) inverted.
            # v03 has no dedicated TTFT column yet -> placeholder until DB extension.
            ttft_s = round(1.0 / pp_tps, 3) if pp_tps and pp_tps > 0 else None

            # Quality: mean accuracy across agent benchmarks (0..1 -> 0..100)
            accs = []
            for bench in ("agent_llm_bench", "bfcl_v4", "tau2", "vitabench", "tool_eval"):
                rj_row = conn.execute(
                    """SELECT br.result_json FROM benchmark_runs br
                       WHERE br.suite_run_id=? AND br.benchmark_name=?
                       AND br.status='completed' AND br.result_json IS NOT NULL""",
                    (sid, bench),
                ).fetchone()
                if rj_row:
                    try:
                        a = _acc_from_result_json(json.loads(rj_row["result_json"]))
                        if a is not None:
                            accs.append(a)
                    except (json.JSONDecodeError, TypeError):
                        pass
            quality = round(100.0 * sum(accs) / len(accs), 1) if accs else None

            # config_json may carry cpu/ram/machine details once the harness writes them
            cfg: dict = {}
            cfg_raw = _row_get(s, "config_json")
            if cfg_raw:
                try:
                    cfg = json.loads(cfg_raw)
                except (json.JSONDecodeError, TypeError):
                    cfg = {}

            model_name = s["model_name"]
            family, size, quant = parse_model_name(model_name)
            hw_fit = compute_hw_fit(tg_tps, ttft_s)
            global_score = compute_global(hw_fit, quality)

            rows.append(
                {
                    "suite_run_id": sid,
                    "model": model_name,
                    "family": family,
                    "size": size or "—",
                    "quant": quant or "—",
                    "machine": s["node_id"],
                    "cpu": cfg.get("cpu") or s["node_id"],  # placeholder until config carries CPU
                    "arch": cfg.get("gpu_arch") or (cfg.get("gpu") or "GPU" if cfg else "CPU?"),
                    "os": cfg.get("os") or ("windows" if "inf-1" in s["node_id"] else "linux"),
                    "ram_gb": cfg.get("ram_gb"),  # placeholder: null until DB extension
                    "backend": "OLLAMA",
                    "format": "GGUF",
                    "tok_s": tg_tps,
                    "ttft_s": ttft_s,
                    "hw_fit": hw_fit,
                    "quality": quality,
                    "global_score": global_score,
                    "flags": derive_flags(tg_tps, quality),
                    "verdict": verdict_for(global_score),
                    "started_at": s["started_at"],
                    "duration_sec": s["total_duration_sec"],
                    "profile": _row_get(s, "profile"),
                }
            )
        rows.sort(key=lambda r: (r["global_score"] or 0), reverse=True)
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        return rows
    finally:
        conn.close()


def build_trending() -> dict:
    conn = get_conn()
    try:
        week_ago = "datetime('now', '-7 days')"
        suites = conn.execute(
            f"""SELECT * FROM suite_runs
                WHERE status='completed' AND started_at >= {week_ago}"""
        ).fetchall()

        def top_by(key: str, limit: int) -> list[dict]:
            agg: dict[str, list[float]] = {}
            for s in suites:
                k = s[key]
                # score proxy: quality if available else 0
                rj_row = conn.execute(
                    """SELECT br.result_json FROM benchmark_runs br
                       WHERE br.suite_run_id=? AND br.benchmark_name='agent_llm_bench'
                       AND br.status='completed' AND br.result_json IS NOT NULL""",
                    (s["suite_run_id"],),
                ).fetchone()
                a = _acc_from_result_json(json.loads(rj_row["result_json"])) if rj_row else None
                agg.setdefault(k, []).append(a if a is not None else 0.0)
            scored = [
                {"name": k, "score": round(100 * sum(v) / len(v), 1), "runs": len(v)}
                for k, v in agg.items()
            ]
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:limit]

        return {
            "top_models": top_by("model_name", 5),
            "top_machines": top_by("node_id", 2),
            "top_cpus": top_by("node_id", 2),  # placeholder: CPU==node until config carries CPU
        }
    finally:
        conn.close()


def build_stats() -> dict:
    conn = get_conn()
    try:
        total_runs = conn.execute(
            "SELECT COUNT(*) FROM suite_runs WHERE status='completed'"
        ).fetchone()[0]
        models = conn.execute(
            "SELECT COUNT(DISTINCT model_name) FROM suite_runs WHERE status='completed'"
        ).fetchone()[0]
        families = len({parse_model_name(m)[0] for (m,) in conn.execute(
            "SELECT DISTINCT model_name FROM suite_runs WHERE status='completed'"
        )}) if models else 0
        cpus = conn.execute(
            "SELECT COUNT(DISTINCT node_id) FROM suite_runs WHERE status='completed'"
        ).fetchone()[0]
        return {
            "total_runs": total_runs,
            "unique_models": models,
            "model_families": families,
            "unique_cpus": cpus,
        }
    finally:
        conn.close()


def build_filters() -> dict:
    rows = build_leaderboard_rows()

    def distinct(key):
        vals = sorted({r[key] for r in rows if r.get(key) not in (None, "—")})
        return vals

    return {
        "families": distinct("family"),
        "models": distinct("model"),
        "sizes": distinct("size"),
        "quants": distinct("quant"),
        "cpus": distinct("cpu"),
        "machines": distinct("machine"),
        "architectures": distinct("arch"),
        "os": distinct("os"),
        "ram": [str(r) for r in distinct("ram_gb")],
        "backends": distinct("backend"),
        "formats": distinct("format"),
        "verdicts": [v[0] for v in VERDICTS],
    }


# ---------------------------------------------------------------------------
# HTML — MetriLLM-style (dark, cyan accent #0ea5e9, monospace accents)
# ---------------------------------------------------------------------------
CSS = """
:root {
  --bg: #0a0f1a; --bg2: #0d1424; --card: #101a2e; --card2: #13203a;
  --border: #1e2d4a; --border2: #27395c;
  --text: #dbe4f3; --muted: #7c8db0; --dim: #56678c;
  --accent: #0ea5e9; --accent-dim: rgba(14,165,233,.14);
  --emerald: #10b981; --cyan: #06b6d4; --amber: #f59e0b; --rose: #f43f5e;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg); color: var(--text); line-height: 1.55;
  font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  min-height: 100vh;
}
a { color: var(--accent); text-decoration: none; }
.mono { font-family: var(--mono); }

/* ---------- Nav ---------- */
.nav {
  position: sticky; top: 0; z-index: 50;
  display: flex; align-items: center; gap: .25rem;
  padding: .8rem 1.5rem; background: rgba(10,15,26,.92);
  backdrop-filter: blur(8px); border-bottom: 1px solid var(--border);
}
.logo { display: flex; align-items: center; gap: .5rem; margin-right: 1.25rem; font-weight: 700; font-size: 1.05rem; color: var(--text); }
.logo .mark {
  width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center;
  background: linear-gradient(135deg, #0ea5e9, #06b6d4); color: #04121f; font-weight: 800; font-size: .85rem;
}
.nav a { padding: .4rem .7rem; border-radius: 8px; color: var(--muted); font-size: .92rem; }
.nav a:hover { color: var(--text); background: var(--card); }
.nav a.active { color: var(--accent); }
.nav .spacer { flex: 1; }
.btn {
  display: inline-flex; align-items: center; gap: .45rem; cursor: pointer;
  border: 1px solid var(--border2); background: var(--card); color: var(--text);
  padding: .5rem 1rem; border-radius: 9px; font-size: .9rem; font-weight: 600;
}
.btn:hover { border-color: var(--accent); }
.btn.primary { background: linear-gradient(135deg, #0ea5e9, #0891b2); color: #04121f; border: none; }
.btn.primary:hover { filter: brightness(1.1); }

/* ---------- Hero ---------- */
.hero { padding: 3rem 1.5rem 1.5rem; max-width: 1200px; margin: 0 auto; }
.hero h1 { font-size: 2.6rem; font-weight: 800; letter-spacing: -.02em; }
.hero .sub { color: var(--muted); margin-top: .5rem; max-width: 640px; font-size: 1.05rem; }
.cmd-block {
  margin-top: 1.4rem; background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 1rem 1.2rem; display: flex; gap: .75rem; align-items: center;
  max-width: 560px; font-family: var(--mono); font-size: .92rem;
}
.cmd-block .cmd { flex: 1; color: var(--text); white-space: pre-wrap; }
.copy-btn {
  border: 1px solid var(--border2); background: var(--bg2); color: var(--muted);
  border-radius: 7px; padding: .3rem .6rem; cursor: pointer; font-size: .8rem;
}
.copy-btn:hover { color: var(--accent); border-color: var(--accent); }
.hero .note { color: var(--dim); font-size: .85rem; margin-top: .6rem; }

/* ---------- Panels ---------- */
.wrap { max-width: 1200px; margin: 0 auto; padding: 0 1.5rem 3rem; }
.panel {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 1.25rem 1.4rem; margin-top: 1.6rem;
}
.panel h2 { font-size: 1.05rem; font-weight: 700; margin-bottom: .9rem; display: flex; align-items: center; gap: .6rem; }
.pill {
  font-size: .78rem; padding: .2rem .6rem; border-radius: 999px;
  background: var(--accent-dim); color: var(--accent); font-weight: 600;
}

/* Trending */
.trend-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.2rem; }
.trend-col h3 { font-size: .85rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: .6rem; }
.trend-item { display: flex; align-items: baseline; gap: .5rem; padding: .3rem 0; font-size: .92rem; }
.trend-item .rk { font-family: var(--mono); color: var(--accent); width: 1.2rem; }
.trend-item .nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.trend-item .sc { font-family: var(--mono); color: var(--muted); font-size: .85rem; }
.empty { color: var(--dim); font-size: .9rem; padding: .4rem 0; }

/* Stats */
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
.stat-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 1.1rem 1.2rem; }
.stat-card .num { font-family: var(--mono); font-size: 2rem; font-weight: 700; color: var(--accent); }
.stat-card .lbl { color: var(--muted); font-size: .85rem; margin-top: .2rem; }

/* Notify */
.notify { display: flex; gap: .6rem; align-items: center; }
.notify input {
  flex: 1; max-width: 340px; background: var(--bg2); border: 1px solid var(--border2);
  color: var(--text); border-radius: 9px; padding: .55rem .9rem; font-size: .9rem;
}
.notify input::placeholder { color: var(--dim); }

/* Filters */
.filter-bar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-top: 1.6rem; }
select {
  background: var(--bg2); border: 1px solid var(--border2); color: var(--text);
  border-radius: 8px; padding: .45rem .7rem; font-size: .85rem; cursor: pointer; max-width: 170px;
}
select:hover { border-color: var(--accent); }
.result-count { color: var(--muted); font-size: .9rem; margin-left: auto; font-family: var(--mono); }
.toggle { display: inline-flex; align-items: center; gap: .45rem; font-size: .85rem; color: var(--muted); cursor: pointer; user-select: none; }
.toggle input { accent-color: var(--accent); width: 15px; height: 15px; }

/* Table */
.table-wrap { overflow-x: auto; margin-top: 1.2rem; border: 1px solid var(--border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; min-width: 1080px; background: var(--card); }
th, td { padding: .65rem .9rem; text-align: left; border-bottom: 1px solid var(--border); font-size: .88rem; }
thead th {
  position: sticky; top: 0; background: var(--bg2); color: var(--muted);
  font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; cursor: pointer; user-select: none; white-space: nowrap;
}
thead th:hover { color: var(--text); }
thead th .arrow { color: var(--accent); margin-left: .25rem; }
tbody tr:hover { background: var(--card2); }
td.num, th.num { font-family: var(--mono); text-align: right; }
.model-cell { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.badge {
  display: inline-block; padding: .15rem .55rem; border-radius: 999px; font-size: .74rem;
  font-weight: 700; letter-spacing: .03em; font-family: var(--mono);
}
.v-EXCELLENT { background: rgba(16,185,129,.15); color: var(--emerald); }
.v-GOOD { background: rgba(6,182,212,.15); color: var(--cyan); }
.v-MARGINAL { background: rgba(245,158,11,.15); color: var(--amber); }
.v-NOTRECOMMENDED { background: rgba(244,63,94,.15); color: var(--rose); }
.flag { font-family: var(--mono); font-size: .72rem; color: var(--muted); margin-right: .35rem; }
/* Score gauges — color-coded by score band (MetriLLM-style) */
.score-bar { display: inline-block; width: 64px; height: 8px; border-radius: 999px; background: rgba(30,45,74,.55); vertical-align: middle; margin-right: .5rem; overflow: hidden; }
.score-bar i { display: block; height: 100%; border-radius: 999px; transition: width .6s cubic-bezier(.22,1,.36,1); box-shadow: 0 0 8px var(--glow, transparent); }
.score-bar.c-excellent i { background: linear-gradient(90deg, #059669, #34d399); --glow: rgba(16,185,129,.5); }
.score-bar.c-good i { background: linear-gradient(90deg, #0891b2, #22d3ee); --glow: rgba(6,182,212,.5); }
.score-bar.c-marginal i { background: linear-gradient(90deg, #d97706, #fbbf24); --glow: rgba(245,158,11,.5); }
.score-bar.c-poor i { background: linear-gradient(90deg, #e11d48, #fb7185); --glow: rgba(244,63,94,.5); }
/* Legend dots */
.legend-item { display: inline-flex; align-items: center; gap: .35rem; font-family: var(--mono); }
.legend-item .dot { width: 10px; height: 10px; border-radius: 999px; display: inline-block; }
.legend-item .dot.c-excellent { background: #34d399; box-shadow: 0 0 6px rgba(16,185,129,.6); }
.legend-item .dot.c-good { background: #22d3ee; box-shadow: 0 0 6px rgba(6,182,212,.6); }
.legend-item .dot.c-marginal { background: #fbbf24; box-shadow: 0 0 6px rgba(245,158,11,.6); }
.legend-item .dot.c-poor { background: #fb7185; box-shadow: 0 0 6px rgba(244,63,94,.6); }

/* Pagination */
.pagination { display: flex; gap: .35rem; justify-content: center; margin-top: 1.2rem; flex-wrap: wrap; }
.page-btn {
  min-width: 34px; padding: .4rem .55rem; border-radius: 8px; cursor: pointer;
  background: var(--card); border: 1px solid var(--border2); color: var(--muted); font-size: .85rem; font-family: var(--mono);
}
.page-btn:hover { color: var(--text); }
.page-btn.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }
.page-btn:disabled { opacity: .4; cursor: default; }

/* Placeholder pages */
.placeholder { max-width: 760px; margin: 3rem auto; padding: 0 1.5rem; }
.placeholder h1 { font-size: 2rem; margin-bottom: .8rem; }
.placeholder .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 1.6rem; color: var(--muted); }

.footer { border-top: 1px solid var(--border); margin-top: 3rem; padding: 2rem 1.5rem; text-align: center; color: var(--dim); font-size: .88rem; }
@media (max-width: 900px) { .trend-grid, .stats-grid { grid-template-columns: repeat(2, 1fr); } }
"""

JS = """
const COLS = [
  { key: 'rank', label: '#', num: true },
  { key: 'cpu', label: 'CPU' },
  { key: 'model', label: 'Model' },
  { key: 'size', label: 'Size' },
  { key: 'ram_gb', label: 'RAM', num: true },
  { key: 'runtime', label: 'Runtime' },
  { key: 'tok_s', label: 'tok/s', num: true },
  { key: 'ttft_s', label: 'TTFT', num: true },
  { key: 'hw_fit', label: 'HW Fit', num: true, bar: true },
  { key: 'quality', label: 'Quality', num: true, bar: true },
  { key: 'global_score', label: 'Global', num: true, bar: true },
  { key: 'flags', label: 'Flags' },
  { key: 'verdict', label: 'Verdict' },
];
let ROWS = [];
let state = { sortKey: 'global_score', sortDir: 'desc', page: 1, perPage: 25, filters: {}, bestPerConfig: false };

function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function fmt(v, d = 1) { return v == null ? '—' : Number(v).toFixed(d); }
function fmtTtft(v) { return v == null ? '—' : (v >= 10 ? v.toFixed(0) + 's' : v.toFixed(2) + 's'); }
/* Color band for score gauges: >=80 emerald, >=60 cyan, >=40 amber, else rose */
function barClass(v) {
  const s = Number(v ?? 0);
  if (s >= 80) return 'c-excellent';
  if (s >= 60) return 'c-good';
  if (s >= 40) return 'c-marginal';
  return 'c-poor';
}
function barHTML(v, bold = false) {
  const w = Math.max(0, Math.min(100, Number(v ?? 0)));
  const inner = `<span class="score-bar ${barClass(v)}"><i style="width:${w}%"></i></span>`;
  return `${bold ? '<b>' : ''}${inner}${fmt(v, 0)}${bold ? '</b>' : ''}`;
}

async function fetchJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }

function applyFilters(rows) {
  return rows.filter(r => Object.entries(state.filters).every(([k, v]) => {
    if (!v || v === 'all') return true;
    const rv = k === 'runtime' ? (r.backend + ' ' + r.format) : r[k];
    if (rv == null) return false;
    return String(rv).toLowerCase() === v.toLowerCase();
  }));
}
function bestPerConfig(rows) {
  const best = new Map();
  for (const r of rows) {
    const key = r.model + '|' + r.machine + '|' + (r.variant || '');
    const cur = best.get(key);
    if (!cur || (r.global_score || 0) > (cur.global_score || 0)) best.set(key, r);
  }
  return [...best.values()];
}
function sortRows(rows) {
  const dir = state.sortDir === 'asc' ? 1 : -1;
  return rows.slice().sort((a, b) => {
    let av = a[state.sortKey], bv = b[state.sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'string') return dir * av.localeCompare(bv);
    return dir * (av - bv);
  });
}

function renderTable() {
  const body = document.getElementById('lb-body');
  let rows = applyFilters(ROWS);
  if (state.bestPerConfig) rows = bestPerConfig(rows);
  rows = sortRows(rows);
  document.getElementById('result-count').textContent = rows.length + ' results';

  const pages = Math.max(1, Math.ceil(rows.length / state.perPage));
  if (state.page > pages) state.page = pages;
  const slice = rows.slice((state.page - 1) * state.perPage, state.page * state.perPage);

  if (!slice.length) {
    body.innerHTML = '<tr><td colspan="13" style="text-align:center;padding:2rem;color:var(--dim)">No results — the leaderboard fills automatically as soon as the first V0.3 benchmark run completes (auto-refresh 30s).</td></tr>';
  } else {
    body.innerHTML = slice.map(r => `
      <tr>
        <td class="num">${r.rank ?? '—'}</td>
        <td>${esc(r.cpu)}</td>
        <td class="model-cell" title="${esc(r.model)}">${esc(r.model)}</td>
        <td class="mono">${esc(r.size)}</td>
        <td class="num">${r.ram_gb == null ? '—' : r.ram_gb + ' GB'}</td>
        <td class="mono" style="font-size:.8rem">${esc(r.backend)}<br><span style="color:var(--dim)">${esc(r.format)}</span></td>
        <td class="num">${fmt(r.tok_s)}</td>
        <td class="num">${fmtTtft(r.ttft_s)}</td>
        <td class="num">${barHTML(r.hw_fit)}</td>
        <td class="num">${r.quality == null ? '—' : barHTML(r.quality)}</td>
        <td class="num">${barHTML(r.global_score, true)}</td>
        <td>${(r.flags || []).map(f => `<span class="flag">${esc(f)}</span>`).join('') || '—'}</td>
        <td><span class="badge v-${esc(r.verdict).replace(/ /g, '')}">${esc(r.verdict)}</span></td>
      </tr>`).join('');
  }

  // header arrows
  document.querySelectorAll('#lb-head th').forEach(th => {
    const k = th.dataset.key;
    const arrow = th.querySelector('.arrow');
    if (k === state.sortKey) arrow.textContent = state.sortDir === 'asc' ? '↑' : '↓';
    else arrow.textContent = '';
  });

  // pagination
  const pg = document.getElementById('pagination');
  let html = `<button class="page-btn" ${state.page <= 1 ? 'disabled' : ''} onclick="goPage(${state.page - 1})">‹</button>`;
  for (let p = 1; p <= pages; p++) {
    if (pages > 7 && Math.abs(p - state.page) > 2 && p !== 1 && p !== pages) {
      if (p === 2 || p === pages - 1) html += '<span style="align-self:center;color:var(--dim)">…</span>';
      continue;
    }
    html += `<button class="page-btn ${p === state.page ? 'active' : ''}" onclick="goPage(${p})">${p}</button>`;
  }
  html += `<button class="page-btn" ${state.page >= pages ? 'disabled' : ''} onclick="goPage(${state.page + 1})">›</button>`;
  pg.innerHTML = html;
}
function goPage(p) { state.page = p; renderTable(); }

function renderTrending(t) {
  const col = (title, items) => `
    <div class="trend-col"><h3>${title}</h3>
      ${items && items.length ? items.map((x, i) => `
        <div class="trend-item"><span class="rk">${i + 1}</span><a class="nm" href="#" title="${esc(x.name)}">${esc(x.name)}</a>
        <span class="score-bar mini ${barClass(x.score)}" style="width:48px;flex:none"><i style="width:${Math.max(0, Math.min(100, x.score || 0))}%"></i></span><span class="sc">${x.score}</span></div>`).join('')
      : '<div class="empty">No data yet</div>'}
    </div>`;
  document.getElementById('trend-grid').innerHTML =
    col('Top Models', t.top_models) + col('Top Machines', t.top_machines) + col('Top CPUs', t.top_cpus);
}

function renderStats(s) {
  document.querySelectorAll('.stat-card .num').forEach(el => { el.textContent = '0'; });
  const targets = [s.total_runs, s.unique_models, s.model_families, s.unique_cpus];
  document.querySelectorAll('.stat-card .num').forEach((el, i) => {
    const target = targets[i] || 0; const t0 = performance.now();
    (function tick(now) {
      const p = Math.min(1, (now - t0) / 600);
      el.textContent = Math.round(target * p);
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  });
}

async function loadAll() {
  try {
    const [lb, trend, stats] = await Promise.all([
      fetchJSON('/api/leaderboard'), fetchJSON('/api/trending'), fetchJSON('/api/stats')
    ]);
    ROWS = lb;
    renderTable();
    renderTrending(trend);
    renderStats(stats);
    document.getElementById('updated-at').textContent = 'updated ' + new Date().toLocaleTimeString();
  } catch (e) { console.error(e); }
}

function initFilters() {
  fetchJSON('/api/filters').then(f => {
    const defs = [
      ['f_family', f.families, 'All families'],
      ['f_model', f.models, 'All models'],
      ['f_size', f.sizes, 'All sizes'],
      ['f_quant', f.quants, 'All quants'],
      ['f_verdict', f.verdicts, 'All verdicts'],
      ['f_cpu', f.cpus, 'All CPUs'],
      ['f_machine', f.machines, 'All machines'],
      ['f_arch', f.architectures, 'All architectures'],
      ['f_os', f.os, 'All OS'],
      ['f_ram', f.ram, 'All RAM'],
      ['f_backend', f.backends, 'All backends'],
      ['f_format', f.formats, 'All formats'],
    ];
    for (const [id, vals, label] of defs) {
      const sel = document.getElementById(id);
      if (!sel) continue;
      sel.innerHTML = `<option value="all">${label}</option>` + vals.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
      sel.onchange = () => { state.filters[id.replace('f_', '')] = sel.value === 'all' ? '' : sel.value; state.page = 1; renderTable(); };
    }
  });
}

function copyCmd(btn) {
  const txt = btn.closest('.cmd-block').querySelector('.cmd').textContent;
  navigator.clipboard.writeText(txt).then(() => { btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = 'Copy', 1500); });
}

// sort headers
document.querySelectorAll('#lb-head th[data-key]').forEach(th => {
  th.onclick = () => {
    const k = th.dataset.key;
    if (state.sortKey === k) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    else { state.sortKey = k; state.sortDir = COLS.find(c => c.key === k)?.num ? 'desc' : 'asc'; }
    renderTable();
  };
});
document.getElementById('best-per-config').onchange = e => { state.bestPerConfig = e.target.checked; state.page = 1; renderTable(); };
document.querySelectorAll('.copy-btn').forEach(b => b.onclick = () => copyCmd(b));

initFilters();
loadAll();
setInterval(loadAll, 30000); // auto-refresh: new v03 runs appear within 30s
"""

DASHBOARD_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nexus-Bench — Leaderboard</title>
<style>{CSS}</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="/"><span class="mark">N</span>Nexus-Bench</a>
  <a href="/" class="active">Leaderboard</a>
  <a href="/my-benchmarks">My Benchmarks</a>
  <a href="/methodology">Methodology</a>
  <a href="/blog">Blog</a>
  <a href="/contributors">Contributors</a>
  <a href="/founding" style="color:var(--accent)">Founding</a>
  <span class="spacer"></span>
  <button class="btn primary" onclick="location.href='/methodology'">Get started</button>
  <button class="btn" onclick="location.href='/blog'">Blog</button>
</nav>

<section class="hero">
  <h1>Leaderboard</h1>
  <p class="sub">Real benchmarks from real hardware. Compare local LLM performance across different setups.</p>
  <div class="cmd-block">
    <span class="cmd">$ python -m agent_llm_bench_v03 run --profile quick</span>
    <button class="copy-btn" type="button">Copy</button>
  </div>
  <p class="note">Requires a registered Nexus node with llama-server running (Ollama-compatible endpoint).</p>
  <div class="cmd-block">
    <span class="cmd">$ python -m agent_llm_bench_v03 run --profile quick --model &lt;name&gt;</span>
    <button class="copy-btn" type="button">Copy</button>
  </div>
</section>

<div class="wrap">

  <div class="panel">
    <h2>Trending <span class="pill">Last 7 days</span></h2>
    <div class="trend-grid" id="trend-grid"></div>
  </div>

  <div class="stats-grid">
    <div class="stat-card"><div class="num">0</div><div class="lbl">total runs</div></div>
    <div class="stat-card"><div class="num">0</div><div class="lbl">unique models</div></div>
    <div class="stat-card"><div class="num">0</div><div class="lbl">model families</div></div>
    <div class="stat-card"><div class="num">0</div><div class="lbl">unique CPUs</div></div>
  </div>

  <div class="panel">
    <h2>Get notified when new models &amp; hardware are benchmarked</h2>
    <div class="notify">
      <input type="email" placeholder="you@example.com">
      <button class="btn primary" onclick="this.textContent='Subscribed ✓'">Notify me</button>
    </div>
  </div>

  <div class="filter-bar">
    <select id="f_family"></select>
    <select id="f_model"></select>
    <select id="f_size"></select>
    <select id="f_quant"></select>
    <select id="f_verdict"></select>
    <select id="f_cpu"></select>
    <select id="f_machine"></select>
    <select id="f_arch"></select>
    <select id="f_os"></select>
    <select id="f_ram"></select>
    <select id="f_backend"></select>
    <select id="f_format"></select>
    <label class="toggle"><input type="checkbox" id="best-per-config"> Best per config</label>
    <span class="result-count" id="result-count">0 results</span>
  </div>

  <div class="table-wrap">
    <table>
      <thead id="lb-head">
        <tr>
          <th data-key="rank">#<span class="arrow"></span></th>
          <th data-key="cpu">CPU<span class="arrow"></span></th>
          <th data-key="model">Model<span class="arrow"></span></th>
          <th data-key="size">Size<span class="arrow"></span></th>
          <th data-key="ram_gb" class="num">RAM<span class="arrow"></span></th>
          <th data-key="runtime">Runtime<span class="arrow"></span></th>
          <th data-key="tok_s" class="num">tok/s<span class="arrow"></span></th>
          <th data-key="ttft_s" class="num">TTFT<span class="arrow"></span></th>
          <th data-key="hw_fit" class="num">HW Fit<span class="arrow"></span></th>
          <th data-key="quality" class="num">Quality<span class="arrow"></span></th>
          <th data-key="global_score" class="num">Global<span class="arrow"></span></th>
          <th data-key="flags">Flags<span class="arrow"></span></th>
          <th data-key="verdict">Verdict<span class="arrow"></span></th>
        </tr>
      </thead>
      <tbody id="lb-body"><tr><td colspan="13" style="text-align:center;padding:2rem;color:var(--dim)">Loading…</td></tr></tbody>
    </table>
  </div>

  <div class="pagination" id="pagination"></div>

  <p style="color:var(--dim);font-size:.8rem;margin-top:.8rem;text-align:center">
    <span class="legend-item"><span class="dot c-excellent"></span>EXCELLENT ≥ 80</span>&nbsp;&nbsp;
    <span class="legend-item"><span class="dot c-good"></span>GOOD ≥ 60</span>&nbsp;&nbsp;
    <span class="legend-item"><span class="dot c-marginal"></span>MARGINAL ≥ 40</span>&nbsp;&nbsp;
    <span class="legend-item"><span class="dot c-poor"></span>NOT RECOMMENDED &lt; 40</span>
  </p>
  <p style="color:var(--dim);font-size:.8rem;margin-top:.4rem;text-align:center" id="updated-at"></p>
</div>

<footer class="footer">
  Don't miss new benchmarks — <a href="#" onclick="document.querySelector('.notify input').focus();return false">Notify me</a><br>
  Nexus-Bench V0.3 · local-first LLM benchmarking · port 8083
</footer>

<script>{JS}</script>
</body>
</html>
"""


def placeholder_page(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nexus-Bench — {title}</title>
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
  <a class="logo" href="/"><span class="mark">N</span>Nexus-Bench</a>
  <a href="/">Leaderboard</a>
  <a href="/my-benchmarks">My Benchmarks</a>
  <a href="/methodology">Methodology</a>
  <a href="/blog">Blog</a>
  <a href="/contributors">Contributors</a>
  <a href="/founding" style="color:var(--accent)">Founding</a>
  <span class="spacer"></span>
  <button class="btn primary" onclick="location.href='/'">Get started</button>
</nav>
<div class="placeholder">
  <h1>{title}</h1>
  <div class="card">{body_html}</div>
</div>
</body>
</html>
"""


PAGES = {
    "/methodology": placeholder_page(
        "Methodology",
        "<b>Global Score</b> = 30% × HW-Fit + 70% Quality.<br><br>"
        "HW-Fit (0–100): 50% speed (tok/s) · 20% TTFT · 30% memory efficiency.<br>"
        "Quality (0–100): mean accuracy over agent_llm_bench, BFCL v4, τ²-bench, VitaBench, ToolEval.<br><br>"
        "<b>Verdicts:</b> EXCELLENT ≥ 80 · GOOD ≥ 60 · MARGINAL ≥ 40 · NOT RECOMMENDED &lt; 40.<br><br>"
        "Disqualification (score 0): below minimum speed, TTFT over maximum, load time too long, critical RAM usage.",
    ),
    "/blog": placeholder_page("Blog", "Blog posts about local LLM benchmarking will appear here."),
    "/contributors": placeholder_page("Contributors", "Community contributors and their benchmark hardware will be listed here."),
    "/founding": placeholder_page(
        "Founding",
        "Nexus-Bench is a local-first project: reproducible quick/full/deep benchmark profiles for selecting the best LLM configuration for Hermes-style agent workflows on constrained hardware (12–24 GB VRAM).",
    ),
    "/my-benchmarks": placeholder_page("My Benchmarks", "Your uploaded benchmarks will appear here once the upload pipeline is wired up."),
    "/legal": placeholder_page("Legal", "Legal information placeholder."),
    "/privacy": placeholder_page("Privacy", "Privacy policy placeholder. All data stays local in bench.db — nothing leaves this machine."),
    "/terms": placeholder_page("Terms", "Terms of service placeholder."),
}


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write(f"[dashboard] {self.address_string()} - {format % args}\n")

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                self.send_html(DASHBOARD_HTML)
            elif path == "/api/leaderboard":
                self.send_json(build_leaderboard_rows())
            elif path == "/api/trending":
                self.send_json(build_trending())
            elif path == "/api/stats":
                self.send_json(build_stats())
            elif path == "/api/filters":
                self.send_json(build_filters())
            elif path in PAGES:
                self.send_html(PAGES[path])
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8083
    host = "0.0.0.0"

    # Ensure DB exists and is initialized (idempotent)
    try:
        from agent_llm_bench_v03.storage.database import Database

        db = Database(DB_PATH)
        db.initialize()
        db.close()
    except Exception as e:  # pragma: no cover - stdlib fallback keeps dashboard alive
        sys.stderr.write(f"[dashboard] DB init skipped: {e}\n")

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Nexus-Bench V0.3 Dashboard (MetriLLM-style) running on http://{host}:{port}")
    sys.stderr.write(f"[dashboard] Listening on {host}:{port} — DB: {DB_PATH}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
