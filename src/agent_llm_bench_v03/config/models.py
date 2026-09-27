from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VALID_OSES = {"linux", "windows"}


def _require_string(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must not be empty")
    return value.strip()


def _require_port(data: dict, key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < 1 or value > 65535:
        raise ValueError(f"{key} must be between 1 and 65535")
    return value


@dataclass(slots=True)
class GlobalPaths:
    artifact_root: Path = Path("./artifacts")
    log_root: Path = Path("./logs")
    temp_root: Path = Path("./tmp")
    database_path: Path = Path("./bench.db")

    @classmethod
    def from_dict(cls, data: dict | None) -> "GlobalPaths":
        data = data or {}
        return cls(
            artifact_root=Path(data.get("artifact_root", "./artifacts")),
            log_root=Path(data.get("log_root", "./logs")),
            temp_root=Path(data.get("temp_root", "./tmp")),
            database_path=Path(data.get("database_path", "./bench.db")),
        )


@dataclass(slots=True)
class DashboardConfig:
    port: int = 8083
    host: str = "0.0.0.0"

    @classmethod
    def from_dict(cls, data: dict | None) -> "DashboardConfig":
        data = data or {}
        return cls(
            port=_require_port({"port": data.get("port", 8083)}, "port"),
            host=data.get("host", "0.0.0.0"),
        )


@dataclass(slots=True)
class NodeConfig:
    id: str
    alias: str
    os: str
    host: str
    ssh_user: str
    serving_port: int
    probe_port: int
    gpu_slot: str
    model_dir: str
    llama_server_path: str
    llama_swap_config: str
    flash_attention: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "NodeConfig":
        node_os = _require_string(data, "os")
        if node_os not in VALID_OSES:
            raise ValueError(f"os must be one of {sorted(VALID_OSES)}")

        serving_port = _require_port(data, "serving_port")
        probe_port = _require_port(data, "probe_port")
        if serving_port == probe_port:
            raise ValueError("serving_port and probe_port must differ")

        return cls(
            id=_require_string(data, "id"),
            alias=_require_string(data, "alias"),
            os=node_os,
            host=_require_string(data, "host"),
            ssh_user=_require_string(data, "ssh_user"),
            serving_port=serving_port,
            probe_port=probe_port,
            gpu_slot=_require_string(data, "gpu_slot"),
            model_dir=_require_string(data, "model_dir"),
            llama_server_path=_require_string(data, "llama_server_path"),
            llama_swap_config=_require_string(data, "llama_swap_config"),
            flash_attention=bool(data.get("flash_attention", True)),
        )


@dataclass(slots=True)
class SuiteConfig:
    global_paths: GlobalPaths
    nodes: list[NodeConfig]
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "SuiteConfig":
        if not isinstance(data, dict):
            raise ValueError("configuration root must be a mapping")

        nodes_raw = data.get("nodes")
        if not isinstance(nodes_raw, list) or not nodes_raw:
            raise ValueError("at least one node is required")

        nodes = [NodeConfig.from_dict(item) for item in nodes_raw]
        ids = [node.id for node in nodes]
        aliases = [node.alias for node in nodes]
        host_ports = [(node.host, node.serving_port) for node in nodes]

        if len(ids) != len(set(ids)):
            raise ValueError("node ids must be unique")
        if len(aliases) != len(set(aliases)):
            raise ValueError("node aliases must be unique")
        if len(host_ports) != len(set(host_ports)):
            raise ValueError("serving_port must be unique per host")

        return cls(
            global_paths=GlobalPaths.from_dict(data.get("global")),
            nodes=nodes,
            dashboard=DashboardConfig.from_dict(data.get("dashboard")),
        )
