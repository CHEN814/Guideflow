from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ── Search-time unit (BM25 / vector / retrieval) ──────────────────────────

@dataclass
class SearchDocument:
    """Flat unit used by BM25, vector index and retrieval pipeline.

    Generated from GuidelinePage, DiscussionChunk or ReferenceEntry.
    """

    source_id: str
    page_type: str            # clinical_guideline | discussion | reference | front_matter
    pdf_page: int
    text: str
    printed_page_code: Optional[str] = None
    module_code: Optional[str] = None
    section: Optional[str] = None
    article_id: Optional[str] = None
    reference_ids: List[str] = field(default_factory=list)
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchDocument":
        return cls(
            source_id=data["source_id"],
            page_type=data.get("page_type", "discussion"),
            pdf_page=int(data.get("pdf_page", 0)),
            text=data.get("text", ""),
            printed_page_code=data.get("printed_page_code"),
            module_code=data.get("module_code"),
            section=data.get("section"),
            article_id=data.get("article_id"),
            reference_ids=list(data.get("reference_ids", [])),
            needs_review=bool(data.get("needs_review", False)),
        )


# ── Structured knowledge base models ──────────────────────────────────────

@dataclass
class PageLink:
    """One outgoing link from a clinical guideline page.

    ``edge_type`` distinguishes clinical-flow edges (a flowchart arrow that
    advances the decision path, e.g. BCEL-1 -> BCEL-2) from navigation/chrome
    edges (back to Index / Table of Contents / Discussion / cross-disease TOC).
    Older knowledge-base JSON files predate this field, so it is optional and
    defaults to ``None`` (graph navigation re-classifies at runtime when absent).
    """

    source_page_code: Optional[str]
    target_pdf_page: int
    target_page_code: Optional[str]
    anchor_text: str
    edge_type: Optional[str] = None     # "flow" | "navigation" | None (unknown)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageLink":
        return cls(
            source_page_code=data.get("source_page_code"),
            target_pdf_page=int(data.get("target_pdf_page", 0)),
            target_page_code=data.get("target_page_code"),
            anchor_text=str(data.get("anchor_text", "")),
            edge_type=data.get("edge_type"),
        )


@dataclass
class GuidelinePage:
    """One PDF page from front_matter or clinical_guideline sections."""

    page_id: str
    pdf_page: int
    page_type: str            # front_matter | clinical_guideline | discussion_toc | discussion_text | discussion_references
    clean_text: str
    printed_page_code: Optional[str] = None
    module_code: Optional[str] = None
    outgoing_links: List[PageLink] = field(default_factory=list)
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["outgoing_links"] = [lnk.to_dict() for lnk in self.outgoing_links]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuidelinePage":
        return cls(
            page_id=data["page_id"],
            pdf_page=int(data["pdf_page"]),
            page_type=data.get("page_type", "front_matter"),
            clean_text=data.get("clean_text", ""),
            printed_page_code=data.get("printed_page_code"),
            module_code=data.get("module_code"),
            outgoing_links=[PageLink.from_dict(lnk) for lnk in data.get("outgoing_links", [])],
            needs_review=bool(data.get("needs_review", False)),
        )

    def to_search_document(self) -> SearchDocument:
        if self.printed_page_code:
            source_id = f"page-{self.printed_page_code.replace(' ', '_')}"
        else:
            source_id = f"page-{self.pdf_page}"
        return SearchDocument(
            source_id=source_id,
            page_type=self.page_type,
            pdf_page=self.pdf_page,
            text=self.clean_text,
            printed_page_code=self.printed_page_code,
            module_code=self.module_code,
            needs_review=self.needs_review,
        )


@dataclass
class DiscussionChunk:
    """One semantic chunk from a disease article's discussion text."""

    chunk_id: str
    article_id: str
    article_title: str
    pdf_page: int
    ms_page_code: Optional[str]
    section: str
    clean_text: str
    reference_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscussionChunk":
        return cls(
            chunk_id=data["chunk_id"],
            article_id=data.get("article_id", ""),
            article_title=data.get("article_title", ""),
            pdf_page=int(data.get("pdf_page", 0)),
            ms_page_code=data.get("ms_page_code"),
            section=data.get("section", ""),
            clean_text=data.get("clean_text", ""),
            reference_ids=list(data.get("reference_ids", [])),
        )

    def to_search_document(self) -> SearchDocument:
        return SearchDocument(
            source_id=self.chunk_id,
            page_type="discussion",
            pdf_page=self.pdf_page,
            text=self.clean_text,
            section=self.section,
            article_id=self.article_id,
            reference_ids=self.reference_ids,
        )


