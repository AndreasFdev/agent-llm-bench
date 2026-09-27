from __future__ import annotations

from pathlib import Path

import pytest

from agent_llm_bench_v03.config import load_config


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
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
    llama_swap_config: /opt/llama-swap/config.yaml
    flash_attention: true
""",
    )

    config = load_config(path)

    assert len(config.nodes) == 2
    assert config.nodes[0].os == "windows"
    assert config.nodes[1].serving_port == 9292


def test_reject_duplicate_node_ids(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
global:
  artifact_root: ./artifacts
  log_root: ./logs
  temp_root: ./tmp
nodes:
  - id: inf-1
    alias: a
    os: linux
    host: h1
    ssh_user: bench
    serving_port: 9191
    probe_port: 19191
    gpu_slot: "0"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
  - id: inf-1
    alias: b
    os: linux
    host: h2
    ssh_user: bench
    serving_port: 9292
    probe_port: 19292
    gpu_slot: "1"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
""",
    )

    with pytest.raises(ValueError, match="node ids must be unique"):
        load_config(path)


def test_reject_duplicate_aliases(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
global:
  artifact_root: ./artifacts
  log_root: ./logs
  temp_root: ./tmp
nodes:
  - id: inf-1
    alias: same
    os: linux
    host: h1
    ssh_user: bench
    serving_port: 9191
    probe_port: 19191
    gpu_slot: "0"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
  - id: inf-2
    alias: same
    os: linux
    host: h2
    ssh_user: bench
    serving_port: 9292
    probe_port: 19292
    gpu_slot: "1"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
""",
    )

    with pytest.raises(ValueError, match="node aliases must be unique"):
        load_config(path)


def test_reject_duplicate_serving_port_on_same_host(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
global:
  artifact_root: ./artifacts
  log_root: ./logs
  temp_root: ./tmp
nodes:
  - id: inf-1
    alias: a
    os: linux
    host: h1
    ssh_user: bench
    serving_port: 9191
    probe_port: 19191
    gpu_slot: "0"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
  - id: inf-2
    alias: b
    os: linux
    host: h1
    ssh_user: bench
    serving_port: 9191
    probe_port: 19292
    gpu_slot: "1"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
""",
    )

    with pytest.raises(ValueError, match="serving_port must be unique per host"):
        load_config(path)


@pytest.mark.parametrize("bad_port", [0, 65536])
def test_reject_invalid_port(tmp_path: Path, bad_port: int) -> None:
    path = write_config(
        tmp_path,
        f"""
global:
  artifact_root: ./artifacts
  log_root: ./logs
  temp_root: ./tmp
nodes:
  - id: inf-1
    alias: a
    os: linux
    host: h1
    ssh_user: bench
    serving_port: {bad_port}
    probe_port: 19191
    gpu_slot: "0"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
""",
    )

    with pytest.raises(ValueError, match="between 1 and 65535"):
        load_config(path)


def test_reject_unknown_os(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
global:
  artifact_root: ./artifacts
  log_root: ./logs
  temp_root: ./tmp
nodes:
  - id: inf-1
    alias: a
    os: mac
    host: h1
    ssh_user: bench
    serving_port: 9191
    probe_port: 19191
    gpu_slot: "0"
    model_dir: /a
    llama_server_path: /b
    llama_swap_config: /c
""",
    )

    with pytest.raises(ValueError):
        load_config(path)


def test_reject_empty_file(tmp_path: Path) -> None:
    path = write_config(tmp_path, "")

    with pytest.raises(ValueError, match="configuration file is empty"):
        load_config(path)