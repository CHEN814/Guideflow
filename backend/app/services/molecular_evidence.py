from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional, Protocol

import httpx


MappingStatus = Literal["unique", "protein_level_only", "ambiguous", "insufficient", "conflicting"]
EvidenceDecision = Literal["allow", "downgrade", "ask_for_confirmation", "refuse"]
ProviderMode = Literal["mock", "live", "hybrid"]

GENE_ALIASES = {
    "P53": "TP53",
    "C-MYC": "MYC",
    "CMYC": "MYC",
    "BCL-2": "BCL2",
    "BCL-6": "BCL6",
}

DLBCL_DIRECT_TERMS = {
    "dlbcl",
    "diffuse large b-cell lymphoma",
    "diffuse large b cell lymphoma",
    "弥漫大b细胞淋巴瘤",
}

LBCL_NEAR_TERMS = {
    "lbcl",
    "large b-cell lymphoma",
    "large b cell lymphoma",
    "大b细胞淋巴瘤",
}

LYMPHOMA_TERMS = {
    "lymphoma",
    "non-hodgkin lymphoma",
    "b-cell lymphoma",
    "b cell lymphoma",
    "淋巴瘤",
    "非霍奇金淋巴瘤",
}

AMINO_ACID_3_TO_1 = {
    "Ala": "A",
    "Arg": "R",
    "Asn": "N",
    "Asp": "D",
    "Cys": "C",
    "Gln": "Q",
    "Glu": "E",
    "Gly": "G",
    "His": "H",
    "Ile": "I",
    "Leu": "L",
    "Lys": "K",
    "Met": "M",
    "Phe": "F",
    "Pro": "P",
    "Ser": "S",
    "Thr": "T",
    "Trp": "W",
    "Tyr": "Y",
    "Val": "V",
    "Ter": "*",
}

MOCK_KNOWLEDGE: dict[str, list[dict[str, Any]]] = {
    "MYD88|P.L265P": [
        {
            "provider": "CIViC",
            "provider_record_id": "MOCK-CIVIC-MYD88-L265P-001",
            "source_title": "CIViC mock evidence: MYD88 L265P in DLBCL",
            "source_url": "https://civicdb.org/",
            "source_version": "mock-mvp",
            "publication_or_release_date": "2026-08-12",
            "access_status": "metadata_only",
            "evidence_type": "predictive / biological",
            "evidence_level": "L3",
            "disease": "Diffuse Large B-Cell Lymphoma",
            "drug": "BTK inhibitor research context",
            "direction": "supports",
            "record_status": "mock_accepted",
            "claim": "MYD88 p.L265P 在 DLBCL 语境下可支持 BCR/TLR/NF-κB 通路异常和分子分型相关解释，但不能单独决定诊断或治疗。",
            "population": "DLBCL 或 LBCL 相关研究人群；MVP mock 数据未核验完整入组条件。",
            "intervention_and_outcome": "涉及 BTK 抑制剂研究背景时需核验治疗线次、联合用药和结局指标。",
            "applicability": "适用于 DLBCL 分子证据解释，不构成患者级用药建议。",
            "limitations": "当前为 MVP mock 证据，需后续接入 CIViC 实时记录和原文核验。",
        },
        {
            "provider": "ClinVar",
            "provider_record_id": "MOCK-CLINVAR-MYD88-L265P-001",
            "source_title": "ClinVar mock variation: MYD88 L265P",
            "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/",
            "source_version": "mock-mvp",
            "publication_or_release_date": "2026-08-12",
            "access_status": "metadata_only",
            "evidence_type": "somatic oncogenicity",
            "evidence_level": "database_curated",
            "disease": "Neoplasm / lymphoma context",
            "direction": "supports",
            "record_status": "mock",
            "review_status": "mock review status",
            "star_rating": "mock",
            "submission_conflict": False,
            "last_evaluated": "2026-08-12",
            "claim": "ClinVar 层面可作为体细胞致癌性或变异解释线索，但不能自动等同于 DLBCL 中存在可靶向治疗证据。",
            "population": "数据库记录未提供完整患者级上下文。",
            "intervention_and_outcome": "不适用；ClinVar 记录本身不是治疗试验。",
            "applicability": "用于数据库层面的变异解释，需要结合 DLBCL 直接证据。",
            "limitations": "不能把 ClinVar 致癌性分类直接转化为治疗推荐。",
        },
    ],
    "CD79B|P.Y196H": [
        {
            "provider": "CIViC",
            "provider_record_id": "MOCK-CIVIC-CD79B-Y196H-001",
            "source_title": "CIViC mock evidence: CD79B Y196H in DLBCL",
            "source_url": "https://civicdb.org/",
            "source_version": "mock-mvp",
            "publication_or_release_date": "2026-08-12",
            "access_status": "metadata_only",
            "evidence_type": "predictive / biological",
            "evidence_level": "L3",
            "disease": "Diffuse Large B-Cell Lymphoma",
            "drug": "BTK inhibitor research context",
            "direction": "supports",
            "record_status": "mock_accepted",
            "claim": "CD79B p.Y196H 可作为 BCR 信号通路异常相关证据，和 MYD88 共突变时具有分子分型和治疗研究背景意义。",
            "population": "DLBCL 或 LBCL 相关研究人群；MVP mock 数据未核验完整入组条件。",
            "intervention_and_outcome": "涉及 BTK 抑制剂研究时需核验治疗线次、联合用药和疗效终点。",
            "applicability": "适用于 DLBCL 分子证据解释，不构成患者级用药建议。",
            "limitations": "当前为 MVP mock 证据，需后续接入 CIViC 实时记录和原文核验。",
        }
    ],
    "TP53|P.R248Q": [
        {
            "provider": "ClinVar",
            "provider_record_id": "MOCK-CLINVAR-TP53-R248Q-001",
            "source_title": "ClinVar mock variation: TP53 R248Q",
            "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/",
            "source_version": "mock-mvp",
            "publication_or_release_date": "2026-08-12",
            "access_status": "metadata_only",
            "evidence_type": "germline pathogenicity / somatic oncogenicity",
            "evidence_level": "database_curated",
            "disease": "Multiple neoplasms; not DLBCL-specific in this mock record",
            "direction": "supports",
            "record_status": "mock",
            "review_status": "mock review status",
            "star_rating": "mock",
            "submission_conflict": False,
            "last_evaluated": "2026-08-12",
            "claim": "TP53 p.R248Q 可作为致病性或致癌性数据库线索，但不能仅凭该突变预测 DLBCL 患者个体预后。",
            "population": "数据库记录未限定为 DLBCL 直接人群。",
            "intervention_and_outcome": "不适用；该记录不是 DLBCL 治疗试验。",
            "applicability": "仅可作为变异解释线索；若用于 DLBCL 预后判断需查找 DLBCL 直接群体研究。",
            "limitations": "不能把跨肿瘤数据库记录直接外推为 DLBCL 患者级预后结论。",
        }
    ],
}


@dataclass
class NormalizedVariant:
    variant_id: str
    raw_input: str
    gene: str
    protein_hgvs: Optional[str] = None
    cdna_hgvs: Optional[str] = None
    genomic_hgvs: Optional[str] = None
    genome_build: Optional[str] = None
    transcript: Optional[str] = None
    variant_type: Optional[str] = None
    disease: str = "DLBCL"
    sample_type: Optional[str] = None
    mapping_status: MappingStatus = "insufficient"
    requires_confirmation: bool = False
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    unresolved_position: Optional[str] = None
    molecular_annotation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawEvidenceRecord:
    provider: str
    provider_record_id: str
    raw_response: dict[str, Any]
    retrieved_at: str
    provider_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceConflict:
    has_conflict: bool = False
    conflict_type: Optional[str] = None
    description: Optional[str] = None
    resolution: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceCard:
    evidence_id: str
    claim: str
    source_type: str
    source_title: str
    source_id: str
    source_url: str
    publication_or_release_date: Optional[str]
    source_version: Optional[str]
    access_status: str
    evidence_level: str
    disease_match: str
    population: str
    intervention_and_outcome: str
    applicability: str
    limitations: str
    conflict: EvidenceConflict
    retrieved_at: str
    provider: str
    variant_id: str
    evidence_type: Optional[str] = None
    direction: Optional[str] = None
    disease: Optional[str] = None
    drug: Optional[str] = None
    record_status: Optional[str] = None
    review_status: Optional[str] = None
    star_rating: Optional[str] = None
    matched_variant: Optional[str] = None
    original_claim: Optional[str] = None
    safety_flags: list[str] = field(default_factory=list)
    # Framework-aligned labels (orthogonal to internal L1–L5).
    # AMP/ASCO/CAP 2017 Tier I–IV: somatic clinical significance.
    amp_tier: Optional[str] = None
    # ESMO ESCAT I–V: actionability scale for precision oncology.
    escat_level: Optional[str] = None
    # ACMG/AMP 2015: germline pathogenicity only (P/LP/VUS/LB/B).
    acmg_class: Optional[str] = None
    framework_note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["conflict"] = self.conflict.to_dict()
        return data


