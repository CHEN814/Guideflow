from __future__ import annotations

from backend.app.models import MetadataFilters, ReferenceEntry, RetrievalHit, SearchDocument
from backend.app.services.bm25_store import BM25Store
from backend.app.services.disease_scope import detect_disease_scope, with_common_modules, DISEASE_SCOPES
from backend.app.services.query_normalizer import normalize_query
from backend.app.services.qwen import _heuristic_intent
from backend.app.services.reference_resolver import ReferenceResolver
from backend.app.services.retrieval import route_query
from backend.app.models import StructuredKnowledgeBase
from backend.app.services.verifier import verify_answer


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
    scope = detect_disease_scope(normalized.original)
    route, filters, triggers = route_query(normalized, disease_scope=scope)

    assert route == "evidence"
    assert filters.page_types == ["clinical_guideline", "discussion"]
    assert "reference" not in filters.page_types
    assert "dlbcl" in filters.article_ids
    assert "overview" in filters.article_ids  # common article
    assert "BCEL" in filters.module_codes
    assert "NHODG" in filters.module_codes  # common module
    assert triggers


def test_detect_disease_scope_dlbcl_and_fl() -> None:
    dlbcl = detect_disease_scope("什么时候考虑 CNS prophylaxis？DLBCL", forced_key="auto")
    assert dlbcl.key == "dlbcl"
    assert "BCEL" in dlbcl.module_codes

    fl = detect_disease_scope("滤泡淋巴瘤一线治疗", forced_key="auto")
    assert fl.key == "fl"
    assert "FOLL" in fl.module_codes

    all_scope = detect_disease_scope("淋巴瘤总体分期怎么做", forced_key="auto")
    assert all_scope.key == "all"
    assert all_scope.article_ids == []
    assert all_scope.module_codes == []


def test_forced_all_scope_skips_filters() -> None:
    scope = DISEASE_SCOPES["all"]
    normalized = normalize_query("一线治疗")
    _route, filters, _triggers = route_query(normalized, disease_scope=scope)
    assert filters.article_ids == []
    assert filters.module_codes == []


def test_with_common_modules_idempotent_for_all() -> None:
    assert with_common_modules(DISEASE_SCOPES["all"]).key == "all"


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
    resolver = ReferenceResolver(kb, max_attached_refs=6)
    hits = [
        _hit(
            _doc(
                "disc-dlbcl-p140-c0",
                "TP53 mutation discussion cites 27 and 33.",
                article_id="dlbcl",
                reference_ids=["27", "33"],
            )
        )
    ]

    attached, links = resolver.resolve_references(hits, question="TP53 mutation")

    assert [entry.ref_number for entry in attached] == ["27", "33"]
    assert links == {"disc-dlbcl-p140-c0": ["27", "33"]}


def test_reference_resolver_prefers_window_and_caps() -> None:
    """Long chunk with many refs should only attach those near the matched window."""
    ref_nums = [str(n) for n in list(range(92, 101)) + list(range(112, 125))]
    entries = [
        ReferenceEntry(
            entry_id=f"ref-dlbcl-{n}",
            article_id="dlbcl",
            ref_number=n,
            text=f"Reference {n}.",
        )
        for n in ref_nums
    ]
    kb = StructuredKnowledgeBase(
        guideline_pages=[],
        discussion_chunks=[],
        reference_entries=entries,
    )
    resolver = ReferenceResolver(kb, max_attached_refs=6)
    text = (
        "Follow-up after therapy is recommended.92,93,94,95,96,97,98,99,100 "
        "Considerable debate remains regarding imaging. "
        "CNS prophylaxis can be considered for high-risk disease.112,113,114 "
        "Other topics continue.115,116,117,118,119,120,121,122,123,124"
    )
    hits = [
        _hit(
            _doc(
                "disc-dlbcl-p257-c9",
                text,
                article_id="dlbcl",
                reference_ids=ref_nums,
            )
        )
    ]

    attached, links = resolver.resolve_references(
        hits, question="什么时候考虑 CNS prophylaxis？"
    )

    nums = [e.ref_number for e in attached]
    assert len(nums) <= 6
    # Window around CNS prophylaxis should prefer 112-114 over early follow-up refs.
    assert any(n in {"112", "113", "114"} for n in nums)
    assert "92" not in nums
    assert links["disc-dlbcl-p257-c9"]


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
                "discussion one cites 27.",
                article_id="dlbcl",
                reference_ids=["27"],
            )
        ),
        _hit(
            _doc(
                "disc-b",
                "discussion two cites 27.",
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


def test_heuristic_intent_routing() -> None:
    assert _heuristic_intent("你好？") == "chitchat"
    assert _heuristic_intent("多少度是发烧？") == "general_medical"
    assert _heuristic_intent("什么时候考虑 CNS prophylaxis？") == "guideline"
    assert _heuristic_intent("滤泡淋巴瘤一线治疗") == "guideline"


def test_verifier_skips_citation_requirement_for_chitchat() -> None:
    result = verify_answer(
        "你好？",
        "你好！我是指南助手。",
        [],
        answer_kind="chitchat",
    )
    assert result["ok"] is True
    assert "answer_missing_source_citations" not in result["issues"]


def test_verifier_skips_citation_requirement_for_general_medical() -> None:
    result = verify_answer(
        "多少度算发烧？",
        "> **非指南内容 · 通用医学知识（仅供参考，不替代临床判断）**\n\n一般腋温≥37.3℃可视为发热。",
        [],
        answer_kind="general_medical",
    )
    assert result["ok"] is True
