from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.models import DiscussionChunk, GraphTriple, GuidelinePage, ReferenceEntry, StructuredKnowledgeBase


ENTITY_PATTERNS: List[tuple[str, str, Sequence[str]]] = [
    ("Disease", "DLBCL", [r"\bDLBCL\b", r"diffuse large b[- ]cell lymphoma", r"弥漫大B细胞淋巴瘤"]),
    ("Disease", "FL", [r"\bFL\b", r"follicular lymphoma", r"滤泡性淋巴瘤"]),
    ("Disease", "MCL", [r"\bMCL\b", r"mantle cell lymphoma", r"套细胞淋巴瘤"]),
    ("Disease", "PMBL", [r"primary mediastinal b[- ]cell lymphoma", r"\bPMBL\b"]),
    ("Disease", "LBCL", [r"large B-cell lymphoma", r"large b[- ]cell lymphoma"]),
    ("Subtype", "GCB", [r"\bGCB\b", r"germinal center b[- ]cell"]),
    ("Subtype", "ABC", [r"\bABC\b", r"activated b[- ]cell"]),
    ("Subtype", "Double-hit", [r"double[- ]hit", r"双打击"]),
    ("Subtype", "Double-expressor", [r"double[- ]expressor", r"双表达"]),
    ("Subtype", "Non-GCB", [r"non[- ]?GCB", r"non germinal center"]),
    ("Treatment", "R-CHOP", [r"\bR-CHOP\b", r"\bRCHOP\b"]),
    ("Treatment", "Pola-R-CHP", [r"Pola[- ]?R[- ]?CHP"]),
    ("Treatment", "DA-EPOCH-R", [r"DA[- ]?EPOCH[- ]?R"]),
    ("Treatment", "CAR-T", [r"CAR[- ]?T"]),
    ("Treatment", "ASCT", [r"ASCT", r"autologous stem cell transplantation"]),
    ("Treatment", "Bispecific antibody", [r"bispecific antibody", r"双特异性抗体"]),
    ("Procedure", "CNS prophylaxis", [r"CNS prophylaxis", r"central nervous system prophylaxis", r"中枢神经系统预防"]),
    ("Procedure", "Radiotherapy", [r"radiotherapy", r"放疗"]),
    ("Procedure", "Biopsy", [r"biopsy", r"活检"]),
    ("Test", "PET-CT", [r"PET[- ]?CT", r"PET/CT"]),
    ("Test", "FISH", [r"\bFISH\b"]),
    ("Test", "Bone marrow biopsy", [r"bone marrow biopsy", r"骨髓活检"]),
    ("Test", "Echocardiography", [r"echocardiography", r"超声心动图"]),
    ("Test", "LDH", [r"\bLDH\b", r"乳酸脱氢酶"]),
    ("Biomarker", "TP53", [r"\bTP53\b"]),
    ("Biomarker", "MYC", [r"\bMYC\b"]),
    ("Biomarker", "BCL2", [r"\bBCL2\b"]),
    ("Biomarker", "BCL6", [r"\bBCL6\b"]),
    ("Biomarker", "CD19", [r"\bCD19\b"]),
    ("Biomarker", "CD20", [r"\bCD20\b"]),
    ("RiskFactor", "IPI", [r"\bIPI\b"]),
    ("RiskFactor", "ECOG", [r"\bECOG\b", r"performance status"]),
    ("RiskFactor", "Age", [r"age", r"年龄"]),
    ("RiskFactor", "LDH", [r"\bLDH\b", r"乳酸脱氢酶"]),
    ("RiskFactor", "Bulky disease", [r"bulky disease", r"bulky"]),
    ("AdverseEvent", "Neutropenia", [r"neutropenia", r"中性粒细胞减少"]),
    ("AdverseEvent", "Infection", [r"infection", r"感染"]),
    ("AdverseEvent", "Neuropathy", [r"neuropathy", r"周围神经病变"]),
    ("AdverseEvent", "Cardiotoxicity", [r"cardiotoxicity", r"心脏毒性"]),
    ("SupportiveCare", "G-CSF", [r"G-CSF", r"granulocyte colony[- ]?stimulating factor", r"粒细胞集落刺激因子"]),
    ("SupportiveCare", "Antiemetic prophylaxis", [r"antiemetic", r"止吐", r"预防性止吐"]),
    ("Scoring", "IPI", [r"\bIPI\b"]),
    ("Outcome", "Prognosis", [r"prognosis", r"预后"]),
    ("Outcome", "Response", [r"response", r"缓解", r"反应"]),
    ("Outcome", "Remission", [r"remission", r"缓解"]),
    ("Stage", "Staging", [r"staging", r"分期"]),
    ("PatientGroup", "Transplant-ineligible", [r"transplant[- ]?ineligible", r"不适合移植"]),
    ("PatientGroup", "Elderly", [r"elderly", r"老年"]),
    ("PatientGroup", "Frail", [r"frail", r"脆弱"]),
]

