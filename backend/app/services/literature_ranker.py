"""Doctor-facing tier-first literature ranking on top of PubMed Best Match."""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import List, Optional, Sequence, Set

from backend.app.models import LiteratureHit
from backend.app.services.bm25_store import tokenize
from backend.app.services.evidence_tier import classify_evidence_tier
from backend.app.services.guideline_cited import lookup_guideline_citation
from backend.app.services.journal_quality import lookup_journal
from backend.app.services.literature_query import DISEASE_VOCAB, LINE_OF_THERAPY_VOCAB, LiteratureConcepts
from backend.app.services.pubmed_client import PubmedArticle


_PENALTY_TYPES = {
    "retracted publication",
    "retraction of publication",
    "comment",
    "editorial",
    "letter",
    "news",
    "published erratum",
}

# Competing lymphoma entities used to detect disease mismatch (e.g. MCL in a DLBCL query).
_COMPETING_DISEASE = {
    "mcl": ["mantle cell lymphoma", "mantle-cell lymphoma"],
    "fl": ["follicular lymphoma"],
    "mzl": ["marginal zone lymphoma"],
    "cll": ["chronic lymphocytic leukemia", "small lymphocytic lymphoma", "richter"],
    "hl": ["hodgkin lymphoma", "hodgkin's lymphoma"],
    "ptcl": ["peripheral t-cell lymphoma", "t-cell lymphoma"],
}


def _recency_score(year: Optional[str]) -> float:
    if not year or not str(year)[:4].isdigit():
        return 0.4
    pub_year = int(str(year)[:4])
    age = max(0, datetime.utcnow().year - pub_year)
    return math.exp(-age / 3.0)


def _must_term_bonus(article: PubmedArticle, concepts: LiteratureConcepts) -> float:
    """Boost papers that literally mention key biomarkers / interventions."""
    blob = f"{article.title}\n{article.abstract}".lower()
    title = (article.title or "").lower()
    must = [t.lower() for t in (concepts.biomarker + concepts.intervention) if t]
    if not must:
        return 0.0
    bonus = 0.0
    for term in must:
        compact = term.lower().replace("-", "").replace(" ", "")
        if term.lower() in title or compact in title.replace("-", "").replace(" ", ""):
            bonus += 0.25
        elif term.lower() in blob or compact in blob.replace("-", "").replace(" ", ""):
            bonus += 0.12
        else:
            bonus -= 0.18
    return max(-0.35, min(0.45, bonus))


def _rel_score(
    article: PubmedArticle,
    query_tokens: Set[str],
    pubmed_rank: int,
    candidate_n: int,
    concepts: LiteratureConcepts,
) -> float:
    text = f"{article.title} {article.abstract}"
    d_tokens = set(tokenize(text))
    overlap = len(query_tokens & d_tokens) / max(len(query_tokens), 1)
    rank_norm = 1.0 - ((pubmed_rank - 1) / max(candidate_n, 1))
    rank_norm = max(0.0, min(1.0, rank_norm))
    title_tokens = set(tokenize(article.title))
    title_overlap = len(query_tokens & title_tokens) / max(len(query_tokens), 1)
    must = _must_term_bonus(article, concepts)
    return 0.45 * overlap + 0.20 * rank_norm + 0.20 * title_overlap + 0.15 * (must + 0.35) / 0.8


def _penalty(article: PubmedArticle) -> float:
    penalty = 0.0
    types = {p.lower() for p in article.pub_types}
    if types & _PENALTY_TYPES:
        penalty += 0.6
    if not (article.abstract or "").strip():
        penalty += 0.5
    lang = (article.language or "").lower()
    if lang and lang not in {"eng", "en", "english"}:
        penalty += 0.3
    if re.search(r"\bretract", article.title or "", re.I):
        penalty += 0.8
    return penalty


