from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.services.case_extractor import CaseExtractor, summarize_structured_case
from backend.app.settings import load_settings, settings_for_source

router = APIRouter(prefix="/api/cases", tags=["cases"])


class CaseAnalyzeIn(BaseModel):
    case_text: str = Field(default="", max_length=60000)
    question: str = Field(default="请结合指南分析该病例的诊疗路径和下一步建议。", max_length=1000)
    data_source: str = "csco"

    @model_validator(mode="after")
    def _clean(self):
        self.case_text = (self.case_text or "").strip()
        self.question = (self.question or "").strip() or "请结合指南分析该病例的诊疗路径和下一步建议。"
        self.data_source = (self.data_source or "csco").strip().lower()
        return self


class CaseAnalyzeOut(BaseModel):
    case_summary: str
    structured_case: dict[str, Any]
    answer_markdown: str
    data_source: str
    qa_payload: dict[str, Any]


@router.post("/analyze", response_model=CaseAnalyzeOut)
def analyze_case(body: CaseAnalyzeIn, db: Session = Depends(get_db)) -> CaseAnalyzeOut:
    if len(body.case_text) < 20:
        raise HTTPException(status_code=400, detail="case_text is too short")

    base_settings = load_settings()
    source_key = body.data_source if body.data_source in ("nccn", "csco") else "csco"
    source_settings = settings_for_source(source_key, base_settings)
    extractor = CaseExtractor(source_settings)
    structured = extractor.extract(body.case_text)
    summary = summarize_structured_case(structured)

    # Import here to avoid expensive QA initialization when only importing routes.
    from backend.app.services.qa import QAService

    service = QAService(source_settings)
    enhanced_question = (
        "以下是结构化病例摘要，请结合所选指南证据回答医生问题。\n\n"
        f"【结构化病例摘要】\n{summary}\n\n"
        f"【医生问题】\n{body.question}\n\n"
        "请先说明病例关键信息和风险因素，再给出指南匹配的治疗路径建议；"
        "对病历缺失或不确定的信息必须明确列出，不要编造。"
    )
    result = service.ask(enhanced_question, history=[], trace_enabled=True)
    payload = result.to_web_payload()

    return CaseAnalyzeOut(
        case_summary=summary,
        structured_case=structured,
        answer_markdown=str(payload.get("answer_markdown") or ""),
        data_source=source_key,
        qa_payload=payload,
    )
