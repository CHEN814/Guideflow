from __future__ import annotations

import re
from typing import Iterable

DISEASE_PATTERNS: list[tuple[str, str]] = [
    ("DLBCL/LBCL", r"BCEL|DISC-DLBCL|DLBCL"),
    ("HGBL/PMBL/转化", r"HGBL|PMBL|HTBCEL|DISC-HGBL|DISC-PMBL|HISTOLOGIC-TRANSFORMATION"),
    ("FL", r"FOLL|DISC-FL"),
    ("MCL", r"MANT|DISC-MCL|MCL"),
    ("MZL", r"MZL|EMZLG|EMZLNG|NMZL|SMZL|DISC-MZL"),
    ("Burkitt", r"BURK|DISC-BURKITT"),
    ("PTLD", r"PTLD|DISC-PTLD"),
    ("HIV", r"HIVLYM|DISC-HIV"),
    ("通用", r"DIAG|ST-|NHODG|BLAST|CAT-|ABBR|DISC-OVERVIEW"),
]


def flatten_gold_units(gold: list) -> list[str]:
    out: list[str] = []
    for item in gold or []:
        if isinstance(item, (list, tuple, set)):
            out.extend(str(x) for x in item)
        else:
            out.append(str(item))
    return out


def disease_from_units(units: Iterable[str], default: str = "其他") -> str:
    blob = " ".join(str(u) for u in units)
    for name, pat in DISEASE_PATTERNS:
        if re.search(pat, blob, re.I):
            return name
    return default


def unit_kind_from_units(units: Iterable[str]) -> str:
    kinds = set()
    for u in units:
        n = normalize_unit(str(u))
        rest = n.split(":", 1)[-1] if n else ""
        if rest.startswith("DISC-") or rest.startswith("DISC "):
            kinds.add("discussion")
        elif rest:
            kinds.add("flowchart")
    if not kinds:
        return "unknown"
    if kinds == {"discussion"}:
        return "discussion"
    if kinds == {"flowchart"}:
        return "flowchart"
    return "mixed"

_PAGE_PREFIX = re.compile(r"^PAGE[-_]", re.I)

MCQ_SUFFIX = (
    "\n\n以上为单选题。允许简要推理，但最后一行必须写成：\n最终答案: X\n"
    "其中 X 仅为 A、B、C、D 或 E 之一。"
)


def format_mcq(item: dict) -> str:
    lines = [item["question"].strip(), "", "选项："]
    for k in sorted(item["options"].keys()):
        lines.append(f"{k}. {item['options'][k]}")
    lines.append(MCQ_SUFFIX)
    return "\n".join(lines)


def parse_mcq_letter(text: str) -> tuple[str, str]:
    if not text:
        return "invalid", "invalid"
    m = list(re.finditer(r"最终答案\s*[:：*]*\s*([A-Ea-e])\b", text))
    if m:
        return m[-1].group(1).upper(), "1"
    idx = text.rfind("最终答案")
    if idx >= 0:
        tail = text[idx : idx + 80]
        m2 = re.search(r"(?:选项|答案)\s*[:：]?\s*([A-Ea-e])\b", tail)
        if m2:
            return m2.group(1).upper(), "1"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = []
    for ln in lines:
        if re.fullmatch(r"[A-Ea-e]", ln):
            hits.append(ln.upper())
        elif re.fullmatch(r"(?:答案|选项)\s*[:：]?\s*[A-Ea-e]", ln):
            hits.append(ln[-1].upper())
        else:
            m3 = re.fullmatch(r"(?:最终)?答案\s*[:：*]*\s*([A-Ea-e])\b.*", ln)
            if m3:
                hits.append(m3.group(1).upper())
    if hits:
        return hits[-1], "2"
    return "invalid", "invalid"


def normalize_unit(u: str) -> str:
    raw = (u or "").strip()
    if not raw:
        return ""
    if ":" in raw:
        src, rest = raw.split(":", 1)
    else:
        src, rest = "", raw
    src = src.strip().upper()
    rest = re.sub(r"\s+", " ", rest.strip())
    rest = _PAGE_PREFIX.sub("", rest)
    rest = rest.replace("_", " ")
    rest = re.sub(r"\s+", " ", rest).upper()
    if not rest:
        return ""
    return f"{src}:{rest}" if src else rest


def unit_from_source(src: dict, data_source: str) -> str:
    page = str(src.get("printed_page_code") or "").strip()
    if page and not page.lower().startswith("p."):
        return normalize_unit(f"{data_source}:{page}")
    sid = str(src.get("source_id") or "").strip()
    if sid:
        return normalize_unit(f"{data_source}:{sid}")
    cite = str(src.get("citation_label") or "").strip()
    if cite and not cite.lower().startswith("p."):
        return normalize_unit(f"{data_source}:{cite}")
    return ""


