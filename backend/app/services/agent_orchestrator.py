"""Agentic retrieval loop: tool-calling over guidelines / KG / page images."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence

from backend.app.models import FigureReference, RetrievalHit
from backend.app.services.agent_tools import (
    TOOL_DEFINITIONS,
    AgentState,
    extract_ready_payload,
    parse_tool_arguments,
    status_event,
    status_for_tool,
    summarize_candidates,
    summarize_hits_for_agent,
)
from backend.app.services.disease_scope import DiseaseScope
from backend.app.services.dlbcl_flow_map import (
    is_decision_flow_page,
    normalize_page_code,
    resolve_entry_page,
)
from backend.app.services.figure_selection import backfill_source_indices
from backend.app.services.query_normalizer import normalize_query
from backend.app.services.tracing import TraceLogger


StatusCallback = Callable[[Dict[str, Any]], None]


class AgentOrchestrator:
    """Runs the tool-calling loop and mutates an AgentState."""

    def __init__(self, qa_service: Any):
        self.qa = qa_service
        self.settings = qa_service.settings

    @property
    def figure_ceiling(self) -> int:
        return int(
            getattr(self.settings, "figure_ceiling", None)
            or getattr(self.settings, "max_images", 4)
            or 4
        )

    @staticmethod
    def _should_upgrade_to_flowchart(state: AgentState) -> bool:
        """Upgrade evidence→flowchart only when flowchart intent is genuine.

        A leaked low-rank decision page (common after BM25 summary injection)
        must NOT force the VLM path. Require either an intent-map seed that is
        a decision page, or a rank-1 hit that is itself a decision page.
        """
        if state.route != "evidence":
            return False
        if is_decision_flow_page(state.seed_page_code):
            return True
        if state.hits and is_decision_flow_page(state.hits[0].document.printed_page_code):
            return True
        return False

    def run(
        self,
        *,
        question: str,
        standalone: str,
        history: Sequence[dict],
        disease_scope: DiseaseScope,
        trace: TraceLogger,
        on_status: Optional[StatusCallback] = None,
    ) -> AgentState:
        state = AgentState()
        emit = on_status or (lambda _e: None)
        emit(status_event("planning", "规划中…"))

        if not self.qa.qwen.api_key:
            return self._linear_fallback(
                standalone=standalone,
                disease_scope=disease_scope,
                trace=trace,
                state=state,
                reason="agent_no_api_key",
            )

        messages = self.qa.qwen.build_agent_messages(standalone, history)
        max_steps = max(1, int(getattr(self.settings, "agent_max_steps", 4) or 4))

        for step_idx in range(max_steps):
            assistant_msg, tool_calls, degraded = self.qa.qwen.run_tool_turn(
                messages, tools=TOOL_DEFINITIONS, timeout=45
            )
            if degraded:
                state.diagnostics.setdefault("degraded", []).append(degraded)
                trace.log("agent_degraded", {"reason": degraded, "step": step_idx})
                return self._linear_fallback(
                    standalone=standalone,
                    disease_scope=disease_scope,
                    trace=trace,
                    state=state,
                    reason=degraded,
                )

            messages.append(assistant_msg)
            content = str(assistant_msg.get("content") or "")
            ready = extract_ready_payload(content)
            if ready and not tool_calls:
                state.ready = True
                route = str(ready.get("route") or state.route or "evidence")
                if route in ("flowchart", "evidence", "hybrid"):
                    state.route = route
                state.steps.append(
                    {"step": step_idx + 1, "type": "ready", "route": state.route}
                )
                trace.log("agent_ready", {"step": step_idx + 1, "route": state.route})
                break

            if not tool_calls:
                # Model stopped without tools — treat as ready if we already have hits.
                state.ready = True
                if content:
                    state.steps.append(
                        {"step": step_idx + 1, "type": "stop", "content": content[:200]}
                    )
                break

            for call in tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                args = parse_tool_arguments(fn.get("arguments"))
                emit(status_for_tool(name, args))
                result_text = self._dispatch(
                    name,
                    args,
                    state=state,
                    standalone=standalone,
                    disease_scope=disease_scope,
                    trace=trace,
                )
                state.steps.append(
                    {
                        "step": step_idx + 1,
                        "tool": name,
                        "arguments": args,
                        "result_preview": result_text[:500],
                    }
                )
                trace.log(
                    "agent_tool_call",
                    {
                        "step": step_idx + 1,
                        "tool": name,
                        "arguments": args,
                        "result_preview": result_text[:800],
                    },
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "name": name,
                        "content": result_text,
                    }
                )
                if state.early_answer is not None:
                    state.ready = True
                    return state

        if not state.hits and state.early_answer is None:
            # Ensure at least one retrieval if the agent forgot.
            emit(status_event("search", "补充检索指南中…"))
            self._tool_search_guidelines(
                {"query": standalone, "kind": "any"},
                state=state,
                standalone=standalone,
                disease_scope=disease_scope,
                trace=trace,
            )

        if self._should_upgrade_to_flowchart(state):
            state.route = "flowchart"

        state.ready = True
        return state

    def run_streaming(
        self,
        *,
        question: str,
        standalone: str,
        history: Sequence[dict],
        disease_scope: DiseaseScope,
        trace: TraceLogger,
    ) -> Generator[Dict[str, Any], None, AgentState]:
        state = AgentState()
        yield status_event("planning", "规划中…")

        if not self.qa.qwen.api_key:
            state = self._linear_fallback(
                standalone=standalone,
                disease_scope=disease_scope,
                trace=trace,
                state=state,
                reason="agent_no_api_key",
            )
            yield status_event("fallback", "回退到线性检索…")
            return state

        messages = self.qa.qwen.build_agent_messages(standalone, history)
        max_steps = max(1, int(getattr(self.settings, "agent_max_steps", 4) or 4))

        for step_idx in range(max_steps):
            assistant_msg, tool_calls, degraded = self.qa.qwen.run_tool_turn(
                messages, tools=TOOL_DEFINITIONS, timeout=45
            )
            if degraded:
                state.diagnostics.setdefault("degraded", []).append(degraded)
                trace.log("agent_degraded", {"reason": degraded, "step": step_idx})
                yield status_event("fallback", "智能体异常，回退线性检索…")
                state = self._linear_fallback(
                    standalone=standalone,
                    disease_scope=disease_scope,
                    trace=trace,
                    state=state,
                    reason=degraded,
                )
                return state

            messages.append(assistant_msg)
            content = str(assistant_msg.get("content") or "")
            ready = extract_ready_payload(content)
            if ready and not tool_calls:
                state.ready = True
                route = str(ready.get("route") or state.route or "evidence")
                if route in ("flowchart", "evidence", "hybrid"):
                    state.route = route
                state.steps.append(
                    {"step": step_idx + 1, "type": "ready", "route": state.route}
                )
                trace.log("agent_ready", {"step": step_idx + 1, "route": state.route})
                break

            if not tool_calls:
                state.ready = True
                break

            for call in tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                args = parse_tool_arguments(fn.get("arguments"))
                yield status_for_tool(name, args)
                result_text = self._dispatch(
                    name,
                    args,
                    state=state,
                    standalone=standalone,
                    disease_scope=disease_scope,
                    trace=trace,
                )
                state.steps.append(
                    {
                        "step": step_idx + 1,
                        "tool": name,
                        "arguments": args,
                        "result_preview": result_text[:500],
                    }
                )
                trace.log(
                    "agent_tool_call",
                    {
                        "step": step_idx + 1,
                        "tool": name,
                        "arguments": args,
                        "result_preview": result_text[:800],
                    },
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "name": name,
                        "content": result_text,
                    }
                )
                if state.early_answer is not None:
                    state.ready = True
                    return state

        if not state.hits and state.early_answer is None:
            yield status_event("search", "补充检索指南中…")
            self._tool_search_guidelines(
                {"query": standalone, "kind": "any"},
                state=state,
                standalone=standalone,
                disease_scope=disease_scope,
                trace=trace,
            )

        if self._should_upgrade_to_flowchart(state):
            state.route = "flowchart"

        state.ready = True
        return state

    def _dispatch(
        self,
        name: str,
        args: Dict[str, Any],
        *,
        state: AgentState,
        standalone: str,
        disease_scope: DiseaseScope,
        trace: TraceLogger,
    ) -> str:
        if name == "search_guidelines":
            return self._tool_search_guidelines(
                args,
                state=state,
                standalone=standalone,
                disease_scope=disease_scope,
                trace=trace,
            )
        if name == "query_graph":
            return self._tool_query_graph(args, state=state, disease_scope=disease_scope)
        if name == "view_pages":
            return self._tool_view_pages(args, state=state, standalone=standalone, trace=trace)
        if name == "respond_directly":
            return self._tool_respond_directly(args, state=state, question=standalone)
        return json.dumps({"error": f"unknown_tool:{name}"}, ensure_ascii=False)

    def _tool_search_guidelines(
        self,
        args: Dict[str, Any],
        *,
        state: AgentState,
        standalone: str,
        disease_scope: DiseaseScope,
        trace: TraceLogger,
    ) -> str:
        query = str(args.get("query") or standalone).strip() or standalone
        kind = str(args.get("kind") or "any").strip().lower()
        if kind not in ("flowchart", "evidence", "any"):
            kind = "any"
        if kind == "flowchart":
            state.route = "flowchart"
        elif kind == "evidence":
            state.route = "evidence"
        elif state.route == "evidence":
            state.route = "hybrid" if kind == "any" else state.route

        normalized = normalize_query(query)
        # Temporarily bias route_query via expanded query keywords when kind set.
        if kind == "flowchart" and "therapy" not in " ".join(normalized.search_queries).lower():
            normalized.search_queries = list(normalized.search_queries) + ["therapy treatment"]
        elif kind == "evidence" and "prognosis" not in " ".join(normalized.search_queries).lower():
            normalized.search_queries = list(normalized.search_queries) + ["definition prognosis"]

        hits, diagnostics = self.qa.retriever.retrieve(
            normalized, trace, disease_scope=disease_scope
        )
        route = str(diagnostics.get("route") or state.route)
        if kind == "flowchart":
            route = "flowchart"
        elif kind == "evidence":
            route = "evidence"
        state.route = route
        state.diagnostics = diagnostics

        protect = route in ("flowchart", "hybrid")
        gate_degraded = None
        if self.settings.enable_evidence_gating and hits:
            pre_gate_hits = list(hits)
            hits, gate_degraded, gated_indices = self.qa.qwen.gate_evidence(
                standalone, hits, protect_decision_pages=protect
            )
            # Always reinject intent seed decision page if present in raw retrieval.
            hits = self._ensure_seed_hit(standalone, hits, diagnostics, disease_scope, trace)
            hits, disease_guard = self.qa._reinject_disease_hits(pre_gate_hits, hits, disease_scope)
            trace.log(
                "evidence_gated",
                {
                    "enabled": True,
                    "kept_indices": gated_indices,
                    "kept_count": len(hits),
                    "degraded": gate_degraded,
                    "protect_decision_pages": protect,
                    "disease_guard": disease_guard,
                },
            )
        state.gate_degraded = gate_degraded
        state.hits = hits

        seed_code = resolve_entry_page(standalone, normalize_query(standalone).entities)
        state.seed_page_code = seed_code
        state.candidate_pages = self._build_candidates(hits, seed_code, standalone)
        state.seed_meta = {
            "seed_page_code": seed_code,
            "seed_source": "intent_map" if seed_code else "none",
            "candidate_page_codes": [c.get("page_code") for c in state.candidate_pages],
        }
        return (
            f"检索完成：{len(hits)} 条证据，route={route}。\n"
            f"{summarize_hits_for_agent(hits)}\n\n"
            f"候选页（供 view_pages 点名）：\n{summarize_candidates(state.candidate_pages)}"
        )

    def _ensure_seed_hit(
        self,
        standalone: str,
        hits: List[RetrievalHit],
        diagnostics: Dict[str, Any],
        disease_scope: DiseaseScope,
        trace: TraceLogger,
    ) -> List[RetrievalHit]:
        seed = resolve_entry_page(standalone, normalize_query(standalone).entities)
        if not seed:
            return hits
        seed_norm = normalize_page_code(seed)
        for hit in hits:
            if normalize_page_code(hit.document.printed_page_code) == seed_norm:
                return hits
        # Look up seed page from navigator and synthesize a hit if in KB.
        page = self.qa.graph_navigator.get_page(seed)
        if not page:
            return hits
        from backend.app.models import SearchDocument

        synth = RetrievalHit(
            document=SearchDocument(
                source_id=f"page-{seed.replace(' ', '_')}",
                page_type="clinical_guideline",
                pdf_page=page.pdf_page,
                text=page.clean_text or seed,
                printed_page_code=page.printed_page_code or seed,
                module_code=page.module_code,
            ),
            score=0.0,
            retriever="seed_inject",
            rank=len(hits) + 1,
        )
        merged = list(hits) + [synth]
        trace.log("seed_hit_injected", {"seed_page_code": seed})
        return merged

    def _build_candidates(
        self,
        hits: List[RetrievalHit],
        seed_code: Optional[str],
        question: str,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        seen: set[str] = set()
        summaries = self.qa.summary_cache.all_summaries()

        def add(code: Optional[str], page_kind: str, summary: str, pdf_page: Optional[int]) -> None:
            norm = normalize_page_code(code)
            if not norm or norm in seen:
                return
            seen.add(norm)
            candidates.append(
                {
                    "page_code": norm,
                    "page_kind": page_kind,
                    "summary": summary[:160],
                    "pdf_page": pdf_page,
                }
            )

        if seed_code:
            page = self.qa.graph_navigator.get_page(seed_code)
            add(
                seed_code,
                "decision",
                summaries.get(normalize_page_code(seed_code) or "", "")
                or "意图映射决策入口页",
                page.pdf_page if page else None,
            )

        for hit in hits:
            doc = hit.document
            if doc.page_type != "clinical_guideline":
                continue
            code = doc.printed_page_code
            if is_decision_flow_page(code):
                kind = "decision"
            elif code and " OF " in (normalize_page_code(code) or ""):
                kind = "table"
            else:
                kind = "guideline"
            snippet = (doc.text or "").replace("\n", " ")[:120]
            add(code, kind, summaries.get(normalize_page_code(code) or "", "") or snippet, doc.pdf_page)

        if seed_code:
            neighbours = self.qa.graph_navigator.expand(
                seed_code,
                query=question,
                page_summaries=summaries,
                fanout=self.settings.graph_fanout,
                depth=self.settings.graph_depth,
                budget=self.figure_ceiling,
            )
            for pdf_page, page_code in neighbours:
                add(
                    page_code,
                    "decision" if is_decision_flow_page(page_code) else "guideline",
                    summaries.get(normalize_page_code(page_code) or "", "")
                    or f"由 {seed_code} 跳转",
                    pdf_page,
                )
        return candidates[:12]

    def _tool_query_graph(
        self, args: Dict[str, Any], *, state: AgentState, disease_scope: Optional[DiseaseScope] = None
    ) -> str:
        question = str(args.get("question") or "").strip()
        relation = args.get("relation")
        relation_s = str(relation).strip() if relation else None
        hits = self.qa.kg_retriever.retrieve(
            question,
            top_k=self.settings.final_top_k,
            hops=self.settings.graph_depth,
            relation=relation_s,
            disease_scope=disease_scope,
        )
        state.graph_hits = hits
        if not hits:
            return "知识图谱无足够相关的三元组（已按问题关系过滤）。"
        lines = []
        for idx, hit in enumerate(hits, start=1):
            t = hit.triple
            lines.append(
                f"[G{idx}] {t.subject_name} --{t.relation}--> {t.object_name} "
                f"(score={hit.score:.2f}, conf={t.confidence:.2f})"
            )
        return "图谱命中：\n" + "\n".join(lines)

    def _tool_view_pages(
        self,
        args: Dict[str, Any],
        *,
        state: AgentState,
        standalone: str,
        trace: TraceLogger,
    ) -> str:
        raw_codes = args.get("page_codes") or []
        if isinstance(raw_codes, str):
            raw_codes = [raw_codes]
        allowed = {
            normalize_page_code(c.get("page_code")): c for c in state.candidate_pages if c.get("page_code")
        }
        # Also allow any hit page codes.
        for hit in state.hits:
            code = normalize_page_code(hit.document.printed_page_code)
            if code and code not in allowed:
                allowed[code] = {
                    "page_code": code,
                    "page_kind": "decision" if is_decision_flow_page(code) else "guideline",
                    "summary": "",
                    "pdf_page": hit.document.pdf_page,
                }

        selected: List[str] = []
        for code in raw_codes:
            norm = normalize_page_code(str(code))
            if norm and norm in allowed and norm not in selected:
                selected.append(norm)
            if len(selected) >= self.figure_ceiling:
                break

        # If agent asked for pages but none matched, fall back to seed + top table.
        if not selected and state.candidate_pages:
            for pref_kind in ("decision", "table", "guideline"):
                for cand in state.candidate_pages:
                    if cand.get("page_kind") == pref_kind:
                        code = normalize_page_code(cand.get("page_code"))
                        if code and code not in selected:
                            selected.append(code)
                        if len(selected) >= min(2, self.figure_ceiling):
                            break
                if selected:
                    break

        figures: List[FigureReference] = []
        seen_pages: set[int] = set()
        for code in selected:
            meta = allowed.get(code) or {}
            pdf_page = meta.get("pdf_page")
            page = self.qa.graph_navigator.get_page(code)
            if pdf_page is None and page:
                pdf_page = page.pdf_page
            if pdf_page is None:
                for hit in state.hits:
                    if normalize_page_code(hit.document.printed_page_code) == code:
                        pdf_page = hit.document.pdf_page
                        break
            if pdf_page is None or pdf_page in seen_pages:
                continue
            image_path = self.qa.page_renderer.render(int(pdf_page))
            if image_path is None:
                continue
            seen_pages.add(int(pdf_page))
            source_index = None
            for idx, hit in enumerate(state.hits, start=1):
                if normalize_page_code(hit.document.printed_page_code) == code:
                    source_index = idx
                    break
            figures.append(
                FigureReference(
                    page_code=code,
                    pdf_page=int(pdf_page),
                    image_path=str(image_path),
                    caption=code,
                    source_index=source_index,
                )
            )

        figures = backfill_source_indices(figures, state.hits)
        state.figures = figures
        if figures and state.route == "evidence":
            state.route = "flowchart"
        meta = {
            "seed_page_code": state.seed_page_code,
            "seed_source": state.seed_meta.get("seed_source", "none"),
            "budget": self.figure_ceiling,
            "figure_page_codes": [f.page_code for f in figures],
            "requested": selected,
            "source": "view_pages",
        }
        state.seed_meta = {**state.seed_meta, **meta}
        trace.log("figures_gathered", meta)
        return (
            f"已准备 {len(figures)} 张页面图片（上限 {self.figure_ceiling}）："
            + ", ".join(f.page_code or "" for f in figures)
        )

    def _tool_respond_directly(
        self,
        args: Dict[str, Any],
        *,
        state: AgentState,
        question: str,
    ) -> str:
        kind = str(args.get("kind") or "chitchat").strip().lower()
        if kind not in ("chitchat", "general_medical"):
            kind = "chitchat"
        state.answer_kind = kind
        if kind == "chitchat":
            answer, degraded = self.qa.qwen.generate_chitchat(question)
        else:
            answer, degraded = self.qa.qwen.generate_general_medical(question)
        state.early_answer = answer
        state.early_degraded = degraded
        state.route = "none"
        return f"已生成{kind}回复，无需继续检索。"

    def _linear_fallback(
        self,
        *,
        standalone: str,
        disease_scope: DiseaseScope,
        trace: TraceLogger,
        state: AgentState,
        reason: str,
    ) -> AgentState:
        state.diagnostics.setdefault("degraded", []).append(reason)
        self._tool_search_guidelines(
            {"query": standalone, "kind": "any"},
            state=state,
            standalone=standalone,
            disease_scope=disease_scope,
            trace=trace,
        )
        # Deterministic figures: seed + top guideline hits.
        figures, seed_meta = self.qa._gather_figures(
            hits=state.hits,
            route=state.route if state.route in ("flowchart", "hybrid") else "flowchart",
            question=standalone,
            normalized=normalize_query(standalone),
            trace=trace,
        )
        state.figures = figures
        state.seed_meta = seed_meta
        state.seed_page_code = seed_meta.get("seed_page_code")
        state.ready = True
        return state