RELATION_RULES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "RECOMMENDS": {
        "Disease": ("Treatment", "Test", "Biomarker", "Stage", "Outcome", "Procedure", "SupportiveCare"),
        "Subtype": ("Treatment", "Test", "Biomarker", "RiskFactor"),
        "Stage": ("Treatment", "Test"),
        "Article": ("Treatment", "Test", "Biomarker", "Procedure"),
        "DiscussionChunk": ("Treatment", "Test", "Biomarker", "Procedure", "SupportiveCare"),
    },
    "INDICATED_FOR": {
        "Treatment": ("Disease", "Subtype", "Stage", "PatientGroup"),
        "Test": ("Disease", "Subtype", "Stage", "PatientGroup"),
        "Procedure": ("Disease", "Subtype", "Stage", "PatientGroup"),
        "SupportiveCare": ("Treatment", "Disease", "PatientGroup"),
    },
    "PREFERRED_OVER": {
        "Treatment": ("Treatment",),
        "Procedure": ("Procedure",),
    },
    "APPLIES_TO": {
        "Treatment": ("Disease", "Stage", "Scoring", "PatientGroup", "Subtype"),
        "Test": ("Disease", "Stage", "Biomarker", "PatientGroup", "Subtype"),
        "Disease": ("PatientGroup", "Stage"),
        "Procedure": ("Disease", "Subtype", "Stage", "PatientGroup"),
        "DiscussionChunk": ("Disease", "Stage", "Scoring", "Subtype", "PatientGroup"),
    },
    "REQUIRES": {
        "Treatment": ("Test", "Biomarker", "Stage", "Scoring", "RiskFactor"),
        "Procedure": ("Test", "Biomarker", "Stage", "Scoring"),
        "Page": ("Page",),
        "GuidelinePage": ("GuidelinePage",),
    },
    "CONTRAINDICATED_FOR": {
        "Treatment": ("Disease", "Stage", "PatientGroup", "Subtype"),
        "Test": ("Disease", "PatientGroup"),
        "Procedure": ("Disease", "PatientGroup"),
    },
    "NOT_RECOMMENDED_FOR": {
        "Treatment": ("Disease", "Stage", "PatientGroup", "Subtype"),
        "Procedure": ("Disease", "Stage", "PatientGroup"),
    },
    "ASSOCIATED_WITH": {
        "Disease": ("Biomarker", "Outcome", "Stage", "Scoring", "Subtype", "RiskFactor"),
        "Subtype": ("Outcome", "Biomarker", "RiskFactor"),
        "Biomarker": ("Outcome", "Disease"),
        "DiscussionChunk": ("Biomarker", "Outcome", "Stage", "Scoring", "Subtype", "RiskFactor"),
    },
    "NEXT_STEP": {
        "GuidelinePage": ("GuidelinePage",),
        "Page": ("Page",),
    },
    "CITES": {
        "DiscussionChunk": ("ReferenceEntry",),
        "GuidelinePage": ("ReferenceEntry",),
    },
    "MENTIONS": {
        "DiscussionChunk": ("Entity",),
        "GuidelinePage": ("Entity",),
        "Article": ("Entity",),
    },
}

