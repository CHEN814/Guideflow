from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.models import ReferenceEntry, SearchDocument
from backend.app.services.figure_anchor import split_answer_paragraphs
from backend.app.services.knowledge_graph import (
    KnowledgeGraphBuilder,
    apply_review_decisions,
    export_review_queue,
    load_knowledge_graph_bundle,
    load_review_decisions,
    save_knowledge_graph_bundle,
)
from backend.app.services.neo4j_importer import import_knowledge_graph_to_neo4j
from backend.app.services.qa import QAService
from backend.app.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the DLBCL CLI RAG Agent.")
    parser.add_argument("question", nargs="?", help="Question to ask.")
    parser.add_argument("--trace", action="store_true", help="Print trace path and retrieved sources.")
    parser.add_argument(
        "--build-kg",
        action="store_true",
        help="Build the knowledge graph bundle and exit.",
    )
    parser.add_argument(
        "--export-review-queue",
        action="store_true",
        help="Export review-ready graph triples and candidates.",
    )
    parser.add_argument(
        "--apply-reviews",
        type=Path,
        help="Apply human or LLM review decisions from a JSON file.",
    )
    parser.add_argument(
        "--import-neo4j",
        action="store_true",
        help="Import the built knowledge graph into Neo4j and exit.",
    )
    parser.add_argument("--neo4j-clear", action="store_true", help="Clear Neo4j before import.")
    parser.add_argument("--neo4j-batch-size", type=int, help="Cypher batch size for Neo4j import.")
    args = parser.parse_args()

    settings = load_settings()

    kg_ops = any(
        [
            args.build_kg,
            args.export_review_queue,
            args.apply_reviews is not None,
            args.import_neo4j,
        ]
    )
    if kg_ops and args.question:
        print("Note: question is ignored for knowledge-graph maintenance commands.")

    if args.build_kg:
        _ensure_knowledge_base(settings)
        from backend.app.services.store import load_knowledge_base

        kb = load_knowledge_base(settings.knowledge_base_path)
        bundle = KnowledgeGraphBuilder().build(kb)
        save_knowledge_graph_bundle(settings.knowledge_graph_path, bundle)
        print(f"Knowledge graph written to: {settings.knowledge_graph_path}")
        for key, value in bundle.stats.items():
            print(f"{key}: {value}")
        return

    if args.export_review_queue:
        _ensure_knowledge_graph(settings)
        bundle = load_knowledge_graph_bundle(settings.knowledge_graph_path)
        review_path = settings.knowledge_graph_path.with_name("knowledge_graph_review_queue.json")
        export_review_queue(review_path, bundle)
        print(f"Review queue exported to: {review_path}")
        print(f"count: {len(bundle.triples) + len(bundle.rejected_candidates)}")
        return

    if args.apply_reviews is not None:
        _ensure_knowledge_graph(settings)
        bundle = load_knowledge_graph_bundle(settings.knowledge_graph_path)
        decisions = load_review_decisions(args.apply_reviews)
        reviewed = apply_review_decisions(bundle, decisions)
        save_knowledge_graph_bundle(settings.knowledge_graph_path, reviewed)
        print(f"Applied review decisions from: {args.apply_reviews}")
        print(f"trusted_triples: {len(reviewed.triples)}")
        print(f"remaining_candidates: {len(reviewed.rejected_candidates)}")
        return

    if args.import_neo4j:
        _ensure_knowledge_base(settings)
        _ensure_knowledge_graph(settings)
        stats = import_knowledge_graph_to_neo4j(
            settings.knowledge_base_path,
            settings.knowledge_graph_path,
            settings,
            clear=args.neo4j_clear,
            batch_size=args.neo4j_batch_size,
        )
        print("Neo4j import complete.")
        for key, value in stats.items():
            print(f"{key}: {value}")
        return

    if not args.question:
        raise SystemExit("question is required unless using a knowledge-graph maintenance flag.")

    _ensure_indexes(settings)
    _ensure_knowledge_graph(settings)
    result = QAService(settings).ask(args.question, trace_enabled=True)

    _print_answer_with_figures(result.answer, result.figures)

    print("\n【证据来源】")
    for idx, source in enumerate(result.sources, start=1):
        print(_format_primary_source(idx, source, show_internal_id=args.trace))

    if result.graph_triples:
        print("\n【图谱证据】")
        for idx, triple in enumerate(result.graph_triples, start=1):
            print(_format_graph_triple(idx, triple))

    if result.attached_references:
        print("\n【关联参考文献】")
        source_index = {source.source_id: idx for idx, source in enumerate(result.sources, start=1)}
        for entry in result.attached_references:
            print(_format_attached_reference(entry, result.reference_links, source_index))

    if result.degraded:
        print("\n降级提示：")
        for item in sorted(set(result.degraded)):
            print(f"- {item}")

    if args.trace:
        print(f"\nTrace: {result.trace_path}")
        print(f"Verification: {result.verification}")


