from __future__ import annotations

import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models_db import MolecularEvidenceCacheEntry, MolecularEvidenceQueryLog
from backend.app.services.molecular_evidence import MolecularEvidenceService

ProviderMode = Literal["mock", "live", "hybrid"]

router = APIRouter(prefix="/api/molecular-evidence", tags=["molecular-evidence"])


class MolecularEvidenceQueryIn(BaseModel):
    variants_text: str = Field(..., min_length=1, max_length=50000)
    disease: str = Field(default="DLBCL", max_length=200)
    sample_type: str = Field(default="tumor tissue", max_length=200)
    genome_build: Optional[str] = Field(default=None, max_length=20)
    transcript: Optional[str] = Field(default=None, max_length=80)
    variant_type: Optional[str] = Field(default=None, max_length=80)
    question: Optional[str] = Field(default=None, max_length=50000)
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


def _extract_report_fields(text: str) -> dict[str, Any]:
    """Extract report metadata as reviewable hints, never as clinical conclusions."""
    value = text or ""
    vaf_matches = re.findall(r"(?:VAF|变异频率|等位基因频率)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*%", value, re.IGNORECASE)
    depth_matches = re.findall(r"(?:深度|depth|DP|读段深度)\s*[:：=]?\s*(\d+[,.]?\d*)\s*[×x]?", value, re.IGNORECASE)
    transcript_matches = sorted(set(re.findall(r"\bNM_\d+(?:\.\d+)?\b", value, re.IGNORECASE)))
    build_matches = sorted(set(re.findall(r"\bGRCh(?:37|38)\b|hg(?:19|38)", value, re.IGNORECASE)))
    chromosome_matches = sorted(set(re.findall(r"\bchr(?:X|Y|\d{1,2}):g\.[A-Za-z0-9._>+-]+", value, re.IGNORECASE)))
    return {
        "vaf_percent": vaf_matches,
        "depth": depth_matches,
        "transcripts": transcript_matches,
        "genome_builds": build_matches,
        "genomic_coordinates": chromosome_matches,
        "has_sample_context": bool(re.search(r"肿瘤组织|骨髓|外周血|cfDNA|tumor tissue|bone marrow|peripheral blood", value, re.IGNORECASE)),
        "review_note": "以下内容仅为 OCR/文字规则提取结果，请医生逐项对照原始报告确认；OCR 不能替代人工核对。",
    }


@router.post("/extract")
def extract_molecular_information(body: MolecularEvidenceQueryIn) -> dict[str, Any]:
    """Extract report-like molecular fields without running evidence retrieval."""
    service = MolecularEvidenceService(provider_mode="mock")
    variants = service.parser.parse(
        body.variants_text,
        disease=body.disease,
        sample_type=body.sample_type,
        genome_build=body.genome_build,
        transcript=body.transcript,
        variant_type=body.variant_type,
    )
    return {
        "text": body.variants_text,
        "variants": [variant.to_dict() for variant in variants],
        "field_hints": {
            "disease": body.disease,
            "sample_type": body.sample_type,
            "genome_build": body.genome_build,
            "transcript": body.transcript,
            "variant_type": body.variant_type,
        },
        "next_step": "请核对识别出的基因、变异写法、转录本和参考基因组版本，再点击开始分析。",
    }


def _extract_ocr_lines(value: Any) -> list[str]:
    """Extract recognized text lines from RapidOCR/PaddleOCR result shapes.

    Handles RapidOCR v1 (list of [box, text, score]), RapidOCR v2 / PaddleOCR
    DTO objects (``.txts`` or ``.json()``), and plain dicts with text lists.
    """
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) and hasattr(value, "json") and callable(value.json):
        try:
            return _extract_ocr_lines(value.json())
        except Exception:
            return []
    txts = getattr(value, "txts", None)
    if isinstance(txts, (list, tuple)):
        return [str(item).strip() for item in txts if str(item).strip()]
    if isinstance(value, dict):
        for key in ("rec_texts", "texts", "txts", "result", "data"):
            candidate = value.get(key)
            if candidate is not None:
                lines = _extract_ocr_lines(candidate)
                if lines:
                    return lines
        return []
    if isinstance(value, (list, tuple)):
        lines: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                lines.append(item.strip())
            elif isinstance(item, (list, tuple)):
                if len(item) >= 2 and isinstance(item[1], str) and item[1].strip():
                    lines.append(item[1].strip())
                else:
                    lines.extend(_extract_ocr_lines(item))
        return lines
    return []


def _dedupe_ocr_lines(lines: list[str]) -> str:
    return "\n".join(dict.fromkeys(line for line in lines if line and line.strip())).strip()