RELATION_CUES: Dict[str, Sequence[str]] = {
    "RECOMMENDS": (
        "recommended",
        "recommend",
        "preferred",
        "first-line",
        "一线",
        "推荐",
        "首选",
        "优先",
        "suggest",
        "consider",
    ),
    "INDICATED_FOR": (
        "indicated",
        "indication",
        "适应证",
        "适用于",
        "for patients",
        "in patients with",
        "用于",
    ),
    "PREFERRED_OVER": (
        "preferred over",
        "prefer over",
        "优于",
        "优先于",
        "better than",
    ),
    "APPLIES_TO": (
        "applies to",
        "applies",
        "适用于",
        "适合",
        "for patients",
        "in patients with",
        "用于",
    ),
    "REQUIRES": (
        "requires",
        "require",
        "needs",
        "need",
        "需要",
        "应",
        "before",
        "prior",
    ),
    "CONTRAINDICATED_FOR": (
        "contraindicated",
        "not recommended",
        "avoid",
        "禁忌",
        "不推荐",
        "避免",
    ),
    "NOT_RECOMMENDED_FOR": (
        "not recommended",
        "avoid",
        "不推荐",
    ),
    "ASSOCIATED_WITH": (
        "associated with",
        "correlated with",
        "linked to",
        "prognosis",
        "预后",
        "相关",
        "提示",
    ),
    "NEXT_STEP": (
        "next",
        "下一步",
        "proceed",
        "then",
        "continue to",
        "转入",
    ),
}


@dataclass(frozen=True)
class OntologyConcept:
    concept_type: str
    name: str
    canonical_id: str
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateTriple:
    subject_id: str
    subject_name: str
    subject_type: str
    relation: str
    object_id: str
    object_name: str
    object_type: str
    evidence_text: str
    evidence_source_ids: List[str]
    evidence_kind: str
    confidence: float
    llm_score: Optional[float] = None
    validation_status: str = "candidate"
    reviewer: Optional[str] = None
    review_status: str = "pending"


@dataclass
class KnowledgeGraphBundle:
    ontology: List[OntologyConcept] = field(default_factory=list)
    triples: List[GraphTriple] = field(default_factory=list)
    rejected_candidates: List[CandidateTriple] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


class MedicalOntology:
    def __init__(self) -> None:
        self._concepts = self._build_concepts()
        self._alias_lookup = self._build_alias_lookup(self._concepts)

    @staticmethod
    def _slug(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text, flags=re.UNICODE)
        return re.sub(r"-+", "-", text).strip("-") or "item"

    def _build_concepts(self) -> List[OntologyConcept]:
        concepts: List[OntologyConcept] = []
        for concept_type, name, aliases in ENTITY_PATTERNS:
            canonical_id = f"{concept_type.lower()}:{self._slug(name)}"
            concepts.append(OntologyConcept(concept_type=concept_type, name=name, canonical_id=canonical_id, aliases=tuple(aliases)))
        concepts.extend(
            [
                OntologyConcept("Page", "Guideline Page", "page:guideline-page"),
                OntologyConcept("Article", "Discussion Article", "article:discussion-article"),
                OntologyConcept("ReferenceEntry", "Reference Entry", "reference:entry"),
                OntologyConcept("PatientGroup", "Patient Group", "group:patient"),
            ]
        )
        return concepts

    @staticmethod
    def _build_alias_lookup(concepts: Sequence[OntologyConcept]) -> Dict[str, OntologyConcept]:
        lookup: Dict[str, OntologyConcept] = {}
        for concept in concepts:
            lookup[concept.name.lower()] = concept
            lookup[concept.canonical_id.lower()] = concept
            for alias in concept.aliases:
                lookup[alias.lower()] = concept
        return lookup

    @property
    def concepts(self) -> List[OntologyConcept]:
        return list(self._concepts)

    def normalize(self, term: str) -> Optional[OntologyConcept]:
        key = term.strip().lower()
        if key in self._alias_lookup:
            return self._alias_lookup[key]
        for pattern, concept in self._alias_lookup.items():
            try:
                if re.search(pattern, term, flags=re.IGNORECASE):
                    return concept
            except re.error:
                continue
        return None

    def resolve_alias(self, term: str) -> Tuple[str, str]:
        concept = self.normalize(term)
        if concept:
            return concept.canonical_id, concept.name
        fallback = self._slug(term)
        return f"entity:{fallback}", term.strip()

    def allowed(self, subject_type: str, relation: str, object_type: str) -> bool:
        allowed_objects = RELATION_RULES.get(relation, {}).get(subject_type, ())
        return object_type in allowed_objects


