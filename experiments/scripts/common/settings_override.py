from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from backend.app.settings import Settings, load_settings, settings_for_source


def load_arm_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def apply_arm(base: Settings | None, arm: dict[str, Any], source: str = "nccn") -> Settings:
    settings = settings_for_source(source, base or load_settings())
    mapping = {
        "qwen_model": "qwen_model",
        "reranker_model": "reranker_model",
        "enable_vlm": "enable_vlm",
        "routing_mode": "routing_mode",
        "allow_labeled_parametric": "allow_labeled_parametric",
        "relevance_gate_threshold": "relevance_gate_threshold",
        "gate_min_keep": "gate_min_keep",
        "penalize_reference_pages": "penalize_reference_pages",
        "generate_temperature": "generate_temperature",
        "enable_evidence_gating": "enable_evidence_gating",
        "answer_policy": "answer_policy",
    }
    kwargs = {}
    for src, dest in mapping.items():
        if src in arm:
            kwargs[dest] = arm[src]
    if kwargs:
        settings = replace(settings, **kwargs)
    return settings
