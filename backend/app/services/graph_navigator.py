"""Controlled link-graph navigation over NCCN clinical guideline pages.

NCCN flowchart pages link to each other as a graph (a page can jump back to the
table of contents, which links to every disease). Blindly following links would
explode the number of pages/images. This navigator expands from a single
starting page through the four gates from the plan:

  1. edge classification - only follow "flow" edges, drop navigation/chrome ones
  2. same-module        - only follow edges whose target shares the source module
  3. depth / fan-out    - bounded hop depth and bounded out-degree per node
  4. budget cap         - a hard global cap, with de-duplication

When a page has multiple flow edges, candidates are ranked by query relevance
(anchor text + target page summary overlap) before fan-out truncation.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.app.models import GuidelinePage, PageLink, StructuredKnowledgeBase
from backend.app.services.dlbcl_flow_map import (
    is_decision_flow_page,
    normalize_page_code,
    pick_seed_page_code,
)
from backend.app.services.figure_selection import lexical_overlap
from backend.app.services.pdf_extractor import classify_edge
from backend.app.services.store import load_knowledge_base


def _module_of(page_code: Optional[str]) -> Optional[str]:
    if not page_code:
        return None
    return page_code.split("-")[0].strip() or None


class GraphNavigator:
    def __init__(self, knowledge_base: StructuredKnowledgeBase):
        self._by_code: Dict[str, GuidelinePage] = {}
        for page in knowledge_base.guideline_pages:
            if page.page_type == "clinical_guideline" and page.printed_page_code:
                key = normalize_page_code(page.printed_page_code)
                if key:
                    self._by_code[key] = page

    @classmethod
    def from_path(cls, path: Path) -> "GraphNavigator":
        return cls(load_knowledge_base(path))

    def get_page(self, page_code: Optional[str]) -> Optional[GuidelinePage]:
        if not page_code:
            return None
        return self._by_code.get(normalize_page_code(page_code) or "")

    def pick_seed(
        self,
        query: str,
        hits,
        entities: Optional[List[str]] = None,
    ) -> tuple[Optional[str], str]:
        return pick_seed_page_code(query, hits, entities)

    def _score_link(
        self,
        link: PageLink,
        target: GuidelinePage,
        query: str,
        page_summaries: Dict[str, str],
    ) -> float:
        target_code = normalize_page_code(target.printed_page_code) or ""
        summary = page_summaries.get(target_code, "")
        anchor = link.anchor_text or target_code
        return lexical_overlap(query, anchor, summary, target.clean_text[:400])

    def _rank_flow_links(
        self,
        page: GuidelinePage,
        start_module: Optional[str],
        visited: set[str],
        query: str,
        page_summaries: Dict[str, str],
    ) -> List[Tuple[float, PageLink, GuidelinePage]]:
        ranked: List[Tuple[float, PageLink, GuidelinePage]] = []
        for link in page.outgoing_links:
            target_code = normalize_page_code(link.target_page_code)
            if not target_code or target_code in visited:
                continue
            edge_type = link.edge_type or classify_edge(link.anchor_text, link.target_page_code)
            if edge_type != "flow":
                continue
            if _module_of(target_code) != start_module:
                continue
            target_page = self._by_code.get(target_code)
            if not target_page:
                continue
            score = self._score_link(link, target_page, query, page_summaries)
            ranked.append((score, link, target_page))
        ranked.sort(key=lambda item: (-item[0], item[2].printed_page_code or ""))
        return ranked

    def expand(
        self,
        start_page_code: Optional[str],
        query: str = "",
        page_summaries: Optional[Dict[str, str]] = None,
        fanout: int = 3,
        depth: int = 1,
        budget: int = 4,
    ) -> List[Tuple[int, str]]:
        """Return downstream (pdf_page, page_code) neighbours of a flowchart page.

        Excludes the start page itself. Order is BFS with query-ranked fan-out;
        truncated at ``budget``.
        """
        summaries = page_summaries or {}
        start_norm = normalize_page_code(start_page_code)
        if not start_norm or start_norm not in self._by_code:
            return []

        start_module = _module_of(start_norm)
        visited = {start_norm}
        out: List[Tuple[int, str]] = []
        queue: deque[Tuple[str, int]] = deque([(start_norm, 0)])

        while queue and len(out) < budget:
            code, hop = queue.popleft()
            if hop >= depth:
                continue
            page = self._by_code.get(code)
            if not page:
                continue

            ranked = self._rank_flow_links(page, start_module, visited, query, summaries)
            followed = 0
            for _score, _link, target_page in ranked:
                target = normalize_page_code(target_page.printed_page_code)
                if not target or target in visited:
                    continue
                visited.add(target)
                out.append((target_page.pdf_page, target))
                queue.append((target, hop + 1))
                followed += 1
                if len(out) >= budget or followed >= fanout:
                    break

        return out[:budget]


__all__ = [
    "GraphNavigator",
    "is_decision_flow_page",
    "normalize_page_code",
]
