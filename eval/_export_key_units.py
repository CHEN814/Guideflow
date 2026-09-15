"""Write selected guideline units to UTF-8 text for gold drafting."""
from __future__ import annotations

import json
from pathlib import Path

CAT = Path(__file__).resolve().parent / "catalogs"
OUT = Path(__file__).resolve().parent / "catalogs" / "key_units.txt"


def load(name: str) -> dict:
    return json.loads((CAT / f"{name}_catalog.json").read_text(encoding="utf-8"))


def main() -> None:
    lines: list[str] = []
    nccn = load("nccn")
    want = {
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
        "MANT-1",
        "MANT-2",
        "MANT-A 1 OF 5",
        "BURK-2",
        "NHODG-C 1 OF 3",
        "NHODG-C 2 OF 3",
    }
    lines.append("===== NCCN pages =====")
    for p in nccn["pages"]:
        if p["page_code"] in want:
            lines.append(f"{p['unit_id']}\t{p['source_id']}\t{p['snippet']}")

    lines.append("\n===== NCCN discussion (dlbcl, keywords) =====")
    keys = ("Pola-R-CHP", "R-mini-CHOP", "CNS", "ASCR", "HGBL", "testicular")
    for c in nccn["chunks"]:
        if c.get("article") == "dlbcl" and any(k.lower() in (c["snippet"] or "").lower() for k in keys):
            lines.append(f"{c['unit_id']}\t{c['section']}\t{c['snippet']}")

    csco = load("csco")
    lines.append("\n===== CSCO =====")
    for c in csco["chunks"]:
        art = c.get("article") or ""
        sec = c.get("section") or ""
        if art in {
            "dlbcl",
            "appendix-1",
            "fl",
            "mcl",
            "evidence-categories",
            "recommendation-levels",
            "ptdlbcl",
            "hgbl",
        } or "睾丸" in (c["snippet"] or "") or "Lugano" in (c["snippet"] or "") + sec:
            if art in {"dlbcl", "fl", "mcl", "evidence-categories", "recommendation-levels", "appendix-1", "hgbl"} or "睾丸" in (c["snippet"] or ""):
                lines.append(f"{c['unit_id']}\t{art}\t{sec}\t{c['content_type']}\t{c['snippet']}")

    eha = load("eha")
    lines.append("\n===== EHA =====")
    for c in eha["chunks"]:
        lines.append(f"{c['unit_id']}\t{c['section']}\t{c['content_type']}\tp{c['pdf_page']}\t{c['snippet']}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} lines={len(lines)}")


if __name__ == "__main__":
    main()
