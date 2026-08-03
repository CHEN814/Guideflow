from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import list_source_keys, load_settings, source_paths
from backend.app.services.paper_extractor import PROFILES, build_paper_knowledge_base, get_paper_profile
from backend.app.services.store import save_knowledge_base


def main() -> None:
    settings = load_settings()
    paper_keys = sorted(PROFILES.keys())
    parser = argparse.ArgumentParser(
        description="Build a paper-style guideline knowledge base (e.g. EHA)."
    )
    parser.add_argument(
        "--source",
        choices=tuple(paper_keys),
        default="eha",
        help=f"Paper profile / source key (default: eha). Known: {', '.join(paper_keys)}",
    )
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--skip-vlm",
        action="store_true",
        help="Skip offline VLM table transcription (narrative + refs only).",
    )
    args = parser.parse_args()

    profile = get_paper_profile(args.source)
    paths = source_paths(args.source, settings) if args.source in list_source_keys() else None
    pdf = args.pdf
    if pdf is None:
        if paths is not None:
            pdf = paths["pdf"]
        else:
            matches = sorted(settings.root_dir.glob(f"*{args.source.upper()}*.pdf"))
            pdf = matches[0] if matches else settings.root_dir / f"{args.source}.pdf"
    out = args.out
    if out is None:
        out = (
            paths["knowledge_base"]
            if paths is not None
            else settings.root_dir / "data" / "processed" / f"{args.source}_knowledge_base.json"
        )

    cache_path = settings.root_dir / "data" / "cache" / f"{args.source}_table_md.json"
    page_image_dir = (
        paths["page_images"]
        if paths is not None
        else settings.root_dir / "data" / "cache" / f"{args.source}_page_images"
    )

    kb = build_paper_knowledge_base(
        pdf,
        profile,
        skip_vlm=bool(args.skip_vlm),
        vlm_api_key=settings.vlm_api_key,
        vlm_base_url=settings.vlm_base_url,
        vlm_model=settings.vlm_model,
        table_cache_path=cache_path,
        page_image_dir=page_image_dir,
    )
    save_knowledge_base(out, kb)

    s = kb.stats
    print(f"Paper knowledge base written to: {out}")
    print(f"  Source           : {args.source}")
    print(f"  PDF              : {pdf}")
    print(f"  PDF pages        : {s.get('pdf_page_count', 0)}")
    print(f"  Front pages      : {s.get('guideline_page_count', 0)}")
    print(f"  Discussion chunks: {s.get('discussion_chunk_count', 0)}")
    print(f"    table chunks   : {s.get('table_chunk_count', 0)}")
    print(f"  Reference entries: {s.get('reference_entry_count', 0)}")
    print(f"  Sections         : {len(s.get('sections', []))}")
    print(f"  Search documents : {len(kb.to_search_documents())}")
    if not args.skip_vlm and not settings.vlm_api_key:
        print("  WARNING: VLM_API_KEY/DASHSCOPE_API_KEY missing; tables may be empty.")
        print(f"  Table cache path : {cache_path}")


if __name__ == "__main__":
    main()
