"""Print selected catalog units for gold-standard drafting."""
from __future__ import annotations

import json
from pathlib import Path

CAT = Path(__file__).resolve().parent / "catalogs"


def load(name: str) -> dict:
    return json.loads((CAT / f"{name}_catalog.json").read_text(encoding="utf-8"))


def show_pages(data: dict, codes: list[str]) -> None:
    by = {p["page_code"]: p for p in data["pages"]}
    for code in codes:
        p = by.get(code)
        if not p:
            print("MISSING", code)
            continue
        print(f"\n## {p['unit_id']} | {p['source_id']} | pdf {p['pdf_page']}")
        print(p["snippet"])


def show_chunks(data: dict, pred) -> None:
    n = 0
    for c in data["chunks"]:
        if pred(c):
            n += 1
            print(f"\n## {c['unit_id']} | {c['article']} | {c['section']} | p{c['pdf_page']}")
            print(c["snippet"])
    print(f"\n--- matched {n} ---")


if __name__ == "__main__":
    nccn = load("nccn")
    show_pages(
        nccn,
        [
            "DIAG-1",
            "BCEL-1",
            "BCEL-2",
            "BCEL-3",
            "BCEL-4",
            "BCEL-5",
            "BCEL-6",
            "BCEL-7",
            "BCEL-8",
            "BCEL-9",
            "BCEL-A 1 OF 3",
            "BCEL-A 2 OF 3",
            "BCEL-A 3 OF 3",
            "BCEL-B 1 OF 2",
            "BCEL-B 2 OF 2",
            "BCEL-C 1 OF 7",
            "BCEL-C 2 OF 7",
            "ST-1",
            "ST-5",
            "FOLL-3",
            "FOLL-B 1 OF 6",
            "MANT-2",
            "MANT-A 1 OF 5",
            "BURK-2",
            "NHODG-B 1 OF 5",
        ],
    )
    print("\n\n======== CSCO DLBCL / appendix / FL / MCL ========")
    csco = load("csco")
    show_chunks(
        csco,
        lambda c: c["article"] in {"dlbcl", "appendix-1", "fl", "mcl", "evidence-categories", "recommendation-levels"}
        and c["content_type"] in {"text", "table"},
    )
    print("\n\n======== EHA key sections ========")
    eha = load("eha")
    show_chunks(
        eha,
        lambda c: any(
            k in (c["section"] or "")
            for k in (
                "Staging",
                "Diagnosis",
                "Management Of 1L",
                "Summary Of Recommendations 1L",
                "Cns-Ipi",
                "Refractory",
                "Response",
                "TABLE A1",
                "Tables",
                "Follow-Up",
            )
        ),
    )
