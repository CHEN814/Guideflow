from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from backend.app.models import DiscussionChunk, GuidelinePage, ReferenceEntry, StructuredKnowledgeBase
from backend.app.settings import Settings
from backend.app.services.knowledge_graph import KnowledgeGraphBundle, load_or_build_knowledge_graph_bundle
from backend.app.services.store import load_knowledge_base

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None


class Neo4jGraphImporter:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        if GraphDatabase is None:  # pragma: no cover
            raise RuntimeError("neo4j package is required. Install with: pip install -r requirements.txt")
        if not password:
            raise ValueError("NEO4J_PASSWORD is required")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.driver.verify_connectivity()

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jGraphImporter":
        return cls(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password or "",
            database=settings.neo4j_database,
        )

    def close(self) -> None:
        self.driver.close()

    def import_knowledge_graph(
        self,
        kb: StructuredKnowledgeBase,
        bundle: KnowledgeGraphBundle,
        clear: bool = False,
        batch_size: int = 500,
    ) -> Dict[str, int]:
        pages = list(kb.guideline_pages)
        chunks = list(kb.discussion_chunks)
        refs = list(kb.reference_entries)
        ontology_rows = [
            {
                "canonical_id": concept.canonical_id,
                "concept_type": concept.concept_type,
                "name": concept.name,
                "aliases": list(concept.aliases),
            }
            for concept in bundle.ontology
        ]
        triple_rows = [triple.to_dict() for triple in bundle.triples]
        article_rows = self._article_rows(chunks, refs)

        stats = {
            "ontology_nodes": 0,
            "triple_nodes": 0,
            "page_nodes": 0,
            "article_nodes": 0,
            "chunk_nodes": 0,
            "reference_nodes": 0,
            "page_links": 0,
            "triple_subject_links": 0,
            "triple_object_links": 0,
            "triple_evidence_links": 0,
            "article_chunk_links": 0,
            "chunk_reference_links": 0,
        }

        with self.driver.session(database=self.database) as session:
            if clear:
                session.execute_write(self._clear_graph)

            stats["ontology_nodes"] = self._write_rows(session, self._merge_ontology_cypher(), ontology_rows, batch_size)
            stats["triple_nodes"] = self._write_rows(session, self._merge_triple_nodes_cypher(), triple_rows, batch_size)
            stats["page_nodes"] = self._write_rows(session, self._merge_page_nodes_cypher(), self._page_rows(pages), batch_size)
            stats["article_nodes"] = self._write_rows(session, self._merge_article_nodes_cypher(), article_rows, batch_size)
            stats["chunk_nodes"] = self._write_rows(session, self._merge_chunk_nodes_cypher(), self._chunk_rows(chunks), batch_size)
            stats["reference_nodes"] = self._write_rows(session, self._merge_reference_nodes_cypher(), self._reference_rows(refs), batch_size)
            stats["page_links"] = self._write_rows(session, self._merge_page_link_cypher(), self._page_link_rows(pages), batch_size)
            stats["triple_subject_links"] = self._write_rows(session, self._merge_triple_subject_cypher(), self._triple_subject_rows(bundle), batch_size)
            stats["triple_object_links"] = self._write_rows(session, self._merge_triple_object_cypher(), self._triple_object_rows(bundle), batch_size)
            stats["triple_evidence_links"] = self._write_rows(session, self._merge_triple_evidence_cypher(), self._triple_evidence_rows(bundle), batch_size)
            stats["article_chunk_links"] = self._write_rows(session, self._merge_article_chunk_cypher(), self._article_chunk_rows(chunks), batch_size)
            stats["chunk_reference_links"] = self._write_rows(session, self._merge_chunk_reference_cypher(), self._chunk_reference_rows(chunks, refs), batch_size)

        stats["total_nodes"] = sum(
            stats[key]
            for key in ("ontology_nodes", "triple_nodes", "page_nodes", "article_nodes", "chunk_nodes", "reference_nodes")
        )
        stats["total_relationships"] = sum(
            stats[key]
            for key in (
                "page_links",
                "triple_subject_links",
                "triple_object_links",
                "triple_evidence_links",
                "article_chunk_links",
                "chunk_reference_links",
            )
        )
        return stats

    @staticmethod
    def _clear_graph(tx) -> None:
        tx.run("MATCH (n) DETACH DELETE n").consume()

    @staticmethod
    def _write_rows(session, cypher: str, rows: Sequence[dict], batch_size: int) -> int:
        rows = list(rows)
        if not rows:
            return 0
        written = 0
        step = max(1, batch_size)
        for start in range(0, len(rows), step):
            batch = rows[start : start + step]
            session.execute_write(lambda tx, b=batch: tx.run(cypher, rows=b).consume())
            written += len(batch)
        return written

    @staticmethod
    def _merge_ontology_cypher() -> str:
        return """
        UNWIND $rows AS row
        MERGE (n:OntologyConcept {canonical_id: row.canonical_id})
        SET n.concept_type = row.concept_type,
            n.name = row.name,
            n.aliases = row.aliases
        """

    @staticmethod
    def _merge_triple_nodes_cypher() -> str:
        return """
        UNWIND $rows AS row
        MERGE (t:TrustedTriple {triple_id: row.triple_id})
        SET t.subject_id = row.subject_id,
            t.subject_name = row.subject_name,
            t.subject_type = row.subject_type,
            t.relation = row.relation,
            t.object_id = row.object_id,
            t.object_name = row.object_name,
            t.object_type = row.object_type,
            t.confidence = row.confidence,
            t.validation_status = row.validation_status,
            t.evidence_text = row.evidence_text,
            t.evidence_source_ids = row.evidence_source_ids,
            t.evidence_kind = row.evidence_kind,
            t.llm_score = row.llm_score,
            t.reviewer = row.reviewer,
            t.review_status = row.review_status
        """

    @staticmethod
    def _merge_page_nodes_cypher() -> str:
        return """
        UNWIND $rows AS row
        MERGE (p:Page {page_id: row.page_id})
        SET p.pdf_page = row.pdf_page,
            p.page_type = row.page_type,
            p.printed_page_code = row.printed_page_code,
            p.module_code = row.module_code,
            p.clean_text = row.clean_text,
            p.needs_review = row.needs_review,
            p.source_id = row.source_id
        """

    @staticmethod
    def _merge_article_nodes_cypher() -> str:
        return """
        UNWIND $rows AS row
        MERGE (a:Article {article_id: row.article_id})
        SET a.title = row.title,
            a.chunk_count = row.chunk_count,
            a.reference_count = row.reference_count
        """

    @staticmethod
    def _merge_chunk_nodes_cypher() -> str:
        return """
        UNWIND $rows AS row
        MERGE (c:DiscussionChunk {chunk_id: row.chunk_id})
        SET c.article_id = row.article_id,
            c.article_title = row.article_title,
            c.pdf_page = row.pdf_page,
            c.ms_page_code = row.ms_page_code,
            c.section = row.section,
            c.clean_text = row.clean_text,
            c.reference_ids = row.reference_ids,
            c.source_id = row.source_id
        """

    @staticmethod
    def _merge_reference_nodes_cypher() -> str:
        return """
        UNWIND $rows AS row
        MERGE (r:Reference {entry_id: row.entry_id})
        SET r.article_id = row.article_id,
            r.ref_number = row.ref_number,
            r.text = row.text,
            r.pmid = row.pmid,
            r.doi = row.doi,
            r.url = row.url,
            r.source_id = row.source_id
        """

    @staticmethod
    def _merge_page_link_cypher() -> str:
        return """
        UNWIND $rows AS row
        MATCH (src:Page {page_id: row.source_page_id})
        MATCH (dst:Page {printed_page_code: row.target_page_code})
        MERGE (src)-[r:LINKS_TO {target_page_code: row.target_page_code, anchor_text: row.anchor_text}]->(dst)
        SET r.edge_type = row.edge_type,
            r.target_pdf_page = row.target_pdf_page
        """

    @staticmethod
    def _merge_triple_subject_cypher() -> str:
        return """
        UNWIND $rows AS row
        MATCH (src:OntologyConcept {canonical_id: row.subject_id})
        MATCH (t:TrustedTriple {triple_id: row.triple_id})
        MERGE (src)-[r:SUBJECT_OF]->(t)
        SET r.relation = row.relation,
            r.confidence = row.confidence,
            r.validation_status = row.validation_status,
            r.evidence_kind = row.evidence_kind,
            r.evidence_source_ids = row.evidence_source_ids
        """

    @staticmethod
    def _merge_triple_object_cypher() -> str:
        return """
        UNWIND $rows AS row
        MATCH (t:TrustedTriple {triple_id: row.triple_id})
        MATCH (dst:OntologyConcept {canonical_id: row.object_id})
        MERGE (t)-[:OBJECT_OF]->(dst)
        """

    @staticmethod
    def _merge_triple_evidence_cypher() -> str:
        return """
        UNWIND $rows AS row
        MATCH (src {source_id: row.source_id})
        MATCH (t:TrustedTriple {triple_id: row.triple_id})
        MERGE (src)-[r:TRIPLE_EVIDENCE]->(t)
        SET r.evidence_kind = row.evidence_kind,
            r.confidence = row.confidence
        """

    @staticmethod
    def _merge_article_chunk_cypher() -> str:
        return """
        UNWIND $rows AS row
        MATCH (a:Article {article_id: row.article_id})
        MATCH (c:DiscussionChunk {chunk_id: row.chunk_id})
        MERGE (a)-[:HAS_CHUNK]->(c)
        """

    @staticmethod
    def _merge_chunk_reference_cypher() -> str:
        return """
        UNWIND $rows AS row
        MATCH (c:DiscussionChunk {chunk_id: row.chunk_id})
        MATCH (r:Reference {entry_id: row.entry_id})
        MERGE (c)-[rel:CITES_REFERENCE {ref_number: row.ref_number}]->(r)
        SET rel.ref_number = row.ref_number
        """

    @staticmethod
    def _page_rows(pages: Sequence[GuidelinePage]) -> List[dict]:
        rows = []
        for page in pages:
            rows.append(
                {
                    "source_id": page.page_id,
                    "page_id": page.page_id,
                    "pdf_page": page.pdf_page,
                    "page_type": page.page_type,
                    "printed_page_code": page.printed_page_code,
                    "module_code": page.module_code,
                    "clean_text": page.clean_text[:1500],
                    "needs_review": page.needs_review,
                }
            )
        return rows

    @staticmethod
    def _chunk_rows(chunks: Sequence[DiscussionChunk]) -> List[dict]:
        rows = []
        for chunk in chunks:
            rows.append(
                {
                    "source_id": chunk.chunk_id,
                    "chunk_id": chunk.chunk_id,
                    "article_id": chunk.article_id,
                    "article_title": chunk.article_title,
                    "pdf_page": chunk.pdf_page,
                    "ms_page_code": chunk.ms_page_code,
                    "section": chunk.section,
                    "clean_text": chunk.clean_text[:3000],
                    "reference_ids": list(chunk.reference_ids),
                }
            )
        return rows

    @staticmethod
    def _reference_rows(refs: Sequence[ReferenceEntry]) -> List[dict]:
        rows = []
        for ref in refs:
            rows.append(
                {
                    "source_id": ref.entry_id,
                    "entry_id": ref.entry_id,
                    "article_id": ref.article_id,
                    "ref_number": ref.ref_number,
                    "text": ref.text[:2000],
                    "pmid": ref.pmid,
                    "doi": ref.doi,
                    "url": ref.url,
                }
            )
        return rows

    @staticmethod
    def _article_rows(chunks: Sequence[DiscussionChunk], refs: Sequence[ReferenceEntry]) -> List[dict]:
        articles: Dict[str, dict] = {}
        for chunk in chunks:
            article = articles.setdefault(
                chunk.article_id,
                {"article_id": chunk.article_id, "title": chunk.article_title, "chunk_count": 0, "ref_numbers": set()},
            )
            article["chunk_count"] += 1
            article["title"] = article["title"] or chunk.article_title
            article["ref_numbers"].update(chunk.reference_ids)
        for ref in refs:
            article = articles.setdefault(
                ref.article_id,
                {"article_id": ref.article_id, "title": ref.article_id, "chunk_count": 0, "ref_numbers": set()},
            )
            article["ref_numbers"].add(ref.ref_number)
        rows = []
        for article in articles.values():
            rows.append(
                {
                    "article_id": article["article_id"],
                    "title": article["title"],
                    "chunk_count": article["chunk_count"],
                    "reference_count": len(article["ref_numbers"]),
                }
            )
        return rows

    @staticmethod
    def _page_link_rows(pages: Sequence[GuidelinePage]) -> List[dict]:
        rows = []
        for page in pages:
            for link in page.outgoing_links:
                if not link.target_page_code:
                    continue
                rows.append(
                    {
                        "source_page_id": page.page_id,
                        "target_page_code": link.target_page_code,
                        "anchor_text": link.anchor_text,
                        "edge_type": link.edge_type or "unknown",
                        "target_pdf_page": link.target_pdf_page,
                    }
                )
        return rows

    @staticmethod
    def _triple_subject_rows(bundle: KnowledgeGraphBundle) -> List[dict]:
        return [
            {
                "triple_id": triple.triple_id,
                "subject_id": triple.subject_id,
                "relation": triple.relation,
                "confidence": triple.confidence,
                "validation_status": triple.validation_status,
                "evidence_kind": triple.evidence_kind,
                "evidence_source_ids": triple.evidence_source_ids,
            }
            for triple in bundle.triples
        ]

    @staticmethod
    def _triple_object_rows(bundle: KnowledgeGraphBundle) -> List[dict]:
        return [
            {
                "triple_id": triple.triple_id,
                "object_id": triple.object_id,
            }
            for triple in bundle.triples
        ]

    @staticmethod
    def _triple_evidence_rows(bundle: KnowledgeGraphBundle) -> List[dict]:
        rows = []
        for triple in bundle.triples:
            for source_id in triple.evidence_source_ids:
                rows.append(
                    {
                        "source_id": source_id,
                        "triple_id": triple.triple_id,
                        "evidence_kind": triple.evidence_kind,
                        "confidence": triple.confidence,
                    }
                )
        return rows

    @staticmethod
    def _chunk_reference_rows(chunks: Sequence[DiscussionChunk], refs: Sequence[ReferenceEntry]) -> List[dict]:
        ref_lookup = {(ref.article_id, ref.ref_number): ref.entry_id for ref in refs}
        rows = []
        for chunk in chunks:
            for ref_number in chunk.reference_ids:
                entry_id = ref_lookup.get((chunk.article_id, ref_number))
                if entry_id:
                    rows.append({"chunk_id": chunk.chunk_id, "entry_id": entry_id, "ref_number": ref_number})
        return rows


def import_knowledge_graph_to_neo4j(kb_path: Path, kg_path: Path, settings: Settings, clear: bool = False, batch_size: Optional[int] = None) -> Dict[str, int]:
    kb = load_knowledge_base(kb_path)
    bundle = load_or_build_knowledge_graph_bundle(kb_path, kg_path)
    importer = Neo4jGraphImporter.from_settings(settings)
    try:
        return importer.import_knowledge_graph(
            kb,
            bundle,
            clear=clear or settings.neo4j_clear,
            batch_size=batch_size or settings.neo4j_batch_size,
        )
    finally:
        importer.close()