_SENTENCE_RE = re.compile(r"[^。！？!?\.]+[。！？!?\.]*")


def _split_sentences(text: str) -> List[str]:
    sentences = [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]
    if sentences:
        return sentences
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_entities(text: str, ontology: MedicalOntology) -> List[Tuple[str, str, str]]:
    entities: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for concept_type, name, patterns in ENTITY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                concept_id, concept_name = ontology.resolve_alias(name)
                if concept_id in seen:
                    break
                seen.add(concept_id)
                entities.append((concept_id, concept_name, concept_type))
                break
    return entities


def _relation_from_sentence(sentence: str) -> Optional[str]:
    lowered = sentence.lower()
    for relation, cues in RELATION_CUES.items():
        if any(cue.lower() in lowered for cue in cues):
            return relation
    return None


def _score_relation(relation: str, source_kind: str, sentence: str) -> float:
    if relation == "NEXT_STEP":
        return 0.97 if source_kind == "flowchart" else 0.88
    if relation in {"CONTRAINDICATED_FOR", "NOT_RECOMMENDED_FOR"}:
        return 0.92 if source_kind == "text" else 0.86
    if relation in {"RECOMMENDS", "APPLIES_TO", "REQUIRES"}:
        base = {"flowchart": 0.95, "text": 0.83, "reference": 0.72}.get(source_kind, 0.75)
        if len(sentence) < 120:
            base += 0.03
        return min(base, 0.99)
    if relation == "ASSOCIATED_WITH":
        return 0.74 if source_kind == "text" else 0.68
    if relation == "CITES":
        return 0.98
    if relation == "MENTIONS":
        return 0.65
    return 0.6


