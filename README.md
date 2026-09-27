# Agent-LLM-Bench V0.3

Agent-LLM-Bench V0.3 is a local-first benchmark platform for selecting the best
LLM configuration for Hermes-style agent workflows on constrained hardware.
It combines a Nexus-specific control plane for multi-node model orchestration
with a generic, reproducible benchmark runner for quick, full and deep
evaluation profiles.

The project is designed around one core question:

Which model, quantization and runtime configuration delivers the best practical
quality for a local agent workload on the available hardware?

## Status

This repository is currently in active implementation.

Completed foundation work:

- V0.3 concept and execution prompts are documented.
- Public project scaffold has been created.
- Initial configuration system for portable node definitions has been added.
- A first typed node registry abstraction has been implemented.
- The first extracted parameter-resolution service has been implemented.
- GitHub-safe repository hygiene files and baseline docs have been added.

Not yet completed:

- real benchmark adapters
- database migration for V0.3 task-level results
- Quick profile orchestration
- dashboard drill-down implementation
- production cutover from V0.2

## Goals

- Optimize local Hermes-agent model selection for quality first, efficiency
	second.
- Support local llama.cpp-style inference on 12-24 GB VRAM systems.
- Keep a reproducible Quick benchmark run in the 20-30 minute range, with a
	hard ceiling of 40 minutes.
- Enforce a per-benchmark default timeout of 300 seconds.
- Provide a local leaderboard and drill-down UI from model to experiment,
	benchmark and task.

## Architecture

V0.3 separates the system into two layers.

### 1. Control Plane

The control plane remains Nexus-specific and is responsible for:

- multi-node orchestration
- Windows and Linux node handling
- GGUF discovery and download
- parameter lookup and effective runtime configuration
- llama-swap configuration and health checks
- active-node lifecycle control

This is the part that gives Agent-LLM-Bench its unique value and should not be
replaced by generic upstream tooling.

### 2. Execution Plane

The execution plane is generic and portable. It will provide:

- benchmark profiles such as smoke, quick, full and deep
- deterministic manifests and reproducibility hashes
- benchmark adapters for external suites
- centralized timeout and process control
- structured result storage with task-level detail

## Why Not Fork MetriLLM

MetriLLM is an important reference for UX, result presentation and lightweight
quality/performance measurement, but it is not the right foundation for Nexus
Bench.

Reasons:

- its public implementation focuses on Ollama and LM Studio
- the metrillm.dev frontend is not fully available as the project basis here
- its scoring model couples hardware fit and quality in a way that does not map
	directly to the Nexus quality-first objective
- Nexus already has a stronger custom control plane for downloads, node
	management and runtime parameter discovery

MetriLLM may still be integrated later as an optional adapter or UX reference.

## External Benchmark Inputs

The current V0.3 plan intentionally builds on a small set of high-value,
versioned benchmark sources:

- `local-agent-benchmark` for agent and tool behavior
- `local_agentic_llm` for selected coding and task fixtures
- BFCL subsets for tool-calling baselines
- instruction-following subsets such as IFEval and IFBench
- Harbor later, only as an optional deep-eval layer

These projects are treated as pinned external inputs, not as the main runtime
or orchestration layer.

## Repository Layout

The implementation is moving toward the following structure:

```text
agent-llm-bench-v03/
├── README.md
├── pyproject.toml
├── .gitignore
├── config/
│   └── nodes.example.yaml
├── docs/
│   ├── architecture_baseline.md
│   ├── security_inventory.md
│   └── third_party_inventory.md
├── src/
│   └── agent_llm_bench_v03/
│       ├── __init__.py
│       ├── control/
│       │   ├── __init__.py
│       │   └── registry.py
│       └── config/
│           ├── __init__.py
│           ├── loader.py
│           └── models.py
└── tests/
│   ├── test_config_loader.py
│   └── test_node_registry.py
```

## Configuration

The public repository must never contain productive node hosts, credentials,
API keys, GGUF URLs or benchmark databases.

Instead:

- tracked example files live under `config/`
- local secrets live in ignored files or environment variables
- the loader validates configuration early and fails loudly

The first implemented configuration artifact is:

- `config/nodes.example.yaml`

It demonstrates the public schema without exposing infrastructure.

## Development Setup

### Requirements

- Python 3.11+
- `pytest` for tests

### Create a Virtual Environment

```bash
cd /opt/nexus-cluster/bench/agent-llm-bench-v03
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

### Run Tests

```bash
pytest
```

## Roadmap

Near-term milestones:

1. Finish Prompt 0 baseline inventory.
2. Finish Prompt 1 public project scaffold and configuration validation.
3. Implement node registry and compatible control-plane facade.
4. Extract artifact download and parameter resolution services.
5. Add process runner, timeout enforcement and suite budget logic.
6. Integrate first benchmark adapters.
7. Extend storage and dashboard.

## Safety and Publication Rules

Before anything from V0.3 is pushed publicly:

- no productive IP addresses
- no usernames or passwords
- no API keys or LiteLLM secrets
- no private model URLs
- no copied production logs or databases
- no opaque local patches to third-party repos without documentation

See:

- `docs/security_inventory.md`
- `docs/third_party_inventory.md`

## Current Scope

Included now:

- project scaffold
- configuration models and validation
- typed node registry
- extracted parameter parsing and hierarchy resolution
- GitHub-safe documentation foundation

Not included yet:

- benchmark execution
- adapter parsing
- schema migrations
- dashboard implementation changes
- Harbor integration

## License and Upstream Notice

This directory is being prepared for public release. License selection and final
third-party notices still need to be finalized before publication.

Until then, treat the code here as implementation-in-progress.
