from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models_db import MolecularEvidenceCacheEntry, MolecularEvidenceQueryLog
from backend.app.services.molecular_evidence import MolecularEvidenceService

ProviderMode = Literal["mock", "live", "hybrid"]

router = APIRouter(prefix="/api/molecular-evidence", tags=["molecular-evidence"])


class MolecularEvidenceQueryIn(BaseModel):
    variants_text: str = Field(..., min_length=1, max_length=8000)
    disease: str = Field(default="DLBCL", max_length=200)
    sample_type: str = Field(default="tumor tissue", max_length=200)
    genome_build: Optional[str] = Field(default=None, max_length=20)
    transcript: Optional[str] = Field(default=None, max_length=80)
    variant_type: Optional[str] = Field(default=None, max_length=80)
    question: Optional[str] = Field(default=None, max_length=1000)
    provider_mode: ProviderMode = Field(default="live")

    @field_validator("variants_text", "disease", "sample_type", "genome_build", "transcript", "variant_type", "question", mode="before")
    @classmethod
    def _strip_strings(cls, value):
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None
        return value

    @model_validator(mode="after")
    def _normalize(self):
        self.genome_build = self.genome_build or None
        self.transcript = self.transcript or None
        self.variant_type = self.variant_type or None
        self.question = self.question or None
        return self


def _json_list(raw: str) -> list[Any]:
    import json

    try:
        parsed = json.loads(raw or "[]")
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


@router.post("/query")
def query_molecular_evidence(body: MolecularEvidenceQueryIn) -> dict:
    service = MolecularEvidenceService(provider_mode=body.provider_mode)
    result = service.query(
        text=body.variants_text,
        disease=body.disease,
        sample_type=body.sample_type,
        genome_build=body.genome_build,
        transcript=body.transcript,
        variant_type=body.variant_type,
        question=body.question,
    )
    return result.to_dict()


@router.get("/logs")
def list_molecular_evidence_logs(
    limit: int = 20,
    offset: int = 0,
    cache_hit: Optional[bool] = None,
    provider_mode: Optional[str] = None,
    q: str = "",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    query = db.query(MolecularEvidenceQueryLog)
    if provider_mode:
        query = query.filter(MolecularEvidenceQueryLog.provider_mode == provider_mode)
    if cache_hit is not None:
        query = query.filter(MolecularEvidenceQueryLog.cache_hit.is_(bool(cache_hit)))
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            (MolecularEvidenceQueryLog.input_json.like(like))
            | (MolecularEvidenceQueryLog.answer_markdown.like(like))
            | (MolecularEvidenceQueryLog.query_key.like(like))
        )
    total = int(query.count())
    rows = query.order_by(desc(MolecularEvidenceQueryLog.retrieved_at)).offset(safe_offset).limit(safe_limit).all()
    items = [
        {
            "id": row.id,
            "query_key": row.query_key,
            "provider_mode": row.provider_mode,
            "cache_hit": row.cache_hit,
            "cache_source_log_id": row.cache_source_log_id,
            "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
            "input_json": row.input_json,
            "normalized": _json_list(row.normalized_json),
            "raw_records": _json_list(row.raw_records_json),
            "evidence_cards": _json_list(row.evidence_cards_json),
            "safety_results": _json_list(row.safety_results_json),
            "answer_markdown": row.answer_markdown,
        }
        for row in rows
    ]
    return {"total": total, "items": items}


@router.get("/cache")
def list_molecular_evidence_cache(
    limit: int = 20,
    offset: int = 0,
    provider_mode: Optional[str] = None,
    q: str = "",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    query = db.query(MolecularEvidenceCacheEntry)
    if provider_mode:
        query = query.filter(MolecularEvidenceCacheEntry.provider_mode == provider_mode)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            (MolecularEvidenceCacheEntry.query_key.like(like))
            | (MolecularEvidenceCacheEntry.payload_json.like(like))
        )
    total = int(query.count())
    rows = query.order_by(MolecularEvidenceCacheEntry.retrieved_at.desc()).offset(safe_offset).limit(safe_limit).all()
    items = [
        {
            "id": row.id,
            "query_key": row.query_key,
            "provider_mode": row.provider_mode,
            "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "payload": row.payload_json,
        }
        for row in rows
    ]
    return {"total": total, "items": items}
