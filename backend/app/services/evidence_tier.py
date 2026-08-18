"""Doctor-facing clinical literature evidence tiers (E1–E5).

Not ACMG (variant pathogenicity) and not OCEBM alone — hematology needs a
dedicated E2 bucket for pivotal single-arm registrational phase II work
(CAR-T / bispecifics / ADCs).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

TIER_RANK = {"E1": 1, "E2": 2, "E3": 3, "E4": 4, "E5": 5}

TIER_LABEL_ZH = {
    "E1": "改变实践",
    "E2": "注册性证据",
    "E3": "前瞻性探索",
    "E4": "真实世界",
    "E5": "弱证据",
}

_PIVOTAL_TRIAL_RE = re.compile(
    r"\b("
    r"ZUMA[-\s]?\d*"
    r"|JULIET"
    r"|TRANSCEND"
    r"|TRANSFORM"
    r"|BELINDA"
    r"|EPCORE"
    r"|POLARIX"
    r"|GOYA"
    r"|PHOENIX"
    r"|ROSEWOOD"
    r"|LOTIS"
    r"|STARGLO"
    r"|ALEXANDER"
    r"|PILOT"
    r"|ZUMA-7"
    r"|ELARA"
    r"|CARTITUDE"
    r"|KARMA"
    r")\b",
    re.I,
)

_SINGLE_ARM_RE = re.compile(
    r"\b("
    r"single[- ]arm"
    r"|single[- ]center"
    r"|open[- ]label"
    r"|pivotal"
    r"|registrational"
    r"|seamless"
    r"|phase\s*1b/?2"
    r"|phase\s*i/?ii"
    r"|phase\s*ib/?ii"
    r")\b",
    re.I,
)

_RWE_RE = re.compile(
    r"\b("
    r"real[- ]world"
    r"|retrospective"
    r"|observational"
    r"|chart review"
    r"|multicen(?:ter|tre)\s+retrospective"
    r")\b",
    re.I,
)

_PROSPECTIVE_RE = re.compile(
    r"\b("
    r"prospective"
    r"|cohort"
    r"|nonrandomized"
    r"|non-randomi[sz]ed"
    r"|investigator-initiated"
    r")\b",
    re.I,
)


@dataclass
class EvidenceTierResult:
    tier: str  # E1–E5
    study_design_zh: str
    reasons: List[str] = field(default_factory=list)
    in_guideline: bool = False
    guideline_ref: Optional[str] = None

    @property
    def tier_rank(self) -> int:
        return TIER_RANK.get(self.tier, 5)

    @property
    def tier_label_zh(self) -> str:
        return TIER_LABEL_ZH.get(self.tier, self.tier)


def _types_blob(pub_types: Sequence[str]) -> str:
    return " | ".join(p.lower() for p in pub_types)


def _has_any(blob: str, *needles: str) -> bool:
    return any(n in blob for n in needles)


def classify_evidence_tier(
    *,
    title: str = "",
    abstract: str = "",
    pub_types: Optional[Sequence[str]] = None,
    in_guideline: bool = False,
    guideline_ref: Optional[str] = None,
) -> EvidenceTierResult:
    """Classify a PubMed hit into E1–E5 with a short Chinese design label."""
    pub_types = list(pub_types or [])
    types = _types_blob(pub_types)
    text = f"{title}\n{abstract}"
    reasons: List[str] = []

    # Weak evidence first (hard demotion) — but guideline citation can still lift.
    if _has_any(types, "case reports", "letter", "editorial", "comment", "news", "published erratum"):
        design = "病例报告/短评"
        if "case reports" in types:
            design = "病例报告"
        elif "editorial" in types:
            design = "社论"
        elif "letter" in types:
            design = "读者来信"
        reasons.append(f"pub_types弱证据:{design}")
        if in_guideline:
            reasons.append("已被指南引用→提升至E1")
            return EvidenceTierResult(
                tier="E1",
                study_design_zh=design,
                reasons=reasons,
                in_guideline=True,
                guideline_ref=guideline_ref,
            )
        return EvidenceTierResult(
            tier="E5",
            study_design_zh=design,
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )

    if _has_any(types, "review") and not _has_any(types, "systematic review", "meta-analysis"):
        reasons.append("非系统综述/叙述性综述")
        if in_guideline:
            reasons.append("已被指南引用→提升至E1")
            return EvidenceTierResult(
                tier="E1",
                study_design_zh="综述",
                reasons=reasons,
                in_guideline=True,
                guideline_ref=guideline_ref,
            )
        return EvidenceTierResult(
            tier="E5",
            study_design_zh="综述",
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )

    # E1: Meta / SR / Phase III RCT / guideline citation
    if _has_any(types, "meta-analysis"):
        reasons.append("Meta-Analysis")
        return EvidenceTierResult(
            tier="E1",
            study_design_zh="Meta分析",
            reasons=reasons + (["已被指南引用"] if in_guideline else []),
            in_guideline=in_guideline,
            guideline_ref=guideline_ref,
        )
    if _has_any(types, "systematic review"):
        reasons.append("Systematic Review")
        return EvidenceTierResult(
            tier="E1",
            study_design_zh="系统综述",
            reasons=reasons + (["已被指南引用"] if in_guideline else []),
            in_guideline=in_guideline,
            guideline_ref=guideline_ref,
        )
    if _has_any(types, "practice guideline", "guideline"):
        reasons.append("Guideline pub_type")
        return EvidenceTierResult(
            tier="E1",
            study_design_zh="实践指南",
            reasons=reasons + (["已被指南引用"] if in_guideline else []),
            in_guideline=in_guideline,
            guideline_ref=guideline_ref,
        )
    if _has_any(types, "randomized controlled trial") or _has_any(
        types, "clinical trial, phase iii", "clinical trial, phase 3"
    ):
        reasons.append("RCT / Phase III")
        return EvidenceTierResult(
            tier="E1",
            study_design_zh="III期RCT",
            reasons=reasons + (["已被指南引用"] if in_guideline else []),
            in_guideline=in_guideline,
            guideline_ref=guideline_ref,
        )
    if re.search(r"\bphase\s*(iii|3)\b", text, re.I) and re.search(
        r"\brandomi[sz]ed\b|\brct\b", text, re.I
    ):
        reasons.append("标题/摘要明示Phase III RCT")
        return EvidenceTierResult(
            tier="E1",
            study_design_zh="III期RCT",
            reasons=reasons + (["已被指南引用"] if in_guideline else []),
            in_guideline=in_guideline,
            guideline_ref=guideline_ref,
        )

    if in_guideline:
        reasons.append("已被指南引用→E1")
        # Keep a useful design label even when lifted by citation.
        design = _infer_design_label(types, text, fallback="指南引用研究")
        return EvidenceTierResult(
            tier="E1",
            study_design_zh=design,
            reasons=reasons,
            in_guideline=True,
            guideline_ref=guideline_ref,
        )

    # E2: pivotal / registrational single-arm phase I/II or II
    phase_ii = _has_any(types, "clinical trial, phase ii", "clinical trial, phase 2") or bool(
        re.search(r"\bphase\s*(ii|2|1b/?2|i/?ii|ib/?ii)\b", text, re.I)
    )
    phase_i = _has_any(types, "clinical trial, phase i", "clinical trial, phase 1")
    pivotalish = bool(_PIVOTAL_TRIAL_RE.search(text) or _SINGLE_ARM_RE.search(text))
    if phase_ii and pivotalish:
        reasons.append("单臂/注册性 II 期或 Ib/II")
        return EvidenceTierResult(
            tier="E2",
            study_design_zh="单臂II期注册研究",
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )
    if pivotalish and (phase_ii or phase_i or _has_any(types, "clinical trial")):
        reasons.append("已知注册试验名或 pivotal 表述")
        return EvidenceTierResult(
            tier="E2",
            study_design_zh="注册性临床试验",
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )

    # E4 before E3: retrospective / RWE must not be swallowed by "cohort" / observational.
    if _RWE_RE.search(text) or _has_any(types, "retrospective studies", "case-control studies"):
        reasons.append("真实世界/回顾性")
        design = (
            "多中心回顾性队列"
            if re.search(r"multicen|multi[- ]center|多中心", text, re.I)
            else "回顾性队列"
        )
        if re.search(r"real[- ]world", text, re.I):
            design = "真实世界研究"
        return EvidenceTierResult(
            tier="E4",
            study_design_zh=design,
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )

    # E3: prospective / exploratory phase II
    if phase_ii or (
        _has_any(types, "clinical trial", "controlled clinical trial")
        and not _has_any(types, "retrospective")
    ):
        reasons.append("前瞻性/探索性临床试验")
        return EvidenceTierResult(
            tier="E3",
            study_design_zh="前瞻性临床试验",
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )
    if _PROSPECTIVE_RE.search(text) and not _RWE_RE.search(text):
        reasons.append("前瞻队列/非随机")
        return EvidenceTierResult(
            tier="E3",
            study_design_zh="前瞻性队列",
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )
    if _has_any(types, "observational study", "prospective studies", "cohort studies"):
        reasons.append("观察性/队列 pub_type")
        return EvidenceTierResult(
            tier="E3",
            study_design_zh="观察性队列",
            reasons=reasons,
            in_guideline=False,
            guideline_ref=guideline_ref,
        )

    # Default: original research without clear design → soft E3
    reasons.append("未识别明确设计，默认探索性原研")
    return EvidenceTierResult(
        tier="E3",
        study_design_zh="原研研究",
        reasons=reasons,
        in_guideline=False,
        guideline_ref=guideline_ref,
    )


def _infer_design_label(types: str, text: str, *, fallback: str) -> str:
    if _has_any(types, "meta-analysis"):
        return "Meta分析"
    if _has_any(types, "systematic review"):
        return "系统综述"
    if _has_any(types, "randomized controlled trial") or re.search(
        r"\bphase\s*(iii|3)\b", text, re.I
    ):
        return "III期RCT"
    if _PIVOTAL_TRIAL_RE.search(text) or _SINGLE_ARM_RE.search(text):
        return "单臂II期注册研究"
    if _RWE_RE.search(text):
        return "真实世界研究"
    return fallback