def _print_answer_with_figures(answer: str, figures) -> None:
    """Print answer with figures inlined after anchored paragraphs."""
    if not figures:
        print(answer)
        return

    paragraphs = split_answer_paragraphs(answer) or [answer]
    anchored: dict[int, list] = {}
    unanchored = []
    for fig in figures:
        if fig.anchor_paragraph is not None:
            anchored.setdefault(fig.anchor_paragraph, []).append(fig)
        else:
            unanchored.append(fig)

    for idx, paragraph in enumerate(paragraphs):
        print(paragraph)
        for fig in anchored.get(idx, []):
            _print_figure_line(fig)
        if idx < len(paragraphs) - 1:
            print()

    if unanchored:
        print("\n【相关流程图】")
        for fig in unanchored:
            _print_figure_line(fig)


def _print_figure_line(fig) -> None:
    label = fig.page_code or f"pdf_page={fig.pdf_page}"
    sn = f"[S{fig.source_index}] " if fig.source_index else ""
    display_path = fig.crop_image_path or fig.image_path
    print(f"\n{sn}{label}: ![{label}]({display_path})")


def _format_primary_source(idx: int, source: SearchDocument, show_internal_id: bool) -> str:
    page_info = f"pdf_page={source.pdf_page}"
    section = source.section or "N/A"
    line = f"[S{idx}] {page_info} | {source.page_type} | {section}"
    if show_internal_id:
        line += f" | {source.source_id}"
    return line


def _format_graph_triple(idx, triple) -> str:
    evidence_ids = ", ".join(triple.evidence_source_ids) if triple.evidence_source_ids else "无"
    score = f"{triple.confidence:.2f}"
    llm = f", llm={triple.llm_score:.2f}" if triple.llm_score is not None else ""
    reviewer = f", reviewer={triple.reviewer}" if triple.reviewer else ""
    return (
        f"[G{idx}] {triple.subject_name}({triple.subject_type}) --{triple.relation}--> "
        f"{triple.object_name}({triple.object_type}) | conf={score}{llm}{reviewer} | "
        f"status={triple.validation_status} | sources={evidence_ids}"
    )


def _format_attached_reference(
    entry: ReferenceEntry,
    reference_links: dict[str, list[str]],
    source_index: dict[str, int],
) -> str:
    linked_sources = sorted(
        {
            f"S{source_index[source_id]}"
            for source_id, ref_numbers in reference_links.items()
            if entry.ref_number in ref_numbers and source_id in source_index
        },
        key=lambda value: int(value[1:]),
    )
    linked_label = f"由 {', '.join(linked_sources)} 关联" if linked_sources else "关联"
    text = entry.text.replace("\n", " ").strip()
    if len(text) > 220:
        text = text[:217] + "..."
    return f"[{entry.ref_number}] {text} ({linked_label})"


def _ensure_indexes(settings) -> None:
    missing = []
    if not settings.knowledge_base_path.exists():
        missing.append("python scripts/build_knowledge_base.py")
    if not settings.bm25_index_path.exists():
        missing.append("python scripts/build_bm25_index.py")
    if missing:
        commands = "\n".join(f"  {command}" for command in missing)
        raise SystemExit(f"Indexes are not ready. Run:\n{commands}")


def _ensure_knowledge_base(settings) -> None:
    if not settings.knowledge_base_path.exists():
        raise SystemExit("Knowledge base is not ready. Run: python scripts/build_knowledge_base.py")


def _ensure_knowledge_graph(settings) -> None:
    if not settings.knowledge_graph_path.exists():
        raise SystemExit(
            "Knowledge graph is not ready. Run: python scripts/ask.py --build-kg\n"
            "  (or: python scripts/build_knowledge_graph.py)"
        )


if __name__ == "__main__":
    main()
