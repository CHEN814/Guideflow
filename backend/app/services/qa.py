from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional, Tuple

from backend.app.models import EvidenceBundle, FigureReference, NormalizedQuery, QAResult, RetrievalHit
from backend.app.settings import Settings
from backend.app.services.agent_orchestrator import AgentOrchestrator
from backend.app.services.agent_tools import status_event
from backend.app.services.answer_formatter import format_answer
from backend.app.services.bm25_store import BM25Store
from backend.app.services.disease_scope import DiseaseScope, detect_disease_scope
from backend.app.services.qwen import QwenClient
from backend.app.prompts import PAGE_SUMMARY_MARKER, build_evidence_prompt
from backend.app.services.dlbcl_flow_map import is_decision_flow_page, normalize_page_code
from backend.app.services.figure_crop import (
    assess_vlm_bbox_quality,
    detect_display_bboxes_for_page,
    detect_figure_bbox_for_page,
    lookup_vlm_bbox,
)
from backend.app.services.citation_filter import filter_attached_references, filter_cited_hits
from backend.app.services.figure_anchor import compute_anchors
from backend.app.services.figure_selection import backfill_source_indices, prune_figures_by_answer
from backend.app.services.graph_navigator import GraphNavigator
from backend.app.services.kg_retriever import KnowledgeGraphRetriever
from backend.app.services.multimodal_client import _split_answer_and_summary, load_multimodal_client
from backend.app.services.page_image import PageImageRenderer
from backend.app.services.page_summary_cache import PageSummaryCache
from backend.app.services.query_normalizer import normalize_query
from backend.app.services.reference_resolver import ReferenceResolver
from backend.app.services.reranker import load_reranker
from backend.app.services.retrieval import Bm25Retriever
from backend.app.services.source_display import build_cite_context_payload
from backend.app.services.tracing import TraceLogger
from backend.app.services.verifier import verify_answer


@dataclass
class _AskContext:
    question: str
    standalone_question: str
    history: List[dict]
    answer_kind: str
    disease_scope: DiseaseScope
    topic_shift: bool
    trace: TraceLogger
    normalized: NormalizedQuery
    hits: List[RetrievalHit]
    diagnostics: dict
    route: str
    gate_degraded: Optional[str]
    attached_references: list
    reference_links: dict
    graph_hits: list
    graph_triples: list
    graph_context: List[str]
    figures: List[FigureReference]
    seed_page_code: Optional[str]
    seed_meta: dict
    bundle: EvidenceBundle
    use_vlm: bool
    structured_trace: dict
    early_answer: Optional[str] = None
    early_degraded: Optional[str] = None
    agent_steps: List[dict] = field(default_factory=list)
    status_events: List[dict] = field(default_factory=list)


