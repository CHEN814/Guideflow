"""Build Part 2 v2: tag disease, move negatives, add drafted non-DLBCL items."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from common.paths import DATASETS, ensure_sys_path

ensure_sys_path()
from common.io import load_json, save_json

MOD = [
    ("DLBCL/LBCL", r"BCEL|DLBCL|PMBL|HGBL|HTBCEL"),
    ("FL", r"FOLL|-FL-"),
    ("MCL", r"MANT|MCL"),
    ("MZL", r"MZL|EMZL|NMZL|SMZL"),
    ("Burkitt", r"BURK"),
    ("PTLD", r"PTLD"),
    ("HIV", r"HIVLYM|HIV"),
    ("通用", r"DIAG|ST-|NHODG|GENERAL|EVIDENCE|ABBR"),
]


def infer_disease(item: dict) -> str:
    if item.get("disease"):
        return item["disease"]
    blob = " ".join(map(str, (item.get("G") or []) + (item.get("G_opt") or []) + [item.get("topic") or ""]))
    for name, pat in MOD:
        if re.search(pat, blob, re.I):
            return name
    return "其他"


DRAFTS = [
    {"id": "P2-N17", "disease": "FL", "G": ["nccn:FOLL-1"], "question": "NCCN 滤泡性淋巴瘤初诊必需检查（workup essential）写在哪一页？是否要求完整分期影像？", "expected_conclusion": "FOLL-1 为 FL workup；需完整分期"},
    {"id": "P2-N18", "disease": "FL", "G": ["nccn:FOLL-2"], "question": "NCCN 如何按组织学分级与分期开始滤泡淋巴瘤治疗分流？见哪一页决策图？", "expected_conclusion": "FOLL-2 按 1–2 级 vs 3 级等分流"},
    {"id": "P2-N19", "disease": "FL", "G": ["nccn:FOLL-4"], "G_eq": [["nccn:FOLL-4", "nccn:FOLL-B 1 OF 6"]], "question": "NCCN 对需要治疗的滤泡淋巴瘤，一线方案选择指向决策图还是方案表？请给出页码。", "expected_conclusion": "FOLL-4 / FOLL-B 为一线路径与方案表"},
    {"id": "P2-N20", "disease": "MCL", "G": ["nccn:MANT-2"], "question": "NCCN 套细胞淋巴瘤诱导后如何按缓解情况进入巩固/维持？依据哪一页？", "expected_conclusion": "MANT-2 为诱导后分流"},
    {"id": "P2-N21", "disease": "MCL", "G": ["nccn:MANT-3"], "G_eq": [["nccn:MANT-3", "nccn:MANT-A 2 OF 5"]], "question": "NCCN 复发/难治套细胞淋巴瘤后续治疗路径写在哪一页？", "expected_conclusion": "复发难治见 MANT-3 或方案表后续页"},
    {"id": "P2-N51", "disease": "FL", "G": ["nccn:FOLL-5"], "question": "NCCN 滤泡淋巴瘤维持/随访路径写在哪一页？", "expected_conclusion": "FOLL-5"},
    {"id": "P2-N52", "disease": "MCL", "G": ["nccn:MANT-A 2 OF 5"], "question": "NCCN 套细胞淋巴瘤方案表是否按适合强化与否列出诱导方案？页码？", "expected_conclusion": "MANT-A 方案表按适合强化分层"},
    {"id": "P2-N53", "disease": "MCL", "G": ["nccn:MANT-4"], "question": "NCCN 套细胞淋巴瘤后续治疗或随访页码？", "expected_conclusion": "MANT-4"},
    {"id": "P2-N22", "disease": "MZL", "G": ["nccn:MZL-1"], "question": "NCCN 边缘区淋巴瘤总论/分型入口页是哪一页？胃 MALT 与结内 MZL 是否分开？", "expected_conclusion": "MZL-1 为 MZL 入口，亚型分开"},
    {"id": "P2-N23", "disease": "MZL", "G": ["nccn:EMZLG-1"], "question": "NCCN 胃 MALT 淋巴瘤 H. pylori 阳性局限期的一线处理写在哪一页？", "expected_conclusion": "胃 MALT 抗菌治疗见 EMZLG-1"},
    {"id": "P2-N24", "disease": "MZL", "G": ["nccn:NMZL-1"], "question": "NCCN 结内边缘区淋巴瘤（NMZL）治疗路径页码是？", "expected_conclusion": "NMZL-1"},
    {"id": "P2-N25", "disease": "MZL", "G": ["nccn:SMZL-1"], "question": "NCCN 脾边缘区淋巴瘤（SMZL）初始处理写在哪一页？", "expected_conclusion": "SMZL-1"},
    {"id": "P2-N26", "disease": "MZL", "G": ["nccn:EMZLNG-1"], "question": "NCCN 非胃结外 MZL 的治疗入口页是哪一页？", "expected_conclusion": "EMZLNG-1"},
    {"id": "P2-N27", "disease": "MZL", "G": ["nccn:EMZLG-2"], "question": "NCCN 胃 MALT 抗菌治疗后如何再分期与后续处理？", "expected_conclusion": "再分期见 EMZLG-2"},
    {"id": "P2-N28", "disease": "Burkitt", "G": ["nccn:BURK-1"], "question": "NCCN 伯基特淋巴瘤 workup 与分期入口在哪一页？", "expected_conclusion": "BURK-1"},
    {"id": "P2-N29", "disease": "Burkitt", "G": [["nccn:BURK-2", "nccn:BURK-A 1 OF 3"]], "question": "NCCN 写明所有伯基特方案均含中枢预防的页面有哪些（等价即可）？", "expected_conclusion": "BURK-2 与 BURK-A 方案说明等价"},
    {"id": "P2-N30", "disease": "Burkitt", "G": ["nccn:BURK-A 1 OF 3"], "question": "NCCN 伯基特淋巴瘤推荐方案表首页是哪一页？", "expected_conclusion": "BURK-A 1 of 3"},
    {"id": "P2-N31", "disease": "Burkitt", "G": ["nccn:BURK-A 2 OF 3"], "question": "NCCN 伯基特方案表是否列出 CODOX-M/IVAC 或 DA-EPOCH-R 等强化方案？页码？", "expected_conclusion": "BURK-A 方案表含强化方案"},
    {"id": "P2-N32", "disease": "Burkitt", "G": ["nccn:BURK-3"], "question": "NCCN 伯基特淋巴瘤治疗后随访/再评估写在哪一页？", "expected_conclusion": "BURK-3"},
    {"id": "P2-N33", "disease": "HGBL", "G": ["nccn:HGBL-1"], "question": "NCCN 高级别 B 细胞淋巴瘤（HGBL）治疗入口页是哪一页？", "expected_conclusion": "HGBL-1"},
    {"id": "P2-N34", "disease": "HGBL", "G": ["nccn:HTBCEL-1"], "question": "NCCN 惰性淋巴瘤组织学转化为大 B 细胞的路径入口页？", "expected_conclusion": "HTBCEL-1"},
    {"id": "P2-N35", "disease": "HGBL", "G": ["nccn:HGBL-2"], "question": "NCCN 双打击/HGBL 诱导方案指向哪一页？", "expected_conclusion": "HGBL-2"},
    {"id": "P2-N36", "disease": "HGBL", "G": ["nccn:HTBCEL-2"], "question": "NCCN 转化淋巴瘤若既往未充分治疗惰性成分，一线如何分流？", "expected_conclusion": "HTBCEL-2"},
    {"id": "P2-N37", "disease": "HGBL", "G": ["nccn:HTBCEL-3"], "question": "NCCN 转化淋巴瘤复发/后续治疗页码？", "expected_conclusion": "HTBCEL-3"},
    {"id": "P2-N38", "disease": "HGBL", "G": ["nccn:PMBL-1"], "question": "NCCN 原发纵隔大 B 细胞淋巴瘤（PMBL）治疗入口页？", "expected_conclusion": "PMBL-1"},
    {"id": "P2-N39", "disease": "PTLD", "G": ["nccn:PTLD-1"], "question": "NCCN 移植后淋巴增殖性疾病（PTLD）初始评估页是？", "expected_conclusion": "PTLD-1"},
    {"id": "P2-N40", "disease": "PTLD", "G": ["nccn:PTLD-2"], "question": "NCCN PTLD 是否强调先减免疫？依据哪一页？", "expected_conclusion": "减免疫见 PTLD-2"},
    {"id": "P2-N41", "disease": "PTLD", "G": ["nccn:PTLD-3"], "question": "NCCN PTLD 后续治疗/利妥昔单抗路径页码？", "expected_conclusion": "PTLD-3"},
    {"id": "P2-N42", "disease": "PTLD", "G": ["nccn:PTLD-4"], "question": "NCCN PTLD 中枢受累或进一步治疗写在哪一页？", "expected_conclusion": "PTLD-4"},
    {"id": "P2-N43", "disease": "PTLD", "G": ["nccn:disc-ptld"], "G_eq": [["nccn:PTLD-1", "nccn:PTLD-2"]], "question": "NCCN Discussion 对 PTLD 的 EBV 与减免疫原则对应哪几张流程图（等价组）？", "expected_conclusion": "PTLD-1/2 与讨论段落对应"},
    {"id": "P2-N44", "disease": "PTLD", "G": ["nccn:PTLD-1"], "question": "NCCN PTLD 确诊是否要求活检？见哪一页？", "expected_conclusion": "活检确诊见 PTLD-1"},
    {"id": "P2-N45", "disease": "HIV", "G": ["nccn:HIVLYM-1"], "question": "NCCN HIV 相关 B 细胞淋巴瘤 workup 入口页？", "expected_conclusion": "HIVLYM-1"},
    {"id": "P2-N46", "disease": "HIV", "G": ["nccn:HIVLYM-2"], "question": "NCCN HIV 相关淋巴瘤是否强调继续 ART？页码？", "expected_conclusion": "ART 见 HIVLYM-2"},
    {"id": "P2-N47", "disease": "HIV", "G": ["nccn:HIVLYM-3"], "question": "NCCN HIV 相关 DLBCL 治疗路径页？", "expected_conclusion": "HIVLYM-3"},
    {"id": "P2-N48", "disease": "HIV", "G": ["nccn:HIVLYM-4"], "question": "NCCN HIV 相关伯基特或特殊亚型治疗页？", "expected_conclusion": "HIVLYM-4 或后续页"},
    {"id": "P2-N49", "disease": "HIV", "G": ["nccn:HIVLYM-5"], "question": "NCCN HIV 相关淋巴瘤中枢预防如何写？", "expected_conclusion": "HIVLYM 后续页讨论 CNS"},
    {"id": "P2-N50", "disease": "HIV", "G": ["nccn:HIVLYM-1"], "question": "NCCN 对 HIV 相关淋巴瘤，CD4 计数是否影响治疗可行性评估？依据入口页。", "expected_conclusion": "workup 含免疫状态，见 HIVLYM-1"},
]


def normalize_item(it: dict, *, drafted: bool) -> dict:
    gold = it.get("G") or []
    # unwrap single nested list used as one equivalence group
    if gold and isinstance(gold[0], list):
        groups = gold
    elif it.get("G_eq"):
        groups = it["G_eq"]
    else:
        groups = gold
    return {
        "id": it["id"],
        "data_source": it.get("data_source", "nccn"),
        "topic": it.get("topic") or it.get("disease") or "",
        "disease": infer_disease({**it, "G": gold}),
        "question": it["question"],
        "G": groups,
        "G_opt": it.get("G_opt") or [],
        "negative": False,
        "expected_conclusion": it.get("expected_conclusion") or "",
        "annotation_status": "draft_v2_needs_blind_review" if drafted else "v1_carried",
        "annotators": [],
    }


def main() -> None:
    v1 = load_json(DATASETS / "part2" / "v1_questions.json")
    pos, neg = [], []
    for it in v1:
        it = dict(it)
        it["disease"] = infer_disease(it)
        if it.get("negative"):
            neg.append(
                {
                    **{k: it.get(k) for k in ("id", "data_source", "topic", "question", "G", "G_opt", "expected_conclusion")},
                    "disease": it["disease"],
                    "negative": True,
                    "task": "refuse_or_say_uncovered",
                }
            )
        else:
            pos.append(normalize_item(it, drafted=False))
    extras = []
    existing = {x["id"] for x in pos}
    for d in DRAFTS:
        if d["id"] in existing:
            continue
        extras.append(normalize_item(d, drafted=True))
    v2 = pos + extras
    counts = {}
    for it in v2:
        if it["data_source"] == "nccn":
            counts[it["disease"]] = counts.get(it["disease"], 0) + 1
    out = DATASETS / "part2"
    save_json(out / "v2_questions.json", v2)
    save_json(out / "safety_refusal.json", neg)
    save_json(
        out / "v2_annotation_template.json",
        [
            {
                "id": it["id"],
                "annotator": "",
                "G": it["G"],
                "agree": "",
                "notes": "",
            }
            for it in v2
            if it["annotation_status"].startswith("draft")
        ],
    )
    save_json(out / "v2_stats.json", {"n": len(v2), "nccn_by_disease": counts, "n_neg_moved": len(neg)})
    print("part2 v2", {"n": len(v2), "nccn_by_disease": counts, "neg": len(neg)})


if __name__ == "__main__":
    main()
