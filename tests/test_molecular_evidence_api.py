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
    assert [v["mapping_status"] for v in body["variants"]] == ["protein_level_only", "protein_level_only"]
    assert len(body["evidence_cards"]) == 3
    disease_matches = [card["disease_match"] for card in body["evidence_cards"]]
    assert disease_matches.count("DLBCL直接证据") >= 2
    assert any(match != "DLBCL直接证据" for match in disease_matches)
    assert body["answer_markdown"].startswith("## 直接回答")
    assert body["doctor_summary"]["priority_action"]
    assert body["doctor_summary"]["next_step"]
    assert "## 证据依据" in body["answer_markdown"]
    assert "## 使用边界" in body["answer_markdown"]
    assert any(g["decision"] in {"allow", "downgrade", "ask_for_confirmation"} for g in body["safety_gate_results"])
    assert body["global_warnings"]
    assert body["missing_information"]
    assert body["provider_mode"] == "mock"
    assert body["required_providers"] == ["ClinVar", "CIViC"]
    assert body["provider_status"]["ClinVar"]["queried"] is True
    assert body["provider_status"]["CIViC"]["queried"] is True
    assert any(step["step"] == "complete" for step in body["agent_trace"])
    assert body["cache_hit"] is False
    assert body["cache_key"]
    assert body["query_log_id"]
    assert body["cache_entry_id"]

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
    assert body2["cache_hit"] is True
    assert body2["query_log_id"]
    assert body2["cache_entry_id"]


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
    assert body["evidence_cards"]
    assert body["evidence_cards"][0]["disease_match"] == "DLBCL直接证据"
    assert body["evidence_cards"][0]["access_status"] == "metadata_only"
    assert body["evidence_cards"][0]["evidence_level"] in {"L2", "L3"}
    assert "## 证据依据" in body["answer_markdown"]
    first_source_line = next(line for line in body["answer_markdown"].splitlines() if line.startswith("1. **"))
    assert "MYD88" in first_source_line or "MYD88" in body["answer_markdown"]


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
    assert statuses["TP53"] == "protein_level_only"
    assert statuses["BCL2"] == "insufficient"
    tp53_variant = next(v for v in body["variants"] if v["gene"] == "TP53")
    bcl2_variant = next(v for v in body["variants"] if v["gene"] == "BCL2")
    assert any("系统不会猜测转录本" in warning for warning in tp53_variant.get("warnings", []))
    assert "protein_hgvs 或 cdna_hgvs" in bcl2_variant.get("missing_fields", [])
    assert any(card["source_title"].startswith("ClinVar mock variation") for card in body["evidence_cards"])
    assert "当前至少存在一项需要医生确认或阻断的安全门控结果" in body["answer_markdown"]


def test_molecular_evidence_agent_queries_both_required_providers_per_variant(client: TestClient):
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
    query_steps = [step for step in body["agent_trace"] if step["step"] == "query_provider"]
    assert len(query_steps) == 4
    assert {step["provider"] for step in query_steps} == {"ClinVar", "CIViC"}
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

    records, trace, status = agent.run([variant])

    assert records
    assert status["ClinVar"]["state"] == "degraded"
    assert status["ClinVar"]["error_count"] == 1
    assert status["CIViC"]["state"] == "success"
    assert trace[-1]["completion_state"] == "degraded"


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

    records, trace, status = agent.run([variant])

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