def _population_score(article: PubmedArticle, concepts: LiteratureConcepts) -> float:
    """Disease + line-of-therapy + biomarker/subtype match from a clinician's view."""
    blob = f"{article.title}\n{article.abstract}".lower()
    mesh_all = {m.lower() for m in article.mesh}
    mesh_major = {m.lower() for m in article.mesh_major}
    score = 0.5
    reasons_penalty = 0.0

    target_keys = concepts.disease_keys or ["dlbcl"]
    target_meshes = set()
    target_tiab = set()
    for key in target_keys:
        vocab = DISEASE_VOCAB.get(key)
        if not vocab:
            continue
        target_meshes.add(vocab["mesh"].lower())
        for term in vocab.get("tiab") or []:
            target_tiab.add(term.lower())

    disease_hit = False
    if mesh_major & target_meshes:
        score = 1.0
        disease_hit = True
    elif mesh_all & target_meshes:
        score = 0.85
        disease_hit = True
    elif any(t in blob for t in target_tiab):
        score = 0.75
        disease_hit = True

    # Hard penalty when a competing lymphoma is clearly the subject and target disease is absent.
    for other_key, phrases in _COMPETING_DISEASE.items():
        if other_key in target_keys:
            continue
        if any(p in blob for p in phrases) and not disease_hit:
            reasons_penalty += 0.55
            break
        if any(p in blob for p in phrases) and disease_hit:
            # Mentioned as comparator / transformation — mild dampening only.
            reasons_penalty += 0.08

    # Line-of-therapy match
    if concepts.line_of_therapy:
        line_hits = 0
        for code in concepts.line_of_therapy:
            phrases = [p.lower() for p in LINE_OF_THERAPY_VOCAB.get(code, [])]
            if any(p in blob for p in phrases):
                line_hits += 1
        if line_hits:
            score = min(1.0, score + 0.12 * line_hits)
        else:
            reasons_penalty += 0.12

    # Biomarker / intervention literal presence
    must = [t.lower() for t in (concepts.biomarker + concepts.intervention) if t]
    if must:
        matched = sum(
            1
            for t in must
            if t in blob or t.replace("-", "").replace(" ", "") in blob.replace("-", "").replace(" ", "")
        )
        if matched:
            score = min(1.0, score + 0.08 * matched)
        else:
            reasons_penalty += 0.15

    return max(0.0, min(1.0, score - reasons_penalty))


def rank_articles(
    articles: Sequence[PubmedArticle],
    concepts: LiteratureConcepts,
    *,
    top_k: int = 5,
) -> List[LiteratureHit]:
    """Tier-first rank: E1>E2>… then within-tier continuous score."""
    query_tokens = set(tokenize(" ".join(concepts.english_tokens())))
    if not query_tokens:
        query_tokens = set(tokenize("diffuse large B-cell lymphoma DLBCL"))

    must_terms = [t for t in (concepts.biomarker + concepts.intervention) if t]
    filtered: List[tuple[int, PubmedArticle]] = []
    for idx, article in enumerate(articles, start=1):
        if must_terms:
            blob = f"{article.title}\n{article.abstract}".lower().replace("-", "")
            if not any(
                t.lower().replace("-", "").replace(" ", "") in blob.replace(" ", "")
                for t in must_terms
            ):
                continue
        filtered.append((idx, article))
    # If hard filter emptied the list (MeSH-only hits, OCR quirks), fall back.
    work = filtered if filtered else [(i + 1, a) for i, a in enumerate(articles)]

    n = len(articles)
    scored: List[LiteratureHit] = []
    for idx, article in work:
        citation = lookup_guideline_citation(
            pmid=article.pmid,
            doi=article.doi,
            title=article.title,
        )
        in_guideline = citation is not None
        guideline_ref = citation.label if citation else None

        tier_res = classify_evidence_tier(
            title=article.title or "",
            abstract=article.abstract or "",
            pub_types=article.pub_types,
            in_guideline=in_guideline,
            guideline_ref=guideline_ref,
        )
        jq = lookup_journal(article.journal)

        rel = _rel_score(article, query_tokens, idx, n, concepts)
        population = _population_score(article, concepts)
        journal = jq.score if jq else 0.55
        recency = _recency_score(article.year)
        penalty = _penalty(article)

        # Within-tier continuous score (doctor decision order).
        score = (
            0.40 * population
            + 0.25 * journal
            + 0.20 * recency
            + 0.15 * rel
            - penalty
        )

        scored.append(
            LiteratureHit(
                pmid=article.pmid,
                title=article.title,
                abstract=article.abstract,
                journal=article.journal,
                year=article.year,
                doi=article.doi,
                pub_types=list(article.pub_types),
                mesh=list(article.mesh),
                score=float(score),
                rank=0,
                url=article.url,
                pubmed_rank=idx,
                score_components={
                    "population": round(population, 4),
                    "journal": round(journal, 4),
                    "recency": round(recency, 4),
                    "rel": round(rel, 4),
                    "penalty": round(penalty, 4),
                    "tier": tier_res.tier,
                    "tier_rank": tier_res.tier_rank,
                    "tier_reasons": list(tier_res.reasons),
                },
                evidence_tier=tier_res.tier,
                study_design_zh=tier_res.study_design_zh,
                journal_if=jq.jcr_if if jq else None,
                journal_quartile=jq.jcr_quartile if jq else None,
                journal_cas_tier=jq.cas_tier if jq else None,
                journal_tier=jq.tier if jq else None,
                in_guideline=in_guideline,
                guideline_ref=guideline_ref,
            )
        )

    # Disease-compatible first (prevents MCL/FL papers floating above DLBCL hits
    # just because they carry a pivotal trial name), then tier, guideline, score.
    scored.sort(
        key=lambda h: (
            0 if float((h.score_components or {}).get("population") or 0.0) >= 0.35 else 1,
            int((h.score_components or {}).get("tier_rank") or 5),
            0 if h.in_guideline else 1,
            -h.score,
        )
    )
    top = scored[: max(0, top_k)]
    for i, hit in enumerate(top, start=1):
        hit.rank = i
    return top
