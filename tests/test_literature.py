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
