from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


PARAM_KEYS = {
    "jinja",
    "temp",
    "top-p",
    "top-k",
    "repeat-penalty",
    "min-p",
    "presence-penalty",
    "frequency-penalty",
    "ctx-size",
    "batch-size",
    "ubatch-size",
    "threads",
    "n-gpu-layers",
    "n-cpu-moe",
    "override-tensor",
    "tensor-split",
    "split-mode",
    "parallel",
    "flash-attn",
    "conversation",
    "spec-type",
    "model-draft",
    "spec-draft-n-max",
    "spec-draft-p-min",
    "spec-draft-p-split",
    "spec-draft-n-min",
    "cache-type-k",
    "cache-type-v",
    "port",
    "host",
    "no-mmap",
    "mlock",
}

ENV_KEYS = {"HSA_OVERRIDE_GFX_VERSION"}

FAMILY_MAPPING = {
    "gemma-4": "gemma4",
    "ornith-1.5": "ornith-1.5",
    "ornith-1.0": "ornith-1.0",
    "qwen3.5": "qwen3.5",
    "qwen3.6": "qwen3.6",
    "qwen3.8": "qwen3.8",
    "qwen2.5": "qwen2.5",
    "lfm2.5": "lfm2.5",
}


@dataclass(slots=True)
class ParameterResolution:
    params: dict[str, str]
    source: str


def strip_gguf_suffix(model_name: str) -> str:
    return model_name[:-5] if model_name.upper().endswith(".GGUF") else model_name


def resolve_family(model_name: str) -> str:
    slug = strip_gguf_suffix(model_name).lower()
    for prefix, family in FAMILY_MAPPING.items():
        if slug.startswith(prefix):
            return family
    return ""


def parse_param_text(text: str) -> dict[str, str]:
    text = text.strip()
    if not text:
        return {}

    if text.startswith("{") and text.endswith("}"):
        try:
            json_lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
            json_text = "\n".join(json_lines)
            json_text = re.sub(r",\s*([}\]])", r"\1", json_text)
            data = json.loads(json_text)
            return {
                str(key).replace("_", "-"): str(value)
                for key, value in data.items()
                if key != "_disabled"
            }
        except Exception:
            pass

    found: dict[str, str] = {}
    in_cmd = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue

        if line.startswith("cmd:") and "|" in line:
            in_cmd = True
            continue

        if in_cmd and any(line.startswith(key) for key in ("ttl:", "name:", "description:", "env:")):
            in_cmd = False

        if in_cmd:
            if line.startswith("--"):
                rest = line[2:].strip()
                parts = rest.split(None, 1)
                flag = parts[0]
                value = parts[1].rstrip("\\").strip() if len(parts) > 1 else ""
                found[flag] = value or "on"
            continue

        if line.startswith("--"):
            rest = line[2:].strip()
            parts = rest.split(None, 1)
            flag = parts[0]
            value = parts[1].rstrip("\\").strip() if len(parts) > 1 else ""
            found[flag] = value or "on"
            continue

        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().replace("_", "-")
            value = value.strip().strip('"').strip("'")
            if key in PARAM_KEYS or key in {
                "temp",
                "top-p",
                "top-k",
                "min-p",
                "repeat-penalty",
                "presence-penalty",
                "cache-type-k",
                "cache-type-v",
                "n-cpu-moe",
            }:
                found[key] = value

    for env_key in ENV_KEYS:
        match = re.search(rf"{re.escape(env_key)}=(\S+)", text)
        if match:
            found[f"env:{env_key}"] = match.group(1)

    return found


def find_item_param_file(item_path: Path, model_name: str, suffix: str) -> Path:
    stem = strip_gguf_suffix(model_name)
    candidates = [item_path / f"{model_name}{suffix}", item_path / f"{stem}{suffix}"]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return candidates[0]


def _parse_file(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    return parse_param_text(path.read_text(encoding="utf-8", errors="ignore"))


class ParameterResolver:
    def __init__(self, params_dir: Path, fallback_params: dict[str, str]) -> None:
        self.params_dir = params_dir
        self.fallback_params = dict(fallback_params)

    def resolve(self, model_name: str, item_path: Path | None = None) -> ParameterResolution:
        stem = strip_gguf_suffix(model_name)

        search_dir = item_path if item_path and item_path.is_dir() else item_path.parent if item_path else None
        if search_dir:
            optimal_file = find_item_param_file(search_dir, model_name, ".parms_optimal")
            params = _parse_file(optimal_file)
            if params:
                return ParameterResolution(params=params, source=str(optimal_file))

            preset_file = find_item_param_file(search_dir, model_name, ".parms")
            params = _parse_file(preset_file)
            if params:
                return ParameterResolution(params=params, source=str(preset_file))

        tuned_candidates = [
            self.params_dir / "tuned" / f"{model_name}_agentic_parm.md",
            self.params_dir / "tuned" / f"{stem}_agentic_parm.md",
            self.params_dir / "tuned" / f"{stem}_node2_agentic_agentic_parm.md",
            self.params_dir / "tuned" / f"{stem}_agentic_agentic_parm.md",
        ]
        for candidate in tuned_candidates:
            params = _parse_file(candidate)
            if params:
                return ParameterResolution(params=params, source=str(candidate))

        direct_candidates = [
            self.params_dir / f"{model_name}_agentic_parm.md",
            self.params_dir / f"{stem}_agentic_parm.md",
        ]
        for candidate in direct_candidates:
            params = _parse_file(candidate)
            if params:
                return ParameterResolution(params=params, source=str(candidate))

        family = resolve_family(model_name)
        if family:
            family_file = self.params_dir / f"{family}_agentic_parm.md"
            params = _parse_file(family_file)
            if params:
                return ParameterResolution(params=params, source=str(family_file))

        return ParameterResolution(params=dict(self.fallback_params), source="FALLBACK_PARAMS")