class QAService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bm25 = BM25Store.load(settings.bm25_index_path)
        # Merge cached first-hit page summaries into the BM25 corpus so
        # previously-summarised flowchart pages become more findable.
        self.summary_cache = PageSummaryCache(settings.summary_cache_path)
        self._rebuild_bm25_with_summaries()
        self.reranker = load_reranker(settings.reranker_model)
        self.retriever = Bm25Retriever(
            bm25=self.bm25,
            reranker=self.reranker,
            bm25_top_k=settings.bm25_top_k,
            rerank_top_k=settings.rerank_top_k,
            final_top_k=settings.final_top_k,
        )
        self.reference_resolver = ReferenceResolver.from_path(
            settings.knowledge_base_path,
            max_attached_refs=settings.max_attached_refs,
        )
        self.graph_navigator = GraphNavigator.from_path(settings.knowledge_base_path)
        self.kg_retriever = KnowledgeGraphRetriever.from_path(settings.knowledge_graph_path)
        self.qwen = QwenClient(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
        )
        self.vlm = load_multimodal_client(
            api_key=settings.vlm_api_key,
            base_url=settings.vlm_base_url,
            model=settings.vlm_model,
        )
        self.page_renderer = PageImageRenderer(
            pdf_path=settings.pdf_path,
            cache_dir=settings.page_image_dir,
            dpi=settings.page_image_dpi,
        )

    def ask(
        self,
        question: str,
        trace_enabled: bool = True,
        history: Optional[List[dict]] = None,
    ) -> QAResult:
        ctx = self._prepare_ask(question, trace_enabled=trace_enabled, history=history)
        if ctx.early_answer is not None:
            return self._finalize_ask(
                ctx,
                answer=ctx.early_answer,
                generation_mode="text",
                generation_degraded=ctx.early_degraded,
                page_bboxes={},
            )
        if ctx.use_vlm:
            answer, generation_degraded, page_summaries, page_bboxes = self.vlm.generate(
                ctx.standalone_question, ctx.bundle, route=ctx.route
            )
            generation_mode = "multimodal"
            self._apply_summaries(page_summaries, ctx.trace)
            ctx.trace.log(
                "vlm_page_bboxes",
                {
                    "received_page_codes": sorted(page_bboxes.keys()),
                    "bboxes": page_bboxes,
                    "missing_for_figures": [
                        fig.page_code
                        for fig in ctx.figures
                        if fig.page_code and not lookup_vlm_bbox(fig.page_code, page_bboxes)
                    ],
                },
            )
        else:
            answer, generation_degraded = self.qwen.generate(
                ctx.standalone_question,
                ctx.bundle,
                route=ctx.route,
                history=None if ctx.topic_shift else ctx.history,
            )
            generation_mode = "text"
            page_bboxes = {}
        return self._finalize_ask(
            ctx,
            answer=answer,
            generation_mode=generation_mode,
            generation_degraded=generation_degraded,
            page_bboxes=page_bboxes,
        )

    def ask_stream(
        self,
        question: str,
        trace_enabled: bool = True,
        history: Optional[List[dict]] = None,
    ) -> Generator[dict, None, None]:
        """True streaming: yield meta → status* → token* → final(payload)."""
        history = list(history or [])
        trace = TraceLogger(self.settings.logs_dir, enabled=trace_enabled)
        trace.log("query_received", {"question": question, "history_turns": len(history)})

        standalone, topic_shift, condense_degraded = self.qwen.condense_question(question, history)
        if topic_shift:
            history = []
        disease_scope = detect_disease_scope(standalone)
        routing_mode = str(getattr(self.settings, "routing_mode", "agentic") or "agentic").lower()

        yield {
            "type": "meta",
            "route": "agent" if routing_mode == "agentic" else "pending",
            "generation_mode": "text",
            "answer_kind": "guideline",
            "disease_scope": disease_scope.key,
            "sources": [],
            "run_id": trace.run_id,
            "routing_mode": routing_mode,
        }

        status_events: List[dict] = []
        if routing_mode == "agentic":
            orch = AgentOrchestrator(self)
            gen = orch.run_streaming(
                question=question,
                standalone=standalone,
                history=history,
                disease_scope=disease_scope,
                trace=trace,
            )
            agent_state = None
            while True:
                try:
                    event = next(gen)
                except StopIteration as stop:
                    agent_state = stop.value
                    break
                if event.get("type") == "status":
                    status_events.append(event)
                    yield event
            ctx = self._context_from_agent_state(
                question=question,
                standalone=standalone,
                history=history,
                topic_shift=topic_shift,
                disease_scope=disease_scope,
                trace=trace,
                condense_degraded=condense_degraded,
                agent_state=agent_state,
                status_events=status_events,
            )
        else:
            ctx = self._prepare_ask_linear(
                question=question,
                standalone=standalone,
                history=history,
                topic_shift=topic_shift,
                disease_scope=disease_scope,
                trace=trace,
                condense_degraded=condense_degraded,
            )
            for event in ctx.status_events:
                if event.get("type") == "status":
                    yield event

        yield status_event("generate", "生成回答中…")

        # Provisional cite labels so streaming tokens can decorate [Sn] → page codes.
        yield {
            "type": "cite_context",
            **build_cite_context_payload(ctx.hits, ctx.attached_references),
        }

        if ctx.early_answer is not None:
            yield {"type": "token", "text": ctx.early_answer}
            result = self._finalize_ask(
                ctx,
                answer=ctx.early_answer,
                generation_mode="text",
                generation_degraded=ctx.early_degraded,
                page_bboxes={},
            )
            yield {"type": "final", "payload": result.to_web_payload()}
            return

        raw_parts: List[str] = []
        generation_degraded: Optional[str] = None
        page_bboxes: Dict[str, List[float]] = {}
        page_summaries: Dict[str, str] = {}

        if ctx.use_vlm:
            generation_mode = "multimodal"
            if not self.vlm.available:
                generation_degraded = "vlm_api_unavailable"
                fallback = self.vlm._fallback(question, ctx.bundle)
                raw_parts.append(fallback)
                yield {"type": "token", "text": fallback}
            else:
                buffer = ""
                marker_hit = False
                try:
                    for delta in self.vlm.generate_stream(
                        ctx.standalone_question, ctx.bundle, route=ctx.route
                    ):
                        raw_parts.append(delta)
                        if marker_hit:
                            continue
                        buffer += delta
                        if PAGE_SUMMARY_MARKER in buffer:
                            before, _, after = buffer.partition(PAGE_SUMMARY_MARKER)
                            if before:
                                yield {"type": "token", "text": before}
                            buffer = PAGE_SUMMARY_MARKER + after
                            marker_hit = True
                        else:
                            # Keep a short tail so we don't split the marker across chunks.
                            keep = max(0, len(PAGE_SUMMARY_MARKER) - 1)
                            if len(buffer) > keep:
                                emit = buffer[:-keep] if keep else buffer
                                buffer = buffer[-keep:] if keep else ""
                                if emit:
                                    yield {"type": "token", "text": emit}
                    if not marker_hit and buffer:
                        yield {"type": "token", "text": buffer}
                except Exception as exc:  # pragma: no cover
                    generation_degraded = f"vlm_stream_failed:{type(exc).__name__}"
                    fallback = self.vlm._fallback(ctx.standalone_question, ctx.bundle)
                    raw_parts = [fallback]
                    yield {"type": "token", "text": fallback}
            raw_text = "".join(raw_parts)
            answer, page_summaries, page_bboxes = _split_answer_and_summary(raw_text)
            self._apply_summaries(page_summaries, ctx.trace)
            ctx.trace.log(
                "vlm_page_bboxes",
                {
                    "received_page_codes": sorted(page_bboxes.keys()),
                    "bboxes": page_bboxes,
                    "missing_for_figures": [
                        fig.page_code
                        for fig in ctx.figures
                        if fig.page_code and not lookup_vlm_bbox(fig.page_code, page_bboxes)
                    ],
                },
            )
        else:
            generation_mode = "text"
            gen_history = None if ctx.topic_shift else ctx.history
            try:
                for delta in self.qwen.generate_stream(
                    ctx.standalone_question,
                    ctx.bundle,
                    route=ctx.route,
                    history=gen_history,
                ):
                    raw_parts.append(delta)
                    yield {"type": "token", "text": delta}
            except Exception as exc:  # pragma: no cover
                generation_degraded = f"qwen_stream_failed:{type(exc).__name__}"
                fallback = self.qwen._fallback_answer(
                    ctx.standalone_question,
                    ctx.bundle,
                    reason="request_failed",
                    detail=str(exc),
                )
                raw_parts = [fallback]
                yield {"type": "token", "text": fallback}
            answer = "".join(raw_parts)
            if not self.qwen.api_key:
                generation_degraded = generation_degraded or "qwen_api_unavailable"

        result = self._finalize_ask(
            ctx,
            answer=answer,
            generation_mode=generation_mode,
            generation_degraded=generation_degraded,
            page_bboxes=page_bboxes,
        )
        yield {"type": "final", "payload": result.to_web_payload()}

    def _prepare_ask(
        self,
        question: str,
        trace_enabled: bool = True,
        history: Optional[List[dict]] = None,
    ) -> _AskContext:
        history = list(history or [])
        trace = TraceLogger(self.settings.logs_dir, enabled=trace_enabled)
        trace.log("query_received", {"question": question, "history_turns": len(history)})

        standalone, topic_shift, condense_degraded = self.qwen.condense_question(question, history)
        if topic_shift:
            history = []
        disease_scope = detect_disease_scope(standalone)
        routing_mode = str(getattr(self.settings, "routing_mode", "agentic") or "agentic").lower()
        if routing_mode == "agentic":
            orch = AgentOrchestrator(self)
            status_events: List[dict] = []
            agent_state = orch.run(
                question=question,
                standalone=standalone,
                history=history,
                disease_scope=disease_scope,
                trace=trace,
                on_status=lambda e: status_events.append(e),
            )
            return self._context_from_agent_state(
                question=question,
                standalone=standalone,
                history=history,
                topic_shift=topic_shift,
                disease_scope=disease_scope,
                trace=trace,
                condense_degraded=condense_degraded,
                agent_state=agent_state,
                status_events=status_events,
            )
        return self._prepare_ask_linear(
            question=question,
            standalone=standalone,
            history=history,
            topic_shift=topic_shift,
            disease_scope=disease_scope,
            trace=trace,
            condense_degraded=condense_degraded,
        )

    def _context_from_agent_state(
        self,
        *,
        question: str,
        standalone: str,
        history: List[dict],
        topic_shift: bool,
        disease_scope: DiseaseScope,
        trace: TraceLogger,
        condense_degraded: Optional[str],
        agent_state,
        status_events: List[dict],
    ) -> _AskContext:
        trace.log(
            "query_condensed",
            {
                "original": question,
                "standalone_question": standalone,
                "topic_shift": topic_shift,
                "degraded": condense_degraded,
            },
        )
        trace.log(
            "agent_finished",
            {
                "steps": agent_state.steps,
                "route": agent_state.route,
                "answer_kind": agent_state.answer_kind,
                "figure_count": len(agent_state.figures),
                "hit_count": len(agent_state.hits),
            },
        )

        if agent_state.early_answer is not None:
            empty_normalized = normalize_query(standalone)
            structured_trace = {
                "question": question,
                "standalone_question": standalone,
                "route": "none",
                "answer_kind": agent_state.answer_kind,
                "disease_scope": disease_scope.key,
                "retrieval_stages": [],
                "evidence_hits": [],
                "graph_steps": [],
                "agent_steps": agent_state.steps,
                "verification": {},
                "panel_hint": {"mode": "agent_direct", "evidence_count": 0, "graph_count": 0},
            }
            return _AskContext(
                question=question,
                standalone_question=standalone,
                history=history,
                answer_kind=agent_state.answer_kind,
                disease_scope=disease_scope,
                topic_shift=topic_shift,
                trace=trace,
                normalized=empty_normalized,
                hits=[],
                diagnostics={
                    "route": "none",
                    "triggers": [],
                    "disease_scope": disease_scope.key,
                    "retrieval_mode": "skipped",
                    "filters": {},
                    "degraded": [
                        d
                        for d in [
                            condense_degraded,
                            agent_state.early_degraded,
                            *list((agent_state.diagnostics or {}).get("degraded") or []),
                        ]
                        if d
                    ],
                },
                route="none",
                gate_degraded=None,
                attached_references=[],
                reference_links={},
                graph_hits=[],
                graph_triples=[],
                graph_context=[],
                figures=[],
                seed_page_code=None,
                seed_meta={"seed_page_code": None, "seed_source": "none"},
                bundle=EvidenceBundle(primary_hits=[]),
                use_vlm=False,
                structured_trace=structured_trace,
                early_answer=agent_state.early_answer,
                early_degraded=agent_state.early_degraded,
                agent_steps=list(agent_state.steps),
                status_events=status_events,
            )

        hits = list(agent_state.hits)
        normalized = normalize_query(standalone)
        route = str(agent_state.route or "evidence")
        diagnostics = dict(agent_state.diagnostics or {})
        diagnostics["route"] = route
        diagnostics["disease_scope"] = disease_scope.key
        diagnostics["degraded"] = list(diagnostics.get("degraded") or [])
        if condense_degraded:
            diagnostics["degraded"].append(condense_degraded)
        if agent_state.gate_degraded:
            diagnostics["degraded"].append(agent_state.gate_degraded)

        attached_references, reference_links = self.reference_resolver.resolve_references(
            hits, question=standalone
        )
        graph_hits = list(agent_state.graph_hits)
        graph_triples = []
        for hit in graph_hits:
            triple = hit.triple
            triple.score_components = getattr(hit, "components", {})
            graph_triples.append(triple)
        graph_context = self._graph_context(graph_hits)
        figures = list(agent_state.figures)
        seed_meta = dict(agent_state.seed_meta or {})
        seed_page_code = agent_state.seed_page_code or seed_meta.get("seed_page_code")

        # If agent never called view_pages but route is flowchart, gather deterministically.
        if not figures and route in ("flowchart", "hybrid"):
            figures, seed_meta = self._gather_figures(
                hits=hits,
                route=route,
                question=standalone,
                normalized=normalized,
                trace=trace,
            )
            seed_page_code = seed_meta.get("seed_page_code")

        bundle = EvidenceBundle(
            primary_hits=hits,
            attached_references=attached_references,
            reference_links=reference_links,
            figures=figures,
            graph_triples=graph_triples,
            graph_context=graph_context,
        )
        use_vlm = bool(figures) and self.vlm.available
        trace.log(
            "multimodal_decision",
            {
                "use_vlm": use_vlm,
                "vlm_available": self.vlm.available,
                "figure_count": len(figures),
                "figures": [fig.to_dict() for fig in figures],
                "seed": seed_meta,
            },
        )
        structured_trace = self._build_structured_trace(
            question,
            normalized.search_queries,
            hits,
            graph_hits,
            diagnostics,
            bundle,
        )
        structured_trace["standalone_question"] = standalone
        structured_trace["answer_kind"] = "guideline"
        structured_trace["disease_scope"] = disease_scope.key
        structured_trace["agent_steps"] = list(agent_state.steps)
        prompt_text = build_evidence_prompt(standalone, bundle, route=route)
        trace.log(
            "prompt_built",
            {
                "evidence_source_ids": [hit.document.source_id for hit in hits],
                "evidence_count": len(hits),
                "attached_reference_count": len(attached_references),
                "graph_triple_count": len(graph_triples),
                "prompt_char_count": len(prompt_text),
                "routing_mode": "agentic",
            },
        )
        trace.log("reasoning_path", structured_trace)
        return _AskContext(
            question=question,
            standalone_question=standalone,
            history=history,
            answer_kind="guideline",
            disease_scope=disease_scope,
            topic_shift=topic_shift,
            trace=trace,
            normalized=normalized,
            hits=hits,
            diagnostics=diagnostics,
            route=route,
            gate_degraded=agent_state.gate_degraded,
            attached_references=attached_references,
            reference_links=reference_links,
            graph_hits=graph_hits,
            graph_triples=graph_triples,
            graph_context=graph_context,
            figures=figures,
            seed_page_code=seed_page_code,
            seed_meta=seed_meta,
            bundle=bundle,
            use_vlm=use_vlm,
            structured_trace=structured_trace,
            agent_steps=list(agent_state.steps),
            status_events=status_events,
        )

    def _prepare_ask_linear(
        self,
        *,
        question: str,
        standalone: str,
        history: List[dict],
        topic_shift: bool,
        disease_scope: DiseaseScope,
        trace: TraceLogger,
        condense_degraded: Optional[str],
    ) -> _AskContext:
        effective_history = history
        trace.log(
            "query_condensed",
            {
                "original": question,
                "standalone_question": standalone,
                "topic_shift": topic_shift,
                "degraded": condense_degraded,
            },
        )

        intent, intent_degraded = self.qwen.classify_intent(standalone, effective_history)
        trace.log(
            "intent_classified",
            {
                "intent": intent,
                "degraded": intent_degraded,
                "disease_scope": disease_scope.key,
                "article_ids": list(disease_scope.article_ids),
                "module_codes": list(disease_scope.module_codes),
            },
        )

        empty_normalized = normalize_query(standalone)
        empty_bundle = EvidenceBundle(primary_hits=[])
        empty_diagnostics = {
            "route": "none",
            "triggers": [],
            "disease_scope": disease_scope.key,
            "retrieval_mode": "skipped",
            "filters": {},
            "degraded": [d for d in [condense_degraded, intent_degraded] if d],
        }

        if intent in ("chitchat", "general_medical"):
            if intent == "chitchat":
                early_answer, early_degraded = self.qwen.generate_chitchat(question)
            else:
                early_answer, early_degraded = self.qwen.generate_general_medical(standalone)
            structured_trace = {
                "question": question,
                "standalone_question": standalone,
                "route": "none",
                "answer_kind": intent,
                "disease_scope": disease_scope.key,
                "retrieval_stages": [],
                "evidence_hits": [],
                "graph_steps": [],
                "verification": {},
                "panel_hint": {"mode": "skipped", "evidence_count": 0, "graph_count": 0},
            }
            trace.log("early_answer", {"answer_kind": intent, "degraded": early_degraded})
            return _AskContext(
                question=question,
                standalone_question=standalone,
                history=effective_history,
                answer_kind=intent,
                disease_scope=disease_scope,
                topic_shift=topic_shift,
                trace=trace,
                normalized=empty_normalized,
                hits=[],
                diagnostics=empty_diagnostics,
                route="none",
                gate_degraded=None,
                attached_references=[],
                reference_links={},
                graph_hits=[],
                graph_triples=[],
                graph_context=[],
                figures=[],
                seed_page_code=None,
                seed_meta={"seed_page_code": None, "seed_source": "none"},
                bundle=empty_bundle,
                use_vlm=False,
                structured_trace=structured_trace,
                early_answer=early_answer,
                early_degraded=early_degraded,
            )

        normalized = normalize_query(standalone)
        trace.log(
            "query_normalized",
            {
                "original": normalized.original,
                "entities": normalized.entities,
                "expanded_queries": normalized.expanded_queries,
                "search_queries": normalized.search_queries,
            },
        )

        hits, diagnostics = self.retriever.retrieve(
            normalized, trace, disease_scope=disease_scope
        )
        route = str(diagnostics.get("route", "evidence"))
        diagnostics["degraded"] = list(diagnostics.get("degraded") or [])
        for extra in (condense_degraded, intent_degraded):
            if extra:
                diagnostics["degraded"].append(extra)

        gate_degraded: Optional[str] = None
        gated_indices: List[int] = list(range(1, len(hits) + 1))
        if self.settings.enable_evidence_gating and hits:
            hits, gate_degraded, gated_indices = self.qwen.gate_evidence(
                standalone,
                hits,
                protect_decision_pages=route in ("flowchart", "hybrid"),
            )
            trace.log(
                "evidence_gated",
                {
                    "enabled": True,
                    "kept_indices": gated_indices,
                    "kept_count": len(hits),
                    "degraded": gate_degraded,
                    "protect_decision_pages": route in ("flowchart", "hybrid"),
                },
            )
        else:
            trace.log("evidence_gated", {"enabled": False, "kept_count": len(hits)})

        attached_references, reference_links = self.reference_resolver.resolve_references(
            hits, question=standalone
        )

        graph_hits = self.kg_retriever.retrieve(
            standalone,
            top_k=self.settings.final_top_k,
            hops=self.settings.graph_depth,
        )
        graph_triples = []
        for hit in graph_hits:
            triple = hit.triple
            triple.score_components = getattr(hit, "components", {})
            graph_triples.append(triple)
        graph_context = self._graph_context(graph_hits)

        figures, seed_meta = self._gather_figures(
            hits=hits,
            route=route,
            question=standalone,
            normalized=normalized,
            trace=trace,
        )
        seed_page_code = seed_meta.get("seed_page_code")

        bundle = EvidenceBundle(
            primary_hits=hits,
            attached_references=attached_references,
            reference_links=reference_links,
            figures=figures,
            graph_triples=graph_triples,
            graph_context=graph_context,
        )
        use_vlm = bool(figures) and self.vlm.available
        trace.log(
            "multimodal_decision",
            {
                "use_vlm": use_vlm,
                "vlm_available": self.vlm.available,
                "figure_count": len(figures),
                "figures": [fig.to_dict() for fig in figures],
                "seed": seed_meta,
            },
        )
        trace.log(
            "attached_references",
            {
                "count": len(attached_references),
                "ref_numbers": [entry.ref_number for entry in attached_references],
                "reference_links": reference_links,
            },
        )
        prompt_text = build_evidence_prompt(standalone, bundle, route=route)
        structured_trace = self._build_structured_trace(
            question,
            normalized.search_queries,
            hits,
            graph_hits,
            diagnostics,
            bundle,
        )
        structured_trace["standalone_question"] = standalone
        structured_trace["answer_kind"] = "guideline"
        structured_trace["disease_scope"] = disease_scope.key
        trace.log(
            "prompt_built",
            {
                "evidence_source_ids": [hit.document.source_id for hit in hits],
                "evidence_count": len(hits),
                "attached_reference_count": len(attached_references),
                "graph_triple_count": len(graph_triples),
                "prompt_char_count": len(prompt_text),
            },
        )
        trace.log("reasoning_path", structured_trace)

        return _AskContext(
            question=question,
            standalone_question=standalone,
            history=effective_history,
            answer_kind="guideline",
            disease_scope=disease_scope,
            topic_shift=topic_shift,
            trace=trace,
            normalized=normalized,
            hits=hits,
            diagnostics=diagnostics,
            route=route,
            gate_degraded=gate_degraded,
            attached_references=attached_references,
            reference_links=reference_links,
            graph_hits=graph_hits,
            graph_triples=graph_triples,
            graph_context=graph_context,
            figures=figures,
            seed_page_code=seed_page_code,
            seed_meta=seed_meta,
            bundle=bundle,
            use_vlm=use_vlm,
            structured_trace=structured_trace,
        )

    def _finalize_ask(
        self,
        ctx: _AskContext,
        *,
        answer: str,
        generation_mode: str,
        generation_degraded: Optional[str],
        page_bboxes: Dict[str, List[float]],
    ) -> QAResult:
        answer = format_answer(answer)
        hits = ctx.hits
        figures = ctx.figures
        attached_references = ctx.attached_references
        reference_links = ctx.reference_links
        graph_triples = ctx.graph_triples
        graph_context = ctx.graph_context
        seed_page_code = ctx.seed_page_code
        diagnostics = ctx.diagnostics
        gate_degraded = ctx.gate_degraded
        structured_trace = ctx.structured_trace
        trace = ctx.trace
        question = ctx.question

        # Keep only evidence actually cited via [Sn]; renumber and remap figures.
        hits_before = len(hits)
        answer, hits, figures, citation_remap = filter_cited_hits(answer, hits, figures)
        attached_references, reference_links = filter_attached_references(
            hits, attached_references, reference_links
        )
        if citation_remap or hits_before != len(hits):
            trace.log(
                "citations_filtered",
                {
                    "hits_before": hits_before,
                    "hits_after": len(hits),
                    "remap": {str(k): v for k, v in citation_remap.items()},
                    "kept_source_ids": [hit.document.source_id for hit in hits],
                    "attached_reference_count": len(attached_references),
                },
            )

        figures_before = len(figures)
        figures = prune_figures_by_answer(
            answer,
            figures,
            hits,
            seed_page_code=seed_page_code,
            display_max=max(
                self.settings.display_max_figures,
                self._figure_ceiling(),
            ),
        )
        figures = compute_anchors(answer, figures, hits)
        figures.sort(
            key=lambda fig: (
                fig.anchor_paragraph is None,
                fig.anchor_paragraph if fig.anchor_paragraph is not None else 9999,
            )
        )
        trace.log(
            "figures_pruned",
            {
                "before": figures_before,
                "after": len(figures),
                "kept_page_codes": [fig.page_code for fig in figures],
                "seed_page_code": seed_page_code,
            },
        )
        crop_trace: Dict[str, object] = {"enabled": self.settings.crop_enabled, "figures": []}
        if self.settings.crop_enabled:
            figures, crop_trace = self._apply_figure_crops(figures, page_bboxes, trace)
        bundle = EvidenceBundle(
            primary_hits=hits,
            attached_references=attached_references,
            reference_links=reference_links,
            figures=figures,
            graph_triples=graph_triples,
            graph_context=graph_context,
        )

        degraded = list(diagnostics.get("degraded", []))
        if gate_degraded:
            degraded.append(gate_degraded)
        if generation_degraded:
            degraded.append(generation_degraded)
        structured_trace["answer_generated"] = {
            "answer": answer,
            "generation_mode": generation_mode,
            "used_source_ids": [hit.document.source_id for hit in hits],
            "attached_reference_ids": [entry.entry_id for entry in attached_references],
            "figure_paths": [fig.image_path for fig in figures],
            "crop_image_paths": [fig.crop_image_path for fig in figures],
            "figure_crop_methods": crop_trace.get("figures", []),
            "degraded": degraded,
        }
        trace.log("answer_generated", structured_trace["answer_generated"])

        verification = verify_answer(
            question,
            answer,
            hits,
            figures=figures,
            answer_kind=ctx.answer_kind,
        )
        structured_trace["verification_result"] = verification
        structured_trace["verification"] = verification
        trace.log("verification_result", verification)

        return QAResult(
            question=question,
            answer=answer,
            sources=[hit.document for hit in hits],
            verification=verification,
            run_id=trace.run_id,
            trace_path=str(trace.path),
            degraded=degraded,
            attached_references=attached_references,
            reference_links=reference_links,
            figures=figures,
            graph_triples=graph_triples,
            generation_mode=generation_mode,
            answer_kind=ctx.answer_kind,
            standalone_question=ctx.standalone_question,
            disease_scope=ctx.disease_scope.key,
            trace=structured_trace,
        )

    def _build_structured_trace(
        self,
        question: str,
        search_queries: List[str],
        hits: List[RetrievalHit],
        graph_hits,
        diagnostics,
        bundle: EvidenceBundle,
    ) -> dict:
        keywords = [w for q in search_queries for w in re.split(r"\W+", q) if len(w) > 2][:8]
        retrieval_stages = []
        evidence_hits = []
        for hit in hits:
            matched_sentence = self._best_sentence(hit.document.text or "", keywords)
            stage = {
                "source_id": hit.document.source_id,
                "printed_page_code": hit.document.printed_page_code,
                "page_type": hit.document.page_type,
                "section": hit.document.section,
                "pdf_page": hit.document.pdf_page,
                "retriever": hit.retriever,
                "rank": hit.rank,
                "raw_score": hit.score,
                "details": hit.details,
                "matched_sentence": matched_sentence,
                "paragraph_index": self._paragraph_index(hit.document.text or "", matched_sentence),
                "matched_terms": [kw for kw in keywords if kw.lower() in (hit.document.text or "").lower()],
            }
            retrieval_stages.append(stage)
            evidence_hits.append(
                {
                    "source_id": hit.document.source_id,
                    "matched_sentence": matched_sentence,
                    "paragraph_index": stage["paragraph_index"],
                    "matched_terms": stage["matched_terms"],
                    "confidence": float(hit.score or 0.0),
                }
            )
        graph_steps = []
        for idx, gh in enumerate(graph_hits, start=1):
            t = gh.triple
            graph_steps.append(
                {
                    "step": idx,
                    "triple_id": t.triple_id,
                    "subject": t.subject_name,
                    "relation": t.relation,
                    "object": t.object_name,
                    "confidence": t.confidence,
                    "validation_status": t.validation_status,
                    "source_ids": t.evidence_source_ids,
                    "evidence_text": t.evidence_text,
                    "score_components": getattr(gh, "components", {}),
                }
            )
        rerank_comparison = [
            {
                "source_id": h.document.source_id,
                "final_rank": h.rank,
                "final_score": h.score,
                "reranker": h.retriever,
                "details": h.details,
            }
            for h in hits
        ]
        return {
            "question": question,
            "route": diagnostics.get("route"),
            "retrieval_mode": diagnostics.get("retrieval_mode"),
            "triggers": diagnostics.get("triggers", []),
            "filters": diagnostics.get("filters", {}),
            "retrieval_stages": retrieval_stages,
            "evidence_hits": evidence_hits,
            "rerank_comparison": rerank_comparison,
            "graph_steps": graph_steps,
            "verification": {},
            "panel_hint": {
                "mode": diagnostics.get("retrieval_mode"),
                "evidence_count": len(hits),
                "graph_count": len(graph_steps),
            },
            "agent_steps": [],
        }

    def _best_sentence(self, text: str, keywords: List[str]) -> str:
        sentences = re.split(r"(?<=[。.!?\n])\s*", text)
        best = sentences[0] if sentences else text[:160]
        best_score = -1
        for sent in sentences:
            score = sum(1 for kw in keywords if kw.lower() in sent.lower())
            if score > best_score and sent.strip():
                best = sent
                best_score = score
        return best.strip()[:260]

    def _paragraph_index(self, text: str, sentence: str) -> int:
        paragraphs = [p for p in re.split(r"\n{2,}", text) if p.strip()]
        for idx, para in enumerate(paragraphs):
            if sentence and sentence in para:
                return idx
        return 0

    def _graph_context(self, graph_hits) -> List[str]:
        lines: List[str] = []
        for idx, hit in enumerate(graph_hits, start=1):
            triple = hit.triple
            evidence_ids = ", ".join(triple.evidence_source_ids) if triple.evidence_source_ids else "无"
            lines.append(
                f"[G{idx}] {triple.subject_name}({triple.subject_type}) --{triple.relation}--> "
                f"{triple.object_name}({triple.object_type}) | 置信度={triple.confidence:.2f} | "
                f"来源={evidence_ids} | 状态={triple.validation_status}"
            )
        return lines

    def _rebuild_bm25_with_summaries(self) -> None:
        """Re-tokenise the BM25 corpus with cached page summaries merged in.

        No-op when the cache is empty (avoids a pointless re-tokenise at startup).
        """
        if self.summary_cache.count == 0:
            return
        augmented = self.summary_cache.augment_documents(self.bm25.documents)
        self.bm25 = BM25Store(augmented)

    def _apply_summaries(self, summaries, trace: TraceLogger) -> None:
        """Persist newly produced page summaries and refresh the BM25 index."""
        if not summaries:
            return
        if self.summary_cache.set_many(summaries):
            self._rebuild_bm25_with_summaries()
            self.retriever.bm25 = self.bm25
            trace.log("page_summaries_cached", {"page_codes": sorted(summaries.keys())})

    def _index_for_hit(self, hits: List[RetrievalHit], hit: RetrievalHit) -> Optional[int]:
        for idx, item in enumerate(hits, start=1):
            if item.document.source_id == hit.document.source_id:
                return idx
        return None

    def _figure_ceiling(self) -> int:
        return int(
            getattr(self.settings, "figure_ceiling", None)
            or getattr(self.settings, "max_images", 4)
            or 4
        )

    def _gather_figures(
        self,
        hits: List[RetrievalHit],
        route: str,
        question: str,
        normalized: NormalizedQuery,
        trace: TraceLogger,
    ) -> Tuple[List[FigureReference], Dict[str, object]]:
        """Render flowchart images: seed decision page first, then hits, then neighbours."""
        empty_meta: Dict[str, object] = {"seed_page_code": None, "seed_source": "none"}
        if route not in ("flowchart", "hybrid"):
            return [], empty_meta

        seed_code, seed_source = self.graph_navigator.pick_seed(
            question, hits, normalized.entities
        )
        if not seed_code:
            return [], empty_meta

        budget = self._figure_ceiling()
        figures: List[FigureReference] = []
        seen_pages: set[int] = set()
        page_summaries = self.summary_cache.all_summaries()

        def _add(
            pdf_page: int,
            page_code: Optional[str],
            caption: str,
            source_index: Optional[int],
        ) -> bool:
            if pdf_page in seen_pages or len(figures) >= budget:
                return False
            image_path = self.page_renderer.render(pdf_page)
            if image_path is None:
                return False
            seen_pages.add(pdf_page)
            figures.append(
                FigureReference(
                    page_code=page_code,
                    pdf_page=pdf_page,
                    image_path=str(image_path),
                    caption=caption,
                    source_index=source_index,
                )
            )
            return True

        # Phase 1: seed decision page (must not be crowded out by regimen tables)
        seed_page = self.graph_navigator.get_page(seed_code)
        seed_hit_index: Optional[int] = None
        if seed_page:
            for hit in hits:
                if normalize_page_code(hit.document.printed_page_code) == seed_code:
                    seed_hit_index = self._index_for_hit(hits, hit)
                    break
            _add(
                seed_page.pdf_page,
                seed_page.printed_page_code or seed_code,
                seed_page.printed_page_code or seed_code,
                seed_hit_index,
            )

        # Phase 2: clinical guideline hits — prefer decision pages, then tables
        ordered_hits = sorted(
            [
                h
                for h in hits
                if h.document.page_type == "clinical_guideline"
            ],
            key=lambda h: (
                0 if is_decision_flow_page(h.document.printed_page_code) else 1,
                h.rank or 999,
            ),
        )
        for hit in ordered_hits:
            doc = hit.document
            if doc.pdf_page in seen_pages:
                continue
            idx = self._index_for_hit(hits, hit)
            _add(
                doc.pdf_page,
                doc.printed_page_code,
                doc.section or doc.printed_page_code or "",
                idx,
            )
            if len(figures) >= budget:
                break

        # Phase 3: graph neighbours
        neighbours: List[tuple[int, str]] = []
        if len(figures) < budget:
            neighbours = self.graph_navigator.expand(
                seed_code,
                query=question,
                page_summaries=page_summaries,
                fanout=self.settings.graph_fanout,
                depth=self.settings.graph_depth,
                budget=budget - len(figures),
            )
            for pdf_page, page_code in neighbours:
                _add(pdf_page, page_code, f"由 {seed_code} 跳转", None)
                if len(figures) >= budget:
                    break

        figures = backfill_source_indices(figures, hits)

        meta = {
            "seed_page_code": seed_code,
            "seed_source": seed_source,
            "budget": budget,
            "neighbour_codes": [code for _page, code in neighbours],
            "figure_page_codes": [fig.page_code for fig in figures],
            "source_indices": [fig.source_index for fig in figures],
        }
        trace.log("figures_gathered", meta)
        return figures, meta

    def _crop_method_label(self, source: str) -> str:
        labels = {
            "vlm": "VLM 返回 bbox（兜底）",
            "table": "PyMuPDF 表格检测",
            "flowchart": "PyMuPDF 流程图检测",
            "figure": "PyMuPDF 矢量图检测",
            "text": "PyMuPDF 文本块检测",
            "pymupdf": "PyMuPDF 检测兜底",
            "none": "未裁剪（展示整页）",
        }
        return labels.get(source, source)

    @staticmethod
    def _bboxes_differ(a: Optional[List[float]], b: Optional[List[float]]) -> bool:
        if a is None or b is None:
            return a != b
        return tuple(round(v, 4) for v in a) != tuple(round(v, 4) for v in b)

    def _resolve_crop_bbox(
        self,
        fig: FigureReference,
        page_bboxes: Dict[str, List[float]],
    ) -> tuple[
        Optional[List[float]],
        Optional[List[float]],
        bool,
        str,
        str,
        Optional[List[float]],
        Optional[List[float]],
        Optional[str],
    ]:
        """Return (compact_bbox, full_bbox, has_footnote, crop_method, bbox_quality, vlm_bbox, deterministic_bbox, det_method)."""
        prefer = self.settings.crop_prefer
        vlm_bbox = lookup_vlm_bbox(fig.page_code, page_bboxes)
        compact_det, full_det, det_method, has_footnote = detect_display_bboxes_for_page(
            self.page_renderer,
            fig.pdf_page,
            min_area_ratio=self.settings.crop_min_area,
        )
        deterministic_bbox = compact_det
        figure_bbox = detect_figure_bbox_for_page(
            self.page_renderer,
            fig.pdf_page,
            min_area_ratio=self.settings.crop_min_area,
        )
        quality = assess_vlm_bbox_quality(
            vlm_bbox,
            page_bboxes,
            max_area=self.settings.crop_vlm_max_area,
            dedup_guard=self.settings.crop_vlm_dedup_guard,
            deterministic_bbox=deterministic_bbox,
        )
        vlm_usable = vlm_bbox is not None and quality == "good"

        if prefer == "vlm":
            if vlm_usable and vlm_bbox:
                return vlm_bbox, None, False, "vlm", quality, vlm_bbox, compact_det, det_method
            if compact_det and det_method:
                return compact_det, full_det, has_footnote, det_method, quality, vlm_bbox, compact_det, det_method
        elif prefer == "detect":
            if figure_bbox:
                return figure_bbox, figure_bbox, False, "figure", quality, vlm_bbox, compact_det, det_method
            if vlm_usable and vlm_bbox:
                return vlm_bbox, None, False, "vlm", quality, vlm_bbox, compact_det, det_method
        else:
            # auto (default): deterministic geometry first, VLM fallback
            if compact_det and det_method:
                return (
                    compact_det,
                    full_det,
                    has_footnote,
                    det_method,
                    quality,
                    vlm_bbox,
                    compact_det,
                    det_method,
                )
            if vlm_usable and vlm_bbox:
                return vlm_bbox, None, False, "vlm", quality, vlm_bbox, compact_det, det_method

        return None, None, False, "none", quality, vlm_bbox, compact_det, det_method

    def _apply_figure_crops(
        self,
        figures: List[FigureReference],
        page_bboxes: Dict[str, List[float]],
        trace: TraceLogger,
    ) -> tuple[List[FigureReference], Dict[str, object]]:
        crop_dpi = self.settings.crop_dpi or self.settings.page_image_dpi
        cropped: List[FigureReference] = []
        trace_rows: List[Dict[str, object]] = []

        for fig in figures:
            (
                compact_bbox,
                full_bbox,
                has_footnote,
                crop_method,
                bbox_quality,
                vlm_bbox,
                deterministic_bbox,
                det_method,
            ) = self._resolve_crop_bbox(fig, page_bboxes)
            crop_path: Optional[str] = None
            crop_full_path: Optional[str] = None
            if compact_bbox:
                rendered = self.page_renderer.render_crop(
                    fig.pdf_page,
                    compact_bbox,
                    padding=self.settings.crop_padding,
                    dpi=crop_dpi,
                )
                if rendered is not None:
                    crop_path = str(rendered)

            if has_footnote and full_bbox and self._bboxes_differ(full_bbox, compact_bbox):
                rendered_full = self.page_renderer.render_crop(
                    fig.pdf_page,
                    full_bbox,
                    padding=self.settings.crop_padding,
                    dpi=crop_dpi,
                )
                if rendered_full is not None:
                    crop_full_path = str(rendered_full)

            cropped.append(
                FigureReference(
                    page_code=fig.page_code,
                    pdf_page=fig.pdf_page,
                    image_path=fig.image_path,
                    caption=fig.caption,
                    source_index=fig.source_index,
                    crop_image_path=crop_path,
                    crop_full_image_path=crop_full_path,
                    anchor_paragraph=fig.anchor_paragraph,
                    anchor_key=fig.anchor_key,
                    crop_method=crop_method,
                    bbox_quality=bbox_quality,
                )
            )
            trace_rows.append(
                {
                    "page_code": fig.page_code,
                    "pdf_page": fig.pdf_page,
                    "crop_method": crop_method,
                    "crop_method_label": self._crop_method_label(crop_method),
                    "bbox_quality": bbox_quality,
                    "bbox_used": compact_bbox,
                    "compact_bbox": compact_bbox,
                    "full_bbox": full_bbox,
                    "has_footnote": has_footnote,
                    "vlm_bbox": vlm_bbox,
                    "deterministic_bbox": deterministic_bbox,
                    "deterministic_method": det_method,
                    "pymupdf_bbox": deterministic_bbox,
                    "crop_image_path": crop_path,
                    "crop_full_image_path": crop_full_path,
                    "anchor_paragraph": fig.anchor_paragraph,
                    "anchor_key": fig.anchor_key,
                }
            )

        summary = {
            "enabled": True,
            "prefer": self.settings.crop_prefer,
            "vlm_count": sum(1 for row in trace_rows if row["crop_method"] == "vlm"),
            "deterministic_count": sum(
                1
                for row in trace_rows
                if row["crop_method"] in ("table", "flowchart", "figure", "text", "pymupdf")
            ),
            "pymupdf_count": sum(
                1
                for row in trace_rows
                if row["crop_method"] in ("table", "flowchart", "figure", "text", "pymupdf")
            ),
            "none_count": sum(1 for row in trace_rows if row["crop_method"] == "none"),
            "figures": trace_rows,
        }
        trace.log("figures_cropped", summary)
        return cropped, summary
