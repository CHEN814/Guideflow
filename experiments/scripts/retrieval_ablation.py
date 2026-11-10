"""Offline retrieval ablations. Default is BM25/lexical only; --live calls Bailian."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from common.paths import CODE_ROOT, DATASETS, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(CODE_ROOT))

from common.io import load_json, save_json
from common.scoring import disease_from_units, flatten_gold_units, gold_size, match_gold_groups, unit_from_source
from backend.app.services.bm25_store import BM25Store
from backend.app.services.evidence_policy import penalize_reference_pages
from backend.app.services.query_normalizer import normalize_query
from backend.app.services.reranker import BailianReranker, LexicalReranker
from backend.app.services.retrieval import route_query
from backend.app.settings import load_settings, settings_for_source


def hit_unit(hit, source: str) -> str:
    return unit_from_source(
        {
            "printed_page_code": hit.document.printed_page_code,
            "source_id": hit.document.source_id,
        },
        source,
    )


def metrics_at_k(gold: list, ranked_units: list[str], ks=(3, 6, 10, 16, 24, 32)) -> dict:
    out = {}
    for k in ks:
        top = ranked_units[:k]
        hit = match_gold_groups(gold, top)
        g_n = gold_size(gold) or 1
        out[f"recall@{k}"] = len(hit) / g_n if gold else 0.0
        rr = 0.0
        for i, u in enumerate(top, start=1):
            if match_gold_groups(gold, [u]):
                rr = 1.0 / i
                break
        out[f"mrr@{k}"] = rr
    return out


def retrieve_bm25(store: BM25Store, question: str, source: str, top_k: int):
    from backend.app.services.disease_scope import detect_disease_scope

    normalized = normalize_query(question)
    scope = detect_disease_scope(question, source=source)
    route, filters, _ = route_query(normalized, disease_scope=scope)
    return store.search(normalized.search_queries, filters, top_k), scope.key


def maybe_rerank(name: str, question: str, hits, top_k: int, live: bool, settings=None):
    if name == "bm25":
        return hits[:top_k], None
    if name == "lexical":
        ranked, deg = LexicalReranker().rerank(question, hits, top_k)
        return ranked, deg
    if name.startswith("bailian") and live and settings is not None:
        ranked, deg = BailianReranker(
            settings.reranker_model,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        ).rerank(question, hits, top_k)
        return ranked, deg
    return hits[:top_k], "skipped_not_live"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DATASETS / "part2" / "v3_nccn_questions.json")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--bm25-k", type=int, default=40)
    parser.add_argument("--final-k", type=int, default=32)
    parser.add_argument("--cutoffs", default="16,24,32")
    args = parser.parse_args()
    qpath = args.questions if args.questions.exists() else DATASETS / "part2" / "v1_questions.json"
    cutoffs = tuple(int(x) for x in str(args.cutoffs).split(",") if x.strip())
    ks = tuple(sorted(set((3, 6, 10) + cutoffs)))
    items = [it for it in load_json(qpath) if not it.get("negative") and it.get("data_source", "nccn") == "nccn"]
    variants = ["bm25", "lexical"]
    if args.live:
        variants += ["bailian", "bailian+refpen"]
    else:
        variants += ["lexical+refpen"]

    base_settings = load_settings()
    stores = {}
    rows = []
    for it in items:
        src = it["data_source"]
        if src not in stores:
            settings = settings_for_source(src, base_settings)
            stores[src] = BM25Store.load(settings.bm25_index_path)
        raw, dz = retrieve_bm25(stores[src], it["question"], src, args.bm25_k)
        gold = it.get("G") or []
        rec = {
            "id": it["id"],
            "data_source": src,
            "disease": it.get("disease") or disease_from_units(flatten_gold_units(gold), default=dz),
            "gold": gold,
        }
        for name in variants:
            hits = list(raw)
            if "refpen" in name:
                hits = penalize_reference_pages(hits)
            ranked, deg = maybe_rerank(
                name.replace("+refpen", ""),
                it["question"],
                hits,
                args.final_k,
                args.live,
                settings=base_settings,
            )
            units = [u for h in ranked if (u := hit_unit(h, src))]
            rec[name] = {**metrics_at_k(gold, units, ks=ks), "degraded": deg, "units": units[:32]}
        rows.append(rec)
        print(f"[ablation] {it['id']}", flush=True)

    def avg(variant: str, key: str, subset=None) -> float:
        xs = [r[variant][key] for r in (subset or rows) if variant in r]
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    summary = []
    for name in variants:
        entry = {"variant": name, "n": len(rows)}
        metric_keys = [f"recall@{k}" for k in ks] + ["mrr@6"]
        for key in metric_keys:
            entry[key] = avg(name, key)
        by_dz = defaultdict(list)
        for r in rows:
            by_dz[r["disease"]].append(r)
        cutoff_keys = [f"recall@{k}" for k in cutoffs] + ["mrr@6"]
        entry["by_disease"] = {
            dz: {k: avg(name, k, rs) for k in cutoff_keys}
            for dz, rs in sorted(by_dz.items())
        }
        summary.append(entry)

    out = RUNS / "offline_retrieval_ablation"
    out.mkdir(parents=True, exist_ok=True)
    save_json(out / "rows.json", rows)
    save_json(out / "summary.json", {"live": args.live, "variants": summary})
    print(summary)


if __name__ == "__main__":
    main()
