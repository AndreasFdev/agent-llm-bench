# Security Inventory

Status: initial public-release hygiene baseline.

## Rules

The V0.3 public repository must not contain:

- productive IP addresses
- SSH usernames/passwords
- API keys or LiteLLM secrets
- private model URLs
- benchmark databases from production
- copied production logs
- local diagnostic helper scripts with credentials

## Current Safe Files Added

- `README.md`
- `.gitignore`
- `pyproject.toml`
- `config/nodes.example.yaml`
- `src/agent_llm_bench_v03/config/*`
- `tests/test_config_loader.py`

## Current Review Notes

- `config/nodes.example.yaml` uses placeholder hosts and users.
- No production paths, secrets or benchmark databases were copied into the new
  V0.3 package files created in this step.

## Observed Sensitive Sources in V0.2

The following sensitive or infrastructure-specific patterns were observed in
the active V0.2 codebase and must remain out of public V0.3 examples:

- embedded SSH targets in `bench/model_harness.py`
- Windows and Linux absolute runtime paths in `bench/model_harness.py`
- llama-swap production config paths in `bench/model_harness.py`
- default OpenAI-compatible base URL in `bench/suite_lib.sh`
- local extraction of the LiteLLM `master_key` in `bench/suite_lib.sh`
- local tokenizer paths in `bench/model_harness.py` and `bench/suite_lib.sh`

## Publication Constraint

Public V0.3 examples may describe the shape of configuration but must never
embed the real values discovered in V0.2.

## Required Later Checks

- scan future config loaders and adapters for path leaks
- scan test fixtures for copied production raw_json payloads
- scan dashboard examples for embedded hostnames
- scan commit history before first public push
- scan generated manifests and artifact names for endpoint leakage