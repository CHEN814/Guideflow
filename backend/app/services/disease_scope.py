from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class DiseaseScope:
    """Retrieval scope for one disease within the shared NCCN B-cell lymphoma PDF."""

    key: str
    label: str
    article_ids: List[str]
    module_codes: List[str]


# Registry for multi-disease support. Only one scope is active per run (see TARGET_DISEASE_SCOPE).
DISEASE_SCOPES: Dict[str, DiseaseScope] = {
    "dlbcl": DiseaseScope(
        key="dlbcl",
        label="Diffuse Large B-Cell Lymphoma",
        article_ids=["dlbcl"],
        module_codes=["BCEL"],
    ),
}


def get_active_disease_scope() -> DiseaseScope:
    key = os.getenv("TARGET_DISEASE_SCOPE", "dlbcl").strip().lower()
    scope = DISEASE_SCOPES.get(key)
    if scope is None:
        known = ", ".join(sorted(DISEASE_SCOPES))
        raise ValueError(f"Unknown TARGET_DISEASE_SCOPE={key!r}. Known scopes: {known}")
    return scope
