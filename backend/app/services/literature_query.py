"""Q2Q: Chinese clinical question → structured PubMed query (MeSH + tiab)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from backend.app.services.query_normalizer import extract_entities, normalize_query


# Fixed disease vocabulary — do not let the LLM invent MeSH headings.
DISEASE_VOCAB: Dict[str, Dict[str, Any]] = {
    "dlbcl": {
        "mesh": "Lymphoma, Large B-Cell, Diffuse",
        "tiab": ["diffuse large B-cell lymphoma", "DLBCL"],
        "aliases": ["弥漫大B细胞淋巴瘤", "大B细胞淋巴瘤", "DLBCL", "LBCL"],
    },
    "fl": {
        "mesh": "Lymphoma, Follicular",
        "tiab": ["follicular lymphoma", "FL"],
        "aliases": ["滤泡性淋巴瘤", "滤泡淋巴瘤", "FL"],
    },
    "mcl": {
        "mesh": "Lymphoma, Mantle-Cell",
        "tiab": ["mantle cell lymphoma", "MCL"],
        "aliases": ["套细胞淋巴瘤", "MCL"],
    },
    "mzl": {
        "mesh": "Lymphoma, B-Cell, Marginal Zone",
        "tiab": ["marginal zone lymphoma", "MZL"],
        "aliases": ["边缘区淋巴瘤", "MZL"],
    },
    "pmbl": {
        "mesh": "Lymphoma, Large B-Cell, Diffuse",
        "tiab": ["primary mediastinal B-cell lymphoma", "PMBL", "PMBCL"],
        "aliases": ["原发纵隔大B细胞淋巴瘤", "PMBL", "PMBCL"],
    },
    "hgbl": {
        "mesh": "Lymphoma, Large B-Cell, Diffuse",
        "tiab": ["high-grade B-cell lymphoma", "HGBL", "double-hit lymphoma"],
        "aliases": ["高级别B细胞淋巴瘤", "双打击", "HGBL"],
    },
    "lbcl": {
        "mesh": "Lymphoma, Large B-Cell, Diffuse",
        "tiab": ["large B-cell lymphoma", "LBCL", "DLBCL"],
        "aliases": ["大B细胞淋巴瘤", "LBCL"],
    },
}

BIOMARKER_MESH: Dict[str, str] = {
    "TP53": "Tumor Suppressor Protein p53",
    "MYC": "Proto-Oncogene Proteins c-myc",
    "BCL2": "Proto-Oncogene Proteins c-bcl-2",
    "BCL6": "Proto-Oncogene Proteins c-bcl-6",
    "CD19": "Antigens, CD19",
    "CD20": "Antigens, CD20",
}

OUTCOME_HINTS: Dict[str, List[str]] = {
    "prognosis": ["prognosis", "survival", "outcome"],
    "预后": ["prognosis", "survival", "outcome"],
    "生存": ["survival", "overall survival", "progression-free survival"],
    "治疗": ["therapy", "treatment"],
    "疗效": ["efficacy", "response", "remission"],
    "复发": ["relapsed", "relapse"],
    "难治": ["refractory"],
}

CONCEPT_EXTRACT_SYSTEM = """你是生物医学检索助手。从中文临床问题中抽取 PubMed 检索概念，只输出 JSON：
{"disease":["..."],"biomarker":["..."],"intervention":["..."],"outcome":["..."],"population":[],"focus":"prognosis|therapy|diagnosis|other"}
规则：
1. disease/biomarker/intervention/outcome 用英文术语或标准缩写（如 DLBCL、TP53、CAR-T、R-CHOP）。
2. 若问题未涉及某字段，用空数组。
3. 不要编造 MeSH 正式主题词；不要输出检索式本身。
4. 只输出一个 JSON 对象。"""


@dataclass
class LiteratureConcepts:
    disease: List[str] = field(default_factory=list)
    biomarker: List[str] = field(default_factory=list)
    intervention: List[str] = field(default_factory=list)
    outcome: List[str] = field(default_factory=list)
    population: List[str] = field(default_factory=list)
    focus: str = "other"
    disease_keys: List[str] = field(default_factory=list)
    source: str = "rules"  # rules | llm

    def english_tokens(self) -> List[str]:
        tokens: List[str] = []
        for group in (self.disease, self.biomarker, self.intervention, self.outcome, self.population):
            tokens.extend(group)
        return [t for t in tokens if t]


def _or_clause(terms: Sequence[str], field_tag: str) -> str:
    parts = []
    for term in terms:
        term = term.strip()
        if not term:
            continue
        if " " in term or "-" in term:
            parts.append(f'"{term}"[{field_tag}]')
        else:
            parts.append(f"{term}[{field_tag}]")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def _disease_block(concepts: LiteratureConcepts, *, tiab_only: bool = False) -> str:
    mesh_terms: List[str] = []
    tiab_terms: List[str] = []
    keys = concepts.disease_keys or ["dlbcl"]
    for key in keys:
        vocab = DISEASE_VOCAB.get(key)
        if not vocab:
            continue
        mesh_terms.append(vocab["mesh"])
        tiab_terms.extend(vocab["tiab"])
    # Also keep free-text disease labels from concepts
    for label in concepts.disease:
        if label and label not in tiab_terms:
            tiab_terms.append(label)
    if not tiab_terms and not mesh_terms:
        tiab_terms = ["diffuse large B-cell lymphoma", "DLBCL"]
        mesh_terms = ["Lymphoma, Large B-Cell, Diffuse"]
    # dedupe preserving order
    seen = set()
    tiab_u = []
    for t in tiab_terms:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        tiab_u.append(t)
    parts: List[str] = []
    if not tiab_only:
        for mesh in dict.fromkeys(mesh_terms):
            parts.append(f'"{mesh}"[MeSH Terms]')
    parts.append(_or_clause(tiab_u, "tiab"))
    parts = [p for p in parts if p]
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def _biomarker_block(concepts: LiteratureConcepts, *, tiab_only: bool = False) -> str:
    if not concepts.biomarker:
        return ""
    parts: List[str] = []
    for marker in concepts.biomarker:
        m = marker.strip()
        if not m:
            continue
        parts.append(_or_clause([m], "tiab"))
        mesh = BIOMARKER_MESH.get(m.upper())
        if mesh and not tiab_only:
            parts.append(f'"{mesh}"[MeSH Terms]')
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def _simple_block(terms: Sequence[str], *, mesh: Optional[str] = None, tiab_only: bool = False) -> str:
    if not terms:
        return ""
    parts = [_or_clause(list(terms), "tiab")]
    if mesh and not tiab_only:
        parts.insert(0, f'"{mesh}"[MeSH Terms]')
    parts = [p for p in parts if p]
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def detect_disease_keys(question: str) -> List[str]:
    q = question.upper()
    keys: List[str] = []
    for key, vocab in DISEASE_VOCAB.items():
        for alias in vocab["aliases"] + vocab["tiab"]:
            if alias.upper() in q or alias in question:
                if key not in keys:
                    keys.append(key)
                break
    if "双打击" in question or "DOUBLE-HIT" in q or "HGBL" in q:
        if "hgbl" not in keys:
            keys.append("hgbl")
    if not keys:
        # Default to DLBCL for lymphoma assistant scope when unspecified.
        if "淋巴瘤" in question or "LYMPHOMA" in q:
            keys.append("dlbcl")
        else:
            keys.append("dlbcl")
    return keys


_DISEASE_STOPWORDS = {
    "DLBCL",
    "LBCL",
    "FL",
    "MCL",
    "MZL",
    "PMBL",
    "PMBCL",
    "HGBL",
    "NHL",
    "LYMPHOMA",
}


def _extra_named_terms(question: str) -> List[str]:
    """Capture product / assay names not covered by gene entity regex (e.g. LymphoGEN).

    Avoid ASCII ``\\b`` alone: Chinese characters are Unicode word chars, so
    ``分型LymphoGEN`` has no boundary between 型 and L.
    """
    sep = r"(?:^|(?<=[^A-Za-z0-9]))"
    end = r"(?:$|(?=[^A-Za-z0-9]))"
    found: List[str] = []
    found.extend(re.findall(rf"{sep}(Lympho(?:GEN|Plex)){end}", question, flags=re.I))
    found.extend(re.findall(rf"{sep}([A-Z][A-Za-z0-9]*(?:GEN|Plex)){end}", question))
    # CamelCase product names; do NOT use IGNORECASE (would match rrDLBCL).
    found.extend(re.findall(rf"{sep}([A-Z][a-z]+[A-Z][A-Za-z0-9]+){end}", question))
    out = []
    for item in found:
        up = item.upper().replace("-", "")
        if up in _DISEASE_STOPWORDS or up.endswith("DLBCL") or up.endswith("LBCL"):
            continue
        if item.lower() == "lymphogen":
            item = "LymphoGEN"
        elif item.lower() == "lymphoplex":
            item = "LymphPlex"
        if item not in out:
            out.append(item)
    return out


def extract_concepts_rule(question: str) -> LiteratureConcepts:
    """Rule-based fallback when LLM is unavailable."""
    normalized = normalize_query(question)
    entities = extract_entities(question)
    disease_keys = detect_disease_keys(question)

    disease: List[str] = []
    for key in disease_keys:
        disease.extend(DISEASE_VOCAB[key]["tiab"][:2])

    biomarker: List[str] = []
    intervention: List[str] = []
    for ent in entities:
        up = ent.upper().replace(" ", "")
        if up in _DISEASE_STOPWORDS or re.fullmatch(r"(RR)?DLBCL", up):
            continue
        if up in {"R-CHOP", "POLA-R-CHP", "CAR-T", "CART", "GEMOX", "RCHOP"}:
            intervention.append("CAR-T" if up == "CART" else ent.replace("CART", "CAR-T"))
            continue
        if up in BIOMARKER_MESH or up in {"TP53", "MYC", "BCL2", "BCL6", "CD19", "CD20", "EZH2", "MYD88"}:
            biomarker.append(up)
            continue
        if re.search(r"CHOP|CAR|Pola|GEMOX|Rituximab", ent, re.I):
            intervention.append(ent)
            continue
        # Avoid treating disease-ish tokens as biomarkers
        if re.search(r"LYMPHOMA|DLBCL|LBCL", up):
            continue
        if re.match(r"^[A-Z]{2,}[0-9A-Z-]*$", up) and not up.endswith("DLBCL"):
            biomarker.append(ent)
    for term in _extra_named_terms(question):
        up = term.upper().replace("-", "")
        if up in {"CART", "CAR-T", "CARTCELL"}:
            if "CAR-T" not in intervention:
                intervention.append("CAR-T")
            continue
        if term not in biomarker and term not in intervention:
            biomarker.append(term)

    # Explicit intervention phrases
    if re.search(r"CAR[- ]?T|CART", question, re.I):
        if "CAR-T" not in intervention:
            intervention.append("CAR-T")
        # Drop accidental CART biomarker duplicate
        biomarker = [b for b in biomarker if b.upper().replace("-", "") not in {"CART", "CAR-T"}]
    if re.search(r"R[- ]?CHOP", question, re.I):
        if "R-CHOP" not in intervention:
            intervention.append("R-CHOP")
    if "Pola" in question or "pola-r-chp" in question.lower():
        if "Pola-R-CHP" not in intervention:
            intervention.append("Pola-R-CHP")

    outcome: List[str] = []
    focus = "other"
    for zh, en_list in OUTCOME_HINTS.items():
        if zh in question:
            outcome.extend(en_list)
            if zh in {"预后", "prognosis", "生存"}:
                focus = "prognosis"
            elif zh in {"治疗", "疗效"}:
                focus = "therapy"
    # Keep outcome vocabulary tight — do not dump TRANSLATION_HINTS noise (e.g. "significance").
    if "预后" in question and "prognosis" not in outcome:
        outcome.extend(["prognosis", "survival"])
    if "复发" in question and "relapse" not in {o.lower() for o in outcome}:
        outcome.extend(["relapsed", "relapse"])
    if "难治" in question and "refractory" not in {o.lower() for o in outcome}:
        outcome.append("refractory")
    # Drop ultra-generic outcome tokens that dilute PubMed Best Match
    outcome = [o for o in outcome if o.lower() not in {"therapy", "treatment", "disease", "outcome", "regimen"}]

    # Deduplicate
    def _dedupe(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return LiteratureConcepts(
        disease=_dedupe(disease),
        biomarker=_dedupe(biomarker),
        intervention=_dedupe(intervention),
        outcome=_dedupe(outcome),
        population=[],
        focus=focus,
        disease_keys=disease_keys,
        source="rules",
    )


def extract_concepts_llm(question: str, qwen_client: Any) -> Optional[LiteratureConcepts]:
    """Ask Qwen for concept JSON; return None on failure."""
    if qwen_client is None or not getattr(qwen_client, "api_key", None):
        return None
    try:
        text = qwen_client._chat_text(
            [
                {"role": "system", "content": CONCEPT_EXTRACT_SYSTEM},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            timeout=20,
        )
    except Exception:
        return None
    match = re.search(r"\{.*\}", text or "", flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    concepts = LiteratureConcepts(
        disease=[str(x) for x in (data.get("disease") or []) if x],
        biomarker=[str(x) for x in (data.get("biomarker") or []) if x],
        intervention=[str(x) for x in (data.get("intervention") or []) if x],
        outcome=[str(x) for x in (data.get("outcome") or []) if x],
        population=[str(x) for x in (data.get("population") or []) if x],
        focus=str(data.get("focus") or "other"),
        disease_keys=detect_disease_keys(question + " " + " ".join(str(x) for x in (data.get("disease") or []))),
        source="llm",
    )
    # Merge rule entities so gene/regimen tokens are not dropped by a weak LLM parse.
    rules = extract_concepts_rule(question)
    for attr in ("biomarker", "intervention", "outcome"):
        merged = list(getattr(concepts, attr))
        for item in getattr(rules, attr):
            if item not in merged:
                merged.append(item)
        setattr(concepts, attr, merged)
    if not concepts.disease:
        concepts.disease = rules.disease
    if not concepts.disease_keys:
        concepts.disease_keys = rules.disease_keys
    return concepts


def extract_concepts(question: str, qwen_client: Any = None) -> LiteratureConcepts:
    llm = extract_concepts_llm(question, qwen_client)
    if llm is not None:
        return llm
    return extract_concepts_rule(question)


def build_pubmed_query(
    concepts: LiteratureConcepts,
    *,
    level: int = 1,
    recent_years: int = 5,
    tighten: bool = False,
) -> str:
    """Build an explicit MeSH/tiab PubMed query for a ladder level (1–3)."""
    year_now = datetime.utcnow().year
    tiab_only = level >= 3

    disease = _disease_block(concepts, tiab_only=tiab_only)
    biomarker = _biomarker_block(concepts, tiab_only=tiab_only)
    intervention = _simple_block(concepts.intervention, tiab_only=tiab_only)
    outcome_mesh = "Prognosis" if concepts.focus == "prognosis" else None
    outcome = _simple_block(concepts.outcome, mesh=outcome_mesh, tiab_only=tiab_only)

    and_parts: List[str] = [disease]

    # Prefer AND between distinct concept blocks; OR only within a block.
    # If both biomarker and intervention exist, keep both with AND (more precise).
    def _append_mid(parts: List[str]) -> None:
        if biomarker and intervention:
            parts.append(biomarker)
            parts.append(intervention)
        elif biomarker:
            parts.append(biomarker)
        elif intervention:
            parts.append(intervention)

    if level == 1:
        _append_mid(and_parts)
        if outcome:
            and_parts.append(outcome)
        years = recent_years
    elif level == 2:
        _append_mid(and_parts)
        # drop outcome; widen years
        years = max(recent_years * 2, 10)
    else:
        # L3: disease AND (biomarker/intervention), tiab only, no year filter
        _append_mid(and_parts)
        years = 0

    filters = ["hasabstract", "English[lang]"]
    if years > 0:
        start = year_now - years
        filters.append(f'("{start}"[dp] : "3000"[dp])')
    if tighten:
        filters.append(
            "(Meta-Analysis[pt] OR Randomized Controlled Trial[pt] OR systematic[sb] OR Guideline[pt])"
        )

    return " AND ".join(and_parts + filters)
