from __future__ import annotations

from backend.app.services.figure_crop import lookup_vlm_bbox, validate_bbox
from backend.app.services.multimodal_client import _split_answer_and_summary


def test_split_answer_parses_summary_and_bbox() -> None:
    content = (
        "## 结论\n进入 BCEL-3 流程 [S1]。\n"
        "===PAGE_SUMMARY_JSON===\n"
        '{"BCEL-2": {"summary": "初治评估后进入一线治疗", "bbox": [0.1, 0.2, 0.9, 0.85]}}'
    )
    answer, summaries, bboxes = _split_answer_and_summary(content)
    assert "BCEL-3" in answer
    assert summaries["BCEL-2"] == "初治评估后进入一线治疗"
    assert bboxes["BCEL-2"] == [0.1, 0.2, 0.9, 0.85]


def test_split_answer_supports_legacy_string_summary() -> None:
    content = (
        "## 结论\n测试。\n"
        "===PAGE_SUMMARY_JSON===\n"
        '{"BCEL-4": "旧格式摘要"}'
    )
    answer, summaries, bboxes = _split_answer_and_summary(content)
    assert answer.startswith("## 结论")
    assert summaries["BCEL-4"] == "旧格式摘要"
    assert bboxes == {}


def test_validate_bbox_rejects_invalid_coords() -> None:
    assert validate_bbox([0.2, 0.2, 0.8, 0.8]) == [0.2, 0.2, 0.8, 0.8]
    assert validate_bbox([0.8, 0.2, 0.2, 0.8]) is None
    assert validate_bbox([0.0, 0.0, 1.2, 1.0]) is None


def test_assess_vlm_bbox_quality_flags_full_page() -> None:
    from backend.app.services.figure_crop import assess_vlm_bbox_quality

    bbox = [0.01, 0.01, 0.99, 0.99]
    quality = assess_vlm_bbox_quality(bbox, {"A": bbox, "B": bbox}, max_area=0.8)
    assert quality == "full_page_like"


def test_assess_vlm_bbox_quality_flags_duplicated() -> None:
    from backend.app.services.figure_crop import assess_vlm_bbox_quality

    shared = [0.05, 0.15, 0.95, 0.85]
    quality = assess_vlm_bbox_quality(
        shared,
        {"BCEL-2": shared, "BCEL-3": shared},
        max_area=0.8,
        dedup_guard=True,
    )
    assert quality == "duplicated"


def test_assess_vlm_bbox_quality_flags_too_narrow() -> None:
    from backend.app.services.figure_crop import assess_vlm_bbox_quality

    deterministic = [0.03, 0.2, 0.97, 0.75]
    vlm = [0.08, 0.22, 0.92, 0.75]
    quality = assess_vlm_bbox_quality(
        vlm,
        {"BCEL-C 1 OF 7": vlm},
        deterministic_bbox=deterministic,
    )
    assert quality == "too_narrow"


def test_assess_vlm_bbox_quality_accepts_wide_vlm_when_no_deterministic() -> None:
    from backend.app.services.figure_crop import assess_vlm_bbox_quality

    vlm = [0.08, 0.22, 0.92, 0.75]
    quality = assess_vlm_bbox_quality(vlm, {"A": vlm})
    assert quality == "good"


def test_lookup_vlm_bbox_normalizes_page_code() -> None:
    bboxes = {"BCEL-2": [0.1, 0.1, 0.9, 0.9]}
    assert lookup_vlm_bbox("bcel-2", bboxes) == [0.1, 0.1, 0.9, 0.9]


def _load_pdf_renderer():
    import pytest

    from backend.app.settings import load_settings
    from backend.app.services.page_image import PageImageRenderer

    settings = load_settings()
    if not settings.pdf_path.exists():
        pytest.skip(f"PDF not available: {settings.pdf_path}")
    return PageImageRenderer(
        settings.pdf_path,
        settings.page_image_dir,
        dpi=settings.page_image_dpi,
    )


def test_detect_flowchart_bboxes_p64_compact_and_full() -> None:
    from backend.app.services.figure_crop import detect_flowchart_bboxes

    renderer = _load_pdf_renderer()
    page = renderer.get_page(64)
    assert page is not None

    compact, full, has_footnote = detect_flowchart_bboxes(page)
    assert compact is not None
    assert full is not None
    assert has_footnote is True
    assert 0.13 <= compact[1] <= 0.18
    assert 0.55 <= compact[3] <= 0.68
    assert full[3] > 0.85
    assert compact[3] < full[3]


def test_detect_flowchart_bboxes_p63_compact_and_full() -> None:
    from backend.app.services.figure_crop import detect_flowchart_bboxes

    renderer = _load_pdf_renderer()
    page = renderer.get_page(63)
    assert page is not None

    compact, full, has_footnote = detect_flowchart_bboxes(page)
    assert compact is not None
    assert full is not None
    assert has_footnote is True
    assert 0.15 <= compact[1] <= 0.22
    assert 0.60 <= compact[3] <= 0.75
    assert full[3] > 0.85


def test_detect_display_bboxes_p77_table_single_view() -> None:
    from backend.app.services.figure_crop import detect_display_bboxes_for_page

    renderer = _load_pdf_renderer()
    compact, full, method, has_footnote = detect_display_bboxes_for_page(renderer, 77)
    assert method == "table"
    assert has_footnote is False
    assert compact == full
    assert compact is not None
