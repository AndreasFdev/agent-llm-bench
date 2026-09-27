"""Test that V0.3 NodeRegistry provides compatible legacy NODES dict."""

import pytest

from agent_llm_bench_v03.config.models import SuiteConfig, NodeConfig
from agent_llm_bench_v03.control.registry import NodeRegistry


@pytest.fixture
def sample_config():
    """Create a test suite config matching V0.2 NODES structure."""
    return {
        "nodes": [
            {
                "id": "inf-2",
                "alias": "nexus-bench-inf-2",
                "os": "linux",
                "host": "192.168.188.8",
                "ssh_user": "kime",
                "serving_port": 9292,
                "probe_port": 19292,
                "gpu_slot": "0",
                "model_dir": "/opt/nexus-cluster/llm_models",
                "llama_server_path": "/opt/nexus-cluster/llama.cpp/build/bin/llama-server",
                "llama_swap_config": "/opt/nexus-cluster/llama-swap/config-2.yaml",
                "flash_attention": True,
            },
            {
                "id": "inf-3",
                "alias": "nexus-bench-inf-3",
                "os": "linux",
                "host": "192.168.188.8",
                "ssh_user": "kime",
                "serving_port": 9393,
                "probe_port": 19393,
                "gpu_slot": "1",
                "model_dir": "/opt/nexus-cluster/llm_models",
                "llama_server_path": "/opt/nexus-cluster/llama.cpp/build/bin/llama-server",
                "llama_swap_config": "/opt/nexus-cluster/llama-swap/config-3.yaml",
                "flash_attention": True,
            },
            {
                "id": "inf-1",
                "alias": "nexus-bench-inf-1",
                "os": "windows",
                "host": "192.168.188.7",
                "ssh_user": "kime",
                "serving_port": 9191,
                "probe_port": 19191,
                "gpu_slot": "0",
                "model_dir": "D:\\models",
                "llama_server_path": "D:\\llama.cpp\\llama-server.exe",
                "llama_swap_config": "D:\\llama-swap\\config.yaml",
                "flash_attention": True,
            },
        ]
    }


def test_legacy_dict_structure(sample_config):
    """Legacy dict must have same keys as V0.2 NODES."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)
    legacy = registry.as_legacy_nodes_dict()

    # Must have all 3 nodes
    assert set(legacy.keys()) == {"1", "2", "3"}

    # Check node 2 structure matches V0.2
    node2 = legacy["2"]
    expected_keys = {
        "alias", "db_node", "host", "os", "model_dir",
        "config", "port", "probe_port", "sm_build", "flash_attn", "gpu"
    }
    assert expected_keys.issubset(node2.keys())


def test_legacy_dict_values(sample_config):
    """Legacy dict values must match V0.2 format."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)
    legacy = registry.as_legacy_nodes_dict()

    node2 = legacy["2"]
    assert node2["alias"] == "nexus-bench-inf-2"
    assert node2["db_node"] == "inf-2"
    assert node2["os"] == "linux"
    assert node2["port"] == "9292"  # string in V0.2
    assert node2["probe_port"] == "19292"
    assert node2["flash_attn"] == "on"
    assert node2["gpu"] == "0"

    node1 = legacy["1"]
    assert node1["os"] == "windows"


def test_host_format(sample_config):
    """Host must be in ssh_user@host format like V0.2."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)
    legacy = registry.as_legacy_nodes_dict()

    assert legacy["2"]["host"] == "kime@192.168.188.8"
    assert legacy["1"]["host"] == "kime@192.168.188.7"


def test_node_lookup_by_id(sample_config):
    """Registry must support lookup by node ID."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)

    node = registry.get("inf-2")
    assert node.serving_port == 9292


def test_node_lookup_by_alias(sample_config):
    """Registry must support lookup by alias."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)

    node = registry.get_by_alias("nexus-bench-inf-2")
    assert node.id == "inf-2"


def test_node_lookup_by_legacy_slot(sample_config):
    """Registry must support legacy slot lookup (1, 2, 3)."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)

    node = registry.get_by_legacy_slot("2")
    assert node.id == "inf-2"


def test_endpoint_format(sample_config):
    """Endpoint must be in http://host:port format."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)

    endpoint = registry.endpoint("inf-2")
    assert endpoint == "http://192.168.188.8:9292"


def test_nodes_on_host(sample_config):
    """Must be able to list nodes on the same host."""
    config = SuiteConfig.from_dict(sample_config)
    registry = NodeRegistry.from_suite_config(config)

    linux_nodes = registry.nodes_on_host("192.168.188.8")
    assert len(linux_nodes) == 2


def test_unknown_node_raises():
    """Lookup of unknown node must raise KeyError."""
    config = SuiteConfig.from_dict({
        "nodes": [{
            "id": "inf-2",
            "alias": "nexus-bench-inf-2",
            "os": "linux",
            "host": "192.168.188.8",
            "ssh_user": "kime",
            "serving_port": 9292,
            "probe_port": 19292,
            "gpu_slot": "0",
            "model_dir": "/models",
            "llama_server_path": "/llama-server",
            "llama_swap_config": "/config.yaml",
        }]
    })
    registry = NodeRegistry.from_suite_config(config)

    with pytest.raises(KeyError):
        registry.get("inf-99")
