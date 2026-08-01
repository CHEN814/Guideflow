from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.settings import Settings

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    type: str
    properties: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: str
    target: str
    label: str
    type: str
    properties: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "type": self.type,
            "properties": self.properties,
        }


class Neo4jGraphService:
    def __init__(self, settings: Settings) -> None:
        if GraphDatabase is None:  # pragma: no cover
            raise RuntimeError("neo4j package is required. Install with: pip install -r requirements.txt")
        if not settings.neo4j_password:
            raise ValueError("NEO4J_PASSWORD is required")
        self.settings = settings
        self.driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def import_triples(self, triples: Sequence[Any], clear: Optional[bool] = None, batch_size: Optional[int] = None) -> Dict[str, int]:
        clear = self.settings.neo4j_clear if clear is None else clear
        batch_size = self.settings.neo4j_batch_size if batch_size is None else int(batch_size)
        batch_size = max(1, batch_size)
        imported = 0
        with self.driver.session(database=self.settings.neo4j_database) as session:
            if clear:
                session.run("MATCH (n) DETACH DELETE n")
            for start in range(0, len(triples), batch_size):
                batch = triples[start : start + batch_size]
                payload = [self._triple_payload(t) for t in batch]
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (s:OntologyConcept {id: row.subject_id})
                    SET s.name = row.subject_name,
                        s.label = row.subject_name,
                        s.type = row.subject_type
                    MERGE (o:OntologyConcept {id: row.object_id})
                    SET o.name = row.object_name,
                        o.label = row.object_name,
                        o.type = row.object_type
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
                        t.evidence_kind = row.evidence_kind,
                        t.review_status = row.review_status,
                        t.llm_score = row.llm_score,
                        t.reviewer = row.reviewer
                    MERGE (s)-[:SUBJECT_OF]->(t)
                    MERGE (t)-[:OBJECT_OF]->(o)
                    WITH row, s, o, t
                    CALL apoc.create.relationship(s, row.relation, {confidence: row.confidence, evidence_kind: row.evidence_kind}, o) YIELD rel
                    RETURN count(rel) AS rel_count
                    """,
                    rows=payload,
                )
                imported += len(payload)
        return {"imported": imported}

    def neighborhood(self, seed: str, limit: int = 60, depth: int = 1) -> Dict[str, Any]:
        seed = (seed or "").strip()
        if not seed:
            raise ValueError("seed is required")
        limit = max(10, min(int(limit or 60), 250))
        depth = max(0, min(int(depth or 1), 3))

        with self.driver.session(database=self.settings.neo4j_database) as session:
            if seed.startswith("triple:"):
                records = session.run(
                    """
                    MATCH (t:TrustedTriple {triple_id: $seed})
                    OPTIONAL MATCH (s)-[rs:SUBJECT_OF]->(t)
                    OPTIONAL MATCH (t)-[:OBJECT_OF]->(o)
                    RETURN t, collect(DISTINCT s) AS subjects, collect(DISTINCT o) AS objects
                    """,
                    seed=seed,
                )
                row = records.single()
                if not row:
                    return {"nodes": [], "edges": [], "center": seed, "stats": {"found": 0}}
                nodes = []
                edges = []
                triple = row["t"]
                nodes.extend([self._node_from_record(triple)])
                for subj in row["subjects"] or []:
                    if subj is None:
                        continue
                    nodes.append(self._node_from_record(subj))
                    edges.append(self._edge_from_subject(subj, triple))
                for obj in row["objects"] or []:
                    if obj is None:
                        continue
                    nodes.append(self._node_from_record(obj))
                    edges.append(self._edge_from_object(triple, obj))
                return self._pack_graph(nodes, edges, seed, depth)

            cypher = f"""
            MATCH (seed)
            WHERE coalesce(seed.name, seed.title, seed.label, seed.canonical_id, seed.triple_id, seed.page_id, seed.chunk_id, seed.entry_id, seed.article_id) = $seed
               OR seed.canonical_id = $seed
               OR seed.triple_id = $seed
               OR seed.page_id = $seed
               OR seed.chunk_id = $seed
               OR seed.entry_id = $seed
               OR seed.article_id = $seed
               OR seed.printed_page_code = $seed
               OR seed.ref_number = $seed
            CALL {{
                WITH seed
                MATCH path=(seed)-[*0..{depth}]-(nbr)
                RETURN path
                LIMIT $limit
            }}
            RETURN path
            """
            rows = session.run(cypher, seed=seed, limit=limit).values()
            nodes: Dict[str, GraphNode] = {}
            edges: Dict[str, GraphEdge] = {}
            for (path,) in rows:
                self._collect_path(path, nodes, edges)
            return self._pack_graph(list(nodes.values()), list(edges.values()), seed, depth)

    @staticmethod
    def _triple_payload(triple: Any) -> Dict[str, Any]:
        return {
            "triple_id": getattr(triple, "triple_id", ""),
            "subject_id": getattr(triple, "subject_id", ""),
            "subject_name": getattr(triple, "subject_name", ""),
            "subject_type": getattr(triple, "subject_type", ""),
            "relation": getattr(triple, "relation", "RELATED_TO"),
            "object_id": getattr(triple, "object_id", ""),
            "object_name": getattr(triple, "object_name", ""),
            "object_type": getattr(triple, "object_type", ""),
            "confidence": float(getattr(triple, "confidence", 0.0)),
            "validation_status": getattr(triple, "validation_status", "candidate"),
            "evidence_text": getattr(triple, "evidence_text", ""),
            "evidence_kind": getattr(triple, "evidence_kind", "text"),
            "review_status": getattr(triple, "review_status", "trusted"),
            "llm_score": getattr(triple, "llm_score", None),
            "reviewer": getattr(triple, "reviewer", None),
        }

    def _pack_graph(self, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge], center: str, depth: int) -> Dict[str, Any]:
        dedup_nodes = {node.id: node for node in nodes}
        dedup_edges = {edge.id: edge for edge in edges}
        return {
            "center": center,
            "depth": depth,
            "nodes": [node.to_dict() for node in dedup_nodes.values()],
            "edges": [edge.to_dict() for edge in dedup_edges.values()],
            "stats": {
                "nodes": len(dedup_nodes),
                "edges": len(dedup_edges),
            },
        }

    def _collect_path(self, path: Any, nodes: Dict[str, GraphNode], edges: Dict[str, GraphEdge]) -> None:
        for node in path.nodes:
            gnode = self._node_from_record(node)
            nodes[gnode.id] = gnode
        for rel in path.relationships:
            edge = self._edge_from_rel(rel)
            edges[edge.id] = edge

    @staticmethod
    def _labels(record: Any) -> List[str]:
        try:
            return list(record.labels)
        except Exception:
            return []

    @staticmethod
    def _node_id(record: Any) -> str:
        for key in ("canonical_id", "triple_id", "page_id", "chunk_id", "entry_id", "article_id", "source_id"):
            value = getattr(record, key, None)
            if value:
                return str(value)
        name = getattr(record, "name", None) or getattr(record, "title", None) or getattr(record, "label", None)
        if name:
            return str(name)
        return str(getattr(record, "id", "node"))

    @staticmethod
    def _node_label(record: Any) -> str:
        for key in ("name", "title", "label", "printed_page_code", "triple_id"):
            value = getattr(record, key, None)
            if value:
                return str(value)
        return str(Neo4jGraphService._node_id(record))

    def _node_from_record(self, record: Any) -> GraphNode:
        labels = self._labels(record)
        node_type = labels[0] if labels else record.__class__.__name__
        props = dict(record)
        return GraphNode(
            id=self._node_id(record),
            label=self._node_label(record),
            type=node_type,
            properties=props,
        )

    @staticmethod
    def _edge_from_rel(rel: Any) -> GraphEdge:
        props = dict(rel)
        return GraphEdge(
            id=str(getattr(rel, "id", f"rel:{getattr(rel, 'type', 'edge')}:{getattr(rel, 'start_node_id', '')}:{getattr(rel, 'end_node_id', '')}")),
            source=str(getattr(rel, "start_node_id", "")),
            target=str(getattr(rel, "end_node_id", "")),
            label=str(getattr(rel, "type", "EDGE")),
            type=str(getattr(rel, "type", "EDGE")),
            properties=props,
        )

    @staticmethod
    def _edge_from_subject(subject: Any, triple: Any) -> GraphEdge:
        sid = str(getattr(subject, "canonical_id", getattr(subject, "id", "")))
        tid = str(getattr(triple, "triple_id", ""))
        return GraphEdge(id=f"{sid}-SUBJECT_OF-{tid}", source=sid, target=tid, label="SUBJECT_OF", type="SUBJECT_OF", properties={})

    @staticmethod
    def _edge_from_object(triple: Any, obj: Any) -> GraphEdge:
        oid = str(getattr(obj, "canonical_id", getattr(obj, "id", "")))
        tid = str(getattr(triple, "triple_id", ""))
        return GraphEdge(id=f"{tid}-OBJECT_OF-{oid}", source=tid, target=oid, label="OBJECT_OF", type="OBJECT_OF", properties={})
