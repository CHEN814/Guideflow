"""Load and look up curated journal quality metadata (IF / quartile / tier)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

DEFAULT_YAML = Path(__file__).resolve().parents[2] / "data" / "journal_quality.yaml"

# Unmatched journals get a neutral score — never punish unknowns.
NEUTRAL_TIER = "unknown"
TIER_SCORE = {
    "T0": 1.0,
    "T1": 0.9,
    "T2G": 0.85,
    "T2": 0.75,
    "T3": 0.4,
    NEUTRAL_TIER: 0.55,
}


@dataclass(frozen=True)
class JournalQuality:
    full_name: str
    iso_abbr: str
    jcr_if: Optional[float]
    jcr_quartile: Optional[str]
    cas_tier: Optional[int]
    cas_top: bool
    specialty: str
    tier: str
    issn: Optional[str] = None

    @property
    def score(self) -> float:
        return TIER_SCORE.get(self.tier, TIER_SCORE[NEUTRAL_TIER])

    def meta_parts(self, *, year: Optional[str] = None, journal_display: Optional[str] = None) -> List[str]:
        parts: List[str] = []
        name = journal_display or self.iso_abbr or self.full_name
        if name:
            parts.append(str(name))
        if year:
            parts.append(str(year))
        if self.jcr_if is not None:
            parts.append(f"IF {self.jcr_if:g}")
        if self.jcr_quartile:
            parts.append(f"JCR {self.jcr_quartile}")
        if self.cas_tier:
            cas = f"中科院{self.cas_tier}区"
            if self.cas_top:
                cas += "Top"
            parts.append(cas)
        return parts


def normalize_journal_key(name: Optional[str]) -> str:
    if not name:
        return ""
    text = name.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"\bthe\b", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_from_raw(raw: Dict[str, Any]) -> Optional[JournalQuality]:
    full_name = str(raw.get("full_name") or "").strip()
    iso_abbr = str(raw.get("iso_abbr") or "").strip()
    tier = str(raw.get("tier") or "").strip().upper()
    if not full_name or not tier:
        return None
    jcr_if = raw.get("jcr_if")
    try:
        jcr_if_f = float(jcr_if) if jcr_if is not None else None
    except (TypeError, ValueError):
        jcr_if_f = None
    cas_tier = raw.get("cas_tier")
    try:
        cas_tier_i = int(cas_tier) if cas_tier is not None else None
    except (TypeError, ValueError):
        cas_tier_i = None
    return JournalQuality(
        full_name=full_name,
        iso_abbr=iso_abbr or full_name,
        jcr_if=jcr_if_f,
        jcr_quartile=(str(raw["jcr_quartile"]) if raw.get("jcr_quartile") else None),
        cas_tier=cas_tier_i,
        cas_top=bool(raw.get("cas_top")),
        specialty=str(raw.get("specialty") or ""),
        tier=tier,
        issn=(str(raw["issn"]) if raw.get("issn") else None),
    )


@lru_cache(maxsize=4)
def _load_index(path_str: str) -> Dict[str, JournalQuality]:
    path = Path(path_str)
    index: Dict[str, JournalQuality] = {}
    if yaml is None or not path.exists():
        return index
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    for raw in data.get("journals") or []:
        if not isinstance(raw, dict):
            continue
        entry = _entry_from_raw(raw)
        if entry is None:
            continue
        keys = [entry.full_name, entry.iso_abbr, *(raw.get("aliases") or [])]
        for key in keys:
            norm = normalize_journal_key(str(key))
            if norm and norm not in index:
                index[norm] = entry
    return index


def load_journal_index(path: Optional[Path] = None) -> Dict[str, JournalQuality]:
    target = Path(path) if path else DEFAULT_YAML
    return _load_index(str(target.resolve()))


def lookup_journal(name: Optional[str], *, path: Optional[Path] = None) -> Optional[JournalQuality]:
    if not name:
        return None
    index = load_journal_index(path)
    norm = normalize_journal_key(name)
    if not norm:
        return None
    hit = index.get(norm)
    if hit:
        return hit
    # Soft contain match for "Blood." / "Lancet Oncology : ..." variants
    for key, entry in index.items():
        if key and (key in norm or norm in key):
            return entry
    return None


def journal_score(name: Optional[str], *, path: Optional[Path] = None) -> float:
    entry = lookup_journal(name, path=path)
    if entry is None:
        return TIER_SCORE[NEUTRAL_TIER]
    return entry.score


def format_journal_meta(
    journal: Optional[str],
    year: Optional[str] = None,
    *,
    path: Optional[Path] = None,
) -> str:
    entry = lookup_journal(journal, path=path)
    if entry is None:
        parts = [p for p in [journal, year] if p]
        return " · ".join(str(p) for p in parts)
    return " · ".join(entry.meta_parts(year=year, journal_display=journal or entry.iso_abbr))
