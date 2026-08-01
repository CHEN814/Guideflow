from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DiseaseScope:
    """Retrieval scope for one disease within a guideline PDF."""

    key: str
    label: str
    article_ids: List[str]
    module_codes: List[str]


# Shared supportive-care / overview modules that apply across diseases (NCCN).
COMMON_MODULE_CODES: List[str] = ["NHODG", "DIAG", "ABBR", "ST", "CAT"]
COMMON_ARTICLE_IDS: List[str] = ["overview"]

# CSCO shared chapters always included when disease-scoped.
CSCO_COMMON_ARTICLE_IDS: List[str] = [
    "general",
    "pathology",
    "evidence-categories",
    "recommendation-levels",
    "appendix",
    "appendix-1",
    "appendix-2",
    "appendix-3",
    "appendix-4",
]


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


# CSCO-only disease scopes (article_ids only; no NCCN module codes).
CSCO_DISEASE_SCOPES: Dict[str, DiseaseScope] = {
    "all": DiseaseScope(key="all", label="CSCO 全部章节", article_ids=[], module_codes=[]),
    "dlbcl": DiseaseScope(
        key="dlbcl",
        label="弥漫大B细胞淋巴瘤",
        # Keep the main DLBCL chapter only; the primary breast / testicular
        # variants are distinct chapters with their own higher-priority patterns.
        article_ids=["dlbcl"],
        module_codes=[],
    ),
    "fl": DiseaseScope(key="fl", label="滤泡性淋巴瘤", article_ids=["fl"], module_codes=[]),
    "mcl": DiseaseScope(key="mcl", label="套细胞淋巴瘤", article_ids=["mcl"], module_codes=[]),
    "mzl": DiseaseScope(key="mzl", label="边缘区淋巴瘤", article_ids=["mzl"], module_codes=[]),
    "pmbl": DiseaseScope(key="pmbl", label="原发纵隔大B细胞淋巴瘤", article_ids=["pmbl"], module_codes=[]),
    "hgbl": DiseaseScope(key="hgbl", label="高级别B细胞淋巴瘤", article_ids=["hgbl"], module_codes=[]),
    "burkitt": DiseaseScope(key="burkitt", label="伯基特淋巴瘤", article_ids=["burkitt"], module_codes=[]),
    "pcnsl": DiseaseScope(key="pcnsl", label="原发中枢神经系统淋巴瘤", article_ids=["pcnsl"], module_codes=[]),
    "cll": DiseaseScope(key="cll", label="慢性淋巴细胞白血病", article_ids=["cll"], module_codes=[]),
    "ptcl": DiseaseScope(key="ptcl", label="外周T细胞淋巴瘤", article_ids=["ptcl"], module_codes=[]),
    "nktcl": DiseaseScope(key="nktcl", label="结外NK/T细胞淋巴瘤", article_ids=["nktcl"], module_codes=[]),
    "hl": DiseaseScope(key="hl", label="霍奇金淋巴瘤", article_ids=["hl"], module_codes=[]),
    "castleman": DiseaseScope(key="castleman", label="Castleman病", article_ids=["castleman"], module_codes=[]),
    "cutaneous": DiseaseScope(key="cutaneous", label="原发性皮肤淋巴瘤", article_ids=["cutaneous"], module_codes=[]),
    "primary-testicular-dlbcl": DiseaseScope(
        key="primary-testicular-dlbcl",
        label="原发睾丸弥漫大B细胞淋巴瘤",
        article_ids=["primary-testicular-dlbcl"],
        module_codes=[],
    ),
    "primary-breast-dlbcl": DiseaseScope(
        key="primary-breast-dlbcl",
        label="原发乳腺弥漫大B细胞淋巴瘤",
        article_ids=["primary-breast-dlbcl"],
        module_codes=[],
    ),
}


# ASCII-safe word boundaries. Python's ``\b`` treats CJK characters as word
# characters, so ``\bDLBCL\b`` FAILS to match "DLBCL的治疗" (the trailing "的"
# is a word char, so no boundary exists). These lookarounds only treat ASCII
# letters as boundaries, so acronyms match when hugged by Chinese text.
_L = r"(?<![A-Za-z])"   # left boundary before an ASCII acronym
_R = r"(?![A-Za-z])"    # right boundary after an ASCII acronym

