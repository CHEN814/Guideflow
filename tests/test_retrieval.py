from __future__ import annotations

from backend.app.models import MetadataFilters, ReferenceEntry, RetrievalHit, SearchDocument
from backend.app.services.bm25_store import BM25Store
from backend.app.services.query_normalizer import normalize_query
from backend.app.services.reference_resolver import ReferenceResolver
from backend.app.services.retrieval import reciprocal_rank_fusion, route_query
from backend.app.models import StructuredKnowledgeBase


def _doc(
    source_id: str,
    text: str,
    page_type: str = "discussion",
    module_code: str | None = None,
    article_id: str | None = None,
    reference_ids: list[str] | None = None,
) -> SearchDocument:
    return SearchDocument(
        source_id=source_id,
        page_type=page_type,
        pdf_page=1,
        text=text,
        module_code=module_code,
        article_id=article_id,
        reference_ids=reference_ids or [],
    )


def _hit(document: SearchDocument) -> RetrievalHit:
    return RetrievalHit(document=document, score=1.0, retriever="test", rank=1)


def test_query_normalizer_expands_chinese_medical_query() -> None:
    normalized = normalize_query("TP53 R248Q 在 DLBCL 的预后意义是什么？")

    assert "TP53" in normalized.entities
    assert "DLBCL" in normalized.entities
    assert any("prognosis" in query for query in normalized.search_queries)
    assert any("diffuse large B-cell lymphoma" in query for query in normalized.search_queries)


def test_route_query_uses_evidence_filter_for_mutation_question() -> None:
    normalized = normalize_query("TP53 R248Q 在 DLBCL 的预后意义是什么？")
    route, filters, triggers = route_query(normalized)

    assert route == "evidence"
    assert filters.page_types == ["clinical_guideline", "discussion"]
    assert "reference" not in filters.page_types
    assert filters.article_ids == ["dlbcl"]
    assert filters.module_codes == ["BCEL"]
    assert triggers


def test_metadata_filter_by_article_id() -> None:
    docs = [
        SearchDocument(
            source_id="disc-dlbcl",
            page_type="discussion",
            pdf_page=1,
            text="DLBCL prognosis",
            article_id="dlbcl",
        ),
        SearchDocument(
            source_id="disc-fl",
            page_type="discussion",
            pdf_page=1,
            text="FL prognosis",
            article_id="fl",
        ),
    ]
    store = BM25Store(docs)
    filters = MetadataFilters(page_types=["discussion"], article_ids=["dlbcl"])
    hits = store.search(["prognosis"], filters=filters, top_k=5)

    assert all(hit.document.article_id == "dlbcl" for hit in hits)
    assert any(hit.document.source_id == "disc-dlbcl" for hit in hits)


def test_bm25_retrieves_exact_medical_entity() -> None:
    docs = [
        _doc("a", "TP53 mutation is discussed in diffuse large B-cell lymphoma prognosis."),
        _doc("b", "First-line therapy includes immunochemotherapy."),
    ]
    store = BM25Store(docs)
    hits = store.search(["TP53 DLBCL prognosis"], top_k=2)

    assert hits[0].document.source_id == "a"


def test_rrf_deduplicates_sources() -> None:
    docs = [_doc("a", "TP53 mutation"), _doc("b", "therapy")]
    bm25 = BM25Store(docs).search(["TP53"], top_k=2)
    vector = BM25Store(docs).search(["mutation"], top_k=2)

    fused = reciprocal_rank_fusion([bm25, vector])

    assert len({hit.document.source_id for hit in fused}) == len(fused)
    assert fused[0].rank == 1


def test_metadata_filter_excludes_reference_from_guideline_discussion_search() -> None:
    docs = [
        _doc("a", "clinical guideline text", page_type="clinical_guideline"),
        _doc("b", "discussion text", page_type="discussion"),
        _doc("c", "reference text", page_type="reference"),
    ]
    store = BM25Store(docs)
    filters = MetadataFilters(page_types=["clinical_guideline", "discussion"])
    hits = store.search(["text"], filters=filters, top_k=5)

    returned_types = {hit.document.page_type for hit in hits}
    assert "reference" not in returned_types
    assert "clinical_guideline" in returned_types or "discussion" in returned_types


def test_metadata_filter_by_module_code() -> None:
    docs = [
        _doc("a", "DLBCL treatment", page_type="clinical_guideline", module_code="BCEL"),
        _doc("b", "MCL treatment", page_type="clinical_guideline", module_code="MANT"),
    ]
    store = BM25Store(docs)
    filters = MetadataFilters(page_types=["clinical_guideline"], module_codes=["BCEL"])
    hits = store.search(["treatment"], filters=filters, top_k=5)

    assert all(hit.document.module_code == "BCEL" for hit in hits)
    assert any(hit.document.source_id == "a" for hit in hits)


def test_reference_resolver_attaches_references_from_discussion_hits() -> None:
    kb = StructuredKnowledgeBase(
        guideline_pages=[],
        discussion_chunks=[],
        reference_entries=[
            ReferenceEntry(
                entry_id="ref-dlbcl-27",
                article_id="dlbcl",
                ref_number="27",
                text="Dodero A, et al. TP53 mutations confer poor prognosis.",
            ),
            ReferenceEntry(
                entry_id="ref-dlbcl-33",
                article_id="dlbcl",
                ref_number="33",
                text="Another reference entry.",
            ),
        ],
    )
    resolver = ReferenceResolver(kb)
    hits = [
        _hit(
            _doc(
                "disc-dlbcl-p140-c0",
                "TP53 mutation discussion",
                article_id="dlbcl",
                reference_ids=["27", "33"],
            )
        )
    ]

    attached, links = resolver.resolve_references(hits)

    assert [entry.ref_number for entry in attached] == ["27", "33"]
    assert links == {"disc-dlbcl-p140-c0": ["27", "33"]}


def test_reference_resolver_deduplicates_and_ignores_non_discussion_hits() -> None:
    kb = StructuredKnowledgeBase(
        guideline_pages=[],
        discussion_chunks=[],
        reference_entries=[
            ReferenceEntry(
                entry_id="ref-dlbcl-27",
                article_id="dlbcl",
                ref_number="27",
                text="Dodero A, et al.",
            )
        ],
    )
    resolver = ReferenceResolver(kb)
    hits = [
        _hit(
            _doc(
                "disc-a",
                "discussion one",
                article_id="dlbcl",
                reference_ids=["27"],
            )
        ),
        _hit(
            _doc(
                "disc-b",
                "discussion two",
                article_id="dlbcl",
                reference_ids=["27"],
            )
        ),
        _hit(_doc("page-1", "guideline page", page_type="clinical_guideline")),
    ]

    attached, links = resolver.resolve_references(hits)

    assert len(attached) == 1
    assert attached[0].ref_number == "27"
    assert links == {"disc-a": ["27"], "disc-b": ["27"]}