@dataclass
class ReferenceEntry:
    """One numbered reference from a disease article's reference list."""

    entry_id: str
    article_id: str
    ref_number: str
    text: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReferenceEntry":
        return cls(
            entry_id=data["entry_id"],
            article_id=data.get("article_id", ""),
            ref_number=str(data.get("ref_number", "")),
            text=data.get("text", ""),
            pmid=data.get("pmid"),
            doi=data.get("doi"),
            url=data.get("url"),
        )

    def to_search_document(self) -> SearchDocument:
        return SearchDocument(
            source_id=self.entry_id,
            page_type="reference",
            pdf_page=0,
            text=self.text,
            section="References",
            article_id=self.article_id,
            reference_ids=[self.ref_number],
        )


@dataclass
class StructuredKnowledgeBase:
    """Top-level knowledge base produced by the PDF extractor."""

    guideline_pages: List[GuidelinePage]
    discussion_chunks: List[DiscussionChunk]
    reference_entries: List[ReferenceEntry]
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guideline_pages": [p.to_dict() for p in self.guideline_pages],
            "discussion_chunks": [c.to_dict() for c in self.discussion_chunks],
            "reference_entries": [e.to_dict() for e in self.reference_entries],
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredKnowledgeBase":
        return cls(
            guideline_pages=[GuidelinePage.from_dict(p) for p in data.get("guideline_pages", [])],
            discussion_chunks=[DiscussionChunk.from_dict(c) for c in data.get("discussion_chunks", [])],
            reference_entries=[ReferenceEntry.from_dict(e) for e in data.get("reference_entries", [])],
            stats=dict(data.get("stats", {})),
        )

    def to_search_documents(self) -> List[SearchDocument]:
        """Generate flat search units for BM25 / vector indexing.

        Only clinical_guideline pages and discussion chunks are indexed.
        Reference entries are intentionally excluded: every retrieval route
        filters them out, and they are attached at answer time via
        ReferenceResolver (which reads the knowledge base directly). Indexing
        them only wastes space and risks duplicate-id collisions.
        A defensive dedup on source_id guards the vector store against
        duplicate ids.
        """
        docs: List[SearchDocument] = []
        seen_ids: set = set()

        def _add(doc: SearchDocument) -> None:
            if doc.source_id in seen_ids:
                return
            seen_ids.add(doc.source_id)
            docs.append(doc)

        for page in self.guideline_pages:
            if page.page_type == "clinical_guideline" and page.clean_text.strip():
                _add(page.to_search_document())
        for chunk in self.discussion_chunks:
            if chunk.clean_text.strip():
                _add(chunk.to_search_document())
        return docs


# ── Query / retrieval types ──────────────────────────────────────────────

@dataclass
class NormalizedQuery:
    original: str
    entities: List[str]
    expanded_queries: List[str]
    search_queries: List[str]


@dataclass
class MetadataFilters:
    page_types: List[str] = field(default_factory=list)
    module_codes: List[str] = field(default_factory=list)
    article_ids: List[str] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)

    def matches(self, document: SearchDocument) -> bool:
        if self.page_types and document.page_type not in self.page_types:
            return False
        if self.module_codes and document.page_type == "clinical_guideline":
            if document.module_code not in self.module_codes:
                return False
        if self.article_ids and document.page_type in ("discussion", "reference"):
            if document.article_id not in self.article_ids:
                return False
        if self.sections and document.section not in self.sections:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_types": self.page_types,
            "module_codes": self.module_codes,
            "article_ids": self.article_ids,
            "sections": self.sections,
        }


@dataclass
class RetrievalHit:
    document: SearchDocument
    score: float
    retriever: str
    rank: int
    details: Dict[str, Any] = field(default_factory=dict)

    def to_trace_dict(self, text_limit: int = 320) -> Dict[str, Any]:
        text = self.document.text.replace("\n", " ")
        return {
            "source_id": self.document.source_id,
            "pdf_page": self.document.pdf_page,
            "page_type": self.document.page_type,
            "printed_page_code": self.document.printed_page_code,
            "section": self.document.section,
            "score": self.score,
            "retriever": self.retriever,
            "rank": self.rank,
            "reference_ids": self.document.reference_ids,
            "text": text[:text_limit],
            "details": self.details,
        }


