# Architecture Baseline

Status: initial baseline for Prompt 0 and Prompt 1.

## Scope

This document records the current V0.3 starting point before deeper extraction
from V0.2 begins.

## Current Implementation Position

- V0.2 remains the active implementation under `/opt/nexus-cluster/bench`.
- `agent-llm-bench-v03` is currently a new project root for the portable V0.3
  implementation.
- The first implemented V0.3 concern is public-safe configuration loading and
  validation.
- A first typed node registry abstraction is now implemented.

## Observed V0.2 Control-Plane Facts

The current V0.2 harness keeps a hardcoded control-plane source of truth in
`bench/model_harness.py`.

Observed runtime constants:

- `TASK_LIMIT_PCT = 10`
- `PROBE_START_TIMEOUT_SEC = 600`
- `HEALTH_REQUEST_TIMEOUT_SEC = 30`
- `PROBE_POLL_INTERVAL_SEC = 5`
- `NODE_JOB_TIMEOUT_SEC = 1800`

Observed node topology:

- `inf-1` / alias `nexus-bench-inf-1`
   - Windows node
   - serving port `9191`
   - probe port `19191`
   - GPU slot `0`
- `inf-2` / alias `nexus-bench-inf-2`
   - Linux node
   - serving port `9292`
   - probe port `19292`
   - GPU slot `0`
- `inf-3` / alias `nexus-bench-inf-3`
   - Linux node
   - serving port `9393`
   - probe port `19393`
   - GPU slot `1`

Observed V0.2 responsibilities already present:

- todo queue scanning
- GGUF URL extraction
- remote GGUF existence and validity checks
- model download and retry behavior
- parameter resolution hierarchy
- MTP probing
- node selection and reuse of existing nodes
- llama-swap config replacement
- suite script generation and background dispatch

## Observed V0.2 Publication Risks

The active V0.2 code still embeds infrastructure-specific values that must not
be copied into public V0.3 examples.

Examples observed in active code:

- embedded SSH targets in `bench/model_harness.py`
- embedded Windows runtime paths in `bench/model_harness.py`
- embedded Linux llama-swap config paths in `bench/model_harness.py`
- default OpenAI-compatible base URL in `bench/suite_lib.sh`
- local extraction of the LiteLLM `master_key` in `bench/suite_lib.sh`
- local tokenizer and model paths under `/opt/nexus-cluster/bench`

## Intended Layers

1. Control Plane
   - node registry
   - model discovery
   - GGUF download and validation
   - parameter resolution
   - serving configuration and health checks

2. Execution Plane
   - profiles
   - benchmark adapters
   - process/time budget enforcement
   - manifests and result normalization

3. Persistence and API
   - SQLite
   - task-level detail
   - dashboard drill-down

## Initial Implemented Artifacts

- `README.md`
- `.gitignore`
- `pyproject.toml`
- `config/nodes.example.yaml`
- `src/agent_llm_bench_v03/config/models.py`
- `src/agent_llm_bench_v03/config/loader.py`
- `src/agent_llm_bench_v03/control/registry.py`
- `tests/test_config_loader.py`
- `tests/test_node_registry.py`

## Next Extraction Target

The next implementation milestone should be a compatible control-plane facade
derived from the V0.2 `NODES` structure, followed by extraction of model
download and parameter-resolution services.