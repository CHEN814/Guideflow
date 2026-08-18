"""Guideline-cited PMID / DOI index for literature enrichment."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from backend.app.settings import ROOT_DIR

DEFAULT_INDEX_PATH = ROOT_DIR / "backend" / "data" / "guideline_cited_pmids.json"

KB_SOURCES = (
    ("nccn", ROOT_DIR / "data" / "processed" / "dlbcl_knowledge_base.json", "NCCN B-Cell Lymphomas"),
    ("csco", ROOT_DIR / "data" / "processed" / "csco_knowledge_base.json", "CSCO 淋巴瘤"),
    ("eha", ROOT_DIR / "data" / "processed" / "eha_knowledge_base.json", "EHA 淋巴瘤"),
)


@dataclass(frozen=True)
class GuidelineCitation:
    pmid: Optional[str]
    doi: Optional[str]
    sources: Tuple[str, ...]
    label: str  # human-readable, e.g. "NCCN B-Cell Lymphomas"


def normalize_doi(doi: Optional[str]) -> str:
    if not doi:
        return ""
    text = str(doi).strip().lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    return text.strip()


def normalize_pmid(pmid: Optional[str]) -> str:
    if not pmid:
        return ""
    digits = re.sub(r"\D", "", str(pmid))
    return digits


def normalize_title_key(text: Optional[str]) -> str:
    if not text:
        return ""
    # Prefer the sentence before "Available at" for NCCN-style refs.
    chunk = re.split(r"\bAvailable at\b|\bhttp", text, maxsplit=1, flags=re.I)[0]
    chunk = chunk.lower()
    chunk = re.sub(r"[^a-z0-9]+", " ", chunk)
    return re.sub(r"\s+", " ", chunk).strip()[:160]


@lru_cache(maxsize=4)
def _load_index(path_str: str) -> Dict[str, Any]:
    path = Path(path_str)
    if not path.exists():
        return {"by_pmid": {}, "by_doi": {}, "by_title": {}, "meta": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {"by_pmid": {}, "by_doi": {}, "by_title": {}, "meta": {}}


def load_guideline_index(path: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(path) if path else DEFAULT_INDEX_PATH
    return _load_index(str(target.resolve()))


def lookup_guideline_citation(
    *,
    pmid: Optional[str] = None,
    doi: Optional[str] = None,
    title: Optional[str] = None,
    path: Optional[Path] = None,
) -> Optional[GuidelineCitation]:
    index = load_guideline_index(path)
    by_pmid = index.get("by_pmid") or {}
    by_doi = index.get("by_doi") or {}
    by_title = index.get("by_title") or {}

    hit = None
    key_pmid = normalize_pmid(pmid)
    if key_pmid and key_pmid in by_pmid:
        hit = by_pmid[key_pmid]
    if hit is None:
        key_doi = normalize_doi(doi)
        if key_doi and key_doi in by_doi:
            hit = by_doi[key_doi]
    if hit is None:
        key_title = normalize_title_key(title)
        if key_title and key_title in by_title:
            hit = by_title[key_title]
    if not hit:
        return None
    sources = tuple(hit.get("sources") or ())
    label = str(hit.get("label") or (" / ".join(sources) if sources else "指南"))
    return GuidelineCitation(
        pmid=key_pmid or None,
        doi=normalize_doi(doi) or None,
        sources=sources,
        label=label,
    )


def build_guideline_cited_index(
    kb_paths: Optional[Iterable[Tuple[str, Path, str]]] = None,
) -> Dict[str, Any]:
    """Scan knowledge bases and build PMID/DOI/title index."""
    by_pmid: Dict[str, Dict[str, Any]] = {}
    by_doi: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    counts = {"entries": 0, "with_pmid": 0, "with_doi": 0}

    for source_key, path, label in kb_paths or KB_SOURCES:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            kb = json.load(handle)
        refs = kb.get("reference_entries") or []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            counts["entries"] += 1
            pmid = normalize_pmid(ref.get("pmid"))
            doi = normalize_doi(ref.get("doi"))
            title_key = normalize_title_key(ref.get("text") or ref.get("title"))
            payload = {
                "sources": [source_key],
                "label": label,
                "pmid": pmid or None,
                "doi": doi or None,
            }
            if pmid:
                counts["with_pmid"] += 1
                existing = by_pmid.get(pmid)
                if existing:
                    srcs: Set[str] = set(existing.get("sources") or [])
                    srcs.add(source_key)
                    existing["sources"] = sorted(srcs)
                    if source_key not in (existing.get("label") or ""):
                        existing["label"] = " / ".join(
                            sorted({existing.get("label", label), label})
                        )
                else:
                    by_pmid[pmid] = dict(payload)
            if doi:
                counts["with_doi"] += 1
                existing = by_doi.get(doi)
                if existing:
                    srcs = set(existing.get("sources") or [])
                    srcs.add(source_key)
                    existing["sources"] = sorted(srcs)
                else:
                    by_doi[doi] = dict(payload)
            if title_key and title_key not in by_title:
                by_title[title_key] = dict(payload)

    return {
        "meta": {
            "built_from": [
                {"source": s, "path": str(p), "label": lab}
                for s, p, lab in (kb_paths or KB_SOURCES)
                if p.exists()
            ],
            "counts": {
                **counts,
                "unique_pmid": len(by_pmid),
                "unique_doi": len(by_doi),
                "unique_title": len(by_title),
            },
        },
        "by_pmid": by_pmid,
        "by_doi": by_doi,
        "by_title": by_title,
    }


def write_guideline_cited_index(
    out_path: Optional[Path] = None,
    kb_paths: Optional[Iterable[Tuple[str, Path, str]]] = None,
) -> Path:
    target = Path(out_path) if out_path else DEFAULT_INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    data = build_guideline_cited_index(kb_paths)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    _load_index.cache_clear()
    return target