@dataclass
class SafetyGateResult:
    evidence_id: Optional[str]
    decision: EvidenceDecision
    allowed_claim_strength: str
    required_warnings: list[str] = field(default_factory=list)
    blocked_outputs: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MolecularEvidenceResult:
    variants: list[NormalizedVariant]
    raw_records: list[RawEvidenceRecord]
    evidence_cards: list[EvidenceCard]
    safety_gate_results: list[SafetyGateResult]
    answer_markdown: str
    doctor_summary: dict[str, Any]
    missing_information: list[str]
    global_warnings: list[str]
    retrieved_at: str
    provider_mode: str = "mock"
    cache_hit: bool = False
    cache_key: Optional[str] = None
    cache_entry_id: Optional[str] = None
    query_log_id: Optional[str] = None
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    provider_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    required_providers: list[str] = field(default_factory=lambda: ["ClinVar", "CIViC"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "variants": [item.to_dict() for item in self.variants],
            "raw_records": [item.to_dict() for item in self.raw_records],
            "evidence_cards": [item.to_dict() for item in self.evidence_cards],
            "safety_gate_results": [item.to_dict() for item in self.safety_gate_results],
            "answer_markdown": self.answer_markdown,
            "doctor_summary": self.doctor_summary,
            "missing_information": self.missing_information,
            "global_warnings": self.global_warnings,
            "retrieved_at": self.retrieved_at,
            "provider_mode": self.provider_mode,
            "cache_hit": self.cache_hit,
            "cache_key": self.cache_key,
            "cache_entry_id": self.cache_entry_id,
            "query_log_id": self.query_log_id,
            "agent_trace": self.agent_trace,
            "provider_status": self.provider_status,
            "required_providers": self.required_providers,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_gene(raw_gene: str) -> str:
    gene = re.sub(r"[^A-Za-z0-9-]", "", raw_gene or "").upper()
    return GENE_ALIASES.get(gene, gene)


def normalize_protein_hgvs(raw: str) -> Optional[str]:
    if not raw:
        return None
    token = raw.strip().replace(" ", "")
    token = re.sub(r"^p\.", "", token, flags=re.IGNORECASE)
    three_letter = re.match(r"^([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2}|Ter)$", token)
    if three_letter:
        ref, pos, alt = three_letter.groups()
        ref_one = AMINO_ACID_3_TO_1.get(ref)
        alt_one = AMINO_ACID_3_TO_1.get(alt)
        if ref_one and alt_one:
            return f"p.{ref_one}{pos}{alt_one}"
    short = re.match(r"^([A-Z*])(\d+)([A-Z*])$", token, flags=re.IGNORECASE)
    if short:
        ref, pos, alt = short.groups()
        return f"p.{ref.upper()}{pos}{alt.upper()}"
    return None


def guess_variant_type(protein_hgvs: Optional[str], cdna_hgvs: Optional[str], raw: str) -> Optional[str]:
    text = " ".join([protein_hgvs or "", cdna_hgvs or "", raw or ""]).lower()
    if any(term in text for term in ["fusion", "融合"]):
        return "fusion"
    if any(term in text for term in ["rearrangement", "重排"]):
        return "rearrangement"
    if any(term in text for term in ["amplification", "amp", "扩增"]):
        return "amplification"
    if any(term in text for term in ["gain", "copy number gain", "cnv gain"]):
        return "copy_number_gain"
    if any(term in text for term in ["loss", "deletion", "del", "缺失"]):
        return "deletion"
    if any(term in text for term in ["splice", "剪接"]):
        return "splice_site"
    if any(term in text for term in ["stopgain", "nonsense", "无义", "ter", "*"]):
        return "nonsense"
    if protein_hgvs or (cdna_hgvs and ">" in cdna_hgvs):
        return "SNV"
    return None


def normalize_disease(raw_disease: str) -> str:
    text = (raw_disease or "DLBCL").strip()
    lowered = text.lower()
    if lowered in DLBCL_DIRECT_TERMS:
        return "DLBCL"
    if lowered in LBCL_NEAR_TERMS:
        return "LBCL"
    return text


class MolecularInputParser:
    protein_pattern = re.compile(
        r"(?P<gene>[A-Za-z0-9-]+)\s*(?P<protein>(?:p\.)?(?:[A-Z][a-z]{2}|[A-Z*])\d+(?:[A-Z][a-z]{2}|[A-Z*]|Ter))",
        re.IGNORECASE,
    )
    cdna_pattern = re.compile(r"(?P<gene>[A-Za-z0-9-]+)?\s*(?P<cdna>c\.\d+[A-Za-z]*[>_delinsdupA-Za-z0-9]*)", re.IGNORECASE)
    protein_only_hint_pattern = re.compile(r"(?P<gene>[A-Za-z0-9-]+)\s+(?P<pos>[A-Za-z*]{1,3}\d+[A-Za-z*]{1,3}|\d+[A-Za-z*]{1,3})", re.IGNORECASE)

    def parse(
        self,
        text: str,
        *,
        disease: str = "DLBCL",
        sample_type: Optional[str] = None,
        genome_build: Optional[str] = None,
        transcript: Optional[str] = None,
        variant_type: Optional[str] = None,
    ) -> list[NormalizedVariant]:
        variants: list[NormalizedVariant] = []
        seen: set[tuple[str, Optional[str], Optional[str]]] = set()
        chunks = self._variant_chunks(text)
        for chunk in chunks:
            parsed = self._parse_chunk(
                chunk,
                disease=disease,
                sample_type=sample_type,
                genome_build=genome_build,
                transcript=transcript,
                variant_type=variant_type,
            )
            if parsed is None:
                if re.match(r"^[A-Za-z][A-Za-z0-9-]{1,14}\b", chunk) and not re.search(r"VAF|深度|depth|问题|是否|请|患者|诊断", chunk, re.IGNORECASE):
                    parsed = self._insufficient_variant(chunk, disease=disease, sample_type=sample_type)
                else:
                    continue
            key = (parsed.gene, parsed.protein_hgvs, parsed.cdna_hgvs)
            if key not in seen:
                seen.add(key)
                variants.append(parsed)
        return variants

    def _variant_chunks(self, text: str) -> list[str]:
        normalized = (text or "").replace("\r", "\n")
        starts = list(re.finditer(r"(?<![A-Za-z0-9_-])(?P<gene>[A-Z][A-Z0-9-]{1,14})\s+(?=(?:NM_|ENST|c\.|p\.|[A-Z*]\d+|fusion|融合|扩增|缺失|重排))", normalized, flags=re.IGNORECASE))
        chunks: list[str] = []
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(normalized)
            chunk = normalized[match.start():end].strip(" \n\t,，;；。")
            question_at = re.search(r"(?:问题|请问|是否|能否|如何|有什么临床意义)[：:]?", chunk)
            if question_at and question_at.start() > 0:
                chunk = chunk[:question_at.start()].strip(" \n\t,，;；。")
            if chunk and (self.protein_pattern.search(chunk) or self.cdna_pattern.search(chunk) or re.search(r"融合|fusion|扩增|amplification|缺失|deletion|重排|rearrangement", chunk, re.IGNORECASE)):
                chunks.append(chunk)
        standalone_lines = [
            chunk.strip()
            for chunk in re.split(r"[\n]+", normalized)
            if chunk.strip()
            and re.match(r"^[A-Za-z][A-Za-z0-9-]{1,14}\b", chunk.strip())
            and not re.search(r"VAF|深度|depth|问题|是否|请|患者|诊断", chunk, re.IGNORECASE)
        ]
        if len(standalone_lines) > len(chunks):
            chunks = standalone_lines
        elif not chunks:
            chunks = [chunk.strip() for chunk in re.split(r"[\n,，;；]+", normalized) if chunk.strip() and not re.search(r"VAF|深度|depth|问题|是否|请|患者|诊断", chunk, re.IGNORECASE)]
        return chunks

    def _parse_chunk(
        self,
        chunk: str,
        *,
        disease: str,
        sample_type: Optional[str],
        genome_build: Optional[str],
        transcript: Optional[str],
        variant_type: Optional[str],
    ) -> Optional[NormalizedVariant]:
        leading_gene = re.match(r"^(?P<gene>[A-Za-z][A-Za-z0-9-]{1,14})\b", chunk)
        cdna_match = self.cdna_pattern.search(chunk)
        protein_token_match = re.search(r"\bp\.(?P<protein>(?:[A-Z][a-z]{2}|[A-Z*])\d+(?:[A-Z][a-z]{2}|[A-Z*]|Ter))\b", chunk, flags=re.IGNORECASE)
        gene = normalize_gene(leading_gene.group("gene")) if leading_gene else ""
        protein_token = protein_token_match.group("protein") if protein_token_match else None
        protein_hgvs = normalize_protein_hgvs(protein_token) if protein_token else None
        cdna_hgvs = cdna_match.group("cdna") if cdna_match else None
        transcript_match = re.search(r"\b(NM_\d+(?:\.\d+)?)\b", chunk, flags=re.IGNORECASE)
        chunk_transcript = transcript_match.group(1).upper() if transcript_match else transcript
        unresolved_position: Optional[str] = None
        if not gene and cdna_match and cdna_match.group("gene"):
            gene = normalize_gene(cdna_match.group("gene") or "")
        if not gene:
            bare_gene = re.match(r"^([A-Za-z0-9-]+)\b", chunk)
            gene = normalize_gene(bare_gene.group(1)) if bare_gene else ""
        if not gene:
            return None
        if not protein_hgvs:
            protein_only_hint = self.protein_only_hint_pattern.search(chunk)
            if protein_only_hint:
                unresolved_position = protein_only_hint.group("pos")
                hinted = normalize_protein_hgvs(protein_only_hint.group("pos"))
                if hinted:
                    protein_hgvs = hinted
        normalized = NormalizedVariant(
            variant_id=f"var_{uuid.uuid4().hex[:12]}",
            raw_input=chunk,
            gene=gene,
            protein_hgvs=protein_hgvs,
            cdna_hgvs=cdna_hgvs,
            genome_build=genome_build,
            transcript=chunk_transcript,
            variant_type=variant_type or guess_variant_type(protein_hgvs, cdna_hgvs, chunk),
            disease=normalize_disease(disease),
            sample_type=sample_type,
            unresolved_position=unresolved_position,
        )
        return MappingValidator().validate(normalized)

    def _insufficient_variant(self, chunk: str, *, disease: str, sample_type: Optional[str]) -> NormalizedVariant:
        gene_match = re.match(r"^([A-Za-z0-9-]+)\b", chunk)
        gene = normalize_gene(gene_match.group(1)) if gene_match else ""
        return NormalizedVariant(
            variant_id=f"var_{uuid.uuid4().hex[:12]}",
            raw_input=chunk,
            gene=gene,
            disease=normalize_disease(disease),
            sample_type=sample_type,
            mapping_status="insufficient",
            requires_confirmation=True,
            warnings=["无法从输入中识别明确蛋白或核酸 HGVS。"],
            missing_fields=["protein_hgvs 或 cdna_hgvs"],
        )


class MappingValidator:
    def validate(self, variant: NormalizedVariant) -> NormalizedVariant:
        missing: list[str] = []
        warnings: list[str] = []
        annotation = self._annotate_variant(variant)
        variant.molecular_annotation = annotation
        if not variant.gene:
            missing.append("gene")
        if not variant.protein_hgvs and not variant.cdna_hgvs and not variant.genomic_hgvs:
            missing.append("protein_hgvs 或 cdna_hgvs")
        if not variant.disease:
            missing.append("disease")
        if not variant.sample_type:
            missing.append("sample_type")
        if missing:
            variant.mapping_status = "insufficient"
            variant.requires_confirmation = True
            variant.missing_fields = missing
            variant.warnings = [f"缺少关键字段：{', '.join(missing)}。"]
            return variant
        if variant.unresolved_position and not variant.protein_hgvs:
            warnings.append("输入仅包含蛋白位点线索，但缺少完整蛋白 HGVS；不能给出位点级确定性结论。")
            variant.mapping_status = "ambiguous"
            variant.requires_confirmation = True
        elif variant.cdna_hgvs and not variant.transcript:
            warnings.append("存在核酸 HGVS，但缺少转录本，不能唯一解释核酸位点。")
            variant.mapping_status = "ambiguous"
            variant.requires_confirmation = True
        elif variant.genomic_hgvs and not variant.genome_build:
            warnings.append("存在基因组坐标，但缺少 GRCh37/GRCh38，不能唯一映射。")
            variant.mapping_status = "ambiguous"
            variant.requires_confirmation = True
        elif variant.protein_hgvs and not variant.cdna_hgvs:
            warnings.append("当前仅完成蛋白层面识别，系统不会猜测转录本、核酸 HGVS 或基因组坐标。")
            variant.mapping_status = "protein_level_only"
            variant.requires_confirmation = False
        else:
            variant.mapping_status = "unique"
            variant.requires_confirmation = False
        if not variant.genome_build:
            warnings.append("缺少 GRCh37/GRCh38；涉及基因组坐标或精确位点解释时需补充。")
        if not variant.transcript:
            warnings.append("缺少转录本；系统不会自动猜测转录本。")
        if annotation.get("protein_effect") == "loss_of_function":
            warnings.append("该变异可能导致蛋白功能丢失（LOF）。")
        if annotation.get("protein_effect") == "gain_of_function":
            warnings.append("该变异可能导致蛋白功能获得（GOF）。")
        variant.missing_fields = missing
        variant.warnings = warnings
        return variant

    def _annotate_variant(self, variant: NormalizedVariant) -> dict[str, Any]:
        gene = (variant.gene or "").upper()
        variant_type = (variant.variant_type or guess_variant_type(variant.protein_hgvs, variant.cdna_hgvs, variant.raw_input) or "unknown").lower()
        protein_effect = "unknown"
        if variant_type in {"nonsense", "frameshift", "splice_site", "deletion"}:
            protein_effect = "loss_of_function"
        elif variant_type in {"amplification", "copy_number_gain", "fusion", "rearrangement"}:
            protein_effect = "gain_of_function"
        elif variant_type == "snv" and variant.protein_hgvs:
            protein_effect = "possible_missense_effect"
        gene_role_map = {
            "TP53": "抑癌基因",
            "MYD88": "先天免疫信号通路适配蛋白",
            "CD79B": "BCR 复合体关键组分",
            "BCL2": "抗凋亡调控基因",
            "BCL6": "生发中心程序转录调控因子",
            "EZH2": "表观遗传调控因子（组蛋白甲基转移酶）",
            "CREBBP": "表观遗传调控因子（组蛋白乙酰转移酶）",
            "KMT2D": "表观遗传调控因子（组蛋白甲基转移酶）",
            "MYC": "转录调控与增殖驱动基因",
            "BRAF": "丝/苏氨酸激酶（MAPK 通路）",
            "EGFR": "受体酪氨酸激酶（ERBB 家族）",
            "ALK": "受体酪氨酸激酶（ALK 家族）",
            "FLT3": "受体酪氨酸激酶（FLT3 通路）",
            "BRCA1": "抑癌基因（同源重组修复）",
            "BRCA2": "抑癌基因（同源重组修复）",
            "ATM": "抑癌基因（DNA 损伤检查点激酶）",
            "PTEN": "抑癌基因（PI3K-AKT 负调控）",
            "RB1": "抑癌基因（细胞周期检查点）",
            "IDH1": "代谢酶基因（异柠檬酸脱氢酶）",
            "IDH2": "代谢酶基因（异柠檬酸脱氢酶）",
        }
        upstream_pathway_map = {
            "MYD88": ["TLR 受体信号", "IL-1R 受体信号"],
            "CD79B": ["BCR 受体复合体信号", "抗原刺激输入"],
            "TP53": ["DNA 损伤感应", "基因组应激信号"],
            "BCL2": ["线粒体凋亡信号", "内在凋亡通路"],
            "BCL6": ["生发中心程序信号", "B 细胞分化信号"],
            "EZH2": ["染色质重塑复合体信号", "PRC2 复合体"],
            "CREBBP": ["染色质重塑复合体信号", "转录共激活因子"],
            "KMT2D": ["染色质重塑复合体信号", "组蛋白甲基化信号"],
            "MYC": ["生长因子信号", "WNT 信号"],
            "BRAF": ["RAS 信号", "受体酪氨酸激酶上游信号"],
            "EGFR": ["配体结合受体激活", "ERBB 家族信号"],
            "ALK": ["配体结合受体激活", "ALK 家族信号"],
            "FLT3": ["FLT3 配体受体激活", "造血生长因子信号"],
            "BRCA1": ["DNA 双链断裂损伤", "同源重组修复信号"],
            "BRCA2": ["DNA 双链断裂损伤", "同源重组修复信号"],
            "ATM": ["DNA 双链断裂损伤", "检查点激活信号"],
            "PTEN": ["PI3K 信号", "生长因子受体信号"],
            "RB1": ["CDK4/6 信号", "细胞周期进展信号"],
            "IDH1": ["三羧酸循环代谢信号", "α-酮戊二酸代谢"],
            "IDH2": ["三羧酸循环代谢信号", "α-酮戊二酸代谢"],
        }
        downstream_pathway_map = {
            "MYD88": ["IRAK4 / IRAK1", "TRAF6", "NF-κB", "JAK-STAT"],
            "CD79B": ["SYK", "BTK", "NF-κB", "PI3K-AKT"],
            "TP53": ["细胞周期 arrest", "凋亡", "DNA 修复"],
            "BCL2": ["线粒体凋亡抑制", "CASPASE 级联抑制"],
            "BCL6": ["转录抑制", "生发中心维持"],
            "EZH2": ["H3K27me3 沉默", "转录抑制"],
            "CREBBP": ["组蛋白乙酰化", "转录激活调控"],
            "KMT2D": ["H3K4 甲基化", "转录激活调控"],
            "MYC": ["细胞增殖", "核糖体生物合成", "代谢重编程"],
            "BRAF": ["MEK / ERK", "细胞增殖", "存活信号"],
            "EGFR": ["RAS-RAF-MEK-ERK", "PI3K-AKT", "JAK-STAT"],
            "ALK": ["RAS-RAF-MEK-ERK", "PI3K-AKT", "JAK-STAT"],
            "FLT3": ["RAS-RAF-MEK-ERK", "PI3K-AKT", "STAT5"],
            "BRCA1": ["同源重组修复", "基因组稳定性维持"],
            "BRCA2": ["同源重组修复", "RAD51 招募"],
            "ATM": ["CHK2", "p53 稳定", "细胞周期检查点"],
            "PTEN": ["PI3K-AKT 信号负调控", "凋亡信号"],
            "RB1": ["E2F 转录因子", "G1/S 检查点"],
            "IDH1": ["2-羟基戊二酸累积", "表观遗传重编程"],
            "IDH2": ["2-羟基戊二酸累积", "表观遗传重编程"],
        }
        go_terms_map = {
            "MYD88": ["先天免疫信号转导", "受体介导 NF-κB 激活"],
            "CD79B": ["B 细胞受体信号转导", "适应性免疫应答"],
            "TP53": ["DNA 损伤修复", "凋亡调控", "细胞周期检查点"],
            "BCL2": ["凋亡负调控", "线粒体凋亡通路"],
            "BCL6": ["转录调控", "生发中心 B 细胞分化"],
            "EZH2": ["组蛋白甲基转移酶活性", "染色质修饰"],
            "CREBBP": ["转录共激活因子活性", "组蛋白乙酰转移酶活性"],
            "KMT2D": ["组蛋白甲基转移酶活性", "染色质组装"],
            "MYC": ["转录调控", "细胞增殖"],
            "BRAF": ["丝/苏氨酸激酶活性", "MAPK 级联"],
            "EGFR": ["受体酪氨酸激酶活性", "细胞增殖"],
            "ALK": ["受体酪氨酸激酶活性", "信号转导"],
            "FLT3": ["受体酪氨酸激酶活性", "信号转导"],
            "BRCA1": ["DNA 修复", "双链断裂修复"],
            "BRCA2": ["DNA 修复", "同源重组"],
            "ATM": ["DNA 损伤应答", "蛋白激酶活性"],
            "PTEN": ["脂质磷酸酶活性", "PI3K 信号负调控"],
            "RB1": ["细胞周期检查点", "细胞周期负调控"],
            "IDH1": ["异柠檬酸脱氢酶活性", "代谢过程"],
            "IDH2": ["异柠檬酸脱氢酶活性", "代谢过程"],
        }
        targetability_map = {
            "MYD88": ["BTK 通路抑制剂（研究线索）", "IRAK4 抑制剂（研究线索）"],
            "CD79B": ["BTK 通路抑制剂（研究线索）", "SYK 抑制剂（研究线索）"],
            "EZH2": ["EZH2 抑制剂（研究线索）"],
            "BRAF": ["BRAF 抑制剂", "MEK 抑制剂"],
            "EGFR": ["EGFR 酪氨酸激酶抑制剂"],
            "ALK": ["ALK 酪氨酸激酶抑制剂"],
            "FLT3": ["FLT3 抑制剂"],
            "BRCA1": ["PARP 抑制剂（治疗线索）"],
            "BRCA2": ["PARP 抑制剂（治疗线索）"],
            "IDH1": ["IDH1 抑制剂"],
            "IDH2": ["IDH2 抑制剂"],
            "PTEN": ["PI3K 通路抑制剂（研究线索）"],
        }
        return {
            "variant_type": variant_type,
            "protein_effect": protein_effect,
            "gene_role": gene_role_map.get(gene, "其他/需结合背景判断"),
            "upstream_pathways": upstream_pathway_map.get(gene, []),
            "downstream_pathways": downstream_pathway_map.get(gene, []),
            "go_terms": go_terms_map.get(gene, []),
            "oncology_effect": self._oncology_effect_for_gene(gene),
            "targetability": targetability_map.get(gene, []),
            "exon_relevance": self._infer_exon_relevance(variant),
            "protein_impact_note": self._protein_impact_note(variant, protein_effect),
            "database_class_hint": self._database_class_hint(gene, variant_type),
        }

    def _oncology_effect_for_gene(self, gene: str) -> str:
        return {
            "MYD88": "促进生存与 NF-κB 激活",
            "CD79B": "增强 BCR 下游信号",
            "TP53": "基因组稳定性受损",
            "BCL2": "抑制凋亡",
            "BCL6": "生发中心程序重编程",
            "EZH2": "表观遗传状态改变",
            "CREBBP": "转录与表观遗传失调",
            "KMT2D": "表观遗传失调",
            "MYC": "增殖与代谢重编程",
            "BRAF": "增殖信号激活",
            "EGFR": "生长信号激活",
            "ALK": "生长信号激活",
            "FLT3": "生长信号激活",
            "BRCA1": "DNA 修复缺陷",
            "BRCA2": "DNA 修复缺陷",
            "ATM": "DNA 损伤检查点缺陷",
            "PTEN": "生存信号增强",
            "RB1": "细胞周期检查点失活",
            "IDH1": "代谢与表观遗传重编程",
            "IDH2": "代谢与表观遗传重编程",
        }.get(gene, "背景依赖")

    def _infer_exon_relevance(self, variant: NormalizedVariant) -> str:
        raw = " ".join([variant.raw_input or "", variant.protein_hgvs or "", variant.cdna_hgvs or ""]).lower()
        if any(term in raw for term in ["splice", "剪接"]):
            return "剪接相关位点"
        if any(term in raw for term in ["exon", "外显子"]):
            return "明确外显子相关"
        if variant.cdna_hgvs and re.search(r"c\.\d+", variant.cdna_hgvs):
            return "编码区变异，可能位于外显子"
        if variant.variant_type in {"fusion", "rearrangement", "amplification", "copy_number_gain", "deletion"}:
            return "结构变异或拷贝数事件"
        return "仅有蛋白层信息，外显子需结合转录本确认"

    def _protein_impact_note(self, variant: NormalizedVariant, protein_effect: str) -> str:
        if protein_effect == "loss_of_function":
            return "提示可能导致蛋白功能缺失、截短或表达下降。"
        if protein_effect == "gain_of_function":
            return "提示可能导致蛋白功能增强、异常激活或通路重连。"
        if protein_effect == "possible_missense_effect":
            return "该错义改变可能影响蛋白活性、稳定性或分子相互作用，需结合结构域、保守性和文献进一步判断。"
        return "当前证据不足以对蛋白层功能影响作出定性结论。"

    def _database_class_hint(self, gene: str, variant_type: str) -> str:
        if gene in {"BRCA1", "BRCA2", "ATM", "PTEN", "RB1"} and variant_type in {"nonsense", "frameshift", "splice_site", "deletion"}:
            return "可能致病（功能缺失型）"
        if gene in {"MYD88", "CD79B", "BRAF", "EGFR", "ALK", "FLT3", "IDH1", "IDH2"}:
            return "可能致癌或可操作"
        return "背景依赖"


class EvidenceProvider(Protocol):
    provider_name: str

    def search(self, variant: NormalizedVariant) -> list[RawEvidenceRecord]:
        ...


class MockEvidenceProvider:
    provider_name = "mock"

    def search(self, variant: NormalizedVariant) -> list[RawEvidenceRecord]:
        if variant.mapping_status in {"ambiguous", "insufficient", "conflicting"}:
            return []
        keys = self._candidate_keys(variant)
        retrieved_at = utc_now_iso()
        records: list[RawEvidenceRecord] = []
        seen_ids: set[str] = set()
        for key in keys:
            for record in MOCK_KNOWLEDGE.get(key, []):
                provider_record_id = str(record.get("provider_record_id") or f"MOCK-{uuid.uuid4().hex[:8]}")
                if provider_record_id in seen_ids:
                    continue
                seen_ids.add(provider_record_id)
                records.append(
                    RawEvidenceRecord(
                        provider=str(record.get("provider") or self.provider_name),
                        provider_record_id=provider_record_id,
                        provider_version=str(record.get("source_version") or "mock-mvp"),
                        raw_response=record,
                        retrieved_at=retrieved_at,
                    )
                )
        return records

    def _candidate_keys(self, variant: NormalizedVariant) -> list[str]:
        candidates = [f"{variant.gene}|{(variant.protein_hgvs or '').upper()}"]
        if variant.unresolved_position:
            normalized_pos = variant.unresolved_position.upper()
            if normalized_pos and variant.gene == "TP53" and normalized_pos.startswith("R248"):
                candidates.append("TP53|P.R248Q")
        if variant.protein_hgvs is None and variant.gene in {"TP53", "MYD88", "CD79B"}:
            candidates.extend([f"{variant.gene}|P.{hint}" for hint in ["R248Q", "L265P", "Y196H"] if hint])
        return list(dict.fromkeys(candidates))


class ClinVarProvider:
    provider_name = "ClinVar"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, variant: NormalizedVariant) -> list[RawEvidenceRecord]:
        if variant.mapping_status in {"ambiguous", "insufficient", "conflicting"}:
            return []
        candidates = self._candidate_terms(variant)
        if not candidates:
            return []
        retrieved_at = utc_now_iso()
        records: list[RawEvidenceRecord] = []
        seen_ids: set[str] = set()
        for term in candidates:
            try:
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                    search_resp = client.get(
                        f"{self.base_url}/esearch.fcgi",
                        params={"db": "clinvar", "term": term, "retmode": "json", "retmax": 5},
                    )
                    search_resp.raise_for_status()
                    ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
                    if not ids:
                        continue
                    summary_resp = client.get(
                        f"{self.base_url}/esummary.fcgi",
                        params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
                    )
                    summary_resp.raise_for_status()
                    result = summary_resp.json().get("result", {})
            except Exception as exc:
                return [self._error_record(str(exc), retrieved_at)]
            for uid in result.get("uids", []):
                if uid in seen_ids:
                    continue
                item = result.get(uid, {})
                if not self._passes_variant_gate(item, variant):
                    continue
                seen_ids.add(uid)
                records.append(
                    RawEvidenceRecord(
                        provider=self.provider_name,
                        provider_record_id=str(item.get("accession") or f"VCV{int(uid):09d}"),
                        provider_version="ClinVar E-utilities live",
                        raw_response=self._normalize_summary(uid, item, variant),
                        retrieved_at=retrieved_at,
                    )
                )
        return records

    def _candidate_terms(self, variant: NormalizedVariant) -> list[str]:
        variant_tokens = [variant.protein_hgvs, variant.cdna_hgvs, variant.unresolved_position]
        terms = [f'{variant.gene}[gene] AND "{token}"' for token in variant_tokens if token]
        if variant.gene and not terms:
            terms.append(f"{variant.gene}[gene]")
        return list(dict.fromkeys(terms))

    def _passes_variant_gate(self, item: dict[str, Any], variant: NormalizedVariant) -> bool:
        if not item:
            return False
        haystack = json.dumps(item, ensure_ascii=False, default=str)
        if variant.gene and variant.gene.lower() not in haystack.lower():
            return False
        tokens = [variant.protein_hgvs, variant.cdna_hgvs, variant.unresolved_position]
        return not any(tokens) or any(self._variant_token_matches(token or "", haystack) for token in tokens if token)

    def _variant_token_matches(self, token: str, haystack: str) -> bool:
        compact_haystack = re.sub(r"[^A-Za-z0-9*]", "", haystack).upper()
        compact_token = re.sub(r"^p\.", "", token, flags=re.IGNORECASE)
        compact_token = re.sub(r"[^A-Za-z0-9*]", "", compact_token).upper()
        if compact_token and compact_token in compact_haystack:
            return True
        protein = re.fullmatch(r"([A-Z*])(\d+)([A-Z*])", compact_token)
        if not protein:
            return False
        one_to_three = {value.upper(): key.upper() for key, value in AMINO_ACID_3_TO_1.items()}
        ref, pos, alt = protein.groups()
        three_letter = f"{one_to_three.get(ref, ref)}{pos}{one_to_three.get(alt, alt)}"
        return three_letter in compact_haystack

    def _classification(self, item: dict[str, Any], key: str) -> dict[str, Any]:
        value = item.get(key)
        return value if isinstance(value, dict) else {}

    def _trait_names(self, *classifications: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for classification in classifications:
            for trait in classification.get("trait_set") or []:
                if isinstance(trait, dict) and trait.get("trait_name"):
                    names.append(str(trait["trait_name"]))
        return list(dict.fromkeys(names))

    def _normalize_summary(self, uid: str, item: dict[str, Any], variant: NormalizedVariant) -> dict[str, Any]:
        title = str(item.get("title") or item.get("variation_name") or f"ClinVar Variation {uid}")
        germline = self._classification(item, "germline_classification")
        clinical_impact = self._classification(item, "clinical_impact_classification")
        oncogenicity = self._classification(item, "oncogenicity_classification")
        classifications = [
            ("germline", germline.get("description")),
            ("clinical impact", clinical_impact.get("description")),
            ("oncogenicity", oncogenicity.get("description")),
        ]
        classification_text = "；".join(f"{localize_term(name)}：{localize_term(value)}" for name, value in classifications if value) or "未知"
        review_statuses = [str(value.get("review_status")) for value in [germline, clinical_impact, oncogenicity] if value.get("review_status")]
        review_status = "; ".join(dict.fromkeys(review_statuses)) or "unknown"
        disease = "; ".join(self._trait_names(germline, clinical_impact, oncogenicity)) or "unknown"
        evidence_type = "somatic oncogenicity / somatic clinical impact" if oncogenicity or clinical_impact else "germline pathogenicity"
        accession = str(item.get("accession") or f"VCV{int(uid):09d}")
        return {
            "provider": self.provider_name,
            "provider_record_id": accession,
            "source_title": title,
            "source_title_zh": f"ClinVar变异记录：{variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or ''}",
            "source_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{accession}/",
            "source_version": "ClinVar E-utilities live",
            "publication_or_release_date": item.get("last_update") or oncogenicity.get("last_evaluated") or clinical_impact.get("last_evaluated") or germline.get("last_evaluated"),
            "access_status": "metadata_only",
            "evidence_type": evidence_type,
            "evidence_level": self._clinvar_to_internal_level(item),
            "germline_classification": germline.get("description"),
            "oncogenicity_classification": oncogenicity.get("description"),
            "clinical_impact_classification": clinical_impact.get("description"),
            "disease": disease,
            "direction": "database_record",
            "record_status": "live_metadata",
            "review_status": review_status,
            "star_rating": item.get("star_rating"),
            "matched_variant": f"{variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or variant.unresolved_position or ''}".strip(),
            "submission_conflict": "conflict" in str(review_status).lower(),
            "last_evaluated": oncogenicity.get("last_evaluated") or clinical_impact.get("last_evaluated") or germline.get("last_evaluated"),
            "claim": f"ClinVar 记录提供 {variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or ''} 的分类信息：{classification_text}；需区分胚系致病性、体细胞致癌性和体细胞临床影响，不能自动等同于 DLBCL 可靶向治疗证据。",
            "population": "ClinVar 元数据通常不提供完整 DLBCL 患者级入组人群。",
            "intervention_and_outcome": "不适用；ClinVar 记录本身不是治疗试验。",
            "applicability": "可作为变异数据库解释线索；若要形成 DLBCL 结论，需结合 DLBCL 直接证据和原始来源核验。",
            "limitations": "MVP 阶段仅解析 ClinVar ESummary 元数据，尚未核验完整 VCV/RCV/SCV 细节。",
        }

    def _clinvar_to_internal_level(self, item: dict[str, Any]) -> str:
        descriptions = [
            self._classification(item, key).get("description")
            for key in ["germline_classification", "clinical_impact_classification", "oncogenicity_classification"]
        ]
        classification = " ".join(str(value) for value in descriptions if value).lower()
        reviews = [
            self._classification(item, key).get("review_status")
            for key in ["germline_classification", "clinical_impact_classification", "oncogenicity_classification"]
        ]
        stars = " ".join(str(value) for value in reviews if value)
        if any(term in classification for term in ["pathogenic", "likely pathogenic"]):
            return "L4" if "somatic" in classification or "oncogenic" in classification else "L5"
        if any(term in classification for term in ["oncogenic", "likely oncogenic"]):
            return "L4"
        if any(term in classification for term in ["conflicting", "vus", "uncertain"]):
            return "L5"
        if "3" in stars or "4" in stars:
            return "L4"
        return "L5"

    def _error_record(self, error: str, retrieved_at: str) -> RawEvidenceRecord:
        return RawEvidenceRecord(
            provider=self.provider_name,
            provider_record_id="CLINVAR_QUERY_ERROR",
            provider_version="ClinVar E-utilities live",
            raw_response={
                "provider": self.provider_name,
                "provider_record_id": "CLINVAR_QUERY_ERROR",
                "source_title": "ClinVar query error",
                "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/",
                "source_version": "ClinVar E-utilities live",
                "access_status": "not_accessible",
                "evidence_level": "L5",
                "evidence_type": "query_error",
                "disease": "unknown",
                "record_status": "error",
                "claim": "ClinVar 查询失败，不能据此形成确定性分子证据结论。",
                "population": "无法获取。",
                "intervention_and_outcome": "无法获取。",
                "applicability": "不能作为证据使用。",
                "limitations": error,
                "submission_conflict": False,
            },
            retrieved_at=retrieved_at,
        )


class CivicProvider:
    provider_name = "CIViC"
    graphql_url = "https://civicdb.org/api/graphql"
    variant_query = """
        query FindVariant($gene: String!, $variant: String!) {
          browseVariants(featureName: $gene, variantName: $variant, first: 10) {
            nodes { id name featureName }
          }
        }
    """
    evidence_query = """
        query VariantEvidence($variantId: Int!) {
          evidenceItems(variantId: $variantId, first: 50) {
            nodes {
              id name description status evidenceLevel evidenceType
              evidenceDirection significance variantOrigin
              disease { name displayName }
              therapies { id name }
              source { title citation publicationDate publicationYear sourceUrl }
            }
          }
        }
    """

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, variant: NormalizedVariant) -> list[RawEvidenceRecord]:
        if variant.mapping_status in {"ambiguous", "insufficient", "conflicting"}:
            return []
        variant_name = (variant.protein_hgvs or variant.cdna_hgvs or variant.unresolved_position or "").replace("p.", "")
        if not variant.gene or not variant_name:
            return []
        retrieved_at = utc_now_iso()
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                variant_data = self._graphql(
                    client,
                    self.variant_query,
                    {"gene": variant.gene, "variant": variant_name},
                )
                candidates = variant_data.get("browseVariants", {}).get("nodes", [])
                variant_ids = [
                    int(item["id"])
                    for item in candidates
                    if isinstance(item, dict)
                    and str(item.get("featureName") or "").upper() == variant.gene.upper()
                    and self._same_variant_name(str(item.get("name") or ""), variant_name)
                ]
                items: list[dict[str, Any]] = []
                for variant_id in variant_ids:
                    evidence_data = self._graphql(client, self.evidence_query, {"variantId": variant_id})
                    nodes = evidence_data.get("evidenceItems", {}).get("nodes", [])
                    items.extend(item for item in nodes if isinstance(item, dict))
        except Exception as exc:
            return [self._error_record(str(exc), retrieved_at)]

        records: list[RawEvidenceRecord] = []
        seen_ids: set[str] = set()
        for item in items:
            evidence_id = str(item.get("id") or "")
            if not evidence_id or evidence_id in seen_ids or not self._passes_record_gate(item, variant):
                continue
            seen_ids.add(evidence_id)
            records.append(
                RawEvidenceRecord(
                    provider=self.provider_name,
                    provider_record_id=f"EID{evidence_id}",
                    provider_version="CIViC GraphQL API live",
                    raw_response=self._normalize_item(evidence_id, item, variant),
                    retrieved_at=retrieved_at,
                )
            )
        return records

    def _graphql(self, client: httpx.Client, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = client.post(self.graphql_url, json={"query": query, "variables": variables})
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors") or []
        if errors:
            message = "; ".join(str(item.get("message") or item) for item in errors)
            raise RuntimeError(f"CIViC GraphQL error: {message}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("CIViC GraphQL response did not contain data")
        return data

    def _same_variant_name(self, civic_name: str, requested_name: str) -> bool:
        normalize = lambda value: re.sub(r"[^A-Za-z0-9*]", "", value or "").upper()
        return normalize(civic_name) == normalize(requested_name)

    def _passes_record_gate(self, item: dict[str, Any], variant: NormalizedVariant) -> bool:
        record_status = str(item.get("status") or item.get("record_status") or "").lower()
        if record_status not in {"accepted", "submitted", "supported", "verified", "curated", "mock_accepted"}:
            return False
        if not item.get("disease"):
            return False
        disease = item.get("disease")
        disease_name = (disease.get("displayName") or disease.get("name")) if isinstance(disease, dict) else disease
        disease_text = str(disease_name or "")
        if variant.disease == "DLBCL" and disease_text:
            lowered = disease_text.lower()
            if "diffuse large b-cell" not in lowered and "dlbcl" not in lowered and "large b-cell" not in lowered and "b-cell lymphoma" not in lowered:
                return False
        return True

    def _normalize_item(self, evidence_id: str, item: dict[str, Any], variant: NormalizedVariant) -> dict[str, Any]:
        disease_raw = item.get("disease")
        disease = (disease_raw.get("displayName") or disease_raw.get("name")) if isinstance(disease_raw, dict) else disease_raw
        therapies = item.get("therapies") or item.get("drugs") or []
        drug = self._therapy_names(therapies)
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        evidence_level = self._civic_to_internal_level(item)
        record_status = str(item.get("status") or item.get("record_status") or "unknown")
        original_claim = str(item.get("description") or item.get("evidence_statement") or "").strip()
        claim_zh = self._compose_chinese_claim(
            variant=variant,
            disease=str(disease or "unknown"),
            evidence_type=str(item.get("evidenceType") or item.get("evidence_type") or item.get("type") or "unknown"),
            direction=str(item.get("evidenceDirection") or item.get("evidence_direction") or item.get("direction") or "unknown"),
            level=str(item.get("evidenceLevel") or item.get("evidence_level") or item.get("level") or "unknown"),
            drug=drug,
        )
        return {
            "provider": self.provider_name,
            "provider_record_id": f"EID{evidence_id}",
            "source_title": source.get("title") or f"CIViC证据记录 {evidence_id}",
            "source_title_zh": f"CIViC证据：{variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or ''}（{localize_disease(disease or '疾病未知')}）",
            "source_url": f"https://civicdb.org/evidence/{evidence_id}",
            "source_version": "CIViC GraphQL API live",
            "publication_or_release_date": source.get("publicationDate") or source.get("publicationYear") or source.get("publication_date") or source.get("publication_year"),
            "access_status": "metadata_only",
            "evidence_type": item.get("evidenceType") or item.get("evidence_type") or item.get("type") or "unknown",
            "evidence_level": evidence_level,
            "disease": disease or "unknown",
            "drug": drug,
            "direction": item.get("evidenceDirection") or item.get("evidence_direction") or item.get("direction"),
            "record_status": record_status,
            "review_status": "已由 CIViC 编辑审核接受" if record_status.lower() == "accepted" else "已提交 CIViC，尚待编辑审核",
            "matched_variant": f"{variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or variant.unresolved_position or ''}".strip(),
            "claim": claim_zh if record_status.lower() == "accepted" else claim_zh.replace("CIViC 已审核记录", "CIViC 待审核记录（仅作线索）", 1),
            "original_claim": original_claim or None,
            "population": "需核验 CIViC 来源文献中的具体入组人群。",
            "intervention_and_outcome": "需核验原始文献中的干预、比较和结局。",
            "applicability": "只有疾病匹配 DLBCL/LBCL 且证据状态可靠时，才可作为 DLBCL 证据依据。",
            "limitations": "CIViC 元数据不能替代原文全文核验，非 DLBCL 证据不得直接外推。",
            "submission_conflict": False,
        }

    def _compose_chinese_claim(
        self,
        *,
        variant: NormalizedVariant,
        disease: str,
        evidence_type: str,
        direction: str,
        level: str,
        drug: Optional[str],
    ) -> str:
        variant_label = f"{variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or variant.unresolved_position or ''}".strip()
        type_zh = localize_term(evidence_type)
        direction_zh = localize_term(direction)
        disease_zh = localize_disease(disease)
        parts = [
            f"CIViC 已审核记录收录了 {variant_label} 在{disease_zh}中的{type_zh}证据",
            f"证据方向为{direction_zh}",
            f"CIViC 原始证据级别为 {level}",
        ]
        if drug:
            parts.append(f"相关治疗为 {drug}")
        return "；".join(parts) + "。该记录仅用于分子证据解释，仍需结合原始文献和患者临床背景。"

    def _civic_to_internal_level(self, item: dict[str, Any]) -> str:
        level = str(item.get("evidenceLevel") or item.get("evidence_level") or item.get("level") or "").upper()
        evidence_type = str(item.get("evidenceType") or item.get("evidence_type") or item.get("type") or "").lower()
        direction = str(item.get("evidenceDirection") or item.get("evidence_direction") or item.get("direction") or "").lower()
        if level in {"A", "B"} and direction in {"supports", "relevant", "druggable"}:
            return "L2"
        if level in {"C", "D"}:
            return "L3"
        if any(term in evidence_type for term in ["predictive", "diagnostic", "prognostic", "oncogenic"]):
            return "L3" if level not in {"A", "B"} else "L2"
        return "L4"

    def _therapy_names(self, therapies: Any) -> Optional[str]:
        if not therapies:
            return None
        if isinstance(therapies, str):
            return therapies
        if isinstance(therapies, list):
            names = []
            for therapy in therapies:
                if isinstance(therapy, dict):
                    name = therapy.get("name") or therapy.get("display_name")
                    if name:
                        names.append(str(name))
                elif therapy:
                    names.append(str(therapy))
            return ", ".join(names) if names else None
        return str(therapies)

    def _error_record(self, error: str, retrieved_at: str) -> RawEvidenceRecord:
        return RawEvidenceRecord(
            provider=self.provider_name,
            provider_record_id="CIVIC_QUERY_ERROR",
            provider_version="CIViC GraphQL API live",
            raw_response={
                "provider": self.provider_name,
                "provider_record_id": "CIVIC_QUERY_ERROR",
                "source_title": "CIViC query error",
                "source_url": "https://civicdb.org/",
                "source_version": "CIViC API live",
                "access_status": "not_accessible",
                "evidence_level": "L5",
                "evidence_type": "query_error",
                "disease": "unknown",
                "record_status": "error",
                "claim": "CIViC 查询失败，不能据此形成确定性分子证据结论。",
                "population": "无法获取。",
                "intervention_and_outcome": "无法获取。",
                "applicability": "不能作为证据使用。",
                "limitations": error,
                "submission_conflict": False,
            },
            retrieved_at=retrieved_at,
        )


class CompositeEvidenceProvider:
    provider_name = "composite"

    def __init__(self, providers: list[EvidenceProvider]) -> None:
        self.providers = providers

    def search(self, variant: NormalizedVariant) -> list[RawEvidenceRecord]:
        records: list[RawEvidenceRecord] = []
        for provider in self.providers:
            records.extend(provider.search(variant))
        return records


class _ProviderView:
    def __init__(self, provider: EvidenceProvider, provider_name: str) -> None:
        self.provider = provider
        self.provider_name = provider_name

    def search(self, variant: NormalizedVariant) -> list[RawEvidenceRecord]:
        return [record for record in self.provider.search(variant) if record.provider == self.provider_name]


class MolecularEvidenceAgent:
    """Deterministic agent that executes every required molecular database tool."""

    REQUIRED_PROVIDERS = ("ClinVar", "CIViC")

    def __init__(self, *, provider_mode: str = "live", providers: Optional[list[EvidenceProvider]] = None) -> None:
        self.provider_mode = provider_mode
        self.providers = providers or [ClinVarProvider(), CivicProvider()]
        self.required_providers = self.REQUIRED_PROVIDERS

    def run(
        self, variants: list[NormalizedVariant]
    ) -> tuple[list[RawEvidenceRecord], list[dict[str, Any]], dict[str, dict[str, Any]]]:
        trace: list[dict[str, Any]] = [{
            "step": "plan",
            "required_providers": list(self.required_providers),
            "variant_count": len(variants),
            "policy": "all_required_providers_must_be_queried",
            "execution": "parallel",
        }]
        status = {
            name: {
                "required": True,
                "queried": False,
                "query_count": 0,
                "record_count": 0,
                "error_count": 0,
                "state": "pending",
            }
            for name in self.required_providers
        }
        provider_names = {provider.provider_name for provider in self.providers}
        missing_tools = [name for name in self.required_providers if name not in provider_names]
        if missing_tools:
            raise RuntimeError(f"required molecular provider tools are not configured: {', '.join(missing_tools)}")

        tasks = [(variant, provider) for variant in variants for provider in self.providers]
        outcomes: list[tuple[NormalizedVariant, EvidenceProvider, list[RawEvidenceRecord], Optional[str]]] = []
        if tasks:
            with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
                futures = {
                    executor.submit(provider.search, variant): (variant, provider)
                    for variant, provider in tasks
                }
                for future in as_completed(futures):
                    variant, provider = futures[future]
                    try:
                        provider_records = future.result()
                        outcomes.append((variant, provider, provider_records, None))
                    except Exception as exc:
                        outcomes.append((variant, provider, [], f"{type(exc).__name__}: {exc}"))

        records: list[RawEvidenceRecord] = []
        seen_records: set[tuple[str, str, str]] = set()
        outcomes.sort(key=lambda item: (item[0].variant_id, item[1].provider_name))
        for variant, provider, provider_records, exception_text in outcomes:
            provider_name = provider.provider_name
            provider_status = status.setdefault(provider_name, {
                "required": provider_name in self.required_providers,
                "queried": False,
                "query_count": 0,
                "record_count": 0,
                "error_count": 0,
                "state": "pending",
            })
            provider_status["queried"] = True
            provider_status["query_count"] += 1
            error_count = 1 if exception_text else 0
            usable_count = 0
            duplicate_count = 0
            for record in provider_records:
                record.raw_response.setdefault("variant_id", variant.variant_id)
                is_error = self._is_error_record(record)
                error_count += int(is_error)
                if is_error:
                    records.append(record)
                    continue
                record_key = (record.provider, record.provider_record_id, variant.variant_id)
                if record_key in seen_records:
                    duplicate_count += 1
                    continue
                seen_records.add(record_key)
                records.append(record)
                usable_count += 1
            provider_status["record_count"] += usable_count
            provider_status["error_count"] += error_count
            trace.append({
                "step": "query_provider",
                "provider": provider_name,
                "variant_id": variant.variant_id,
                "variant": self._variant_label(variant),
                "queried": True,
                "record_count": usable_count,
                "duplicate_count": duplicate_count,
                "error_count": error_count,
                "error": exception_text,
            })

        for provider_name, provider_status in status.items():
            expected_queries = len(variants) if provider_status["required"] else 0
            if provider_status["query_count"] < expected_queries:
                provider_status["state"] = "incomplete"
            elif provider_status["error_count"]:
                provider_status["state"] = "degraded"
            elif provider_status["record_count"] == 0:
                provider_status["state"] = "no_evidence"
            else:
                provider_status["state"] = "success"

        incomplete = [name for name in self.required_providers if status[name]["state"] == "incomplete"]
        if incomplete:
            raise RuntimeError(f"required molecular providers were not fully queried: {', '.join(incomplete)}")
        degraded = any(status[name]["state"] == "degraded" for name in self.required_providers)
        trace.append({
            "step": "complete",
            "required_providers_queried": True,
            "completion_state": "degraded" if degraded else "complete",
            "providers": status,
        })
        return records, trace, status

    def _is_error_record(self, record: RawEvidenceRecord) -> bool:
        return (
            record.provider_record_id.endswith("_QUERY_ERROR")
            or str(record.raw_response.get("record_status") or "").lower() == "error"
            or str(record.raw_response.get("evidence_type") or "").lower() == "query_error"
        )

    def _variant_label(self, variant: NormalizedVariant) -> str:
        return " ".join(item for item in [
            variant.gene,
            variant.protein_hgvs or variant.cdna_hgvs or variant.genomic_hgvs or variant.unresolved_position,
        ] if item)


class DiseaseMatcher:
    def match(self, evidence_disease: Optional[str], current_disease: str) -> str:
        evidence = self._normalize_text(evidence_disease)
        current = self._normalize_text(current_disease)
        if current in DLBCL_DIRECT_TERMS or current == "dlbcl":
            if self._is_dlbcl(evidence):
                return "DLBCL直接证据"
            if self._is_lbcl(evidence):
                return "LBCL近似证据"
            if self._is_lymphoma(evidence):
                return "其他淋巴瘤外推"
            if evidence and evidence != "unknown":
                return "其他肿瘤外推"
            return "未知"
        if current in LBCL_NEAR_TERMS or current == "lbcl":
            if self._is_dlbcl(evidence) or self._is_lbcl(evidence):
                return "LBCL近似证据"
            if self._is_lymphoma(evidence):
                return "其他淋巴瘤外推"
            return "其他肿瘤外推" if evidence else "未知"
        return "未知"

    def _normalize_text(self, value: Optional[str]) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    def _is_dlbcl(self, evidence: str) -> bool:
        return evidence in DLBCL_DIRECT_TERMS or "diffuse large b" in evidence or "dlbcl" in evidence

    def _is_lbcl(self, evidence: str) -> bool:
        return evidence in LBCL_NEAR_TERMS or "large b-cell" in evidence or "large b cell" in evidence

    def _is_lymphoma(self, evidence: str) -> bool:
        return any(term in evidence for term in LYMPHOMA_TERMS)


LOCALIZED_TERMS = {
    "accepted": "已接受",
    "submitted": "已提交，尚待审核",
    "supported": "有证据支持",
    "verified": "已核验",
    "curated": "已人工整理",
    "mock_accepted": "本地示例",
    "live_metadata": "在线元数据",
    "metadata_only": "仅元数据",
    "abstract_only": "仅摘要",
    "not_accessible": "无法访问",
    "unknown": "未知",
    "supports": "支持",
    "does_not_support": "不支持",
    "database_record": "数据库记录",
    "predictive": "预测性",
    "diagnostic": "诊断性",
    "prognostic": "预后性",
    "oncogenic": "致癌性",
    "functional": "功能性",
    "biological": "生物学",
    "germline pathogenicity": "胚系致病性",
    "somatic oncogenicity": "体细胞致癌性",
    "somatic clinical impact": "体细胞临床影响",
    "pathogenic": "致病",
    "likely pathogenic": "可能致病",
    "oncogenicity": "致癌性",
    "clinical impact": "临床影响",
    "germline": "胚系",
}

DISEASE_TRANSLATIONS = {
    "Diffuse Large B-cell Lymphoma": "弥漫性大B细胞淋巴瘤",
    "Lymphoplasmacytic Lymphoma": "淋巴浆细胞淋巴瘤",
    "Chronic Lymphocytic Leukemia": "慢性淋巴细胞白血病",
    "Li-Fraumeni syndrome": "李-佛美尼综合征",
    "Neoplasm": "肿瘤",
    "Adenocarcinoma of the large intestine": "大肠腺癌",
    "Nasopharyngeal carcinoma": "鼻咽癌",
    "Embryonal rhabdomyosarcoma": "胚胎性横纹肌肉瘤",
    "Diffuse midline glioma, H3 K27M-mutant": "弥漫性中线胶质瘤，H3 K27M突变型",
    "Medulloblastoma WNT activated": "WNT激活型髓母细胞瘤",
    "Embryonal tumor with multilayered rosettes": "多层菊形团胚胎性肿瘤",
}


def localize_term(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    lowered = text.lower()
    if lowered in LOCALIZED_TERMS:
        return LOCALIZED_TERMS[lowered]
    parts = re.split(r"(\s*/\s*|\s*;\s*)", text)
    translated = [LOCALIZED_TERMS.get(part.strip().lower(), DISEASE_TRANSLATIONS.get(part.strip(), part)) if not re.fullmatch(r"\s*/\s*|\s*;\s*", part) else part for part in parts]
    return "".join(translated)


def localize_disease(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    for english, chinese in DISEASE_TRANSLATIONS.items():
        text = text.replace(english, chinese)
    return text


class EvidenceCardBuilder:
    def __init__(self) -> None:
        self.disease_matcher = DiseaseMatcher()

    def build(self, record: RawEvidenceRecord, variant: NormalizedVariant) -> EvidenceCard:
        raw = record.raw_response
        conflict = EvidenceConflict(
            has_conflict=bool(raw.get("submission_conflict", False)),
            conflict_type="database_submission_conflict" if raw.get("submission_conflict") else None,
            description="数据库提交方存在冲突。" if raw.get("submission_conflict") else None,
            resolution="未解决，降低结论强度。" if raw.get("submission_conflict") else None,
        )
        source_id_prefix = "ClinVar" if record.provider.lower() == "clinvar" else record.provider
        disease_match = self.disease_matcher.match(raw.get("disease"), variant.disease)
        evidence_level = str(raw.get("evidence_level") or "L5")
        evidence_level = self._normalize_internal_level(evidence_level, disease_match, str(raw.get("record_status") or ""))
        safety_flags = self._initial_safety_flags(raw, disease_match, evidence_level)
        frameworks = self._map_framework_labels(
            provider=record.provider,
            evidence_level=evidence_level,
            evidence_type=str(raw.get("evidence_type") or ""),
            disease_match=disease_match,
            raw=raw,
        )
        return EvidenceCard(
            evidence_id=f"ev_{uuid.uuid4().hex[:12]}",
            claim=str(raw.get("claim") or "该数据库记录提供变异解释线索，但需要结合疾病匹配和证据等级判断。"),
            source_type="database",
            source_title=str(raw.get("source_title_zh") or raw.get("source_title") or f"{record.provider} 记录 {record.provider_record_id}"),
            source_id=f"{source_id_prefix}:{record.provider_record_id}",
            source_url=str(raw.get("source_url") or ""),
            publication_or_release_date=raw.get("publication_or_release_date"),
            source_version=raw.get("source_version") or record.provider_version,
            access_status=str(raw.get("access_status") or "metadata_only"),
            evidence_level=evidence_level,
            disease_match=disease_match,
            population=str(raw.get("population") or "数据库记录未提供完整入组人群。"),
            intervention_and_outcome=str(raw.get("intervention_and_outcome") or "未提供干预、比较和结局详情。"),
            applicability=str(raw.get("applicability") or "需结合当前问题、肿瘤类型和临床上下文判断。"),
            limitations=str(raw.get("limitations") or "数据库记录不能替代全文核验和医生判断。"),
            conflict=conflict,
            retrieved_at=record.retrieved_at,
            provider=record.provider,
            variant_id=variant.variant_id,
            evidence_type=raw.get("evidence_type"),
            direction=raw.get("direction"),
            disease=localize_disease(raw.get("disease")),
            drug=raw.get("drug"),
            record_status=raw.get("record_status"),
            review_status=raw.get("review_status"),
            star_rating=str(raw.get("star_rating")) if raw.get("star_rating") is not None else None,
            matched_variant=raw.get("matched_variant") or f"{variant.gene} {variant.protein_hgvs or variant.cdna_hgvs or variant.unresolved_position or ''}".strip(),
            original_claim=raw.get("original_claim"),
            safety_flags=safety_flags,
            amp_tier=frameworks.get("amp_tier"),
            escat_level=frameworks.get("escat_level"),
            acmg_class=frameworks.get("acmg_class"),
            framework_note=frameworks.get("framework_note"),
        )

    def _map_framework_labels(
        self,
        *,
        provider: str,
        evidence_level: str,
        evidence_type: str,
        disease_match: str,
        raw: dict[str, Any],
    ) -> dict[str, Optional[str]]:
        """Map internal L1–L5 onto AMP/ASCO/CAP, ESCAT, and ACMG where applicable.

        ACMG/AMP 2015 applies to *germline pathogenicity*, not therapy papers.
        Somatic clinical significance uses AMP/ASCO/CAP Tier I–IV and ESMO ESCAT.
        """
        level = (evidence_level or "L5").upper()
        etype = (evidence_type or "").lower()
        provider_l = (provider or "").lower()

        # Internal L → AMP Tier (somatic clinical significance)
        amp_map = {"L1": "I", "L2": "I/II", "L3": "II", "L4": "III", "L5": "IV"}
        amp_tier = amp_map.get(level, "IV")

        # ESCAT actionability (therapy-oriented); prognostic/diagnostic stay descriptive.
        if any(k in etype for k in ("predictive", "therapeutic", "therapy")):
            escat_map = {"L1": "I-A", "L2": "I-B", "L3": "II-B", "L4": "III-A", "L5": "V"}
            escat_level = escat_map.get(level, "V")
        elif "prognostic" in etype:
            escat_level = "IV" if level in {"L1", "L2", "L3"} else "V"
        else:
            escat_level = None

        acmg_class = None
        note_parts = [
            "内部等级 L1–L5 为产品统一尺度",
            "体细胞临床意义对齐 AMP/ASCO/CAP 2017 Tier",
        ]
        if escat_level:
            note_parts.append("可靶向/预测性证据同时标注 ESMO ESCAT")

        # ClinVar germline pathogenicity → ACMG class labels
        if provider_l == "clinvar" and "germline" in etype:
            text = " ".join(
                str(v)
                for v in [
                    raw.get("germline_classification"),
                    raw.get("classification"),
                    raw.get("claim"),
                ]
                if v
            ).lower()
            if "likely pathogenic" in text:
                acmg_class = "LP"
            elif re.search(r"(?<!likely )\bpathogenic\b", text):
                acmg_class = "P"
            elif "likely benign" in text:
                acmg_class = "LB"
            elif re.search(r"(?<!likely )\bbenign\b", text):
                acmg_class = "B"
            elif "uncertain" in text or "vus" in text or "conflicting" in text:
                acmg_class = "VUS"
            if acmg_class:
                note_parts.append("ClinVar 胚系致病性对齐 ACMG/AMP 2015 五类")
            else:
                note_parts.append("ClinVar 记录未解析出明确 ACMG 分类")

        if disease_match not in {"DLBCL直接证据", "LBCL近似证据"}:
            note_parts.append("非 DLBCL 直接证据，框架标签仅供参考")

        return {
            "amp_tier": f"Tier {amp_tier}",
            "escat_level": escat_level,
            "acmg_class": acmg_class,
            "framework_note": "；".join(note_parts) + "。",
        }

    def _normalize_internal_level(self, level: str, disease_match: str, record_status: str) -> str:
        level = (level or "L5").upper()
        status = (record_status or "").lower()
        if disease_match == "DLBCL直接证据" and status in {"accepted", "supported", "verified", "curated", "mock_accepted", "live_metadata"}:
            if level in {"L1", "L2"}:
                return level
            if level in {"L3", "L4", "L5"}:
                return "L3"
        if disease_match == "LBCL近似证据" and status in {"accepted", "supported", "verified", "curated", "mock_accepted", "live_metadata"}:
            if level in {"L1", "L2", "L3"}:
                return "L3"
        if disease_match in {"其他淋巴瘤外推", "其他血液肿瘤外推"}:
            return "L4"
        if disease_match == "其他肿瘤外推":
            return "L5"
        return level if level in {"L1", "L2", "L3", "L4", "L5"} else "L5"

    def _initial_safety_flags(self, raw: dict[str, Any], disease_match: str, evidence_level: str) -> list[str]:
        flags: list[str] = []
        if raw.get("access_status") in {"abstract_only", "metadata_only", "conference_abstract", "preprint", "not_accessible"}:
            flags.append("证据仅为摘要或数据库元数据。")
        if disease_match not in {"DLBCL直接证据", "LBCL近似证据"}:
            flags.append("该证据并非 DLBCL 直接证据。")
        if evidence_level in {"L4", "L5"}:
            flags.append("证据等级较低，应视为线索。")
        if raw.get("record_status") and str(raw.get("record_status")).lower() not in {"accepted", "supported", "verified", "curated", "mock_accepted", "live_metadata"}:
            flags.append("记录状态未达到接受阈值。")
        return flags


class SafetyGate:
    def evaluate_variant(self, variant: NormalizedVariant) -> SafetyGateResult:
        if variant.mapping_status in {"ambiguous", "insufficient", "conflicting"}:
            return SafetyGateResult(
                evidence_id=None,
                decision="ask_for_confirmation",
                allowed_claim_strength="no_definitive_variant_claim",
                required_warnings=["当前变异无法唯一映射。请补充转录本、参考基因组版本或检测报告中的标准 HGVS 表达。"],
                blocked_outputs=["diagnosis", "patient_level_treatment_plan", "individual_prognosis_prediction"],
                reasons=variant.warnings or ["变异信息不足或存在歧义。"],
            )
        return SafetyGateResult(
            evidence_id=None,
            decision="allow",
            allowed_claim_strength="variant_level_evidence_lookup",
            required_warnings=variant.warnings,
            blocked_outputs=["patient_level_treatment_plan", "individual_prognosis_prediction"],
            reasons=[],
        )

    def evaluate_card(self, card: EvidenceCard) -> SafetyGateResult:
        warnings: list[str] = []
        blocked = ["drug_dose", "patient_level_treatment_plan", "individual_prognosis_prediction"]
        reasons: list[str] = []
        decision: EvidenceDecision = "allow"
        strength = "evidence_supported_contextual_claim"
        if card.access_status in {"abstract_only", "metadata_only", "conference_abstract", "preprint", "not_accessible"}:
            decision = "downgrade"
            strength = "literature_lead_or_database_signal_only"
            warnings.append("该结论仅基于摘要或数据库元数据，尚无法核验患者入组条件、治疗细节、亚组分析及不良事件，因此仅作为文献线索，不构成患者级诊疗建议。")
            reasons.append("证据访问状态不是全文已核验。")
        if card.disease_match not in {"DLBCL直接证据", "LBCL近似证据"}:
            decision = "downgrade"
            strength = "extrapolation_only"
            warnings.append("该证据不是 DLBCL 直接证据，不能直接外推到 DLBCL。")
            reasons.append(f"疾病匹配程度为：{card.disease_match}。")
        if card.conflict.has_conflict:
            decision = "downgrade"
            strength = "conflicted_evidence"
            warnings.append("该证据存在未解决冲突，不能给出单一确定结论。")
            reasons.append(card.conflict.description or "存在数据库或来源冲突。")
        if "oncogenicity" in (card.evidence_type or "").lower():
            warnings.append("体细胞致癌性不等同于可靶向治疗证据。")
            blocked.append("infer_targetability_from_oncogenicity")
        if card.record_status and str(card.record_status).lower() not in {"accepted", "supported", "verified", "curated", "mock_accepted", "live_metadata"}:
            decision = "downgrade"
            strength = "unaccepted_or_uncertain_record"
            if card.provider.lower() == "civic" and str(card.record_status).lower() == "submitted":
                warnings.append("该 CIViC 记录已提交但尚未经过编辑审核，只能作为待审核数据库线索。")
                reasons.append("CIViC 状态为 SUBMITTED，而不是 ACCEPTED。")
                blocked.extend(["treatment_recommendation", "definitive_diagnosis", "patient_level_prognosis"])
            else:
                warnings.append("证据记录状态未达到接受阈值，需要谨慎解读。")
                reasons.append(f"记录状态为：{card.record_status}。")
        if card.evidence_level in {"L4", "L5"} and decision == "allow":
            decision = "downgrade"
            strength = "low_level_evidence"
            warnings.append("当前证据等级较低，应以线索而非结论表述。")
            reasons.append(f"内部证据等级为：{card.evidence_level}。")
        card.safety_flags = warnings
        return SafetyGateResult(
            evidence_id=card.evidence_id,
            decision=decision,
            allowed_claim_strength=strength,
            required_warnings=warnings,
            blocked_outputs=blocked,
            reasons=reasons,
        )


class AnswerComposer:
    def compose(
        self,
        variants: list[NormalizedVariant],
        cards: list[EvidenceCard],
        gates: list[SafetyGateResult],
        missing_information: list[str],
        global_warnings: list[str],
        question: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        direct = "已完成变异标准化、证据检索、证据卡生成、疾病匹配和安全门控。" if cards else "当前输入未检索到可进入证据卡的记录，或变异信息不足以支持确定性查询。"
        decision_bucket = "allow"
        if any(g.decision in {"ask_for_confirmation", "refuse"} for g in gates):
            decision_bucket = "confirm"
        elif any(g.decision == "downgrade" for g in gates):
            decision_bucket = "downgrade"
        lines = ["## 直接回答", "", direct]
        if decision_bucket == "confirm":
            lines.append("当前至少存在一项需要医生确认或阻断的安全门控结果，结论必须保守表述。")
        elif decision_bucket == "downgrade":
            lines.append("当前证据已进入降级模式，仅可作为线索性解释，不能直接上升为患者级结论。")
        else:
            lines.append("当前证据门控允许在边界内进行分子证据解释。")
        intents = self._question_intents(question)
        if intents:
            lines.extend(["", f"本次重点：{'、'.join(intents)}。"])
        lines.extend(["", "## 针对临床问题的判断"])
        lines.extend(self._clinical_question_answer(variants=variants, cards=cards, intents=intents))
        lines.extend(["", "## 证据依据"])
        if cards:
            for idx, card in enumerate(sorted(cards, key=self._card_rank), start=1):
                lines.append(f"{idx}. **{card.claim}**")
                fw = []
                if card.amp_tier:
                    fw.append(f"AMP/ASCO/CAP {card.amp_tier}")
                if card.escat_level:
                    fw.append(f"ESCAT {card.escat_level}")
                if card.acmg_class:
                    fw.append(f"ACMG {card.acmg_class}")
                fw_bit = f"；框架：{' / '.join(fw)}" if fw else ""
                lines.append(
                    f"   - 来源：[{card.source_id}]({card.source_url})；疾病匹配：{card.disease_match}；"
                    f"证据状态：{card.access_status}；内部等级：{card.evidence_level}{fw_bit}"
                )
                if card.drug:
                    lines.append(f"   - 药物/干预线索：{card.drug}")
                if card.limitations:
                    lines.append(f"   - 局限性：{card.limitations}")
        else:
            lines.append("暂无证据卡。")
        lines.extend(["", "## 适用范围"])
        for variant in variants:
            label = " ".join(item for item in [variant.gene, variant.protein_hgvs or variant.cdna_hgvs or variant.genomic_hgvs or variant.unresolved_position or "未明确位点"] if item)
            lines.append(f"- {label}：肿瘤类型 {variant.disease}，样本类型 {variant.sample_type or '未提供'}，映射状态 {variant.mapping_status}。")
            if variant.warnings:
                lines.append(f"  - 解析提示：{'；'.join(variant.warnings)}")
        lines.extend(["", "## 分子生物学解析"])
        for variant in variants:
            ann = getattr(variant, "molecular_annotation", {}) or {}
            label = " ".join(item for item in [variant.gene or "未识别基因", variant.protein_hgvs or variant.cdna_hgvs or variant.genomic_hgvs or variant.unresolved_position or "未明确位点"] if item)
            lines.append(f"- **{label}**")
            lines.append(f"  - 突变类型：{ann.get('variant_type') or variant.variant_type or 'unknown'}；外显子/结构相关性：{ann.get('exon_relevance') or 'unknown'}")
            lines.append(f"  - 蛋白影响：{ann.get('protein_impact_note') or '当前证据不足'}；预测效应：{ann.get('protein_effect') or 'unknown'}")
            lines.append(f"  - 基因属性：{ann.get('gene_role') or 'unknown'}；肿瘤效应：{ann.get('oncology_effect') or 'unknown'}")
            if ann.get('upstream_pathways'):
                lines.append(f"  - 上游通路：{'；'.join(ann.get('upstream_pathways') or [])}")
            if ann.get('downstream_pathways'):
                lines.append(f"  - 下游通路：{'；'.join(ann.get('downstream_pathways') or [])}")
            if ann.get('go_terms'):
                lines.append(f"  - GO/KEGG/GSEA 功能归类：{'；'.join(ann.get('go_terms') or [])}")
            if ann.get('targetability'):
                lines.append(f"  - 靶向线索：{'；'.join(ann.get('targetability') or [])}")
            lines.append(f"  - 数据库分型提示：{ann.get('database_class_hint') or 'context_dependent'}")
        lines.extend(["", "## 分子诊断报告模板"])
        lines.extend(self._build_report_template(variants=variants, cards=cards, decision_bucket=decision_bucket))
        lines.extend(["", "## 证据状态"])
        statuses = sorted({card.access_status for card in cards}) if cards else []
        lines.append("- " + ("；".join(statuses) if statuses else "暂无可展示证据状态。"))
        # 分级展示证据核验状态，而非一刀切
        full_verified = [c for c in cards if c.access_status == "full_text_verified"]
        metadata_only = [c for c in cards if c.access_status == "metadata_only"]
        mock_cards = [c for c in cards if "mock" in (c.access_status or "").lower() or "mock" in (c.provider or "").lower()]
        not_accessible = [c for c in cards if c.access_status in {"not_accessible", "abstract_only", "preprint"}]
        if full_verified:
            lines.append(f"- 已全文核验证据 {len(full_verified)} 条，可用于临床讨论。")
        if metadata_only:
            lines.append(f"- 元数据级证据 {len(metadata_only)} 条：可作为数据库线索，不宜直接用于用药或疗效判断。")
        if mock_cards:
            lines.append(f"- 本地示例证据 {len(mock_cards)} 条：仅用于演示流程，不代表真实数据库结论。")
        if not_accessible:
            lines.append(f"- 未获取全文证据 {len(not_accessible)} 条：建议补充原文或升级数据源模式后复查。")
        if not cards:
            lines.append("- 当前未检索到证据卡；建议补充更明确的 HGVS 或切换数据源模式。")
        if any(card.evidence_level in {"L4", "L5"} for card in cards):
            lines.append("- 存在低等级证据，已按线索性证据处理。")
        lines.extend(["", "## 冲突与不确定性"])
        conflicts = [card for card in cards if card.conflict.has_conflict]
        if conflicts:
            for card in conflicts:
                lines.append(f"- {card.source_id}：{card.conflict.description or '存在未解决冲突'}")
        else:
            lines.append("- 当前证据卡未标记明确冲突。")
        if any(card.disease_match not in {"DLBCL直接证据", "LBCL近似证据"} for card in cards):
            lines.append("- 存在非 DLBCL 直接证据，已按外推证据降级处理。")
        unaccepted = [c for c in cards if (c.record_status or '').lower() not in {"accepted", "supported", "verified", "curated", "mock_accepted", "live_metadata"}]
        if unaccepted:
            lines.append(f"- 存在 {len(unaccepted)} 条未确认记录，仅作参考线索。")
        lines.extend(["", "## 缺失信息"])
        if missing_information:
            lines.extend(f"- {item}" for item in missing_information)
        else:
            lines.append("- 当前输入已满足基础查询条件。")
        if any(v.mapping_status == "ambiguous" for v in variants):
            lines.append("- 存在歧义映射的变异，无法在不补充信息时给出位点级结论。")
        if cards:
            provider_counts = {}
            for card in cards:
                provider_counts[card.provider] = provider_counts.get(card.provider, 0) + 1
            lines.append("- 来源分布：" + "；".join(f"{provider} {count} 条" for provider, count in provider_counts.items()))
        lines.extend(["", "## 来源"])
        if cards:
            for card in cards:
                lines.append(f"- [{card.source_id}]({card.source_url})，版本：{card.source_version or '未知'}，检索时间：{card.retrieved_at}")
        else:
            lines.append("- 暂无来源。")
        lines.extend(["", "## 使用边界"])
        for item in global_warnings:
            lines.append(f"- {item}")
        doctor_summary = self._build_doctor_summary(
            variants=variants,
            cards=cards,
            gates=gates,
            missing_information=missing_information,
            decision_bucket=decision_bucket,
        )
        doctor_summary["report_template"] = self._build_report_template(
            variants=variants,
            cards=cards,
            decision_bucket=decision_bucket,
        )
        doctor_summary["pathway_notes"] = self._build_pathway_notes(variants=variants)
        return "\n".join(lines), doctor_summary

    def _question_intents(self, question: Optional[str]) -> list[str]:
        text = question or ""
        rules = [
            ("诊断与分型", r"诊断|分型|亚型|MCD|BN2|EZB|N1"),
            ("治疗与可操作性", r"治疗|用药|靶向|抑制剂|获益|敏感"),
            ("预后", r"预后|生存|复发|进展|风险"),
            ("耐药", r"耐药|治疗失败|获得性"),
            ("遗传风险", r"胚系|遗传|家族|遗传咨询"),
            ("功能与通路", r"功能|通路|蛋白|机制"),
            ("补充检测", r"补充|进一步检测|还需要|验证"),
        ]
        intents = [label for label, pattern in rules if re.search(pattern, text, flags=re.IGNORECASE)]
        return intents or ["综合临床意义"]

    def _clinical_question_answer(
        self, *, variants: list[NormalizedVariant], cards: list[EvidenceCard], intents: list[str]
    ) -> list[str]:
        genes = {variant.gene.upper() for variant in variants if variant.gene}
        direct_count = sum(card.disease_match == "DLBCL直接证据" for card in cards)
        lines: list[str] = []
        if "诊断与分型" in intents:
            if {"MYD88", "CD79B"}.issubset(genes):
                lines.append("- **诊断与分型：**MYD88 与 CD79B 共变异在生物学上符合 BCR/TLR–NF-κB 共同激活，并可支持 MCD 样分子特征；但不能仅凭两个位点替代完整分子分型算法，也不能脱离病理和免疫表型独立确诊。")
            else:
                lines.append("- **诊断与分型：**这些变异可作为当前疾病诊断或分型的辅助线索，不能单独替代病理、免疫表型及正式分类标准。")
        if "治疗与可操作性" in intents:
            targetable = [variant.gene for variant in variants if (variant.molecular_annotation or {}).get("targetability")]
            if targetable:
                lines.append(f"- **治疗：**{ '、'.join(dict.fromkeys(targetable)) } 存在通路或药物研究线索；致癌性和通路相关性不等同于已证实的患者级疗效，应结合当前癌种适应证、治疗线次、指南及临床试验。")
            else:
                lines.append("- **治疗：**当前变异不能直接形成患者级用药建议；需确认同癌种预测性证据、适应证和指南推荐。")
        if "预后" in intents:
            lines.append("- **预后：**现有记录最多支持群体层面的相关性线索，不能据此预测该患者的具体复发概率、生存时间或必然结局。")
        if "耐药" in intents:
            lines.append("- **耐药：**需要结合具体药物、治疗前后配对样本、变异出现时间和克隆比例变化判断；单次检测不能确认获得性耐药。")
        if "遗传风险" in intents:
            lines.append("- **遗传风险：**肿瘤样本结果不能确认胚系来源；如变异和家族史提示遗传易感，应进行遗传咨询并使用非肿瘤样本验证。")
        if "功能与通路" in intents:
            pathways = list(dict.fromkeys(pathway for variant in variants for pathway in (variant.molecular_annotation or {}).get("downstream_pathways", [])))
            lines.append(f"- **功能与通路：**涉及的主要下游包括{'、'.join(pathways) if pathways else '需结合具体变异进一步判断'}；这些属于机制解释，不自动构成治疗证据。")
        if "补充检测" in intents:
            lines.append("- **下一步：**优先核对标准HGVS、转录本、GRCh版本、VAF、测序深度、支持读段、肿瘤含量及配对正常样本；涉及分型时应补充完整分类所需的病理和分子数据。")
        if direct_count:
            lines.append(f"- **证据匹配：**当前检索到 {direct_count} 条当前疾病直接证据；仍需结合记录状态和证据等级判断可采用的结论强度。")
        elif cards:
            lines.append("- **证据匹配：**当前证据以相近疾病或外推记录为主，不宜直接用于当前患者决策。")
        else:
            lines.append("- **证据匹配：**当前未形成可展示证据卡，不能把未检索到记录解释为变异无临床意义。")
        return lines

    def _build_report_template(
        self,
        *,
        variants: list[NormalizedVariant],
        cards: list[EvidenceCard],
        decision_bucket: str,
    ) -> list[str]:
        lines: list[str] = []
        if not variants:
            lines.append("- 暂无可生成模板的变异。")
            return lines
        primary_card = next((card for card in cards if self._is_displayable_card(card)), None)
        for idx, variant in enumerate(variants, start=1):
            ann = getattr(variant, "molecular_annotation", {}) or {}
            label = " ".join(item for item in [variant.gene or "未识别基因", variant.protein_hgvs or variant.cdna_hgvs or variant.genomic_hgvs or variant.unresolved_position or "未明确位点"] if item)
            lines.append(f"- 模板 {idx}：{label}")
            lines.append(f"  - 变异类型：{ann.get('variant_type') or variant.variant_type or 'unknown'}；位点性质：{ann.get('exon_relevance') or 'unknown'}")
            lines.append(f"  - 蛋白层判断：{ann.get('protein_impact_note') or '当前证据不足'}")
            lines.append(f"  - 功能属性：{ann.get('gene_role') or 'unknown'}；肿瘤作用：{ann.get('oncology_effect') or 'unknown'}")
            pathway_parts = []
            if ann.get('upstream_pathways'):
                pathway_parts.append("上游" + ' / '.join(ann.get('upstream_pathways') or []))
            if ann.get('downstream_pathways'):
                pathway_parts.append("下游" + ' / '.join(ann.get('downstream_pathways') or []))
            if pathway_parts:
                lines.append(f"  - 通路：{'；'.join(pathway_parts)}")
            if ann.get('go_terms'):
                lines.append(f"  - 功能归类：{'；'.join(ann.get('go_terms') or [])}")
            if ann.get('targetability'):
                lines.append(f"  - 药物线索：{'；'.join(ann.get('targetability') or [])}")
            if primary_card:
                lines.append(f"  - 数据库主证据：{primary_card.provider} / {primary_card.disease_match} / {primary_card.evidence_level}")
            lines.append(f"  - 临床判断：{decision_bucket if decision_bucket else '待判断'}")
        return lines

    def _build_pathway_notes(self, *, variants: list[NormalizedVariant]) -> list[str]:
        notes: list[str] = []
        for variant in variants:
            ann = getattr(variant, "molecular_annotation", {}) or {}
            label = variant.gene or "未识别基因"
            pathways = ann.get("upstream_pathways") or []
            go_terms = ann.get("go_terms") or []
            if pathways or go_terms:
                note = f"{label}："
                if pathways:
                    note += f"通路 {' / '.join(pathways)}"
                if go_terms:
                    note += f"；功能 {' / '.join(go_terms)}"
                notes.append(note)
        return notes[:5]

    def _build_doctor_summary(
        self,
        *,
        variants: list[NormalizedVariant],
        cards: list[EvidenceCard],
        gates: list[SafetyGateResult],
        missing_information: list[str],
        decision_bucket: str,
    ) -> dict[str, Any]:
        direct_cards = [card for card in cards if card.disease_match == "DLBCL直接证据"]
        near_cards = [card for card in cards if card.disease_match == "LBCL近似证据"]
        proxy_cards = [card for card in cards if card.disease_match not in {"DLBCL直接证据", "LBCL近似证据"}]
        provider_counts: dict[str, int] = {}
        for card in cards:
            provider_counts[card.provider] = provider_counts.get(card.provider, 0) + 1
        top_variant = variants[0] if variants else None
        top_gate = next((gate for gate in gates if gate.decision in {"ask_for_confirmation", "refuse", "downgrade"}), gates[0] if gates else None)
        conclusion = "当前证据允许在边界内形成分子解释。"
        if decision_bucket == "confirm":
            conclusion = "当前结果需要医生确认后再下结论。"
        elif decision_bucket == "downgrade":
            conclusion = "当前结果只能作为线索性解释，不能直接作为患者级结论。"
        elif not cards:
            conclusion = "当前未检索到可用证据卡，需补充信息后再判断。"
        has_blocking_missing = self._has_blocking_missing(variants)
        next_step = self._recommend_next_step(
            decision_bucket=decision_bucket,
            missing_information=missing_information,
            cards=cards,
            has_blocking_missing=has_blocking_missing,
        )
        priority_action = self._priority_action(
            decision_bucket=decision_bucket,
            cards=cards,
            missing_information=missing_information,
            has_blocking_missing=has_blocking_missing,
        )
        return {
            "title": "医生摘要",
            "conclusion": conclusion,
            "evidence_strength": decision_bucket,
            "variant_count": len(variants),
            "card_count": len(cards),
            "direct_evidence_count": len(direct_cards),
            "near_evidence_count": len(near_cards),
            "proxy_evidence_count": len(proxy_cards),
            "provider_counts": provider_counts,
            "missing_information_count": len(missing_information),
            "primary_variant": top_variant.to_dict() if top_variant else None,
            "primary_gate": top_gate.to_dict() if top_gate else None,
            "recommended_next_step": next_step,
            "next_step": next_step,
            "priority_action": priority_action,
            "highlights": self._build_summary_highlights(variants=variants, cards=cards, gates=gates, missing_information=missing_information),
            "top_evidence": [card.to_dict() for card in cards[:3]],
        }

    def _build_summary_highlights(
        self,
        *,
        variants: list[NormalizedVariant],
        cards: list[EvidenceCard],
        gates: list[SafetyGateResult],
        missing_information: list[str],
    ) -> list[str]:
        highlights: list[str] = []
        if variants:
            highlights.append(f"已识别 {len(variants)} 个变异条目。")
        if cards:
            highlights.append(f"检索到 {len(cards)} 条证据卡。")
            if any(card.disease_match == "DLBCL直接证据" for card in cards):
                highlights.append("存在 DLBCL 直接证据，可优先阅读。")
            elif any(card.disease_match == "LBCL近似证据" for card in cards):
                highlights.append("存在 LBCL 近似证据，可作为次级参考。")
        if any(g.decision in {"ask_for_confirmation", "refuse"} for g in gates):
            highlights.append("至少存在一条需要确认的门控结果。")
        if missing_information:
            highlights.append(f"还有 {len(missing_information)} 项关键信息缺失。")
        return highlights[:5]

    def _recommend_next_step(self, *, decision_bucket: str, missing_information: list[str], cards: list[EvidenceCard], has_blocking_missing: bool) -> str:
        if decision_bucket == "confirm":
            return "请补充转录本、参考基因组版本和完整病理/检测报告后再讨论。"
        if not cards:
            return "建议补充更明确的 HGVS 或原始检测报告。"
        if has_blocking_missing:
            return "建议先补齐阻断性信息，再结合 DLBCL 直接证据进行临床讨论。"
        if any(card.disease_match == "DLBCL直接证据" for card in cards):
            return "可作为 DLBCL 分子解释线索，建议结合病理和临床背景讨论。"
        if any(card.disease_match == "LBCL近似证据" for card in cards):
            return "可作为近似证据参考，但不宜直接上升为患者级结论。"
        if any(card.provider.lower() == "clinvar" for card in cards) and any(card.provider.lower() == "civic" for card in cards):
            return "ClinVar 与 CIViC 均已检出，可作为数据库与临床证据联合线索。"
        if any(card.provider.lower() == "clinvar" for card in cards):
            return "可作为 ClinVar 变异数据库线索，仍需结合 CIViC 和 DLBCL 直接证据。"
        if any(card.provider.lower() == "civic" for card in cards):
            return "可作为 CIViC 功能/临床证据线索，仍需结合 ClinVar 和 DLBCL 直接证据。"
        return "仅建议作为外推线索。"

    def _priority_action(self, *, decision_bucket: str, cards: list[EvidenceCard], missing_information: list[str], has_blocking_missing: bool) -> str:
        if decision_bucket == "confirm":
            return "补充信息后再判断"
        if not cards:
            return "补充更明确变异信息"
        if has_blocking_missing:
            return "先补齐关键信息"
        if any(card.disease_match == "DLBCL直接证据" for card in cards):
            return "可进入临床讨论"
        if any(card.disease_match == "LBCL近似证据" for card in cards):
            return "仅作辅助参考"
        return "仅作外推参考"

    def _is_displayable_card(self, card: EvidenceCard) -> bool:
        status = (card.access_status or '').lower()
        title = f"{card.source_title or ''} {card.source_id or ''}".lower()
        if status in {"not_accessible", "query_error"}:
            return False
        if 'query error' in title or 'query_error' in title:
            return False
        return True

    def _card_rank(self, card: EvidenceCard) -> tuple[int, int, int, str]:
        disease_rank = {
            "DLBCL直接证据": 0,
            "LBCL近似证据": 1,
            "侵袭性B细胞淋巴瘤近似证据": 2,
            "其他淋巴瘤外推": 3,
            "其他血液肿瘤外推": 4,
            "其他肿瘤外推": 5,
            "疾病不匹配": 6,
            "未知": 7,
        }.get(card.disease_match, 8)
        status_rank = {
            "full_text_verified": 0,
            "accepted": 1,
            "supported": 1,
            "verified": 1,
            "curated": 1,
            "mock_accepted": 1,
            "live_metadata": 2,
            "metadata_only": 3,
            "abstract_only": 4,
            "conference_abstract": 5,
            "preprint": 6,
            "not_accessible": 7,
        }.get((card.access_status or "").lower(), 8)
        level_rank = {
            "L1": 0,
            "L2": 1,
            "L3": 2,
            "L4": 3,
            "L5": 4,
        }.get((card.evidence_level or "").upper(), 5)
        return disease_rank, status_rank, level_rank, card.evidence_level

    def _has_blocking_missing(self, variants: list[NormalizedVariant]) -> bool:
        """Only blocking gaps should trigger 'fill in first' messaging."""
        for variant in variants:
            if variant.missing_fields:
                return True
            if not variant.sample_type:
                return True
            if not variant.gene:
                return True
            if not variant.protein_hgvs and not variant.cdna_hgvs and not variant.genomic_hgvs:
                return True
        return False


class MolecularEvidenceService:
    CACHE_TTL_DAYS = 7

    def __init__(
        self,
        provider: Optional[EvidenceProvider] = None,
        *,
        provider_mode: Optional[ProviderMode] = None,
        agent: Optional[MolecularEvidenceAgent] = None,
    ) -> None:
        self.parser = MolecularInputParser()
        self.provider_mode = (provider_mode or os.getenv("MOLECULAR_EVIDENCE_PROVIDER_MODE", "live")).strip().lower()
        self.agent = agent or MolecularEvidenceAgent(
            provider_mode=self.provider_mode,
            providers=self._build_agent_providers(self.provider_mode, provider),
        )
        self.builder = EvidenceCardBuilder()
        self.safety_gate = SafetyGate()
        self.answer_composer = AnswerComposer()

    def _build_agent_providers(
        self, provider_mode: Optional[str], provider: Optional[EvidenceProvider]
    ) -> list[EvidenceProvider]:
        if provider is not None:
            if isinstance(provider, CompositeEvidenceProvider):
                return provider.providers
            return [provider]
        mode = (provider_mode or os.getenv("MOLECULAR_EVIDENCE_PROVIDER_MODE", "live")).strip().lower()
        if mode == "mock":
            mock = MockEvidenceProvider()
            return [
                _ProviderView(mock, "ClinVar"),
                _ProviderView(mock, "CIViC"),
            ]
        providers: list[EvidenceProvider] = [ClinVarProvider(), CivicProvider()]
        if mode == "hybrid":
            providers.append(MockEvidenceProvider())
        return providers

    def query(
        self,
        *,
        text: str,
        disease: str = "DLBCL",
        sample_type: Optional[str] = None,
        genome_build: Optional[str] = None,
        transcript: Optional[str] = None,
        variant_type: Optional[str] = None,
        question: Optional[str] = None,
    ) -> MolecularEvidenceResult:
        return self.analyze(
            text=text,
            disease=disease,
            sample_type=sample_type,
            genome_build=genome_build,
            transcript=transcript,
            variant_type=variant_type,
            question=question,
        )

    def analyze(
        self,
        *,
        text: str,
        disease: str = "DLBCL",
        sample_type: Optional[str] = None,
        genome_build: Optional[str] = None,
        transcript: Optional[str] = None,
        variant_type: Optional[str] = None,
        question: Optional[str] = None,
    ) -> MolecularEvidenceResult:
        from backend.app.db import get_session_factory
        from backend.app.models_db import MolecularEvidenceCacheEntry, MolecularEvidenceQueryLog

        retrieved_at = utc_now_iso()
        query_payload = {
            "text": text,
            "disease": disease,
            "sample_type": sample_type,
            "genome_build": genome_build,
            "transcript": transcript,
            "variant_type": variant_type,
            "question": question,
            "provider_mode": self.provider_mode,
        }
        cache_key = self._make_cache_key(text=text, disease=disease, sample_type=sample_type, genome_build=genome_build, transcript=transcript, variant_type=variant_type, provider_name=f"{self.provider_mode}:providers-v4-civic-tiered-zh")
        cached = self._load_cache(cache_key)
        if cached is not None:
            result = self._result_from_payload(cached, cache_hit=True, cache_key=cache_key)
            log_id = self._write_audit_log(
                cache_key=cache_key,
                provider_mode=query_payload["provider_mode"],
                query_payload=query_payload,
                result=result,
                cache_hit=True,
                cache_source_log_id=cached.get("query_log_id"),
            )
            result.query_log_id = log_id
            result.cache_hit = True
            result.cache_key = cache_key
            result.cache_entry_id = cached.get("cache_entry_id") or cached.get("id")
            return result

        variants = self.parser.parse(
            text,
            disease=disease,
            sample_type=sample_type,
            genome_build=genome_build,
            transcript=transcript,
            variant_type=variant_type,
        )
        raw_records, agent_trace, provider_status = self.agent.run(variants)
        cards: list[EvidenceCard] = []
        gates: list[SafetyGateResult] = []
        variants_by_id = {variant.variant_id: variant for variant in variants}
        for variant in variants:
            gates.append(self.safety_gate.evaluate_variant(variant))
        for record in raw_records:
            if self.agent._is_error_record(record):
                continue
            raw_variant_id = str(record.raw_response.get("variant_id") or "")
            variant = variants_by_id.get(raw_variant_id)
            if variant is None:
                variant = self._match_record_variant(record, variants)
            if variant is None:
                continue
            card = self.builder.build(record, variant)
            cards.append(card)
            gates.append(self.safety_gate.evaluate_card(card))
        cards.sort(key=self.answer_composer._card_rank)
        missing_information = self._collect_missing_information(variants)
        global_warnings = [
            "本工具仅用于分子证据解释，不构成患者级诊断或治疗建议。",
            "不得将体细胞致癌性自动等同于可靶向治疗。",
            "不得将其他癌种证据直接外推到 DLBCL。",
            "不得仅凭一个或若干突变预测患者个体预后。",
        ]
        degraded_providers = [
            name for name, item in provider_status.items() if item.get("state") == "degraded"
        ]
        if degraded_providers:
            global_warnings.append(
                f"数据库查询发生降级：{', '.join(degraded_providers)}；相关数据库本次未形成完整证据集，不能将未命中解释为无证据。"
            )
        answer, doctor_summary = self.answer_composer.compose(
            variants=variants,
            cards=cards,
            gates=gates,
            missing_information=missing_information,
            global_warnings=global_warnings,
            question=question,
        )
        result = MolecularEvidenceResult(
            variants=variants,
            raw_records=raw_records,
            evidence_cards=cards,
            safety_gate_results=gates,
            answer_markdown=answer,
            doctor_summary=doctor_summary,
            missing_information=missing_information,
            global_warnings=global_warnings,
            retrieved_at=retrieved_at,
            provider_mode=self.provider_mode,
            cache_hit=False,
            cache_key=cache_key,
            agent_trace=agent_trace,
            provider_status=provider_status,
        )
        cache_entry_id = self._store_cache(cache_key, result.to_dict())
        result.cache_entry_id = cache_entry_id
        log_id = self._write_audit_log(
            cache_key=cache_key,
            provider_mode=query_payload["provider_mode"],
            query_payload=query_payload,
            result=result,
            cache_hit=False,
        )
        result.query_log_id = log_id
        if cache_entry_id:
            self._store_cache(cache_key, result.to_dict())
        return result

    def _match_record_variant(
        self, record: RawEvidenceRecord, variants: list[NormalizedVariant]
    ) -> Optional[NormalizedVariant]:
        if len(variants) == 1:
            return variants[0]
        record_text = json.dumps(record.raw_response, ensure_ascii=False).upper()
        for variant in variants:
            tokens = [variant.gene, variant.protein_hgvs, variant.cdna_hgvs, variant.genomic_hgvs]
            if variant.gene and variant.gene.upper() in record_text and any(
                token and token.upper().replace("P.", "") in record_text for token in tokens[1:]
            ):
                return variant
        return next((variant for variant in variants if variant.gene and variant.gene.upper() in record_text), None)

    def _make_cache_key(
        self,
        *,
        text: str,
        disease: str,
        sample_type: Optional[str],
        genome_build: Optional[str],
        transcript: Optional[str],
        variant_type: Optional[str],
        provider_name: str,
    ) -> str:
        normalized = {
            "text": re.sub(r"\s+", " ", text or "").strip().lower(),
            "disease": normalize_disease(disease),
            "sample_type": (sample_type or "").strip().lower(),
            "genome_build": (genome_build or "").strip().upper(),
            "transcript": (transcript or "").strip().lower(),
            "variant_type": (variant_type or "").strip().lower(),
            "provider_name": provider_name.lower(),
        }
        return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _load_cache(self, cache_key: str) -> Optional[dict[str, Any]]:
        from backend.app.db import get_session_factory
        from backend.app.models_db import MolecularEvidenceCacheEntry

        factory = get_session_factory()
        db = factory()
        try:
            entry = db.query(MolecularEvidenceCacheEntry).filter(MolecularEvidenceCacheEntry.query_key == cache_key).first()
            if not entry:
                return None
            expires_at = entry.expires_at
            if expires_at is not None:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at < datetime.now(timezone.utc):
                    return None
            try:
                payload = json.loads(entry.payload_json)
                if isinstance(payload, dict):
                    payload.setdefault("cache_entry_id", entry.id)
                    return payload
                return None
            except Exception:
                return None
        finally:
            db.close()

    def _store_cache(self, cache_key: str, payload: dict[str, Any]) -> Optional[str]:
        from backend.app.db import get_session_factory
        from backend.app.models_db import MolecularEvidenceCacheEntry

        factory = get_session_factory()
        db = factory()
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.CACHE_TTL_DAYS)
            existing = db.query(MolecularEvidenceCacheEntry).filter(MolecularEvidenceCacheEntry.query_key == cache_key).first()
            if existing:
                existing.payload_json = json.dumps(payload, ensure_ascii=False)
                existing.retrieved_at = datetime.now(timezone.utc)
                existing.expires_at = expires_at
                existing.provider_mode = str(payload.get("provider_mode") or existing.provider_mode)
                db.commit()
                return existing.id
            entry = MolecularEvidenceCacheEntry(
                query_key=cache_key,
                provider_mode=str(payload.get("provider_mode") or "mock"),
                payload_json=json.dumps(payload, ensure_ascii=False),
                retrieved_at=datetime.now(timezone.utc),
                expires_at=expires_at,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry.id
        finally:
            db.close()

    def _write_audit_log(
        self,
        *,
        cache_key: str,
        provider_mode: str,
        query_payload: dict[str, Any],
        result: MolecularEvidenceResult,
        cache_hit: bool,
        cache_source_log_id: Optional[str] = None,
    ) -> str:
        from backend.app.db import get_session_factory
        from backend.app.models_db import MolecularEvidenceQueryLog

        factory = get_session_factory()
        db = factory()
        try:
            log = MolecularEvidenceQueryLog(
                query_key=cache_key,
                provider_mode=provider_mode,
                input_json=json.dumps(query_payload, ensure_ascii=False),
                normalized_json=json.dumps([v.to_dict() for v in result.variants], ensure_ascii=False),
                raw_records_json=json.dumps([r.to_dict() for r in result.raw_records], ensure_ascii=False),
                evidence_cards_json=json.dumps([c.to_dict() for c in result.evidence_cards], ensure_ascii=False),
                safety_results_json=json.dumps([g.to_dict() for g in result.safety_gate_results], ensure_ascii=False),
                answer_markdown=result.answer_markdown,
                cache_hit=cache_hit,
                cache_source_log_id=cache_source_log_id,
                retrieved_at=datetime.now(timezone.utc),
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log.id
        finally:
            db.close()

    def _result_from_payload(self, payload: dict[str, Any], *, cache_hit: bool, cache_key: str) -> MolecularEvidenceResult:
        variants = [NormalizedVariant(**item) for item in payload.get("variants", [])]
        raw_records = [RawEvidenceRecord(**item) for item in payload.get("raw_records", [])]
        evidence_cards = [EvidenceCard(conflict=EvidenceConflict(**item.get("conflict", {})), **{k: v for k, v in item.items() if k != "conflict"}) for item in payload.get("evidence_cards", [])]
        safety_results = [SafetyGateResult(**item) for item in payload.get("safety_gate_results", [])]
        return MolecularEvidenceResult(
            variants=variants,
            raw_records=raw_records,
            evidence_cards=evidence_cards,
            safety_gate_results=safety_results,
            answer_markdown=str(payload.get("answer_markdown") or ""),
            doctor_summary=dict(payload.get("doctor_summary") or {}),
            missing_information=list(payload.get("missing_information") or []),
            global_warnings=list(payload.get("global_warnings") or []),
            retrieved_at=str(payload.get("retrieved_at") or utc_now_iso()),
            provider_mode=str(payload.get("provider_mode") or self.provider_mode),
            cache_hit=cache_hit,
            cache_key=cache_key,
            cache_entry_id=str(payload.get("cache_entry_id") or "") or None,
            query_log_id=str(payload.get("query_log_id") or "") or None,
            agent_trace=list(payload.get("agent_trace") or []),
            provider_status=dict(payload.get("provider_status") or {}),
            required_providers=list(payload.get("required_providers") or ["ClinVar", "CIViC"]),
        )

    def _collect_missing_information(self, variants: list[NormalizedVariant]) -> list[str]:
        """收集缺失信息，但区分"阻断性缺失"和"建议性缺失"。

        只有阻断性缺失（gene / protein_hgvs / disease / sample_type）
        才会进入 missing_information，用于门控降级。

        建议性缺失（transcript / genome_build）不会触发降级，
        只会在报告的"解析提示"中提醒。
        """
        blocking_missing: list[str] = []
        advisory_missing: list[str] = []
        for variant in variants:
            label = " ".join(item for item in [variant.gene or "未识别基因", variant.protein_hgvs or variant.cdna_hgvs or "未明确位点"] if item)
            # 阻断性缺失：直接影响能否解析
            if variant.missing_fields:
                blocking_missing.append(f"{label} 缺少：{', '.join(variant.missing_fields)}。")
            if not variant.sample_type:
                blocking_missing.append(f"{label} 缺少样本类型，无法区分肿瘤组织、外周血或胚系检测语境。")
            # 建议性缺失：不影响已有证据的解读，但影响精确度
            if not variant.transcript:
                advisory_missing.append(f"{label} 未提供转录本；如需精确外显子定位请补充。")
            if not variant.genome_build:
                advisory_missing.append(f"{label} 未提供 GRCh37/GRCh38；如需基因组坐标精确匹配请补充。")
        # 去重
        deduped: list[str] = []
        seen: set[str] = set()
        for item in blocking_missing + advisory_missing:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _has_blocking_missing(self, variants: list[NormalizedVariant]) -> bool:
        """判断是否存在阻断性缺失（只有这类缺失才应该触发"先补齐"提示）。"""
        for variant in variants:
            if variant.missing_fields:
                return True
            if not variant.sample_type:
                return True
            if not variant.gene:
                return True
            if not variant.protein_hgvs and not variant.cdna_hgvs and not variant.genomic_hgvs:
                return True
        return False
