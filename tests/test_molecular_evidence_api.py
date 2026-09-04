"""Molecular evidence API smoke tests."""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.db import get_session_factory
from backend.app.models_db import MolecularEvidenceCacheEntry, MolecularEvidenceQueryLog


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["AUTH_SECRET"] = "test-secret-not-for-prod"
    os.environ["COOKIE_SECURE"] = "0"
    os.environ["CORS_ORIGINS"] = "http://testserver,http://127.0.0.1:5173"

    import backend.app.db as dbmod
    from backend.app.web_config import reset_web_config_cache

    reset_web_config_cache()
    if dbmod._engine is not None:
        dbmod._engine.dispose()
    dbmod._engine = None
    dbmod._SessionLocal = None

    from backend.app.db import init_db
    from backend.api.server import create_app

    init_db()
    app = create_app()
    with TestClient(app) as c:
        yield c

    if dbmod._engine is not None:
        dbmod._engine.dispose()
    dbmod._engine = None
    dbmod._SessionLocal = None


def test_molecular_evidence_query_smoke(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P\nCD79B p.Y196H",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
            "question": "这两个变异怎么解释？",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["variants"]) == 2
    assert [v["mapping_status"] for v in body["variants"]] == ["unique", "unique"]
    assert all(v["genomic_hgvs"] and v["genome_build"] == "GRCh38" for v in body["variants"])
    assert len(body["evidence"]) == 5
    providers = {card["provider"] for card in body["evidence"]}
    assert {"ClinVar", "CIViC", "MyVariant"} <= providers
    disease_matches = [card["disease_match"] for card in body["evidence"]]
    assert disease_matches.count("DLBCL直接证据") >= 2
    assert any(match != "DLBCL直接证据" for match in disease_matches)
    assert body["answer"]["markdown"].startswith("## 直接回答")
    assert body["summary"]["priority_action"]
    assert body["summary"]["next_step"]
    assert "## 证据依据" not in body["answer"]["markdown"]
    assert "## 使用边界" in body["answer"]["markdown"]
    all_gates = body["safety"]["variant_gates"] + body["safety"]["card_gates"]
    assert any(g["decision"] in {"allow", "downgrade", "ask_for_confirmation"} for g in all_gates)
    assert body["global_warnings"]
    assert isinstance(body["missing"]["blocking"], list)
    assert isinstance(body["missing"]["advisory"], list)
    assert body["meta"]["provider_mode"] == "mock"
    assert body["meta"]["required_providers"] == ["ClinVar", "CIViC"]
    assert body["meta"]["extended_providers"] == ["MyVariant"]
    assert body["audit"]["provider_status"]["ClinVar"]["queried"] is True
    assert body["audit"]["provider_status"]["CIViC"]["queried"] is True
    assert body["audit"]["provider_status"]["MyVariant"]["required"] is False
    assert body["audit"]["resolver_status"]["resolved_count"] == 2
    assert any(step["step"] == "resolve_variant" and step["status"] == "resolved" for step in body["audit"]["agent_trace"])
    assert any(step["step"] == "complete" for step in body["audit"]["agent_trace"])
    assert body["meta"]["cache_hit"] is False
    assert body["meta"]["cache_key"]
    assert body["meta"]["query_log_id"]
    assert body["meta"]["cache_entry_id"]
    # Structured invariants: every variant carries its own gate, evidence summary and missing info.
    for variant in body["variants"]:
        assert variant["gate"] is not None
        assert variant["gate"]["variant_id"] == variant["variant_id"]
        assert variant["evidence_summary"]["total"] == len(
            [c for c in body["evidence"] if c["variant_id"] == variant["variant_id"]]
        )
        assert set(variant["missing"].keys()) == {"blocking", "advisory"}
    for card in body["evidence"]:
        assert card["variant_id"]
        assert card["gate"] is not None
    assert len(body["safety"]["variant_gates"]) == len(body["variants"])
    assert len(body["safety"]["card_gates"]) == len(body["evidence"])

    factory = get_session_factory()
    db = factory()
    try:
        logs = db.query(MolecularEvidenceQueryLog).all()
        caches = db.query(MolecularEvidenceCacheEntry).all()
        assert len(logs) == 1
        assert len(caches) == 1
        assert logs[0].query_key == caches[0].query_key
    finally:
        db.close()

    resp2 = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P\nCD79B p.Y196H",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
            "question": "这两个变异怎么解释？",
        },
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["meta"]["cache_hit"] is True
    assert body2["meta"]["query_log_id"]
    assert body2["meta"]["cache_entry_id"]
    assert len(body2["evidence"]) == 5
    assert len(body2["safety"]["variant_gates"]) == 2


