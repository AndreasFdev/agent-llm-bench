from __future__ import annotations

from pathlib import Path

import pytest

from agent_llm_bench_v03.config import load_config
from agent_llm_bench_v03.control import NodeRegistry


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
global:
  artifact_root: ./artifacts
  log_root: ./logs
  temp_root: ./tmp
nodes:
  - id: inf-1
    alias: nexus-bench-inf-1
    os: windows
    host: node-1.local
    ssh_user: bench
    serving_port: 9191
    probe_port: 19191
    gpu_slot: "0"
    model_dir: D:\\models\\bench
    llama_server_path: D:\\llama.cpp\\llama-server.exe
    llama_swap_config: D:\\llama-swap\\config.yaml
    flash_attention: true
  - id: inf-2
    alias: nexus-bench-inf-2
    os: linux
    host: node-2.local
    ssh_user: bench
    serving_port: 9292
    probe_port: 19292
    gpu_slot: "0"
    model_dir: /models/bench
    llama_server_path: /opt/llama.cpp/llama-server
    llama_swap_config: /opt/llama-swap/config-9292.yaml
    flash_attention: true
  - id: inf-3
    alias: nexus-bench-inf-3
    os: linux
    host: node-2.local
    ssh_user: bench
    serving_port: 9393
    probe_port: 19393
    gpu_slot: "1"
    model_dir: /models/bench
    llama_server_path: /opt/llama.cpp/llama-server
    llama_swap_config: /opt/llama-swap/config-9393.yaml
    flash_attention: false
""",
        encoding="utf-8",
    )
    return path


def build_registry(tmp_path: Path) -> NodeRegistry:
    config = load_config(write_config(tmp_path))
    return NodeRegistry.from_suite_config(config)


def test_registry_preserves_node_order(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)
    assert registry.ids() == ["inf-1", "inf-2", "inf-3"]


def test_lookup_by_id_and_alias(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)
    assert registry.get("inf-2").alias == "nexus-bench-inf-2"
    assert registry.get_by_alias("nexus-bench-inf-3").id == "inf-3"


def test_lookup_unknown_node_raises_clear_error(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)

    with pytest.raises(KeyError, match="unknown node id"):
        registry.get("missing")

    with pytest.raises(KeyError, match="unknown node alias"):
        registry.get_by_alias("missing")

    with pytest.raises(KeyError, match="unknown legacy node slot"):
        registry.get_by_legacy_slot("9")


def test_endpoints_are_derived_from_node_ports(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)
    assert registry.endpoint("inf-2") == "http://node-2.local:9292"
    assert registry.probe_endpoint("inf-3") == "http://node-2.local:19393"


def test_nodes_on_same_host_are_grouped(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)
    nodes = registry.nodes_on_host("node-2.local")
    assert [node.id for node in nodes] == ["inf-2", "inf-3"]


def test_legacy_slot_lookup_uses_v0_2_style_slot_numbers(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)

    assert registry.legacy_slot(registry.get("inf-1")) == "1"
    assert registry.get_by_legacy_slot("2").alias == "nexus-bench-inf-2"


def test_legacy_nodes_dict_shape(tmp_path: Path) -> None:
    registry = build_registry(tmp_path)
    legacy = registry.as_legacy_nodes_dict()

    assert legacy["1"]["host"] == "bench@node-1.local"
    assert legacy["2"]["port"] == "9292"
    assert legacy["3"]["gpu"] == "1"
    assert legacy["3"]["flash_attn"] == "off"
    assert legacy["2"]["db_node"] == "inf-2"