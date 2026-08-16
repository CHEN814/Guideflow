"""PubMed E-utilities client: ESearch + EFetch with rate limit and TTL cache."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class PubmedArticle:
    pmid: str
    title: str = ""
    abstract: str = ""
    journal: Optional[str] = None
    year: Optional[str] = None
    doi: Optional[str] = None
    pub_types: List[str] = field(default_factory=list)
    mesh: List[str] = field(default_factory=list)
    mesh_major: List[str] = field(default_factory=list)
    language: Optional[str] = None

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "journal": self.journal,
            "year": self.year,
            "doi": self.doi,
            "pub_types": list(self.pub_types),
            "mesh": list(self.mesh),
            "mesh_major": list(self.mesh_major),
            "language": self.language,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PubmedArticle":
        return cls(
            pmid=str(data.get("pmid") or ""),
            title=str(data.get("title") or ""),
            abstract=str(data.get("abstract") or ""),
            journal=data.get("journal"),
            year=data.get("year"),
            doi=data.get("doi"),
            pub_types=list(data.get("pub_types") or []),
            mesh=list(data.get("mesh") or []),
            mesh_major=list(data.get("mesh_major") or []),
            language=data.get("language"),
        )


class PubmedClient:
    """Thin NCBI E-utilities wrapper with disk TTL cache and rate limiting."""

    def __init__(
        self,
        *,
        email: str = "guideflow@example.com",
        api_key: Optional[str] = None,
        tool: str = "guideflow",
        cache_dir: Optional[Path] = None,
        query_cache_ttl_s: int = 86400,
        article_cache_ttl_s: int = 86400 * 30,
        esearch_timeout_s: float = 2.0,
        efetch_timeout_s: float = 3.0,
        session: Optional[requests.Session] = None,
    ):
        self.email = email
        self.api_key = api_key
        self.tool = tool
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/cache/pubmed")
        self.query_cache_dir = self.cache_dir / "query"
        self.article_cache_dir = self.cache_dir / "article"
        self.query_cache_dir.mkdir(parents=True, exist_ok=True)
        self.article_cache_dir.mkdir(parents=True, exist_ok=True)
        self.query_cache_ttl_s = query_cache_ttl_s
        self.article_cache_ttl_s = article_cache_ttl_s
        self.esearch_timeout_s = esearch_timeout_s
        self.efetch_timeout_s = efetch_timeout_s
        self.session = session or requests.Session()
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        # NCBI: ~10/s with key, ~3/s without
        self._min_interval = 0.11 if api_key else 0.37

    def _throttle(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()

    def _common_params(self) -> Dict[str, str]:
        params = {"tool": self.tool, "email": self.email}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _read_cache(self, path: Path, ttl_s: int) -> Optional[Any]:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        ts = float(payload.get("ts") or 0)
        if time.time() - ts > ttl_s:
            return None
        return payload.get("data")

    def _write_cache(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _query_cache_key(term: str, retmax: int) -> str:
        raw = f"{term}|{retmax}|relevance"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def esearch(
        self,
        term: str,
        *,
        retmax: int = 30,
        sort: str = "relevance",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Return {"count": int, "pmids": [str, ...], "term": str, "cached": bool}."""
        cache_path = self.query_cache_dir / f"{self._query_cache_key(term, retmax)}.json"
        if use_cache:
            cached = self._read_cache(cache_path, self.query_cache_ttl_s)
            if isinstance(cached, dict) and "pmids" in cached:
                return {
                    "count": int(cached.get("count") or len(cached.get("pmids") or [])),
                    "pmids": [str(x) for x in (cached.get("pmids") or [])],
                    "term": term,
                    "cached": True,
                }

        params = {
            **self._common_params(),
            "db": "pubmed",
            "term": term,
            "retmax": str(retmax),
            "retmode": "json",
            "sort": sort,
        }
        self._throttle()
        resp = self.session.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params=params,
            timeout=self.esearch_timeout_s,
        )
        resp.raise_for_status()
        body = resp.json()
        result = body.get("esearchresult") or {}
        pmids = [str(x) for x in (result.get("idlist") or [])]
        count = int(result.get("count") or len(pmids))
        payload = {"count": count, "pmids": pmids}
        if use_cache:
            self._write_cache(cache_path, payload)
        return {**payload, "term": term, "cached": False}

    def efetch(self, pmids: Sequence[str], *, use_cache: bool = True) -> List[PubmedArticle]:
        """Fetch article metadata/abstracts for PMIDs (batched)."""
        ids = [str(p).strip() for p in pmids if str(p).strip()]
        if not ids:
            return []

        articles: List[PubmedArticle] = []
        missing: List[str] = []
        for pmid in ids:
            cache_path = self.article_cache_dir / f"{pmid}.json"
            if use_cache:
                cached = self._read_cache(cache_path, self.article_cache_ttl_s)
                if isinstance(cached, dict) and cached.get("pmid"):
                    articles.append(PubmedArticle.from_dict(cached))
                    continue
            missing.append(pmid)

        # Preserve request order: fill missing via network, then reorder.
        fetched: Dict[str, PubmedArticle] = {a.pmid: a for a in articles}
        if missing:
            # NCBI recommends batches; keep modest for timeout budget.
            for i in range(0, len(missing), 30):
                batch = missing[i : i + 30]
                params = {
                    **self._common_params(),
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                }
                self._throttle()
                resp = self.session.get(
                    f"{EUTILS_BASE}/efetch.fcgi",
                    params=params,
                    timeout=self.efetch_timeout_s,
                )
                resp.raise_for_status()
                for article in self._parse_efetch_xml(resp.text):
                    fetched[article.pmid] = article
                    if use_cache:
                        self._write_cache(
                            self.article_cache_dir / f"{article.pmid}.json",
                            article.to_dict(),
                        )

        return [fetched[pmid] for pmid in ids if pmid in fetched]

    @staticmethod
    def _parse_efetch_xml(xml_text: str) -> List[PubmedArticle]:
        articles: List[PubmedArticle] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return articles

        for article_el in root.findall(".//PubmedArticle"):
            medline = article_el.find("MedlineCitation")
            if medline is None:
                continue
            pmid = (medline.findtext("PMID") or "").strip()
            if not pmid:
                continue
            article = medline.find("Article")
            title = ""
            abstract = ""
            journal = None
            year = None
            language = None
            pub_types: List[str] = []
            doi = None
            if article is not None:
                title = " ".join((article.findtext("ArticleTitle") or "").split())
                abstract = _join_abstract(article.find("Abstract"))
                journal_el = article.find("Journal")
                if journal_el is not None:
                    journal = journal_el.findtext("Title") or journal_el.findtext(
                        "ISOAbbreviation"
                    )
                    year = (
                        journal_el.findtext("JournalIssue/PubDate/Year")
                        or journal_el.findtext("JournalIssue/PubDate/MedlineDate")
                    )
                    if year:
                        year = year[:4] if len(year) >= 4 and year[:4].isdigit() else year
                language = article.findtext("Language")
                for pt in article.findall("PublicationTypeList/PublicationType"):
                    if pt.text:
                        pub_types.append(pt.text.strip())
                for id_el in article.findall("ELocationID"):
                    if (id_el.get("EIdType") or "").lower() == "doi" and id_el.text:
                        doi = id_el.text.strip()
                        break

            mesh: List[str] = []
            mesh_major: List[str] = []
            for mh in medline.findall("MeshHeadingList/MeshHeading"):
                desc = mh.find("DescriptorName")
                if desc is None or not desc.text:
                    continue
                name = desc.text.strip()
                mesh.append(name)
                if (desc.get("MajorTopicYN") or "N") == "Y":
                    mesh_major.append(name)

            # Fallback DOI from PubmedData
            if not doi:
                for id_el in article_el.findall(".//ArticleId"):
                    if (id_el.get("IdType") or "").lower() == "doi" and id_el.text:
                        doi = id_el.text.strip()
                        break

            articles.append(
                PubmedArticle(
                    pmid=pmid,
                    title=title,
                    abstract=abstract,
                    journal=journal,
                    year=year,
                    doi=doi,
                    pub_types=pub_types,
                    mesh=mesh,
                    mesh_major=mesh_major,
                    language=language,
                )
            )
        return articles


def _join_abstract(abstract_el: Optional[ET.Element]) -> str:
    if abstract_el is None:
        return ""
    parts: List[str] = []
    for node in abstract_el.findall("AbstractText"):
        label = (node.get("Label") or "").strip()
        text = " ".join("".join(node.itertext()).split())
        if not text:
            continue
        if label:
            parts.append(f"{label}: {text}")
        else:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    # Rare: AbstractText as single text node
    return " ".join("".join(abstract_el.itertext()).split())
