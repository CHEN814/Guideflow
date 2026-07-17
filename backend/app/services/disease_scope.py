from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DiseaseScope:
    """Retrieval scope for one disease within the shared NCCN B-cell lymphoma PDF."""

    key: str
    label: str
    article_ids: List[str]
    module_codes: List[str]


# Shared supportive-care / overview modules that apply across diseases.
COMMON_MODULE_CODES: List[str] = ["NHODG", "DIAG", "ABBR", "ST", "CAT"]
COMMON_ARTICLE_IDS: List[str] = ["overview"]


# Registry for multi-disease support. Key "all" means no disease filter.
DISEASE_SCOPES: Dict[str, DiseaseScope] = {
    "all": DiseaseScope(
        key="all",
        label="All B-Cell Lymphomas",
        article_ids=[],
        module_codes=[],
    ),
    "dlbcl": DiseaseScope(
        key="dlbcl",
        label="Diffuse Large B-Cell Lymphoma",
        article_ids=["dlbcl"],
        module_codes=["BCEL"],
    ),
    "fl": DiseaseScope(
        key="fl",
        label="Follicular Lymphoma",
        article_ids=["fl"],
        module_codes=["FOLL"],
    ),
    "mcl": DiseaseScope(
        key="mcl",
        label="Mantle Cell Lymphoma",
        article_ids=["mcl"],
        module_codes=["MANT"],
    ),
    "mzl": DiseaseScope(
        key="mzl",
        label="Marginal Zone Lymphoma",
        article_ids=["mzl"],
        module_codes=["MZL", "NMZL", "SMZL", "EMZLG", "EMZLNG"],
    ),
    "pmbl": DiseaseScope(
        key="pmbl",
        label="Primary Mediastinal B-Cell Lymphoma",
        article_ids=["pmbl"],
        module_codes=["PMBL"],
    ),
    "hgbl": DiseaseScope(
        key="hgbl",
        label="High-Grade B-Cell Lymphoma",
        article_ids=["hgbl"],
        module_codes=["HGBL", "HTBCEL"],
    ),
    "burkitt": DiseaseScope(
        key="burkitt",
        label="Burkitt Lymphoma",
        article_ids=["burkitt"],
        module_codes=["BURK"],
    ),
    "ptld": DiseaseScope(
        key="ptld",
        label="Post-Transplant Lymphoproliferative Disease",
        article_ids=["ptld"],
        module_codes=["PTLD"],
    ),
    "hiv": DiseaseScope(
        key="hiv",
        label="HIV-Related B-Cell Lymphomas",
        article_ids=["hiv-related-b-cell-lymphomas"],
        module_codes=["HIVLYM"],
    ),
    "transform": DiseaseScope(
        key="transform",
        label="Histologic Transformation of Indolent Lymphomas",
        article_ids=["histologic-transformation-of-indolent-lymphomas-to"],
        module_codes=["HTBCEL"],
    ),
}


# (priority, pattern, scope_key). Higher priority wins when multiple match.
_DISEASE_PATTERNS: List[Tuple[int, re.Pattern[str], str]] = [
    (100, re.compile(r"\bDLBCL\b|弥漫大\s*B\s*细胞|diffuse\s+large\s+b[- ]?cell", re.I), "dlbcl"),
    (90, re.compile(r"\bPMBL\b|原发纵隔|primary\s+mediastinal", re.I), "pmbl"),
    (90, re.compile(r"\bHGBL\b|高级别\s*B\s*细胞|high[- ]?grade\s+b[- ]?cell|双打击|triple[- ]?hit", re.I), "hgbl"),
    (80, re.compile(r"\bFL\b|滤泡淋巴瘤|follicular\s+lymphoma", re.I), "fl"),
    (80, re.compile(r"\bMCL\b|套细胞|mantle\s+cell", re.I), "mcl"),
    (80, re.compile(r"\bMZL\b|\bNMZL\b|\bSMZL\b|\bEMZL\b|边缘区|marginal\s+zone", re.I), "mzl"),
    (80, re.compile(r"\bBL\b|伯基特|burkitt", re.I), "burkitt"),
    (70, re.compile(r"\bPTLD\b|移植后淋巴|post[- ]?transplant\s+lymphoproliferative", re.I), "ptld"),
    (70, re.compile(r"\bHIV\b|艾滋病相关", re.I), "hiv"),
    (60, re.compile(r"组织学转化|histologic\s+transformation|转化型", re.I), "transform"),
]


def get_active_disease_scope() -> DiseaseScope:
    """Legacy helper: resolve TARGET_DISEASE_SCOPE env/config value."""
    key = os.getenv("TARGET_DISEASE_SCOPE", "auto").strip().lower()
    if key in ("", "auto"):
        return DISEASE_SCOPES["all"]
    scope = DISEASE_SCOPES.get(key)
    if scope is None:
        known = ", ".join(sorted(DISEASE_SCOPES))
        raise ValueError(f"Unknown TARGET_DISEASE_SCOPE={key!r}. Known scopes: {known}")
    return scope


def with_common_modules(scope: DiseaseScope) -> DiseaseScope:
    """Merge shared supportive-care modules/articles into a disease scope."""
    if scope.key == "all":
        return scope
    modules = list(dict.fromkeys([*scope.module_codes, *COMMON_MODULE_CODES]))
    articles = list(dict.fromkeys([*scope.article_ids, *COMMON_ARTICLE_IDS]))
    return replace(scope, module_codes=modules, article_ids=articles)


def detect_disease_scope(question: str, forced_key: Optional[str] = None) -> DiseaseScope:
    """Detect disease scope from the question text.

    - ``forced_key`` / env override: use that scope (``auto``/`None` => detect).
    - Match disease name/abbreviation => that disease + common modules.
    - No match => ALL (empty filters = whole book).
    """
    key = (forced_key or os.getenv("TARGET_DISEASE_SCOPE", "auto") or "auto").strip().lower()
    if key not in ("", "auto"):
        scope = DISEASE_SCOPES.get(key)
        if scope is None:
            known = ", ".join(sorted(DISEASE_SCOPES))
            raise ValueError(f"Unknown disease scope {key!r}. Known: {known}")
        return with_common_modules(scope) if scope.key != "all" else scope

    text = question or ""
    best: Optional[Tuple[int, str]] = None
    for priority, pattern, scope_key in _DISEASE_PATTERNS:
        if pattern.search(text):
            if best is None or priority > best[0]:
                best = (priority, scope_key)
    if best is None:
        return DISEASE_SCOPES["all"]
    return with_common_modules(DISEASE_SCOPES[best[1]])


def list_disease_scope_keys() -> Sequence[str]:
    return sorted(DISEASE_SCOPES)
