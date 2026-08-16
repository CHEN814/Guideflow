"""Local weighted rerank on top of PubMed Best Match."""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Set

from backend.app.models import LiteratureHit
from backend.app.services.bm25_store import tokenize
from backend.app.services.literature_query import DISEASE_VOCAB, LiteratureConcepts
from backend.app.services.pubmed_client import PubmedArticle


_DESIGN_SCORES = [
    (("meta-analysis",), 1.0),
    (("systematic review",), 0.95),
    (("practice guideline", "guideline"), 0.9),
    (("randomized controlled trial", "clinical trial, phase iii"), 0.85),
    (("clinical trial", "controlled clinical trial"), 0.75),
    (("observational study", "prospective studies", "cohort studies"), 0.65),
    (("retrospective studies", "case-control studies"), 0.5),
    (("comparative study",), 0.45),
    (("case reports",), 0.2),
]

_PENALTY_TYPES = {
    "retracted publication",
    "retraction of publication",
    "comment",
    "editorial",
    "letter",
    "news",
    "published erratum",
}


def _design_score(pub_types: Sequence[str]) -> float:
    lowered = [p.lower() for p in pub_types]
    best = 0.35  # default original research / unknown
    for keys, score in _DESIGN_SCORES:
        if any(any(k in pt for k in keys) for pt in lowered):
            best = max(best, score)
    # Consensus / guideline bonus already covered; keep soft floor
    return best


def _recency_score(year: Optional[str]) -> float:
    if not year or not str(year)[:4].isdigit():
        return 0.4
    pub_year = int(str(year)[:4])
    age = max(0, datetime.utcnow().year - pub_year)
    return math.exp(-age / 3.0)


def _topic_score(article: PubmedArticle, concepts: LiteratureConcepts) -> float:
    target_meshes: Set[str] = set()
    for key in concepts.disease_keys or ["dlbcl"]:
        vocab = DISEASE_VOCAB.get(key)
        if vocab:
            target_meshes.add(vocab["mesh"].lower())
    if not target_meshes:
        return 0.5
    mesh_all = {m.lower() for m in article.mesh}
    mesh_major = {m.lower() for m in article.mesh_major}
    if mesh_major & target_meshes:
        return 1.0
    if mesh_all & target_meshes:
        return 0.75
    # Title/abstract disease string hit
    blob = f"{article.title} {article.abstract}".lower()
    for key in concepts.disease_keys or []:
        for term in DISEASE_VOCAB.get(key, {}).get("tiab", []):
            if term.lower() in blob:
                return 0.6
    return 0.25


def _must_term_bonus(article: PubmedArticle, concepts: LiteratureConcepts) -> float:
    """Boost papers that literally mention key biomarkers / interventions."""
    blob = f"{article.title}\n{article.abstract}".lower()
    title = (article.title or "").lower()
    must = [t.lower() for t in (concepts.biomarker + concepts.intervention) if t]
    if not must:
        return 0.0
    bonus = 0.0
    for term in must:
        token = term.lower().replace("-", " ")
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
    # PubMed Best Match rank: 1-based; normalize inverse
    rank_norm = 1.0 - ((pubmed_rank - 1) / max(candidate_n, 1))
    rank_norm = max(0.0, min(1.0, rank_norm))
    # Title hit bonus
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
    # Retracted in title
    if re.search(r"\bretract", article.title or "", re.I):
        penalty += 0.8
    return penalty


def rank_articles(
    articles: Sequence[PubmedArticle],
    concepts: LiteratureConcepts,
    *,
    top_k: int = 5,
) -> List[LiteratureHit]:
    """Score and return top_k LiteratureHit objects."""
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
        rel = _rel_score(article, query_tokens, idx, n, concepts)
        design = _design_score(article.pub_types)
        recency = _recency_score(article.year)
        topic = _topic_score(article, concepts)
        penalty = _penalty(article)
        score = 0.35 * rel + 0.25 * design + 0.20 * recency + 0.15 * topic - penalty
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
                    "rel": round(rel, 4),
                    "design": round(design, 4),
                    "recency": round(recency, 4),
                    "topic": round(topic, 4),
                    "penalty": round(penalty, 4),
                },
            )
        )

    scored.sort(key=lambda h: h.score, reverse=True)
    top = scored[: max(0, top_k)]
    for i, hit in enumerate(top, start=1):
        hit.rank = i
    return top
