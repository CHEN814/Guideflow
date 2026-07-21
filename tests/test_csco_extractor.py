"""CSCO extractor / table helpers (unit tests, no full PDF required)."""
from __future__ import annotations

from backend.app.services.csco_extractor import (
    EVIDENCE_CATEGORIES,
    RECOMMENDATION_LEVELS,
    evidence_legend_prompt_block,
    resolve_chapter_id,
)
from backend.app.services.csco_table_extractor import (
    rows_to_markdown,
    _merge_continuation_rows,
    _normalize_regimen_glossary,
)
from backend.app.services.disease_scope import detect_disease_scope, parse_source_scope


def test_evidence_legend_constants():
    assert "1A" in EVIDENCE_CATEGORIES
    assert "I" in RECOMMENDATION_LEVELS
    block = evidence_legend_prompt_block()
    assert "1A" in block and "I级" in block


def test_resolve_chapter_id():
    assert resolve_chapter_id("弥漫大B细胞淋巴瘤")[0] == "dlbcl"
    assert resolve_chapter_id("原发睾丸弥漫大B细胞淋巴瘤")[0] == "primary-testicular-dlbcl"
    assert resolve_chapter_id("结外NK/T 细胞淋巴瘤")[0] == "nktcl"


def test_merge_continuation_rows():
    rows = [
        ["分期", "I级推荐", "II级推荐"],
        ["IE期", "R-CHOP", "CNS预防"],
        ["", "对侧放疗", "鞘注"],
    ]
    merged = _merge_continuation_rows(rows)
    assert len(merged) == 2
    assert "对侧放疗" in merged[1][1]
    assert "鞘注" in merged[1][2]


def test_rows_to_markdown():
    md = rows_to_markdown(
        [
            ["分期", "I级推荐", "II级推荐"],
            ["IE/IIE期", "R-CHOP[2A类]", "CNS预防[2B类]"],
        ]
    )
    assert "| 分期 |" in md
    assert "R-CHOP" in md
    assert "---" in md


def test_normalize_second_line_regimen_glossary():
    """Centered title + left regimens + right margin chrome → 方案|组成."""
    raw = [
        ["", "二线治疗方案", ""],
        ["[R-DHAP]利妥昔单抗+顺铂+阿糖胞苷+地塞米松", "", ""],
        ["[R-ICE]利妥昔单抗+异环磷酰胺+卡铂+依托泊苷", "", ""],
        ["[R-GDP]利妥昔单抗+吉西他滨+顺铂+地塞米松", "", ""],
        ["[R2]利妥昔单抗+来那度胺", "", ""],
        ["[Pola-BR]利妥昔单抗+维泊妥珠单抗+苯达莫司汀", "", ""],
        ["[BR]利妥昔单抗+苯达莫司汀", "", ""],
        ["[Glofit+GemOx]格菲妥单抗+吉西他滨+奥沙利铂", "", ""],
        ["[Tafa-Len]坦昔妥单抗+来那度胺", "", "弥漫大B细胞淋巴瘤"],
        ["", "", "37"],
    ]
    title, grid = _normalize_regimen_glossary(raw)
    assert title == "二线治疗方案"
    assert grid[0] == ["方案", "组成"]
    assert grid[1] == ["[R-DHAP]", "利妥昔单抗+顺铂+阿糖胞苷+地塞米松"]
    assert grid[-1] == ["[Tafa-Len]", "坦昔妥单抗+来那度胺"]
    assert len(grid) == 9  # header + 8 regimens

    md = rows_to_markdown(raw, title="弥漫大B细胞淋巴瘤 DLBCL")
    assert "二线治疗方案" in md
    assert "| [R-DHAP] | 利妥昔单抗+顺铂+阿糖胞苷+地塞米松 |" in md
    assert "| [Tafa-Len] | 坦昔妥单抗+来那度胺 |" in md
    assert "弥漫大B细胞淋巴瘤 37" not in md
    assert md.count("| --- |") == 1


def test_csco_disease_scope_detection():
    scope = detect_disease_scope("原发睾丸弥漫大B一线治疗", source="csco")
    assert scope.key == "primary-testicular-dlbcl"
    assert "primary-testicular-dlbcl" in scope.article_ids
    assert "general" in scope.article_ids  # common chapters merged


def test_parse_hyphenated_article_source_id():
    article, module = parse_source_scope("disc-primary-testicular-dlbcl-p94-c0")
    assert article == "primary-testicular-dlbcl"
    assert module is None
    article2, _ = parse_source_scope("ref-primary-testicular-dlbcl-12")
    assert article2 == "primary-testicular-dlbcl"
