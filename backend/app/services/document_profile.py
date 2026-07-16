"""Per-document configuration profile (multi-guideline scaffold).

Today the pipeline targets one PDF (NCCN B-Cell Lymphomas v3.2026), with page
ranges hard-coded in :class:`pdf_extractor.PageRanges`. To scale to many NCCN
guidelines, the per-document knobs (page-range layout, the disease scopes it
contains, a human label) are collected here behind a registry, so adding a new
guideline becomes "register a profile" rather than "edit the extractor".

This is intentionally a thin scaffold: the extractor still accepts a
``PageRanges`` directly, and ``DEFAULT_PROFILE`` reproduces today's behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from backend.app.services.pdf_extractor import PageRanges


@dataclass(frozen=True)
class DocumentProfile:
    """Everything specific to one source guideline PDF."""

    key: str
    label: str
    page_ranges: PageRanges
    # Disease scope keys (see disease_scope.DISEASE_SCOPES) contained in this PDF.
    disease_scope_keys: List[str] = field(default_factory=list)
    # Extra header/footer noise lines unique to this document (optional).
    noise_markers: List[str] = field(default_factory=list)


# Registry of known guideline documents. Add new NCCN guidelines here.
DOCUMENT_PROFILES: Dict[str, DocumentProfile] = {
    "nccn-bcell-v3-2026": DocumentProfile(
        key="nccn-bcell-v3-2026",
        label="NCCN Clinical Practice Guidelines in Oncology: B-Cell Lymphomas, v3.2026",
        page_ranges=PageRanges(),
        disease_scope_keys=["dlbcl"],
    ),
}

DEFAULT_PROFILE_KEY = "nccn-bcell-v3-2026"


def get_document_profile(key: str | None = None) -> DocumentProfile:
    profile = DOCUMENT_PROFILES.get(key or DEFAULT_PROFILE_KEY)
    if profile is None:
        known = ", ".join(sorted(DOCUMENT_PROFILES))
        raise ValueError(f"Unknown document profile {key!r}. Known profiles: {known}")
    return profile