class KnowledgeGraphBuilder:
    def __init__(self, ontology: Optional[MedicalOntology] = None) -> None:
        self.ontology = ontology or MedicalOntology()

    def build(self, kb: StructuredKnowledgeBase, llm_validator: Optional[Callable[[CandidateTriple], Tuple[bool, Optional[float], Optional[str]]]] = None) -> KnowledgeGraphBundle:
        candidates: List[CandidateTriple] = []
        candidates.extend(self._from_page_links(kb.guideline_pages))
        candidates.extend(self._from_discussion(kb.discussion_chunks, kb.reference_entries))
        candidates.extend(self._from_page_mentions(kb.guideline_pages))
        candidates.extend(self._from_article_mentions(kb.discussion_chunks))

        trusted: List[GraphTriple] = []
        rejected: List[CandidateTriple] = []
        for candidate in candidates:
            validated, llm_score, reviewer = self._validate_candidate(candidate, llm_validator)
            if validated is None:
                rejected.append(candidate)
                continue
            trusted.append(validated)
            if llm_score is not None:
                candidate.llm_score = llm_score
            if reviewer:
                candidate.reviewer = reviewer

        stats = {
            "ontology_concepts": len(self.ontology.concepts),
            "candidates": len(candidates),
            "trusted_triples": len(trusted),
            "rejected_candidates": len(rejected),
        }
        return KnowledgeGraphBundle(ontology=self.ontology.concepts, triples=trusted, rejected_candidates=rejected, stats=stats)

    def _validate_candidate(
        self,
        candidate: CandidateTriple,
        llm_validator: Optional[Callable[[CandidateTriple], Tuple[bool, Optional[float], Optional[str]]]],
    ) -> Tuple[Optional[GraphTriple], Optional[float], Optional[str]]:
        if not self.ontology.allowed(candidate.subject_type, candidate.relation, candidate.object_type):
            return None, None, None
        if candidate.subject_id == candidate.object_id:
            return None, None, None
        llm_score: Optional[float] = candidate.llm_score
        reviewer: Optional[str] = candidate.reviewer
        if llm_validator is not None:
            approved, llm_score, reviewer = llm_validator(candidate)
            if not approved:
                return None, llm_score, reviewer
        validation_status = "trusted" if candidate.confidence >= 0.75 else "needs_review"
        review_status = "auto_trusted" if validation_status == "trusted" else candidate.review_status
        triple = GraphTriple(
            triple_id=candidate_triple_id(candidate),
            subject_id=candidate.subject_id,
            subject_name=candidate.subject_name,
            subject_type=candidate.subject_type,
            relation=candidate.relation,
            object_id=candidate.object_id,
            object_name=candidate.object_name,
            object_type=candidate.object_type,
            confidence=min(1.0, round(candidate.confidence if llm_score is None else max(candidate.confidence, llm_score), 3)),
            validation_status=validation_status,
            evidence_text=candidate.evidence_text,
            evidence_source_ids=list(candidate.evidence_source_ids),
            evidence_kind=candidate.evidence_kind,
            llm_score=llm_score,
            reviewer=reviewer,
            review_status=review_status,
        )
        return triple, llm_score, reviewer

    def _from_page_links(self, pages: Sequence[GuidelinePage]) -> List[CandidateTriple]:
        triples: List[CandidateTriple] = []
        for page in pages:
            if page.page_type != "clinical_guideline":
                continue
            for link in page.outgoing_links:
                if link.edge_type != "flow" or not link.target_page_code:
                    continue
                subject_id = page.printed_page_code or page.page_id
                object_id = link.target_page_code
                triples.append(
                    CandidateTriple(
                        subject_id=subject_id,
                        subject_name=page.printed_page_code or page.page_id,
                        subject_type="GuidelinePage",
                        relation="NEXT_STEP",
                        object_id=object_id,
                        object_name=link.target_page_code,
                        object_type="GuidelinePage",
                        evidence_text=link.anchor_text or page.clean_text[:240],
                        evidence_source_ids=[page.page_id],
                        evidence_kind="flowchart",
                        confidence=_score_relation("NEXT_STEP", "flowchart", link.anchor_text or page.clean_text),
                    )
                )
        return triples

    def _from_discussion(self, chunks: Sequence[DiscussionChunk], refs: Sequence[ReferenceEntry]) -> List[CandidateTriple]:
        ref_lookup = {(ref.article_id, ref.ref_number): ref for ref in refs}
        triples: List[CandidateTriple] = []
        for chunk in chunks:
            for sentence in _split_sentences(chunk.clean_text):
                relation = _relation_from_sentence(sentence)
                if not relation:
                    continue
                entities = _extract_entities(sentence, self.ontology)
                if len(entities) < 2:
                    continue
                source_ids = [chunk.chunk_id]
                linked_refs = [ref_lookup.get((chunk.article_id, ref_num)) for ref_num in chunk.reference_ids]
                source_ids.extend(ref.entry_id for ref in linked_refs if ref)
                subject = entities[0]
                for object_entity in entities[1:]:
                    if not self.ontology.allowed(subject[2], relation, object_entity[2]):
                        continue
                    triples.append(
                        CandidateTriple(
                            subject_id=subject[0],
                            subject_name=subject[1],
                            subject_type=subject[2],
                            relation=relation,
                            object_id=object_entity[0],
                            object_name=object_entity[1],
                            object_type=object_entity[2],
                            evidence_text=sentence,
                            evidence_source_ids=[sid for sid in source_ids if sid],
                            evidence_kind="text",
                            confidence=_score_relation(relation, "text", sentence),
                        )
                    )
        return triples

    def _from_page_mentions(self, pages: Sequence[GuidelinePage]) -> List[CandidateTriple]:
        triples: List[CandidateTriple] = []
        for page in pages:
            if page.page_type not in {"clinical_guideline", "discussion_text"}:
                continue
            entities = _extract_entities(page.clean_text, self.ontology)
            if len(entities) < 2:
                continue
            for idx, subject in enumerate(entities[:-1]):
                for object_entity in entities[idx + 1 :]:
                    triples.append(
                        CandidateTriple(
                            subject_id=subject[0],
                            subject_name=subject[1],
                            subject_type=subject[2],
                            relation="MENTIONS",
                            object_id=object_entity[0],
                            object_name=object_entity[1],
                            object_type=object_entity[2],
                            evidence_text=page.clean_text[:1000],
                            evidence_source_ids=[page.page_id],
                            evidence_kind="text",
                            confidence=_score_relation("MENTIONS", "text", page.clean_text),
                        )
                    )
        return triples

    def _from_article_mentions(self, chunks: Sequence[DiscussionChunk]) -> List[CandidateTriple]:
        triples: List[CandidateTriple] = []
        for chunk in chunks:
            entities = _extract_entities(chunk.article_title, self.ontology)
            if not entities:
                continue
            for entity in entities:
                triples.append(
                    CandidateTriple(
                        subject_id=f"article:{chunk.article_id}",
                        subject_name=chunk.article_title,
                        subject_type="Article",
                        relation="MENTIONS",
                        object_id=entity[0],
                        object_name=entity[1],
                        object_type=entity[2],
                        evidence_text=chunk.article_title,
                        evidence_source_ids=[chunk.chunk_id],
                        evidence_kind="text",
                        confidence=_score_relation("MENTIONS", "text", chunk.article_title),
                    )
                )
        return triples