# (priority, pattern, scope_key). Higher priority wins when multiple match.
_DISEASE_PATTERNS: List[Tuple[int, re.Pattern[str], str]] = [
    (110, re.compile(rf"原发睾丸|primary\s+testicular|{_L}PTDLBCL{_R}", re.I), "primary-testicular-dlbcl"),
    (110, re.compile(r"原发乳腺|primary\s+breast", re.I), "primary-breast-dlbcl"),
    (105, re.compile(rf"原发中枢|{_L}PCNSL{_R}|primary\s+central\s+nervous", re.I), "pcnsl"),
    (100, re.compile(rf"{_L}DLBCL{_R}|弥漫大\s*B\s*细胞|diffuse\s+large\s+b[- ]?cell", re.I), "dlbcl"),
    (90, re.compile(rf"{_L}PMBL{_R}|原发纵隔|primary\s+mediastinal", re.I), "pmbl"),
    (90, re.compile(rf"{_L}HGBL{_R}|高级别\s*B\s*细胞|high[- ]?grade\s+b[- ]?cell|双打击|triple[- ]?hit", re.I), "hgbl"),
    (85, re.compile(rf"{_L}CLL{_R}|{_L}SLL{_R}|慢性淋巴|小淋巴细胞|chronic\s+lymphocytic", re.I), "cll"),
    (85, re.compile(rf"外周\s*T|{_L}PTCL{_R}|peripheral\s+t[- ]?cell", re.I), "ptcl"),
    (85, re.compile(rf"NK/?T|结外\s*NK|{_L}NKTCL{_R}|extranodal\s+nk", re.I), "nktcl"),
    (85, re.compile(rf"霍奇金|{_L}HL{_R}|Hodgkin", re.I), "hl"),
    (80, re.compile(rf"{_L}FL{_R}|滤泡淋巴瘤|滤泡性淋巴瘤|follicular\s+lymphoma", re.I), "fl"),
    (80, re.compile(rf"{_L}MCL{_R}|套细胞|mantle\s+cell", re.I), "mcl"),
    (80, re.compile(rf"{_L}MZL{_R}|{_L}NMZL{_R}|{_L}SMZL{_R}|{_L}EMZL{_R}|边缘区|marginal\s+zone", re.I), "mzl"),
    (80, re.compile(rf"{_L}BL{_R}|伯基特|burkitt", re.I), "burkitt"),
    (70, re.compile(rf"{_L}PTLD{_R}|移植后淋巴|post[- ]?transplant\s+lymphoproliferative", re.I), "ptld"),
    (70, re.compile(r"Castleman|巨大淋巴结增生", re.I), "castleman"),
    (70, re.compile(r"皮肤淋巴瘤|cutaneous\s+lymphoma|mycosis", re.I), "cutaneous"),
    (70, re.compile(rf"{_L}HIV{_R}|艾滋病相关", re.I), "hiv"),
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


def with_common_modules(scope: DiseaseScope, *, source: str = "nccn") -> DiseaseScope:
    """Merge shared supportive-care modules/articles into a disease scope."""
    if scope.key == "all":
        return scope
    if (source or "nccn").lower() == "csco":
        articles = list(dict.fromkeys([*scope.article_ids, *CSCO_COMMON_ARTICLE_IDS]))
        return replace(scope, module_codes=[], article_ids=articles)
    modules = list(dict.fromkeys([*scope.module_codes, *COMMON_MODULE_CODES]))
    articles = list(dict.fromkeys([*scope.article_ids, *COMMON_ARTICLE_IDS]))
    return replace(scope, module_codes=modules, article_ids=articles)


def parse_source_scope(source_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a retrieval ``source_id`` into ``(article_id, module_code)``."""
    if not source_id:
        return (None, None)
    s = source_id.strip()
    lower = s.lower()
    if lower.startswith("disc-"):
        rest = s[5:]
        m = re.match(r"^(.+?)-p\d+-c\d+$", rest, re.I)
        if m:
            return (m.group(1).lower() or None, None)
        article = rest.split("-", 1)[0].lower()
        return (article or None, None)
    if lower.startswith("ref-"):
        rest = s[4:]
        m = re.match(r"^(.+)-(\d+)$", rest)
        if m:
            return (m.group(1).lower() or None, None)
        article = rest.split("-", 1)[0].lower()
        return (article or None, None)
    if lower.startswith("page-"):
        module = s[5:].split("-", 1)[0].upper()
        return (None, module or None)
    return (None, None)


def source_in_scope(source_id: str, scope: DiseaseScope) -> Optional[bool]:
    """Scope verdict for a single source id."""
    article, module = parse_source_scope(source_id)
    if article is None and module is None:
        return None
    allowed_articles = {a.lower() for a in scope.article_ids}
    allowed_modules = {m.upper() for m in scope.module_codes}
    if article is not None and article in allowed_articles:
        return True
    if module is not None and allowed_modules and module in allowed_modules:
        return True
    return False


def triple_sources_in_scope(source_ids: Sequence[str], scope: Optional[DiseaseScope]) -> Optional[bool]:
    """Aggregate scope verdict for a triple's evidence sources."""
    if scope is None or scope.key == "all" or (not scope.article_ids and not scope.module_codes):
        return True
    verdicts = [source_in_scope(sid, scope) for sid in (source_ids or [])]
    resolved = [v for v in verdicts if v is not None]
    if not resolved:
        return None
    return True if any(resolved) else False


def detect_disease_scope(
    question: str,
    forced_key: Optional[str] = None,
    *,
    source: str = "nccn",
) -> DiseaseScope:
    """Detect disease scope from the question text for the active guideline source."""
    src = (source or "nccn").strip().lower()
    registry = CSCO_DISEASE_SCOPES if src == "csco" else DISEASE_SCOPES

    key = (forced_key or os.getenv("TARGET_DISEASE_SCOPE", "auto") or "auto").strip().lower()
    if key not in ("", "auto"):
        scope = registry.get(key)
        if scope is None:
            scope = DISEASE_SCOPES.get(key)
        if scope is None or (src == "csco" and key not in registry and key not in ("all",)):
            if src == "csco":
                return CSCO_DISEASE_SCOPES["all"]
            known = ", ".join(sorted(registry))
            raise ValueError(f"Unknown disease scope {key!r}. Known: {known}")
        return with_common_modules(scope, source=src) if scope.key != "all" else scope

    text = question or ""
    best: Optional[Tuple[int, str]] = None
    for priority, pattern, scope_key in _DISEASE_PATTERNS:
        if pattern.search(text):
            if best is None or priority > best[0]:
                best = (priority, scope_key)
    if best is None:
        return registry["all"]
    scope = registry.get(best[1])
    if scope is None:
        return registry["all"]
    return with_common_modules(scope, source=src)


def list_disease_scope_keys(source: str = "nccn") -> Sequence[str]:
    registry = CSCO_DISEASE_SCOPES if (source or "nccn").lower() == "csco" else DISEASE_SCOPES
    return sorted(registry)
