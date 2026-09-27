from __future__ import annotations

from pathlib import Path

from agent_llm_bench_v03.control.parameters import ParameterResolver, parse_param_text, resolve_family


FALLBACK = {"ctx-size": "65536", "batch-size": "1024"}


def test_parse_json_with_trailing_comma() -> None:
    parsed = parse_param_text(
        '{\n  "temp": 0.6,\n  "top_p": 0.95,\n  "_disabled": true,\n}'
    )
    assert parsed == {"temp": "0.6", "top-p": "0.95"}


def test_parse_cmd_block_and_env() -> None:
    parsed = parse_param_text(
        """
cmd: |
  --ctx-size 65536
  --batch-size 1024
  --jinja
ttl: 180
HSA_OVERRIDE_GFX_VERSION=11.0.0
"""
    )
    assert parsed["ctx-size"] == "65536"
    assert parsed["batch-size"] == "1024"
    assert parsed["jinja"] == "on"
    assert parsed["env:HSA_OVERRIDE_GFX_VERSION"] == "11.0.0"


def test_resolve_family_known_and_unknown() -> None:
    assert resolve_family("Qwen3.8-27B-Fable.gguf") == "qwen3.8"
    assert resolve_family("gemma-4-12b-it-Q5_K_M.gguf") == "gemma4"
    assert resolve_family("unknown-model.gguf") == ""


def test_resolve_prefers_item_optimal_then_item_preset(tmp_path: Path) -> None:
    params_dir = tmp_path / "params"
    params_dir.mkdir()
    item_dir = tmp_path / "todo"
    item_dir.mkdir()

    (item_dir / "foo.gguf.parms_optimal").write_text('{"temp": 0.2}', encoding="utf-8")
    (item_dir / "foo.gguf.parms").write_text('{"temp": 0.8}', encoding="utf-8")

    resolver = ParameterResolver(params_dir=params_dir, fallback_params=FALLBACK)
    result = resolver.resolve("foo.gguf", item_dir)

    assert result.params == {"temp": "0.2"}
    assert result.source.endswith("foo.gguf.parms_optimal")


def test_resolve_prefers_tuned_then_exact_then_family(tmp_path: Path) -> None:
    params_dir = tmp_path / "params"
    tuned_dir = params_dir / "tuned"
    tuned_dir.mkdir(parents=True)

    (tuned_dir / "Qwen3.8-27B-Fable.gguf_agentic_parm.md").write_text("temp: 0.1", encoding="utf-8")
    (params_dir / "Qwen3.8-27B-Fable_agentic_parm.md").write_text("temp: 0.2", encoding="utf-8")
    (params_dir / "qwen3.8_agentic_parm.md").write_text("temp: 0.3", encoding="utf-8")

    resolver = ParameterResolver(params_dir=params_dir, fallback_params=FALLBACK)
    result = resolver.resolve("Qwen3.8-27B-Fable.gguf")

    assert result.params == {"temp": "0.1"}
    assert "tuned" in result.source


def test_resolve_uses_family_file_when_no_tuned_or_exact(tmp_path: Path) -> None:
    params_dir = tmp_path / "params"
    params_dir.mkdir()
    (params_dir / "qwen3.8_agentic_parm.md").write_text("temp: 0.3", encoding="utf-8")

    resolver = ParameterResolver(params_dir=params_dir, fallback_params=FALLBACK)
    result = resolver.resolve("Qwen3.8-27B-Fable.gguf")

    assert result.params == {"temp": "0.3"}
    assert result.source.endswith("qwen3.8_agentic_parm.md")


def test_resolve_falls_back_when_nothing_found(tmp_path: Path) -> None:
    params_dir = tmp_path / "params"
    params_dir.mkdir()

    resolver = ParameterResolver(params_dir=params_dir, fallback_params=FALLBACK)
    result = resolver.resolve("does-not-exist.gguf")

    assert result.params == FALLBACK
    assert result.source == "FALLBACK_PARAMS"