from __future__ import annotations

from dataclasses import dataclass
import re

from agent_llm_bench_v03.config.models import NodeConfig, SuiteConfig


@dataclass(slots=True)
class NodeRegistry:
    """Typed access layer over configured Nexus nodes."""

    _nodes_by_id: dict[str, NodeConfig]
    _node_ids_in_order: list[str]

    @classmethod
    def from_suite_config(cls, config: SuiteConfig) -> "NodeRegistry":
        nodes_by_id = {node.id: node for node in config.nodes}
        node_ids_in_order = [node.id for node in config.nodes]
        return cls(_nodes_by_id=nodes_by_id, _node_ids_in_order=node_ids_in_order)

    def ids(self) -> list[str]:
        return list(self._node_ids_in_order)

    def all(self) -> list[NodeConfig]:
        return [self._nodes_by_id[node_id] for node_id in self._node_ids_in_order]

    def get(self, node_id: str) -> NodeConfig:
        try:
            return self._nodes_by_id[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown node id: {node_id}") from exc

    def get_by_alias(self, alias: str) -> NodeConfig:
        for node in self.all():
            if node.alias == alias:
                return node
        raise KeyError(f"unknown node alias: {alias}")

    def get_by_legacy_slot(self, slot: str) -> NodeConfig:
        for node in self.all():
            if self.legacy_slot(node) == slot:
                return node
        raise KeyError(f"unknown legacy node slot: {slot}")

    def endpoint(self, node_id: str, scheme: str = "http") -> str:
        node = self.get(node_id)
        return f"{scheme}://{node.host}:{node.serving_port}"

    def probe_endpoint(self, node_id: str, scheme: str = "http") -> str:
        node = self.get(node_id)
        return f"{scheme}://{node.host}:{node.probe_port}"

    def nodes_on_host(self, host: str) -> list[NodeConfig]:
        return [node for node in self.all() if node.host == host]

    def legacy_slot(self, node: NodeConfig) -> str:
        candidates = (node.id, node.alias)
        for candidate in candidates:
            match = re.search(r"(?:^|[-_])inf-(\d+)$", candidate)
            if match:
                return match.group(1)
            match = re.search(r"(?:^|[-_])(\d+)$", candidate)
            if match:
                return match.group(1)
        raise ValueError(
            f"cannot derive legacy node slot from id={node.id!r} alias={node.alias!r}"
        )

    def as_legacy_nodes_dict(self) -> dict[str, dict[str, str]]:
        legacy: dict[str, dict[str, str]] = {}
        for node in self.all():
            legacy[self.legacy_slot(node)] = {
                "alias": node.alias,
                "db_node": node.id,
                "host": f"{node.ssh_user}@{node.host}",
                "os": node.os,
                "model_dir": node.model_dir,
                "config": node.llama_swap_config,
                "port": str(node.serving_port),
                "probe_port": str(node.probe_port),
                "sm_build": node.llama_server_path,
                "flash_attn": "on" if node.flash_attention else "off",
                "gpu": node.gpu_slot,
            }
        return legacy