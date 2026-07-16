"""Extract a page range from the NCCN B-Cell Lymphoma PDF into a Markdown file."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.pdf_extractor import (  # noqa: E402
    DOC_TITLE,
    DOCUMENT_VERSION,
    _clean_text,
    _extract_ms_code,
)
from backend.app.settings import load_settings

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


def extract_pages_to_markdown(
    pdf_path: Path,
    out_path: Path,
    start_page: int,
    end_page: int,
) -> None:
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF is required. Install with: pip install -r requirements.txt"
        )
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if start_page < 1 or end_page < start_page:
        raise ValueError(f"Invalid page range: {start_page}-{end_page}")

    pdf = fitz.open(str(pdf_path))
    total = len(pdf)
    if start_page > total:
        raise ValueError(f"Start page {start_page} exceeds PDF length ({total} pages)")

    end_page = min(end_page, total)
    sections: list[str] = [
        f"# {DOC_TITLE}",
        "",
        f"- **Version**: {DOCUMENT_VERSION}",
        f"- **Source**: `{pdf_path.name}`",
        f"- **Pages**: {start_page}–{end_page} (PDF page numbers, 1-based)",
        "",
    ]

    for page_num in range(start_page, end_page + 1):
        page = pdf[page_num - 1]
        raw = page.get_text("text")
        clean = _clean_text(raw)
        ms_code = _extract_ms_code(clean)
        heading = f"## Page {page_num}"
        if ms_code:
            heading += f" ({ms_code})"

        sections.append(heading)
        sections.append("")
        sections.append(clean if clean else "_(empty page)_")
        sections.append("")

    pdf.close()
    out_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    settings = load_settings()
    default_pdf = settings.pdf_path
    default_out = ROOT / "NCCN guidance(sample).md"

    parser = argparse.ArgumentParser(
        description="Extract PDF pages from the NCCN guideline into Markdown."
    )
    parser.add_argument("--pdf", type=Path, default=default_pdf, help="Path to NCCN PDF")
    parser.add_argument("--out", type=Path, default=default_out, help="Output Markdown path")
    parser.add_argument("--start", type=int, default=140, help="First page (1-based, inclusive)")
    parser.add_argument("--end", type=int, default=160, help="Last page (1-based, inclusive)")
    args = parser.parse_args()

    extract_pages_to_markdown(args.pdf, args.out, args.start, args.end)
    print(f"Wrote pages {args.start}-{args.end} to: {args.out}")


if __name__ == "__main__":
    main()
