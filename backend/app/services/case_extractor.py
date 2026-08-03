from __future__ import annotations

import json
import re
from typing import Any

import requests

from backend.app.settings import Settings


CASE_EXTRACT_SYSTEM = """你是血液肿瘤专科病例结构化助手。请只依据用户提供的病历文本抽取信息，不要编造。
输出必须是严格 JSON 对象，不要 Markdown，不要解释。
字段缺失用 null；不确定用 "unknown"；涉及原文关键证据可保留简短中文短语。

JSON schema:
{
  "patient": {"age": null, "sex": null},
  "diagnosis": {"disease": null, "subtype": null, "stage": null, "risk": null, "ipi": null, "aa_ipi": null, "ldh": null, "ecog": null},
  "pathology": {"ihc": {}, "fish": {}, "molecular": {}},
  "treatment_history": [{"line": null, "regimen": null, "cycles": null, "response": null, "date": null}],
  "current_status": {"relapsed_refractory": null, "transplant_candidate": null, "car_t_candidate": null, "main_problem": null},
  "missing_information": []
}
"""


class CaseExtractor:
    def __init__(self, settings: Settings):
        self.api_key = settings.qwen_api_key
        self.base_url = settings.qwen_base_url.rstrip("/")
        self.model = settings.qwen_model

    def extract(self, case_text: str) -> dict[str, Any]:
        text = (case_text or "").strip()
        if not text:
            return self._empty_case()
        if not self.api_key:
            return self._heuristic_extract(text)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CASE_EXTRACT_SYSTEM},
                {"role": "user", "content": text[:16000]},
            ],
            "temperature": 0.0,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=80,
            )
            resp.raise_for_status()
            content = str(resp.json()["choices"][0]["message"].get("content") or "")
            parsed = self._parse_json(content)
            return self._merge_defaults(parsed) if parsed else self._heuristic_extract(text)
        except (requests.RequestException, KeyError, ValueError, TypeError):
            return self._heuristic_extract(text)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any] | None:
        match = re.search(r"\{.*\}", content or "", re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _heuristic_extract(self, text: str) -> dict[str, Any]:
        case = self._empty_case()
        age = re.search(r"(\d{1,3})\s*岁", text)
        if age:
            case["patient"]["age"] = int(age.group(1))
        if "男" in text[:1500]:
            case["patient"]["sex"] = "男"
        elif "女" in text[:1500]:
            case["patient"]["sex"] = "女"
        lower = text.lower()
        if "dlbcl" in lower or "弥漫大b" in lower or "弥漫大 b" in lower:
            case["diagnosis"]["disease"] = "DLBCL"
        if "non-gcb" in lower or "非gcb" in lower:
            case["diagnosis"]["subtype"] = "non-GCB"
        stage = re.search(r"([ⅠⅡⅢⅣIVX]+)\s*期", text, re.I)
        if stage:
            case["diagnosis"]["stage"] = stage.group(1).upper()
        aaipi = re.search(r"aa\s*ipi[^0-9]*(\d+)", text, re.I)
        if aaipi:
            case["diagnosis"]["aa_ipi"] = int(aaipi.group(1))
        if "ldh" in lower:
            case["diagnosis"]["ldh"] = "mentioned"
        if "tp53" in lower:
            case["pathology"]["molecular"]["TP53"] = "mentioned"
        for marker in ["CD20", "CD10", "BCL6", "MUM1", "BCL2", "C-MYC", "MYC", "Ki-67", "EBER"]:
            if marker.lower() in lower:
                case["pathology"]["ihc"][marker] = "mentioned"
        regimens = []
        for name in ["R-CHOP", "Pola-R-CHP", "R-EPOCH", "CAR-T", "自体", "移植"]:
            if name.lower() in lower:
                regimens.append({"line": None, "regimen": name, "cycles": None, "response": None, "date": None})
        case["treatment_history"] = regimens
        missing = ["近期疗效评价", "ECOG", "完整 IPI", "肝肾功能", "移植/CAR-T 适应性"]
        case["missing_information"] = missing
        return case

    @classmethod
    def _merge_defaults(cls, parsed: dict[str, Any]) -> dict[str, Any]:
        base = cls._empty_case()
        for key, value in parsed.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key].update(value)
            elif key in base:
                base[key] = value
        return base

    @staticmethod
    def _empty_case() -> dict[str, Any]:
        return {
            "patient": {"age": None, "sex": None},
            "diagnosis": {"disease": None, "subtype": None, "stage": None, "risk": None, "ipi": None, "aa_ipi": None, "ldh": None, "ecog": None},
            "pathology": {"ihc": {}, "fish": {}, "molecular": {}},
            "treatment_history": [],
            "current_status": {"relapsed_refractory": None, "transplant_candidate": None, "car_t_candidate": None, "main_problem": None},
            "missing_information": [],
        }


def summarize_structured_case(case: dict[str, Any]) -> str:
    patient = case.get("patient") or {}
    diagnosis = case.get("diagnosis") or {}
    pathology = case.get("pathology") or {}
    current = case.get("current_status") or {}
    treatments = case.get("treatment_history") or []
    missing = case.get("missing_information") or []
    lines = [
        f"患者：{patient.get('age') or '年龄未知'}岁，{patient.get('sex') or '性别未知'}。",
        f"诊断：{diagnosis.get('disease') or '未知'}；亚型：{diagnosis.get('subtype') or '未知'}；分期：{diagnosis.get('stage') or '未知'}；风险：{diagnosis.get('risk') or '未知'}；IPI：{diagnosis.get('ipi') or '未知'}；aaIPI：{diagnosis.get('aa_ipi') or '未知'}；LDH：{diagnosis.get('ldh') or '未知'}；ECOG：{diagnosis.get('ecog') or '未知'}。",
        f"病理/IHC：{json.dumps((pathology.get('ihc') or {}), ensure_ascii=False)}",
        f"FISH/分子：FISH={json.dumps((pathology.get('fish') or {}), ensure_ascii=False)}；分子={json.dumps((pathology.get('molecular') or {}), ensure_ascii=False)}",
        "治疗经过：" + ("；".join(json.dumps(t, ensure_ascii=False) for t in treatments) if treatments else "未知"),
        f"当前状态：{json.dumps(current, ensure_ascii=False)}",
        "缺失信息：" + ("；".join(str(x) for x in missing) if missing else "未明确"),
    ]
    return "\n".join(lines)