def _ocr_with_rapidocr(images: list[Any]) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        raise RuntimeError(f"无法初始化 RapidOCR：{type(exc).__name__}: {exc}") from exc
    try:
        engine = RapidOCR()
        lines: list[str] = []
        for image in images:
            result = engine(image)
            if isinstance(result, tuple):
                result = result[0]
            lines.extend(_extract_ocr_lines(result))
        return _dedupe_ocr_lines(lines)
    except Exception as exc:
        raise RuntimeError(f"RapidOCR 识别失败：{type(exc).__name__}: {exc}") from exc


def _ocr_with_paddle(images: list[Any]) -> str:
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise RuntimeError(f"无法初始化 PaddleOCR：{type(exc).__name__}: {exc}") from exc
    try:
        ocr = PaddleOCR(
            lang="ch",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            show_log=False,
        )
        lines: list[str] = []
        for image in images:
            result = ocr.predict(image)
            if isinstance(result, (list, tuple)):
                result = result[0] if result else None
            lines.extend(_extract_ocr_lines(result))
        return _dedupe_ocr_lines(lines)
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR 识别失败：{type(exc).__name__}: {exc}") from exc


def _ocr_with_tesseract(image: Any) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("缺少 pytesseract。") from exc
    try:
        return pytesseract.image_to_string(image, lang="chi_sim+eng").strip()
    except Exception as exc:
        raise RuntimeError(f"Tesseract OCR 识别失败：{type(exc).__name__}: {exc}") from exc


def _ocr_pdf_text(data: bytes) -> str:
    import fitz

    document = fitz.open(stream=data, filetype="pdf")
    try:
        parts = []
        for page in document[:5]:
            text = page.get_text("text") or ""
            if text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    finally:
        document.close()


def _pdf_pages_to_images(data: bytes, max_pages: int = 5) -> list[Any]:
    import numpy as np
    import fitz

    document = fitz.open(stream=data, filetype="pdf")
    try:
        images = []
        for page in document[:max_pages]:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            images.append(np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n))
        return images
    finally:
        document.close()


@router.post("/ocr")
def ocr_molecular_report(file: UploadFile = File(...)) -> dict[str, Any]:
    """OCR an uploaded sequencing report image/PDF and return extracted text only.

    OCR is intentionally separated from evidence retrieval so a doctor can
    inspect and correct the extracted text before it is used for interpretation.
    """
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/bmp", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="请上传 PNG、JPG、WEBP、BMP 图片或 PDF 报告。")
    data = file.file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="报告文件不能超过 15 MB。")
    try:
        from io import BytesIO
        import numpy as np
        from PIL import Image
    except ImportError:
        return {
            "status": "unavailable",
            "text": "",
            "filename": file.filename,
            "message": "当前环境未安装图像处理依赖。请安装 Pillow 和 numpy，也可以直接粘贴报告文字。",
            "next_step": "安装依赖后重新上传，或将报告中的文字粘贴到文本框并点击提取关键信息。",
        }

    is_pdf = file.content_type == "application/pdf"
    extracted = ""
    errors: list[str] = []
    try:
        if is_pdf:
            text = _ocr_pdf_text(data)
            if len(text.strip()) >= 20:
                extracted = text.strip()
            else:
                images = _pdf_pages_to_images(data)
                for engine in (_ocr_with_rapidocr, _ocr_with_paddle):
                    try:
                        extracted = engine(images)
                        if extracted:
                            break
                    except Exception as exc:
                        errors.append(str(exc))
        else:
            image = Image.open(BytesIO(data)).convert("RGB")
            images = [np.asarray(image)]
            try:
                extracted = _ocr_with_rapidocr(images)
            except Exception as exc:
                errors.append(str(exc))
                try:
                    extracted = _ocr_with_paddle(images)
                except Exception as exc2:
                    errors.append(str(exc2))
                    try:
                        extracted = _ocr_with_tesseract(image)
                    except Exception as exc3:
                        errors.append(str(exc3))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"报告 OCR 失败：{type(exc).__name__}: {exc}。请尝试直接粘贴报告文字。") from exc

    if not extracted.strip():
        reason = "；".join(dict.fromkeys(errors)) or "当前环境无法执行 OCR。"
        return {
            "status": "unavailable",
            "text": "",
            "filename": file.filename,
            "message": f"OCR 解析失败：{reason} 请直接粘贴报告文字，或在服务器上安装 RapidOCR / PaddlePaddle / Tesseract。",
            "next_step": "请直接粘贴报告文字到输入框，再点击发送。",
        }
    return {
        "status": "ok",
        "filename": file.filename,
        "text": extracted,
        "message": "OCR 已完成。请检查并修正基因、变异、转录本、VAF、深度与参考基因组版本后再进行证据查询。",
    }


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