@dataclass
class FigureReference:
    """A clinical-guideline page image attached to a multimodal answer.

    ``image_path`` is the full-page render (sent to VLM).
    ``crop_image_path`` is an optional cropped flowchart region for display.
    """

    page_code: Optional[str]
    pdf_page: int
    image_path: str
    caption: str = ""
    source_index: Optional[int] = None     # the [Sn] this figure backs, if any
    crop_image_path: Optional[str] = None
    crop_full_image_path: Optional[str] = None
    anchor_paragraph: Optional[int] = None  # paragraph index for inline placement
    anchor_key: Optional[str] = None        # S{n} or page code that triggered anchor
    crop_method: Optional[str] = None       # vlm | pymupdf | none
    bbox_quality: Optional[str] = None      # good | full_page_like | duplicated | missing

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphTriple:
    """A validated knowledge-graph edge used for recall and path reasoning."""

    triple_id: str
    subject_id: str
    subject_name: str
    subject_type: str
    relation: str
    object_id: str
    object_name: str
    object_type: str
    confidence: float
    validation_status: str
    evidence_text: str
    evidence_source_ids: List[str] = field(default_factory=list)
    evidence_kind: str = "text"
    llm_score: Optional[float] = None
    reviewer: Optional[str] = None
    review_status: str = "trusted"
    score_components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphTriple":
        return cls(
            triple_id=data["triple_id"],
            subject_id=data["subject_id"],
            subject_name=data["subject_name"],
            subject_type=data["subject_type"],
            relation=data["relation"],
            object_id=data["object_id"],
            object_name=data["object_name"],
            object_type=data["object_type"],
            confidence=float(data.get("confidence", 0.0)),
            validation_status=data.get("validation_status", "candidate"),
            evidence_text=data.get("evidence_text", ""),
            evidence_source_ids=list(data.get("evidence_source_ids", [])),
            evidence_kind=data.get("evidence_kind", "text"),
            llm_score=data.get("llm_score"),
            reviewer=data.get("reviewer"),
            review_status=data.get("review_status", "trusted"),
            score_components=dict(data.get("score_components", {})),
        )


@dataclass
class EvidenceBundle:
    """Primary retrieval hits plus attached references from discussion chunks."""

    primary_hits: List[RetrievalHit]
    attached_references: List[ReferenceEntry] = field(default_factory=list)
    reference_links: Dict[str, List[str]] = field(default_factory=dict)
    figures: List[FigureReference] = field(default_factory=list)
    graph_triples: List[GraphTriple] = field(default_factory=list)
    graph_context: List[str] = field(default_factory=list)


@dataclass
class QAResult:
    question: str
    answer: str
    sources: List[SearchDocument]
    verification: Dict[str, Any]
    run_id: str
    trace_path: str
    degraded: List[str] = field(default_factory=list)
    attached_references: List[ReferenceEntry] = field(default_factory=list)
    reference_links: Dict[str, List[str]] = field(default_factory=dict)
    figures: List[FigureReference] = field(default_factory=list)
    graph_triples: List[GraphTriple] = field(default_factory=list)
    generation_mode: str = "text"          # "text" (Qwen) | "multimodal" (VLM)
    trace: Dict[str, Any] = field(default_factory=dict)

    def to_web_payload(self, image_url_prefix: str = "/api/images") -> Dict[str, Any]:
        """Stable data contract for Web UI (paragraphs + figures + metadata)."""
        from backend.app.services.figure_anchor import split_answer_paragraphs

        figures_payload = []
        for fig in self.figures:
            data = fig.to_dict()
            display_path = fig.crop_image_path or fig.image_path
            full_display_path = fig.crop_full_image_path or fig.image_path
            if display_path:
                from pathlib import Path

                data["image_url"] = f"{image_url_prefix}/{Path(display_path).name}"
            else:
                data["image_url"] = None
            if full_display_path:
                from pathlib import Path

                data["full_image_url"] = f"{image_url_prefix}/{Path(full_display_path).name}"
            else:
                data["full_image_url"] = data["image_url"]
            figures_payload.append(data)

        return {
            "question": self.question,
            "answer_markdown": self.answer,
            "answer_paragraphs": split_answer_paragraphs(self.answer),
            "generation_mode": self.generation_mode,
            "figures": figures_payload,
            "sources": [doc.to_dict() for doc in self.sources],
            "attached_references": [ref.to_dict() for ref in self.attached_references],
            "graph_triples": [triple.to_dict() for triple in self.graph_triples],
            "reference_links": self.reference_links,
            "verification": self.verification,
            "degraded": self.degraded,
            "run_id": self.run_id,
            "trace_path": self.trace_path,
            "trace": self.trace,
        }
