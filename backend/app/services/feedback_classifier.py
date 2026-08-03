"""Rule-based doctor feedback classification (keyword match, priority ordered)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# Stable keys for storage / API (Chinese labels for UI).
CATEGORY_LABELS: dict[str, str] = {
    "correctness": "正确性问题",
    "evidence": "证据不足 / 漏证据",
    "retrieval": "召回问题",
    "expression": "表达问题",
    "safety": "安全性 / 风险提示问题",
    "ux": "交互体验问题",
    "positive": "肯定反馈",
    "other": "其他",
}

# Higher priority first when picking primary.
CATEGORY_PRIORITY: Sequence[str] = (
    "correctness",
    "evidence",
    "retrieval",
    "safety",
    "expression",
    "ux",
    "positive",
    "other",
)

# Keyword rules (substring match on lowercased comment + optional doctor category text).
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "correctness",
        (
            "错误",
            "不对",
            "结论有误",
            "方案不对",
            "推荐不对",
            "推荐不准确",
            "版本过旧",
            "过时",
            "指南里不是",
            "不是这样",
            "事实错误",
            "不准确",
            "答错",
        ),
    ),
    (
        "evidence",
        (
            "证据不足",
            "依据不够",
            "缺少引用",
            "没有引用",
            "缺少证据",
            "没有说明来源",
            "来源不足",
            "需要补充证据",
            "缺少关键",
            "没有引用关键",
            "补上证据",
            "明确引用",
        ),
    ),
    (
        "retrieval",
        (
            "没找到",
            "漏检",
            "召回差",
            "检索不准",
            "检索不到",
            "没有检索到",
            "找不到",
            "漏掉",
            "检索结果不相关",
            "召回不全",
            "图谱/检索",
        ),
    ),
    (
        "safety",
        (
            "风险",
            "禁忌",
            "不安全",
            "需要谨慎",
            "边界",
            "副作用",
            "毒性",
            "特殊人群",
            "风险提示",
            "没有提示",
            "禁忌证",
        ),
    ),
    (
        "expression",
        (
            "太长",
            "太短",
            "啰嗦",
            "不清楚",
            "结构混乱",
            "结构不清",
            "不够简洁",
            "更简洁",
            "表达",
            "格式",
            "逻辑乱",
            "结构不好",
        ),
    ),
    (
        "ux",
        (
            "卡顿",
            "太慢",
            "不方便",
            "页面问题",
            "操作复杂",
            "加载慢",
            "手机端",
            "体验",
            "跳转",
            "界面",
            "难用",
        ),
    ),
    (
        "positive",
        (
            "准确",
            "有帮助",
            "很好",
            "方便",
            "清晰",
            "好用",
            "不错",
            "满意",
            "便于查阅",
            "逻辑清楚",
            "赞",
            "靠谱",
        ),
    ),
]


@dataclass(frozen=True)
class ClassificationResult:
    primary: str
    tags: list[str]


def normalize_category_key(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if v in CATEGORY_LABELS:
        return v
    for key, label in CATEGORY_LABELS.items():
        if v == label or v in label or label in v:
            return key
    return None


def classify_feedback(
    comment: str,
    *,
    doctor_category: str | None = None,
    rating: int | None = None,
    helpful: str | None = None,
) -> ClassificationResult:
    """
    Classify free-text feedback into one primary + multi tags.
    Priority: doctor pick (if valid) as primary when present; keywords fill tags.
    """
    text = (comment or "").strip().lower()
    matched: list[str] = []
    for key, keywords in _KEYWORD_RULES:
        if any(k.lower() in text for k in keywords):
            matched.append(key)

    doctor_key = normalize_category_key(doctor_category)
    tags: list[str] = []
    if doctor_key and doctor_key != "other":
        tags.append(doctor_key)
    for key in CATEGORY_PRIORITY:
        if key in matched and key not in tags:
            tags.append(key)

    if not tags:
        if helpful == "yes" or (rating is not None and rating >= 4):
            tags = ["positive"]
        elif helpful == "no" or (rating is not None and rating <= 2):
            tags = ["other"]
        else:
            tags = ["other"]

    primary = tags[0]
    # Re-order tags by clinical priority while keeping primary first.
    rest = [k for k in CATEGORY_PRIORITY if k in tags and k != primary]
    ordered = [primary] + rest
    return ClassificationResult(primary=primary, tags=ordered)


def label_for(key: str) -> str:
    return CATEGORY_LABELS.get(key, CATEGORY_LABELS["other"])


def labels_for(keys: Iterable[str]) -> list[str]:
    return [label_for(k) for k in keys]
