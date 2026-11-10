"""ALCE-style citation support judge. Judge model defaults to qwen-plus."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from common.paths import CODE_ROOT, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(CODE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.io import load_json, save_json
from backend.app.services.qwen import QwenClient
from backend.app.settings import load_settings

JUDGE_SYS = """你是引用支持性评委。对「句子」与「证据原文」判断：证据是否支持该句的关键医学断言。
只输出 JSON：{"supported": true|false, "necessary": true|false, "note": "一句中文"}。
supported=证据足以支撑该句；necessary=若删去该引用，该句会失去依据。"""


def split_claims(answer: str) -> list[tuple[str, list[int]]]:
    claims = []
    for sent in re.split(r"(?<=[。！？.!?])\s+", answer or ""):
        sent = sent.strip()
        if not sent:
            continue
        idxs = [int(m) for m in re.findall(r"\[S(\d+)\]", sent, flags=re.I)]
        claims.append((sent, idxs))
    return claims


def judge_one(client: QwenClient, sentence: str, evidence: str) -> dict:
    raw = client._chat_text(
        [
            {"role": "system", "content": JUDGE_SYS},
            {"role": "user", "content": f"句子：{sentence}\n\n证据：{evidence[:3000]}"},
        ],
        temperature=0.0,
        timeout=45,
    )
    try:
        return json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    except Exception:
        return {"supported": False, "necessary": False, "note": "parse_failed", "raw": raw[:300]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True, help="Part2 run directory with raw/")
    parser.add_argument("--judge-model", default="qwen-plus")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--review-sample", type=int, default=20)
    args = parser.parse_args()
    settings = load_settings()
    client = QwenClient(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_base_url,
        model=args.judge_model,
        generate_temperature=0.0,
    )
    raw_files = sorted((args.run_dir / "raw").glob("p2_guideflow_*.json"))[: args.limit]
    rows = []
    for fp in raw_files:
        blob = load_json(fp)
        payload = blob.get("payload") or {}
        answer = payload.get("answer_markdown") or ""
        sources = payload.get("sources") or []
        claims = split_claims(answer)
        judged = []
        for sent, idxs in claims:
            if not idxs:
                judged.append({"sentence": sent, "idxs": [], "supported": None, "necessary": None})
                continue
            ev = []
            for i in idxs:
                if 1 <= i <= len(sources):
                    ev.append(str(sources[i - 1].get("text") or sources[i - 1].get("snippet") or "")[:1500])
            verdict = judge_one(client, sent, "\n---\n".join(ev) or "(empty)")
            judged.append({"sentence": sent, "idxs": idxs, **verdict})
        cited = [j for j in judged if j["idxs"]]
        supported = [j for j in cited if j.get("supported")]
        necessary = [j for j in cited if j.get("necessary")]
        rows.append(
            {
                "id": (blob.get("item") or {}).get("id") or fp.stem,
                "n_claims": len(judged),
                "n_cited": len(cited),
                "citation_recall": (len(supported) / len(cited)) if cited else None,
                "citation_precision": (len(necessary) / len(cited)) if cited else None,
                "judged": judged,
            }
        )
        print(f"[judge] {fp.name}", flush=True)

    recalls = [r["citation_recall"] for r in rows if r["citation_recall"] is not None]
    precs = [r["citation_precision"] for r in rows if r["citation_precision"] is not None]
    out = args.run_dir / "citation_judge.json"
    review = [{"id": r["id"], "human_agree": None} for r in rows[: args.review_sample]]
    save_json(
        out,
        {
            "judge_model": args.judge_model,
            "n": len(rows),
            "mean_citation_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
            "mean_citation_precision": round(sum(precs) / len(precs), 4) if precs else None,
            "human_review_template": review,
            "rows": rows,
        },
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
