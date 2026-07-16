from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from backend.app.models import GraphTriple
from backend.app.services.knowledge_graph import KnowledgeGraphBundle, MedicalOntology, load_knowledge_graph_bundle


@dataclass(frozen=True)
class KGHit:
    triple: GraphTriple
    score: float
    reason: str
    components: Dict[str, float]


class KnowledgeGraphRetriever:
    def __init__(self, bundle: KnowledgeGraphBundle) -> None:
        self.bundle = bundle
        self.ontology = MedicalOntology()
        self._entity_to_triples = self._build_entity_to_triples(bundle.triples)

    @classmethod
    def from_path(cls, path: Path) -> "KnowledgeGraphRetriever":
        if not path.exists():
            return cls(KnowledgeGraphBundle())
        return cls(load_knowledge_graph_bundle(path))

    @staticmethod
    def _build_entity_to_triples(triples: Sequence[GraphTriple]) -> Dict[str, List[GraphTriple]]:
        mapping: Dict[str, List[GraphTriple]] = defaultdict(list)
        for triple in triples:
            mapping[triple.subject_id].append(triple)
            mapping[triple.object_id].append(triple)
        return mapping

    def resolve_query_entities(self, query: str) -> List[Tuple[str, str]]:
        terms: List[Tuple[str, str]] = []
        for token in query.split():
            concept = self.ontology.normalize(token)
            if concept:
                terms.append((concept.canonical_id, concept.name))
        if not terms:
            lowered = query.lower()
            for concept in self.ontology.concepts:
                if concept.name.lower() in lowered:
                    terms.append((concept.canonical_id, concept.name))
        return self._unique(terms)

    def retrieve(self, query: str, top_k: int = 8, hops: int = 1) -> List[KGHit]:
        seeds = self.resolve_query_entities(query)
        if not seeds:
            return self._fallback_retrieve(query, top_k=top_k)

        scored: Dict[str, KGHit] = {}
        frontier = deque([(entity_id, 0) for entity_id, _ in seeds])
        visited = set()
        while frontier:
            entity_id, depth = frontier.popleft()
            if entity_id in visited or depth > hops:
                continue
            visited.add(entity_id)
            for triple in self._entity_to_triples.get(entity_id, []):
                score, components = self._score_triple(triple, {seed_id for seed_id, _ in seeds}, depth)
                reason = f"seed:{entity_id} depth:{depth}"
                current = scored.get(triple.triple_id)
                if current is None or score > current.score:
                    scored[triple.triple_id] = KGHit(triple=triple, score=score, reason=reason, components=components)
                other = triple.object_id if triple.subject_id == entity_id else triple.subject_id
                if other and other not in visited:
                    frontier.append((other, depth + 1))

        results = sorted(scored.values(), key=lambda hit: (hit.score, hit.triple.confidence), reverse=True)
        return results[:top_k]

    def expand_subgraph(self, entity_ids: Sequence[str], hops: int = 1, top_k: int = 20) -> List[GraphTriple]:
        frontier = deque([(entity_id, 0) for entity_id in entity_ids])
        seen_entities = set()
        seen_triples = set()
        triples: List[GraphTriple] = []
        while frontier:
            entity_id, depth = frontier.popleft()
            if entity_id in seen_entities or depth > hops:
                continue
            seen_entities.add(entity_id)
            for triple in self._entity_to_triples.get(entity_id, []):
                if triple.triple_id in seen_triples:
                    continue
                seen_triples.add(triple.triple_id)
                triples.append(triple)
                if triple.subject_id not in seen_entities:
                    frontier.append((triple.subject_id, depth + 1))
                if triple.object_id not in seen_entities:
                    frontier.append((triple.object_id, depth + 1))
        triples.sort(key=lambda triple: (triple.confidence, triple.validation_status == "trusted"), reverse=True)
        return triples[:top_k]

    def _fallback_retrieve(self, query: str, top_k: int = 8) -> List[KGHit]:
        lowered = query.lower()
        hits: List[KGHit] = []
        for triple in self.bundle.triples:
            text = f"{triple.subject_name} {triple.relation} {triple.object_name} {triple.evidence_text}".lower()
            if any(token in text for token in lowered.split() if len(token) > 1):
                score = triple.confidence * 0.8 + 0.2
                hits.append(KGHit(triple=triple, score=score, reason="lexical", components={"base": triple.confidence, "lexical_fallback": 0.2}))
        hits.sort(key=lambda hit: (hit.score, hit.triple.confidence), reverse=True)
        return hits[:top_k]

    @staticmethod
    def _score_triple(triple: GraphTriple, seed_ids: set[str], depth: int) -> Tuple[float, Dict[str, float]]:
        def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
            return max(low, min(high, value))

        base = float(triple.confidence or 0.0)
        evidence_kind = (triple.evidence_kind or "text").lower()
        source_count = len(triple.evidence_source_ids or [])
        evidence_text = (triple.evidence_text or "").lower()

        source_quality_map = {
            "guideline": 0.18,
            "consensus": 0.16,
            "randomized_trial": 0.15,
            "cohort_study": 0.10,
            "discussion": 0.06,
            "reference_only": 0.03,
            "text": 0.05,
        }
        source_quality = source_quality_map.get(evidence_kind, 0.05)

        evidence_support = min(0.12, 0.03 * max(0, source_count - 1))
        if source_count >= 3:
            evidence_support += 0.04

        text_match = 0.0
        if triple.subject_name and triple.subject_name.lower() in evidence_text:
            text_match += 0.04
        if triple.relation and triple.relation.lower() in evidence_text:
            text_match += 0.04
        if triple.object_name and triple.object_name.lower() in evidence_text:
            text_match += 0.04
        if any(marker in evidence_text for marker in ("recommended", "should", "preferred", "indicated", "guideline")):
            text_match += 0.05

        structural_support = 0.0
        if triple.subject_id in seed_ids or triple.object_id in seed_ids:
            structural_support += 0.10
        structural_support += max(0.0, 0.08 - 0.04 * depth)

        review_bonus = 0.08 if triple.validation_status == "trusted" else 0.0
        if getattr(triple, "review_status", "") == "approved":
            review_bonus += 0.05

        hop_penalty = 0.06 * depth
        conflict_penalty = 0.10 if triple.validation_status in ("needs_review", "conflicted") else 0.0
        ambiguity_penalty = 0.05 if len(triple.evidence_text or "") < 40 else 0.0

        components = {
            "base": round(base, 4),
            "source_quality": round(source_quality, 4),
            "evidence_support": round(evidence_support, 4),
            "text_match": round(text_match, 4),
            "structural_support": round(structural_support, 4),
            "review_bonus": round(review_bonus, 4),
            "hop_penalty": round(hop_penalty, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "ambiguity_penalty": round(ambiguity_penalty, 4),
        }
        score = clamp(
            base
            + source_quality
            + evidence_support
            + text_match
            + structural_support
            + review_bonus
            - hop_penalty
            - conflict_penalty
            - ambiguity_penalty
        )
        components["final"] = round(score, 4)
        return score, components

    @staticmethod
    def _unique(items: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
        seen = set()
        result = []
        for item in items:
            if item[0] in seen:
                continue
            seen.add(item[0])
            result.append(item)
        return result