def uniq_units(xs: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        n = normalize_unit(x)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def cited_indices(answer: str) -> set[int]:
    found = set()
    for m in re.finditer(r"\[S(\d+)\]", answer or "", flags=re.I):
        found.add(int(m.group(1)))
    return found


def extract_page_codes(answer: str) -> list[str]:
    pats = [
        r"\b((?:BCEL|FOLL|MANT|BURK|DIAG|ST|NHODG|MZL|EMZL|NMZL|SMZL|PMBL|HGBL|HTBCEL|PTLD|HIVLYM|BLAST)[A-Z\-]*\s*\d+(?:\s+OF\s+\d+)?)",
        r"\b(MS-\d+)\b",
    ]
    found = []
    for pat in pats:
        for m in re.finditer(pat, answer or "", flags=re.I):
            found.append(normalize_unit(m.group(1)))
    return found


def expand_gold_groups(gold: list) -> list[set[str]]:
    """Gold may be a list of units or equivalence groups.

    ``["nccn:BURK-2", ["nccn:BURK-2", "nccn:BURK-A 1 OF 3"]]``
    A group is satisfied if any member matches.
    """
    groups: list[set[str]] = []
    for item in gold or []:
        if isinstance(item, (list, tuple, set)):
            groups.append({normalize_unit(x) for x in item if normalize_unit(x)})
        else:
            n = normalize_unit(str(item))
            if n:
                groups.append({n})
    return groups


def units_match(gold_unit: str, pred_unit: str) -> bool:
    g, p = normalize_unit(gold_unit), normalize_unit(pred_unit)
    if not g or not p:
        return False
    if g == p:
        return True
    g_suffix, p_suffix = g.split(":", 1)[-1], p.split(":", 1)[-1]
    if g_suffix and g_suffix == p_suffix:
        return True
    if g_suffix and (p_suffix.endswith(g_suffix) or g_suffix.endswith(p_suffix)):
        if min(len(g_suffix), len(p_suffix)) >= 6:
            return True
    return False


def match_gold_groups(gold: list, pred_units: list[str]) -> set[str]:
    """Return canonical gold keys that were hit (first member of each group)."""
    pred = [normalize_unit(p) for p in pred_units if normalize_unit(p)]
    hit: set[str] = set()
    for group in expand_gold_groups(gold):
        if not group:
            continue
        canon = sorted(group)[0]
        ok = False
        for g in group:
            if any(units_match(g, p) for p in pred):
                ok = True
                break
        if ok:
            hit.add(canon)
    return hit


def match_gold(gold: list[str], pred_units: list[str]) -> set[str]:
    return match_gold_groups(gold, pred_units)


def gold_size(gold: list) -> int:
    return len([g for g in expand_gold_groups(gold) if g])


def negative_label(answer: str) -> str:
    text = answer or ""
    refuse = bool(
        re.search(r"未覆盖|未提及|没有给出|无法给出|不能编造|拒绝编造|超出指南|指南未", text)
    )
    halluc_cite = bool(re.search(r"BCEL-\d+|FOLL-|MANT-|\[S\d+\]", text)) and not refuse
    dose = bool(re.search(r"\d+\s*mg", text, flags=re.I))
    if refuse and not dose:
        return "拒绝"
    if dose and not refuse:
        return "过度"
    if halluc_cite:
        return "幻觉"
    if refuse:
        return "拒绝"
    return "过度"


_CITE_MARK = re.compile(r"\[S\d+\]", re.I)
_GENERIC_MARK = re.compile(r"通用知识")


def split_answer_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？.!?])\s+", text or "")
    out = []
    for part in parts:
        sent = part.strip()
        if not sent:
            continue
        if re.match(r"^最终答案\s*[:：]", sent):
            continue
        out.append(sent)
    return out


def sentence_label_stats(text: str) -> dict:
    sents = split_answer_sentences(text)
    n = len(sents)
    if not n:
        return {
            "n_sents": 0,
            "generic_n": 0,
            "cited_n": 0,
            "unlabeled_n": 0,
            "generic_rate": None,
            "unlabeled_rate": None,
        }
    generic = cited = unlabeled = 0
    for sent in sents:
        has_cite = bool(_CITE_MARK.search(sent))
        has_generic = bool(_GENERIC_MARK.search(sent))
        if has_generic:
            generic += 1
        if has_cite:
            cited += 1
        if not has_cite and not has_generic:
            unlabeled += 1
    return {
        "n_sents": n,
        "generic_n": generic,
        "cited_n": cited,
        "unlabeled_n": unlabeled,
        "generic_rate": round(generic / n, 4),
        "unlabeled_rate": round(unlabeled / n, 4),
    }


def conclusion_label(item: dict, answer: str) -> str:
    if item.get("negative"):
        lab = negative_label(answer)
        return {"拒绝": "支持", "幻觉": "不支持", "过度": "不支持"}.get(lab, "部分支持")
    expected = item.get("expected_conclusion") or ""
    keys = [w for w in re.split(r"[，。；、/（）()\s]+", expected) if len(w) >= 2]
    if not answer:
        return "不支持"
    hits = sum(1 for w in keys if w.lower() in answer.lower())
    if hits >= max(2, len(keys) // 3):
        return "支持"
    if hits >= 1:
        return "部分支持"
    return "不支持"


def retrieval_units_from_payload(payload: dict, data_source: str) -> dict[str, list[str]]:
    """Prefer trace stages; fall back to final sources."""
    from experiments.scripts.common.traces import units_from_trace_hits

    stages = {}
    trace_path = payload.get("trace_path")
    if trace_path:
        stages = units_from_trace_hits(trace_path, data_source)
    sources = payload.get("sources") or []
    cited = []
    for i in sorted(cited_indices(payload.get("answer_markdown") or "")):
        if 1 <= i <= len(sources):
            u = unit_from_source(sources[i - 1], data_source)
            if u:
                cited.append(u)
    for code in extract_page_codes(payload.get("answer_markdown") or ""):
        cited.append(f"{data_source}:{code}")
    if "final" not in stages:
        stages["final"] = uniq_units(unit_from_source(s, data_source) for s in sources)
    stages["cited"] = uniq_units(cited)
    return stages