def candidate_triple_id(candidate: CandidateTriple) -> str:
    raw = "|".join(
        [
            candidate.subject_id,
            candidate.relation,
            candidate.object_id,
            "|".join(candidate.evidence_source_ids),
            candidate.evidence_text[:180],
        ]
    )
    return f"triple:{zlib.crc32(raw.encode('utf-8')):08x}"


def save_knowledge_graph_bundle(path: Path, bundle: KnowledgeGraphBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ontology": [
            {
                "concept_type": concept.concept_type,
                "name": concept.name,
                "canonical_id": concept.canonical_id,
                "aliases": list(concept.aliases),
            }
            for concept in bundle.ontology
        ],
        "triples": [triple.to_dict() for triple in bundle.triples],
        "rejected_candidates": [
            {
                "subject_id": candidate.subject_id,
                "subject_name": candidate.subject_name,
                "subject_type": candidate.subject_type,
                "relation": candidate.relation,
                "object_id": candidate.object_id,
                "object_name": candidate.object_name,
                "object_type": candidate.object_type,
                "confidence": candidate.confidence,
                "validation_status": candidate.validation_status,
                "evidence_text": candidate.evidence_text,
                "evidence_source_ids": candidate.evidence_source_ids,
                "evidence_kind": candidate.evidence_kind,
                "llm_score": candidate.llm_score,
                "reviewer": candidate.reviewer,
                "review_status": candidate.review_status,
            }
            for candidate in bundle.rejected_candidates
        ],
        "stats": bundle.stats,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_knowledge_graph_bundle(path: Path) -> KnowledgeGraphBundle:
    data = json.loads(path.read_text(encoding="utf-8"))
    ontology = [
        OntologyConcept(
            concept_type=item["concept_type"],
            name=item["name"],
            canonical_id=item["canonical_id"],
            aliases=tuple(item.get("aliases", [])),
        )
        for item in data.get("ontology", [])
    ]
    triples = [GraphTriple.from_dict(item) for item in data.get("triples", [])]
    rejected = [
        CandidateTriple(
            subject_id=item["subject_id"],
            subject_name=item["subject_name"],
            subject_type=item["subject_type"],
            relation=item["relation"],
            object_id=item["object_id"],
            object_name=item["object_name"],
            object_type=item["object_type"],
            evidence_text=item["evidence_text"],
            evidence_source_ids=list(item.get("evidence_source_ids", [])),
            evidence_kind=item.get("evidence_kind", "text"),
            confidence=float(item.get("confidence", 0.0)),
            llm_score=item.get("llm_score"),
            validation_status=item.get("validation_status", "candidate"),
            reviewer=item.get("reviewer"),
            review_status=item.get("review_status", "pending"),
        )
        for item in data.get("rejected_candidates", [])
    ]
    return KnowledgeGraphBundle(ontology=ontology, triples=triples, rejected_candidates=rejected, stats=dict(data.get("stats", {})))


