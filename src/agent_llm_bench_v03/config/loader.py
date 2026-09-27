from __future__ import annotations

from pathlib import Path

import yaml

from .models import SuiteConfig


def load_config(path: str | Path) -> SuiteConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        raise ValueError(f"configuration file is empty: {config_path}")
    return SuiteConfig.from_dict(raw)