def test_molecular_evidence_query_ranks_direct_evidence_first(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
            "question": "请优先展示 DLBCL 直接证据。",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["evidence"]
    assert body["evidence"][0]["disease_match"] == "DLBCL直接证据"
    assert body["evidence"][0]["access_status"] == "metadata_only"
    assert body["evidence"][0]["evidence_level"] in {"L2", "L3"}
    assert "## 证据依据" not in body["answer"]["markdown"]
    assert "MYD88" in body["answer"]["markdown"]


def test_molecular_evidence_query_logs_and_cache_api(client: TestClient):
    first = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
        },
    )
    assert first.status_code == 200

    logs = client.get("/api/molecular-evidence/logs").json()
    cache = client.get("/api/molecular-evidence/cache").json()

    assert logs["total"] >= 1
    assert cache["total"] >= 1
    assert logs["items"][0]["provider_mode"] == "mock"
    assert cache["items"][0]["provider_mode"] == "mock"
    assert logs["items"][0]["query_key"] == cache["items"][0]["query_key"] or logs["items"][0]["query_key"]


def test_molecular_evidence_query_handles_ambiguous_and_gene_aliases(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "P53 R248Q\nBCL-2 高表达",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
            "question": "这些怎么解释？",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    genes = [v["gene"] for v in body["variants"]]
    assert genes[0] == "TP53"
    assert genes[1] == "BCL2"
    statuses = {v["gene"]: v["mapping_status"] for v in body["variants"]}
    assert statuses["TP53"] == "unique"
    assert statuses["BCL2"] == "insufficient"
    tp53_variant = next(v for v in body["variants"] if v["gene"] == "TP53")
    bcl2_variant = next(v for v in body["variants"] if v["gene"] == "BCL2")
    assert tp53_variant["genomic_hgvs"] == "chr17:g.7674222G>A"
    assert tp53_variant["genome_build"] == "GRCh38"
    assert tp53_variant["enrichment"]["source"] == "mock"
    assert not any("系统不会猜测转录本" in warning for warning in tp53_variant.get("warnings", []))
    assert "protein_hgvs 或 cdna_hgvs" in bcl2_variant.get("missing_fields", [])
    assert any(card["source_title"].startswith("ClinVar mock variation") for card in body["evidence"])
    assert "当前至少存在一项需要医生确认或阻断的安全门控结果" in body["answer"]["markdown"]
    # Structured missing: BCL2 is blocked, TP53 fully resolved.
    assert body["missing"]["blocking"]
    bcl2_missing = next(v for v in body["variants"] if v["gene"] == "BCL2")["missing"]
    assert bcl2_missing["blocking"]
    assert bcl2_missing["blocking"][0].startswith("BCL2")
    assert body["variants"][0]["missing"]["blocking"] == []


def test_molecular_evidence_agent_queries_all_providers_per_variant(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P\nCD79B p.Y196H",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    query_steps = [step for step in body["audit"]["agent_trace"] if step["step"] == "query_provider"]
    assert len(query_steps) == 6
    assert {step["provider"] for step in query_steps} == {"ClinVar", "CIViC", "MyVariant"}
    assert all(step["queried"] is True for step in query_steps)


def test_molecular_agent_marks_provider_exception_as_degraded():
    from backend.app.services.molecular_evidence import (
        MockEvidenceProvider,
        MolecularEvidenceAgent,
        MolecularInputParser,
        _ProviderView,
    )

    class FailingClinVar:
        provider_name = "ClinVar"

        def search(self, variant):
            raise TimeoutError("ClinVar unavailable")

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    mock = MockEvidenceProvider()
    agent = MolecularEvidenceAgent(
        provider_mode="live",
        providers=[FailingClinVar(), _ProviderView(mock, "CIViC")],
    )

    records, trace, status, resolver_status = agent.run([variant])

    assert records
    assert status["ClinVar"]["state"] == "degraded"
    assert status["ClinVar"]["error_count"] == 1
    assert status["CIViC"]["state"] == "success"
    assert trace[-1]["completion_state"] == "degraded"
    assert resolver_status["enabled"] is False


def test_molecular_agent_deduplicates_provider_records():
    from backend.app.services.molecular_evidence import (
        MockEvidenceProvider,
        MolecularEvidenceAgent,
        MolecularInputParser,
        _ProviderView,
    )

    class DuplicateCivic:
        provider_name = "CIViC"

        def __init__(self):
            self.provider = _ProviderView(MockEvidenceProvider(), "CIViC")

        def search(self, variant):
            records = self.provider.search(variant)
            return records + records

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    agent = MolecularEvidenceAgent(
        provider_mode="mock",
        providers=[_ProviderView(MockEvidenceProvider(), "ClinVar"), DuplicateCivic()],
    )

    records, trace, status, resolver_status = agent.run([variant])

    civic_records = [record for record in records if record.provider == "CIViC"]
    assert len(civic_records) == 1
    assert status["CIViC"]["record_count"] == 1
    civic_step = next(step for step in trace if step.get("provider") == "CIViC")
    assert civic_step["duplicate_count"] == 1


def test_molecular_evidence_query_requires_text(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={"variants_text": "   ", "provider_mode": "mock"},
    )
    assert resp.status_code == 422


def test_clinvar_matches_three_letter_protein_hgvs_and_nested_classification():
    from backend.app.services.molecular_evidence import ClinVarProvider, MolecularInputParser

    variant = MolecularInputParser().parse(
        "TP53 p.R248Q", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    item = {
        "accession": "VCV000012356",
        "title": "NM_000546.6(TP53):c.743G>A (p.Arg248Gln)",
        "variation_set": [{"aliases": ["p.R248Q:CGG>CAG"]}],
        "germline_classification": {
            "description": "Pathogenic",
            "review_status": "reviewed by expert panel",
            "trait_set": [{"trait_name": "Li-Fraumeni syndrome"}],
        },
        "oncogenicity_classification": {
            "description": "Oncogenic",
            "review_status": "criteria provided, single submitter",
            "trait_set": [{"trait_name": "Neoplasm"}],
        },
    }
    provider = ClinVarProvider()

    assert provider._passes_variant_gate(item, variant)
    normalized = provider._normalize_summary("12356", item, variant)
    assert normalized["provider_record_id"] == "VCV000012356"
    assert normalized["source_url"] == "https://www.ncbi.nlm.nih.gov/clinvar/variation/VCV000012356/"
    assert normalized["matched_variant"] == "TP53 p.R248Q"
    assert "胚系：致病" in normalized["claim"]
    assert "致癌性：致癌性" in normalized["claim"]
    assert "Li-Fraumeni syndrome" in normalized["disease"]


def test_parser_extracts_only_real_variants_from_unified_clinical_question():
    from backend.app.services.molecular_evidence import MolecularInputParser

    text = """患者诊断为DLBCL，肿瘤组织NGS检出：
    1. MYD88 NM_002468.5:c.794T>C，p.Leu265Pro，VAF 32.4%，深度1486×；
    2. CD79B NM_001039933.4:c.586T>C，p.Tyr196His，VAF 21.8%，深度1260×。
    问题：这两个变异是否支持MCD分子亚型？是否有BTK抑制剂治疗线索？"""

    variants = MolecularInputParser().parse(text, disease="DLBCL", sample_type="tumor tissue")

    assert len(variants) == 2
    assert [(item.gene, item.transcript, item.cdna_hgvs, item.protein_hgvs) for item in variants] == [
        ("MYD88", "NM_002468.5", "c.794T>C", "p.L265P"),
        ("CD79B", "NM_001039933.4", "c.586T>C", "p.Y196H"),
    ]


def test_parser_merges_duplicate_gene_protein_parses_keeping_most_complete():
    from backend.app.services.molecular_evidence import MolecularInputParser

    text = (
        "TP53 NM_000546.6:c.743G>A, p.Arg248Gln, VAF 41.5%, 测序深度1106×。请判断:\n"
        "TP53 p.R248Q"
    )
    variants = MolecularInputParser().parse(text, disease="DLBCL", sample_type="tumor tissue")

    assert len(variants) == 1
    variant = variants[0]
    assert variant.gene == "TP53"
    assert variant.protein_hgvs == "p.R248Q"
    assert variant.cdna_hgvs == "c.743G>A"
    assert variant.transcript == "NM_000546.6"
    assert variant.mapping_status == "unique"
    assert "NM_000546.6:c.743G>A" in variant.raw_input
    assert "TP53 p.R248Q" in variant.raw_input


def test_parser_keeps_distinct_protein_changes_and_different_transcripts():
    from backend.app.services.molecular_evidence import MolecularInputParser

    distinct = MolecularInputParser().parse(
        "TP53 p.R248Q\nTP53 p.R248W",
        disease="DLBCL",
        sample_type="tumor tissue",
    )
    assert len(distinct) == 2
    assert {v.protein_hgvs for v in distinct} == {"p.R248Q", "p.R248W"}

    same_protein_two_transcripts = MolecularInputParser().parse(
        "TP53 NM_000546.6:c.743G>A, p.R248Q\nTP53 NM_001276760.3:c.914G>A, p.R248Q",
        disease="DLBCL",
        sample_type="tumor tissue",
    )
    assert len(same_protein_two_transcripts) == 2
    assert {v.transcript for v in same_protein_two_transcripts} == {"NM_000546.6", "NM_001276760.3"}


def test_molecular_agent_deduplicates_same_record_from_different_variants():
    from backend.app.services.molecular_evidence import (
        MolecularEvidenceAgent,
        MolecularInputParser,
        RawEvidenceRecord,
        utc_now_iso,
    )

    class SameRecordClinVar:
        provider_name = "ClinVar"

        def search(self, variant):
            return [RawEvidenceRecord(
                provider="ClinVar",
                provider_record_id="VCV000012356",
                provider_version="test",
                raw_response={
                    "provider": "ClinVar",
                    "provider_record_id": "VCV000012356",
                    "source_title": "ClinVar record for BTK C481S",
                    "claim": "ClinVar record: BTK p.C481S",
                    "access_status": "metadata_only",
                    "evidence_level": "L5",
                    "disease": "unknown",
                    "record_status": "live_metadata",
                    "matched_variant": "BTK p.C481S",
                },
                retrieved_at=utc_now_iso(),
            )]

    class NoOpCivic:
        provider_name = "CIViC"

        def search(self, variant):
            return []

    # Two transcripts of the same protein change stay as two variants
    # (different cDNA + transcript annotations), yet they hit the same VCV.
    variants = MolecularInputParser().parse(
        "BTK NM_000061.3:c.1442T>C, p.C481S\nBTK NM_001287345.2:c.1544T>C, p.C481S",
        disease="DLBCL",
        sample_type="tumor tissue",
    )
    assert len(variants) == 2

    agent = MolecularEvidenceAgent(
        provider_mode="live",
        providers=[SameRecordClinVar(), NoOpCivic()],
    )
    records, trace, status, resolver_status = agent.run(variants)

    clinvar_records = [record for record in records if record.provider == "ClinVar"]
    assert len(clinvar_records) == 1
    assert status["ClinVar"]["record_count"] == 1


def test_answer_targets_intents_from_unified_clinical_question():
    from backend.app.services.molecular_evidence import AnswerComposer, MolecularInputParser

    question = "MYD88 p.L265P 和 CD79B p.Y196H 是否支持MCD分子亚型？是否有BTK抑制剂治疗线索？"
    variants = MolecularInputParser().parse(question, disease="DLBCL", sample_type="tumor tissue")
    answer, _ = AnswerComposer().compose(
        variants=variants,
        cards=[],
        gates=[],
        missing_information=[],
        global_warnings=[],
        question=question,
    )

    assert "本次重点：诊断与分型、治疗与可操作性" in answer
    assert "可支持 MCD 样分子特征" in answer
    assert "不能仅凭两个位点替代完整分子分型算法" in answer


def test_civic_graphql_record_normalization_uses_current_field_names():
    from backend.app.services.molecular_evidence import CivicProvider, MolecularInputParser

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    item = {
        "id": 9376,
        "status": "ACCEPTED",
        "description": "MYD88 L265P has clinicopathologic significance in DLBCL.",
        "evidenceLevel": "B",
        "evidenceType": "PROGNOSTIC",
        "evidenceDirection": "SUPPORTS",
        "disease": {"name": "Diffuse Large B-cell Lymphoma", "displayName": "Diffuse Large B-cell Lymphoma"},
        "therapies": [],
        "source": {
            "title": "Clinicopathologic significance of MYD88 L265P mutation",
            "publicationDate": "2023-01-01",
        },
    }
    provider = CivicProvider()

    assert provider._passes_record_gate(item, variant)
    normalized = provider._normalize_item("9376", item, variant)
    assert normalized["source_version"] == "CIViC GraphQL API live"
    assert normalized["publication_or_release_date"] == "2023-01-01"
    assert normalized["evidence_type"] == "PROGNOSTIC"
    assert normalized["direction"] == "SUPPORTS"
    assert normalized["review_status"] == "已由 CIViC 编辑审核接受"
    assert normalized["claim"].startswith("CIViC 已审核记录")
    assert "MYD88 L265P has clinicopathologic significance" in normalized["original_claim"]
    assert normalized["record_status"] == "ACCEPTED"
    assert normalized["matched_variant"] == "MYD88 p.L265P"


def test_civic_submitted_record_is_retained_but_not_treated_as_accepted():
    from backend.app.services.molecular_evidence import CivicProvider, MolecularInputParser

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    provider = CivicProvider()
    disease = {"name": "Diffuse Large B-cell Lymphoma"}
    submitted = {
        "id": 1,
        "status": "SUBMITTED",
        "description": "Pending evidence statement.",
        "evidenceLevel": "B",
        "evidenceType": "PROGNOSTIC",
        "evidenceDirection": "SUPPORTS",
        "disease": disease,
    }
    assert provider._passes_record_gate(submitted, variant)
    normalized = provider._normalize_item("1", submitted, variant)
    assert normalized["review_status"] == "已提交 CIViC，尚待编辑审核"
    assert normalized["claim"].startswith("CIViC 待审核记录（仅作线索）")
    assert not provider._passes_record_gate({"id": 2, "status": "", "disease": disease}, variant)
    assert provider._passes_record_gate({"id": 3, "status": "ACCEPTED", "disease": disease}, variant)


def test_civic_submitted_card_is_forced_to_downgrade():
    from backend.app.services.molecular_evidence import (
        CivicProvider,
        EvidenceCardBuilder,
        MolecularInputParser,
        RawEvidenceRecord,
        SafetyGate,
        utc_now_iso,
    )

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    item = {
        "status": "SUBMITTED",
        "description": "Pending evidence statement.",
        "evidenceLevel": "B",
        "evidenceType": "PROGNOSTIC",
        "evidenceDirection": "SUPPORTS",
        "disease": {"name": "Diffuse Large B-cell Lymphoma"},
    }
    raw = CivicProvider()._normalize_item("9376", item, variant)
    record = RawEvidenceRecord("CIViC", "EID9376", raw, utc_now_iso())
    card = EvidenceCardBuilder().build(record, variant)
    gate = SafetyGate().evaluate_card(card)

    assert card.evidence_level == "L2"
    assert gate.decision == "downgrade"
    assert gate.allowed_claim_strength == "unaccepted_or_uncertain_record"
    assert "treatment_recommendation" in gate.blocked_outputs
    assert any("尚未经过编辑审核" in warning for warning in gate.required_warnings)


def test_agent_resolves_missing_genomic_coordinates_for_protein_level_only(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
            "question": "这个变异怎么解释？",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    variant = body["variants"][0]
    assert variant["mapping_status"] == "unique"
    assert variant["cdna_hgvs"] == "c.794T>C"
    assert variant["transcript"] == "NM_002468.5"
    assert variant["genomic_hgvs"] == "chr3:g.38181403T>C"
    assert variant["genome_build"] == "GRCh38"
    assert variant["enrichment"]["source"] == "mock"
    assert variant["enrichment"]["resolved_fields"]["genomic_hgvs"] == "chr3:g.38181403T>C"

    assert body["audit"]["resolver_status"]["queried"] is True
    assert body["audit"]["resolver_status"]["attempted_count"] == 1
    assert body["audit"]["resolver_status"]["resolved_count"] == 1
    resolve_step = next(step for step in body["audit"]["agent_trace"] if step["step"] == "resolve_variant")
    assert resolve_step["status"] == "resolved"
    assert body["evidence"]
    assert "唯一映射" not in variant.get("warnings", []) or not any(
        "缺少转录本" in warning for warning in variant.get("warnings", [])
    )


def test_agent_resolves_cdna_without_transcript_instead_of_blocking(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 c.794T>C",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    variant = body["variants"][0]
    assert variant["transcript"] == "NM_002468.5"
    assert variant["mapping_status"] == "unique"
    assert variant["genomic_hgvs"] == "chr3:g.38181403T>C"
    assert body["audit"]["resolver_status"]["resolved_count"] == 1
    assert body["evidence"]
    assert not any(
        gate.get("decision") == "ask_for_confirmation"
        for gate in body["safety"]["variant_gates"]
    )


def test_agent_leaves_truly_unresolvable_variant_untouched(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "BCL-2 高表达",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    variant = body["variants"][0]
    assert variant["gene"] == "BCL2"
    assert variant["mapping_status"] == "insufficient"
    assert body["audit"]["resolver_status"]["queried"] is False
    assert body["audit"]["resolver_status"]["attempted_count"] == 0
    assert not variant["enrichment"]
    assert variant["gate"]["decision"] == "ask_for_confirmation"
    assert variant["missing"]["blocking"]
    assert "需要医生确认或阻断" in body["answer"]["markdown"]


def test_composite_resolver_falls_back_to_mock_when_live_fails():
    from backend.app.services.molecular_evidence import (
        CompositeVariantResolver,
        MockVariantResolver,
        MolecularInputParser,
    )

    class FailingLive:
        resolver_name = "MyVariant.info"

        def resolve(self, variant):
            raise TimeoutError("network down")

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    resolver = CompositeVariantResolver([FailingLive(), MockVariantResolver()])

    resolved = resolver.resolve(variant)

    assert resolved is not None
    assert resolved["source"] == "mock"
    assert resolved["genomic_hgvs"] == "chr3:g.38181403T>C"


def test_myvariant_resolver_parses_hits_without_network():
    from backend.app.services.molecular_evidence import (
        MolecularInputParser,
        MyVariantResolver,
        _extract_myvariant_hits,
    )

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    resolver = MyVariantResolver()
    data = [
        {
            "_id": "variant-demo",
            "hgvs": {
                "GRCh37": "chr3:g.38181403T>C",
                "GRCh38": "chr3:g.38129912T>C",
            },
            "vcf": {"chrom": "3", "pos": 38181403, "ref": "T", "alt": "C"},
        }
    ]

    hits = _extract_myvariant_hits(data)
    resolved = resolver._resolution_from_hit(hits[0], variant)

    assert len(hits) == 1
    assert resolved is not None
    assert resolved["genomic_hgvs"] == "chr3:g.38181403T>C"
    assert resolver._build_query(variant) == "MYD88:p.L265P"


def test_myvariant_provider_normalizes_annotation_hit():
    from backend.app.services.molecular_evidence import MolecularInputParser, MyVariantProvider

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    hit = {
        "_id": "hgvs:chr3:g.38181403T>C",
        "rsid": "rs387907274",
        "dbsnp": {"rsid": "rs387907274"},
        "clinvar": {"clinical_significance": ["Uncertain significance"], "rsid": "rs387907274"},
        "gnomad_exome": {"af": 1.2e-05},
        "dbnsfp": {"revel_score": 0.95, "polyphen2": {"hdiv": {"pred": "probably damaging"}}, "sift": {"pred": "deleterious"}},
        "cadd": [{"phred": 26.8}],
        "hgvs": "chr3:g.38181403T>C",
    }
    provider = MyVariantProvider()

    raw = provider._normalize_hit(hit, variant)

    assert raw["provider"] == "MyVariant"
    assert raw["rsid"] == "rs387907274"
    assert raw["allele_freq"] == pytest.approx(1.2e-05)
    assert "REVEL 0.95" in raw["claim"]
    assert "CADD 26.8" in raw["claim"]
    assert "dbSNP 编号 rs387907274" in raw["claim"]
    assert raw["genomic_hgvs"] == "chr3:g.38181403T>C"
    assert raw["evidence_level"] == "L5"


def test_myvariant_mock_card_included_in_query(client: TestClient):
    resp = client.post(
        "/api/molecular-evidence/query",
        json={
            "variants_text": "MYD88 p.L265P",
            "disease": "DLBCL",
            "sample_type": "tumor tissue",
            "provider_mode": "mock",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    myvariant_cards = [card for card in body["evidence"] if card["provider"] == "MyVariant"]
    assert len(myvariant_cards) == 1
    assert "群体等位基因频率" in myvariant_cards[0]["claim"]
    assert myvariant_cards[0]["disease_match"] == "未知"
    assert myvariant_cards[0]["evidence_level"] == "L5"
    assert myvariant_cards[0]["gate"] is not None


def test_downgrade_reasons_are_written_for_doctors():
    from backend.app.services.molecular_evidence import (
        CivicProvider,
        EvidenceCardBuilder,
        MolecularInputParser,
        RawEvidenceRecord,
        SafetyGate,
        utc_now_iso,
    )

    variant = MolecularInputParser().parse(
        "MYD88 p.L265P", disease="DLBCL", sample_type="tumor tissue"
    )[0]
    item = {
        "status": "SUBMITTED",
        "description": "Pending evidence statement.",
        "evidenceLevel": "B",
        "evidenceType": "PROGNOSTIC",
        "evidenceDirection": "SUPPORTS",
        "disease": {"name": "Acute Myeloid Leukemia"},
    }
    raw = CivicProvider()._normalize_item("9376", item, variant)
    record = RawEvidenceRecord("CIViC", "EID9376", raw, utc_now_iso())
    card = EvidenceCardBuilder().build(record, variant)
    gate = SafetyGate().evaluate_card(card)

    assert gate.decision == "downgrade"
    reason_text = "；".join(gate.reasons)
    warning_text = "；".join(gate.required_warnings)
    assert "尚未经过编辑审核" in warning_text
    assert "跨病种" in reason_text
    assert "待审核线索" in warning_text
    assert not any("L5" in reason or "SUBMITTED" in reason or "内部证据等级" in reason for reason in gate.reasons)


def test_service_dedupes_content_identical_evidence_cards():
    from backend.app.services.molecular_evidence import (
        EvidenceCard,
        EvidenceConflict,
        MolecularEvidenceService,
    )

    def make_card(evidence_id):
        return EvidenceCard(
            evidence_id=evidence_id,
            claim="ClinVar 记录提供 BTK p.C481S 的分类信息。",
            source_type="database",
            source_title="ClinVar变异记录：BTK p.C481S",
            source_id=f"ClinVar:VCV{evidence_id}",
            source_url=f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{evidence_id}/",
            publication_or_release_date=None,
            source_version="live",
            access_status="metadata_only",
            evidence_level="L5",
            disease_match="其他肿瘤外推",
            population="",
            intervention_and_outcome="",
            applicability="",
            limitations="",
            conflict=EvidenceConflict(has_conflict=False),
            retrieved_at="2026-01-01T00:00:00+00:00",
            provider="ClinVar",
            variant_id="var_1",
        )

    service = MolecularEvidenceService(provider_mode="mock")

    duplicates = [make_card("1"), make_card("2"), make_card("3")]
    assert len(service._dedupe_evidence_cards(duplicates)) == 1
    assert service._dedupe_evidence_cards(duplicates)[0].evidence_id == "1"

    a = make_card("1")
    b = make_card("2")
    b.source_title = "ClinVar变异记录：BTK p.C481S（另一条记录）"
    assert len(service._dedupe_evidence_cards([a, b])) == 2