def load_or_build_knowledge_graph_bundle(kb_path: Path, kg_path: Path) -> KnowledgeGraphBundle:
    if kg_path.exists():
        return load_knowledge_graph_bundle(kg_path)
    from backend.app.services.store import load_knowledge_base

    kb = load_knowledge_base(kb_path)
    bundle = KnowledgeGraphBuilder().build(kb)
    save_knowledge_graph_bundle(kg_path, bundle)
    return bundle


def export_review_queue(path: Path, bundle: KnowledgeGraphBundle, review_threshold: float = 0.9) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    review_items = []
    for triple in bundle.triples:
        if triple.confidence < review_threshold or triple.validation_status != "trusted" or triple.review_status != "auto_trusted":
            review_items.append(
                {
                    "item_type": "triple",
                    "action": "review",
                    "triple_id": triple.triple_id,
                    "subject_id": triple.subject_id,
                    "subject_name": triple.subject_name,
                    "subject_type": triple.subject_type,
                    "relation": triple.relation,
                    "object_id": triple.object_id,
                    "object_name": triple.object_name,
                    "object_type": triple.object_type,
                    "confidence": triple.confidence,
                    "validation_status": triple.validation_status,
                    "review_status": triple.review_status,
                    "evidence_kind": triple.evidence_kind,
                    "evidence_text": triple.evidence_text,
                    "evidence_source_ids": triple.evidence_source_ids,
                    "llm_score": triple.llm_score,
                    "reviewer": triple.reviewer,
                }
            )
    for candidate in bundle.rejected_candidates:
        review_items.append(
            {
                "item_type": "candidate",
                "action": "validate",
                "triple_id": candidate_triple_id(candidate),
                "subject_id": candidate.subject_id,
                "subject_name": candidate.subject_name,
                "subject_type": candidate.subject_type,
                "relation": candidate.relation,
                "object_id": candidate.object_id,
                "object_name": candidate.object_name,
                "object_type": candidate.object_type,
                "confidence": candidate.confidence,
                "validation_status": candidate.validation_status,
                "review_status": candidate.review_status,
                "evidence_kind": candidate.evidence_kind,
                "evidence_text": candidate.evidence_text,
                "evidence_source_ids": candidate.evidence_source_ids,
                "llm_score": candidate.llm_score,
                "reviewer": candidate.reviewer,
            }
        )
    payload = {
        "review_threshold": review_threshold,
        "count": len(review_items),
        "items": review_items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_review_decisions(path: Path) -> Dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "decisions" in data:
        records = data["decisions"]
    elif isinstance(data, list):
        records = data
    else:
        records = data.get("items", []) if isinstance(data, dict) else []
    decisions: Dict[str, dict] = {}
    for item in records:
        triple_id = str(item.get("triple_id", "")).strip()
        if not triple_id:
            continue
        decisions[triple_id] = dict(item)
    return decisions


def apply_review_decisions(bundle: KnowledgeGraphBundle, decisions: Dict[str, dict]) -> KnowledgeGraphBundle:
    reviewed_triples: List[GraphTriple] = []
    rejected_candidates: List[CandidateTriple] = []

    triple_index = {triple.triple_id: triple for triple in bundle.triples}
    for triple in bundle.triples:
        decision = decisions.get(triple.triple_id)
        if not decision:
            reviewed_triples.append(triple)
            continue
        status = str(decision.get("decision", decision.get("validation_status", triple.validation_status))).lower()
        confidence = float(decision.get("confidence", triple.confidence))
        reviewer = decision.get("reviewer", triple.reviewer)
        note = decision.get("note", "")
        if status in {"reject", "rejected", "discard", "false"}:
            continue
        reviewed_triples.append(
            GraphTriple(
                triple_id=triple.triple_id,
                subject_id=triple.subject_id,
                subject_name=triple.subject_name,
                subject_type=triple.subject_type,
                relation=triple.relation,
                object_id=triple.object_id,
                object_name=triple.object_name,
                object_type=triple.object_type,
                confidence=min(1.0, max(triple.confidence, confidence)),
                validation_status="trusted" if confidence >= 0.75 else "needs_review",
                evidence_text=triple.evidence_text if not note else f"{triple.evidence_text}\n[review_note] {note}",
                evidence_source_ids=list(triple.evidence_source_ids),
                evidence_kind=triple.evidence_kind,
                llm_score=triple.llm_score,
                reviewer=reviewer,
                review_status="human_trusted" if status in {"approve", "approved", "accept", "accepted"} else "human_reviewed",
            )
        )

    candidate_index = {candidate_triple_id(candidate): candidate for candidate in bundle.rejected_candidates}
    for candidate in bundle.rejected_candidates:
        decision = decisions.get(candidate_triple_id(candidate))
        if not decision:
            rejected_candidates.append(candidate)
            continue
        status = str(decision.get("decision", decision.get("validation_status", "reject"))).lower()
        confidence = float(decision.get("confidence", candidate.confidence))
        reviewer = decision.get("reviewer", candidate.reviewer)
        note = decision.get("note", "")
        if status in {"reject", "rejected", "discard", "false"}:
            continue
        reviewed_triples.append(
            GraphTriple(
                triple_id=candidate_triple_id(candidate),
                subject_id=candidate.subject_id,
                subject_name=candidate.subject_name,
                subject_type=candidate.subject_type,
                relation=candidate.relation,
                object_id=candidate.object_id,
                object_name=candidate.object_name,
                object_type=candidate.object_type,
                confidence=min(1.0, max(candidate.confidence, confidence)),
                validation_status="trusted" if confidence >= 0.75 else "needs_review",
                evidence_text=candidate.evidence_text if not note else f"{candidate.evidence_text}\n[review_note] {note}",
                evidence_source_ids=list(candidate.evidence_source_ids),
                evidence_kind=candidate.evidence_kind,
                llm_score=candidate.llm_score,
                reviewer=reviewer,
                review_status="human_trusted" if status in {"approve", "approved", "accept", "accepted"} else "human_reviewed",
            )
        )

    return KnowledgeGraphBundle(
        ontology=list(bundle.ontology),
        triples=reviewed_triples,
        rejected_candidates=rejected_candidates,
        stats={**bundle.stats, "reviewed_triples": len(reviewed_triples), "remaining_candidates": len(rejected_candidates)},
    )
