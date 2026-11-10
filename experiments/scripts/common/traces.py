from __future__ import annotations

import json
from pathlib import Path


def iter_trace_events(trace_path: str | Path) -> list[dict]:
    path = Path(trace_path)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _hit_unit(hit: dict, data_source: str) -> str:
    from experiments.scripts.common.scoring import normalize_unit, unit_from_source

    if isinstance(hit, dict) and "document" in hit:
        doc = hit.get("document") or {}
        return unit_from_source(
            {
                "printed_page_code": doc.get("printed_page_code"),
                "source_id": doc.get("source_id"),
                "citation_label": doc.get("citation_label"),
            },
            data_source,
        )
    return unit_from_source(hit, data_source) if isinstance(hit, dict) else normalize_unit(str(hit))


def units_from_trace_hits(trace_path: str | Path, data_source: str) -> dict[str, list[str]]:
    from experiments.scripts.common.scoring import uniq_units

    out = {"raw": [], "rerank": [], "final": [], "gated": []}
    for ev in iter_trace_events(trace_path):
        name = ev.get("event")
        payload = ev.get("payload") or ev.get("data") or {}
        hits = payload.get("hits") or []
        if name == "retrieval_topk_raw":
            out["raw"] = uniq_units(_hit_unit(h, data_source) for h in hits)
        elif name == "rerank_topk":
            out["rerank"] = uniq_units(_hit_unit(h, data_source) for h in hits)
        elif name == "retrieval_topk_final":
            out["final"] = uniq_units(_hit_unit(h, data_source) for h in hits)
        elif name == "evidence_gated":
            out["gated"] = out["final"][:]
    if not out["gated"] and out["final"]:
        out["gated"] = out["final"][:]
    return out
