"""Unit tests for PubMed literature Q2Q / ranker / format (no live NCBI)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.models import LiteratureHit, QAResult, SearchDocument
from backend.app.services.literature_format import format_literature_section
from backend.app.services.literature_query import (
    build_pubmed_query,
    extract_concepts_rule,
)
from backend.app.services.literature_ranker import rank_articles
from backend.app.services.pubmed_client import PubmedArticle, PubmedClient


def test_extract_concepts_tp53_prognosis():
    concepts = extract_concepts_rule("TP53突变类型与DLBCL预后关系")
    assert "dlbcl" in concepts.disease_keys
    assert any("TP53" in b.upper() for b in concepts.biomarker)
    assert concepts.outcome
    assert concepts.focus == "prognosis"


def test_extract_concepts_cart():
    concepts = extract_concepts_rule("CART治疗rrDLBCL的无复发生存率是多少")
    assert any("CAR" in i.upper() for i in concepts.intervention)
    assert "dlbcl" in concepts.disease_keys


def test_extract_concepts_lymphogen_after_chinese():
    concepts = extract_concepts_rule("DLBCL分子分型LymphoGEN和LymphPlex有什么区别？")
    joined = " ".join(concepts.biomarker).lower()
    assert "lymphogen" in joined
    assert "lymphplex" in joined
    q = build_pubmed_query(concepts, level=1)
    assert "LymphoGEN" in q or "lymphogen" in q.lower()


def test_build_query_has_mesh_and_tiab():
    concepts = extract_concepts_rule("TP53突变类型与DLBCL预后关系")
    q1 = build_pubmed_query(concepts, level=1, recent_years=5)
    assert "[MeSH Terms]" in q1
    assert "[tiab]" in q1
    assert "hasabstract" in q1
    assert "English[lang]" in q1
    assert "TP53" in q1

    q3 = build_pubmed_query(concepts, level=3)
    # L3 is tiab-only for disease block path; still may have filters
    assert "[tiab]" in q3
    assert "hasabstract" in q3


def test_build_query_tighten_adds_pubtype():
    concepts = extract_concepts_rule("DLBCL 一线治疗")
    q = build_pubmed_query(concepts, level=1, tighten=True)
    assert "Meta-Analysis[pt]" in q
    assert "Randomized Controlled Trial[pt]" in q


def test_rank_articles_prefers_meta_and_penalizes_retraction():
    concepts = extract_concepts_rule("TP53 DLBCL prognosis")
    articles = [
        PubmedArticle(
            pmid="1",
            title="Editorial on TP53",
            abstract="Comment only",
            year="2024",
            pub_types=["Editorial"],
            mesh=["Lymphoma, Large B-Cell, Diffuse"],
            mesh_major=["Lymphoma, Large B-Cell, Diffuse"],
        ),
        PubmedArticle(
            pmid="2",
            title="TP53 mutations and prognosis in diffuse large B-cell lymphoma",
            abstract="RESULTS: TP53 mutation associated with worse overall survival in DLBCL.",
            year="2023",
            pub_types=["Meta-Analysis"],
            mesh=["Lymphoma, Large B-Cell, Diffuse", "Tumor Suppressor Protein p53"],
            mesh_major=["Lymphoma, Large B-Cell, Diffuse"],
        ),
        PubmedArticle(
            pmid="3",
            title="Retracted: TP53 in DLBCL",
            abstract="Retracted paper",
            year="2022",
            pub_types=["Retracted Publication"],
            mesh=["Lymphoma, Large B-Cell, Diffuse"],
        ),
    ]
    hits = rank_articles(articles, concepts, top_k=3)
    assert hits
    assert hits[0].pmid == "2"
    assert all(h.pmid != "3" or h.rank > 1 for h in hits)


def test_parse_efetch_abstract_sections():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>99999999</PMID>
          <Article>
            <ArticleTitle>Demo DLBCL paper</ArticleTitle>
            <Abstract>
              <AbstractText Label="BACKGROUND">Background text.</AbstractText>
              <AbstractText Label="RESULTS">Result text.</AbstractText>
            </Abstract>
            <Journal>
              <Title>Blood</Title>
              <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
            </Journal>
            <Language>eng</Language>
            <PublicationTypeList>
              <PublicationType>Journal Article</PublicationType>
            </PublicationTypeList>
            <ELocationID EIdType="doi">10.1000/demo</ELocationID>
          </Article>
          <MeshHeadingList>
            <MeshHeading>
              <DescriptorName MajorTopicYN="Y">Lymphoma, Large B-Cell, Diffuse</DescriptorName>
            </MeshHeading>
          </MeshHeadingList>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    articles = PubmedClient._parse_efetch_xml(xml)
    assert len(articles) == 1
    art = articles[0]
    assert art.pmid == "99999999"
    assert "BACKGROUND:" in art.abstract
    assert "RESULTS:" in art.abstract
    assert art.doi == "10.1000/demo"
    assert "Lymphoma, Large B-Cell, Diffuse" in art.mesh_major


def test_format_literature_section_isolated():
    hits = [
        LiteratureHit(
            pmid="123",
            title="Example paper",
            abstract="RESULTS: Something useful about DLBCL.",
            journal="Blood",
            year="2024",
            pub_types=["Journal Article"],
            rank=1,
            url="https://pubmed.ncbi.nlm.nih.gov/123/",
        )
    ]
    text = format_literature_section(hits, question="DLBCL", qwen_client=None)
    assert "## 指南外最新文献" in text
    assert "[L1]" in text
    assert "PMID 123" in text
    assert "[S1]" not in text
    assert "不构成诊疗推荐" in text


def test_qa_result_payload_includes_literature():
    hit = LiteratureHit(
        pmid="42",
        title="Lit title",
        abstract="abs",
        rank=1,
        url="https://pubmed.ncbi.nlm.nih.gov/42/",
    )
    result = QAResult(
        question="q",
        answer="a",
        sources=[],
        verification={"status": "ok"},
        run_id="r1",
        trace_path="",
        literature=[hit],
    )
    payload = result.to_web_payload()
    assert "literature" in payload
    assert payload["literature"][0]["pmid"] == "42"
    assert payload["literature"][0]["badge"] == "PubMed"
    assert "仅摘要" in payload["literature"][0]["tier_label"]


def test_pubmed_cache_roundtrip(tmp_path: Path):
    client = PubmedClient(
        email="test@example.com",
        cache_dir=tmp_path / "pubmed",
        esearch_timeout_s=0.1,
        efetch_timeout_s=0.1,
    )
    path = client.article_cache_dir / "1.json"
    art = PubmedArticle(pmid="1", title="t", abstract="a", year="2020")
    client._write_cache(path, art.to_dict())
    cached = client._read_cache(path, ttl_s=3600)
    assert cached["pmid"] == "1"


def test_extract_line_of_therapy_second_line():
    concepts = extract_concepts_rule("复发难治 DLBCL 二线 CAR-T 怎么选")
    assert "second-line" in concepts.line_of_therapy
    q = build_pubmed_query(concepts, level=1)
    assert "second-line" in q.lower() or "relapsed" in q.lower()


def test_evidence_tier_phase3_rct_is_e1():
    from backend.app.services.evidence_tier import classify_evidence_tier

    res = classify_evidence_tier(
        title="POLARIX: pola-R-CHP in previously untreated DLBCL",
        abstract="A randomized phase III trial of polatuzumab vedotin.",
        pub_types=["Randomized Controlled Trial", "Clinical Trial, Phase III"],
    )
    assert res.tier == "E1"
    assert "III" in res.study_design_zh or "RCT" in res.study_design_zh


def test_evidence_tier_single_arm_pivotal_is_e2():
    from backend.app.services.evidence_tier import classify_evidence_tier

    res = classify_evidence_tier(
        title="Epcoritamab monotherapy for Richter transformation (EPCORE CLL-1): findings from a single-arm, multicentre, open-label, phase 1b/2 trial.",
        abstract="We conducted a single-arm phase 1b/2 trial of epcoritamab.",
        pub_types=["Clinical Trial, Phase II", "Clinical Trial"],
    )
    assert res.tier == "E2"
    assert "注册" in res.study_design_zh or "II" in res.study_design_zh


def test_evidence_tier_real_world_is_e4():
    from backend.app.services.evidence_tier import classify_evidence_tier

    res = classify_evidence_tier(
        title="Polatuzumab Vedotin Plus R-CHP: A Real-World, Multi-Center, Retrospective Cohort Study",
        abstract="This multicenter retrospective real-world study evaluated Pola-R-CHP.",
        pub_types=["Observational Study", "Retrospective Studies"],
    )
    assert res.tier == "E4"


def test_evidence_tier_case_report_is_e5():
    from backend.app.services.evidence_tier import classify_evidence_tier

    res = classify_evidence_tier(
        title="A rare case of DLBCL",
        abstract="We report a single patient.",
        pub_types=["Case Reports"],
    )
    assert res.tier == "E5"


def test_evidence_tier_guideline_citation_lifts_to_e1():
    from backend.app.services.evidence_tier import classify_evidence_tier

    res = classify_evidence_tier(
        title="Some observational DLBCL paper",
        abstract="Retrospective cohort.",
        pub_types=["Retrospective Studies"],
        in_guideline=True,
        guideline_ref="NCCN B-Cell Lymphomas",
    )
    assert res.tier == "E1"
    assert res.in_guideline is True


def test_journal_lookup_blood_and_unknown_neutral():
    from backend.app.services.journal_quality import journal_score, lookup_journal, format_journal_meta

    blood = lookup_journal("Blood")
    assert blood is not None
    assert blood.tier == "T1"
    assert blood.jcr_if is not None
    assert journal_score("Blood") > journal_score("Some Unknown Journal XYZ")
    # Unmatched is neutral, not T3 penalty
    assert abs(journal_score("Some Unknown Journal XYZ") - 0.55) < 1e-6
    meta = format_journal_meta("Blood", "2024")
    assert "IF" in meta
    assert "Q1" in meta or "JCR" in meta


def test_rank_tier_first_e2_before_e4():
    concepts = extract_concepts_rule("DLBCL 二线 epcoritamab")
    articles = [
        PubmedArticle(
            pmid="10",
            title="Efficacy of Pola-R-CHP: A Real-World Retrospective Cohort in DLBCL",
            abstract="Multicenter retrospective real-world study of polatuzumab in diffuse large B-cell lymphoma.",
            year="2024",
            journal="Cancer Med",
            pub_types=["Retrospective Studies", "Observational Study"],
            mesh=["Lymphoma, Large B-Cell, Diffuse"],
            mesh_major=["Lymphoma, Large B-Cell, Diffuse"],
        ),
        PubmedArticle(
            pmid="20",
            title="Epcoritamab in relapsed DLBCL (EPCORE): single-arm open-label phase 1b/2 trial",
            abstract="Single-arm phase 1b/2 pivotal trial of epcoritamab in relapsed/refractory diffuse large B-cell lymphoma.",
            year="2023",
            journal="Lancet Oncol",
            pub_types=["Clinical Trial, Phase II", "Clinical Trial"],
            mesh=["Lymphoma, Large B-Cell, Diffuse"],
            mesh_major=["Lymphoma, Large B-Cell, Diffuse"],
        ),
    ]
    hits = rank_articles(articles, concepts, top_k=2)
    assert hits[0].pmid == "20"
    assert hits[0].evidence_tier == "E2"
    assert hits[1].evidence_tier == "E4"


def test_rank_penalizes_disease_mismatch_mcl():
    concepts = extract_concepts_rule("DLBCL CAR-T 疗效")
    articles = [
        PubmedArticle(
            pmid="mcl",
            title="Lisocabtagene Maraleucel in Relapsed/Refractory Mantle Cell Lymphoma: TRANSCEND NHL 001",
            abstract="Primary analysis of the mantle cell lymphoma cohort from TRANSCEND NHL 001, a phase I study of liso-cel / CAR-T.",
            year="2024",
            journal="J Clin Oncol",
            pub_types=["Clinical Trial, Phase I"],
            mesh=["Lymphoma, Mantle-Cell"],
            mesh_major=["Lymphoma, Mantle-Cell"],
        ),
        PubmedArticle(
            pmid="dlbcl",
            title="CAR-T in relapsed diffuse large B-cell lymphoma: phase 2 study",
            abstract="Prospective phase 2 clinical trial of CAR-T in relapsed/refractory DLBCL.",
            year="2023",
            journal="Blood",
            pub_types=["Clinical Trial, Phase II"],
            mesh=["Lymphoma, Large B-Cell, Diffuse"],
            mesh_major=["Lymphoma, Large B-Cell, Diffuse"],
        ),
    ]
    hits = rank_articles(articles, concepts, top_k=2)
    assert hits[0].pmid == "dlbcl"
    # MCL should score lower on population even if journal is strong
    mcl = next(h for h in hits if h.pmid == "mcl")
    dlbcl = next(h for h in hits if h.pmid == "dlbcl")
    assert dlbcl.score_components["population"] > mcl.score_components["population"]


def test_enrich_literature_has_journal_meta_and_dynamic_tier():
    from backend.app.services.source_display import enrich_literature_dict

    hit = LiteratureHit(
        pmid="99",
        title="Demo",
        abstract="abs",
        journal="Blood",
        year="2024",
        rank=1,
        evidence_tier="E1",
        study_design_zh="III期RCT",
        journal_if=21.0,
        journal_quartile="Q1",
        journal_cas_tier=1,
        journal_tier="T1",
        in_guideline=False,
    )
    data = enrich_literature_dict(hit)
    assert "IF" in data["journal_meta"]
    assert "III期RCT" in data["tier_label"]
    assert "未经指南收录" in data["tier_label"]
    assert data["evidence_tier"] == "E1"


def test_guideline_cited_lookup_from_built_index():
    from backend.app.services.guideline_cited import lookup_guideline_citation

    # NCCN KB has pmid 39817679 (Cancer statistics 2025)
    hit = lookup_guideline_citation(pmid="39817679")
    assert hit is not None
    assert "nccn" in hit.sources
