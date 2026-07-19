from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config.yaml"


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    pdf_path: Path
    knowledge_base_path: Path
    bm25_index_path: Path
    logs_dir: Path
    qwen_api_key: Optional[str]
    qwen_base_url: str
    qwen_model: str
    reranker_model: str
    bm25_top_k: int
    rerank_top_k: int
    final_top_k: int
    max_attached_refs: int
    # ── query-time multimodal (VLM) ──────────────────────────────────────
    vlm_api_key: Optional[str]
    vlm_base_url: str
    vlm_model: str
    page_image_dir: Path
    page_image_dpi: int
    summary_cache_path: Path
    # ── agent / figure budgets ───────────────────────────────────────────
    max_images: int
    figure_ceiling: int
    routing_mode: str              # "agentic" | "linear"
    agent_max_steps: int
    graph_fanout: int
    graph_depth: int
    graph_reserve: int
    enable_evidence_gating: bool
    # ── figure crop (display) ────────────────────────────────────────────
    crop_enabled: bool
    crop_dpi: Optional[int]
    crop_padding: float
    crop_min_area: float
    crop_prefer: str
    display_max_figures: int
    crop_vlm_max_area: float
    crop_vlm_dedup_guard: bool
    # ── knowledge graph ──────────────────────────────────────────────────
    knowledge_graph_path: Path
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: Optional[str]
    neo4j_database: str
    neo4j_clear: bool
    neo4j_batch_size: int
    chunk_index_path: Path
    chunk_embedding_model: str
    chunk_embedding_index_path: Path
    chunk_embedding_meta_path: Path


def _first_pdf(root_dir: Path) -> Path:
    pdfs = sorted(root_dir.glob("*.pdf"))
    if not pdfs:
        return root_dir / "NCCN_B_Cell_Lymphomas.pdf"
    return pdfs[0]


def _load_config_yaml(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def _nested_get(cfg: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = cfg
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _resolve_path(value: str | Path, root_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root_dir / path
    return path


def _cfg_or_env(
    cfg: dict[str, Any],
    env_key: str,
    default: Any,
    *yaml_keys: str,
) -> Any:
    env_val = os.getenv(env_key)
    if env_val is not None and str(env_val).strip() != "":
        return env_val
    yaml_val = _nested_get(cfg, *yaml_keys) if yaml_keys else None
    if yaml_val is not None:
        return yaml_val
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _bridge_config_to_env(cfg: dict[str, Any]) -> None:
    """Expose config.yaml values to legacy os.getenv callers when env is unset."""
    bridges: list[tuple[str, tuple[str, ...], Any]] = [
        ("NCCN_PDF_PATH", ("paths", "pdf"), None),
        ("KNOWLEDGE_BASE_PATH", ("paths", "knowledge_base"), None),
        ("BM25_INDEX_PATH", ("paths", "bm25_index"), None),
        ("TRACE_LOG_DIR", ("paths", "logs"), None),
        ("PAGE_IMAGE_DIR", ("paths", "page_images"), None),
        ("SUMMARY_CACHE_PATH", ("paths", "summary_cache"), None),
        ("KNOWLEDGE_GRAPH_PATH", ("paths", "knowledge_graph"), None),
        ("QWEN_BASE_URL", ("qwen", "base_url"), None),
        ("QWEN_MODEL", ("qwen", "model"), None),
        ("VLM_BASE_URL", ("vlm", "base_url"), None),
        ("VLM_MODEL", ("vlm", "model"), None),
        ("RERANKER_MODEL", ("reranker", "model"), None),
        ("BM25_TOP_K", ("retrieval", "bm25_top_k"), None),
        ("RERANK_TOP_K", ("retrieval", "rerank_top_k"), None),
        ("FINAL_TOP_K", ("retrieval", "final_top_k"), None),
        ("TARGET_DISEASE_SCOPE", ("disease_scope",), None),
        ("MAX_ATTACHED_REFS", ("retrieval", "max_attached_refs"), None),
        ("MAX_IMAGES", ("max_images",), None),
        ("FIGURE_CEILING", ("figure_ceiling",), None),
        ("ROUTING_MODE", ("routing_mode",), None),
        ("AGENT_MAX_STEPS", ("agent_max_steps",), None),
        ("GRAPH_FANOUT", ("graph", "fanout"), None),
        ("GRAPH_DEPTH", ("graph", "depth"), None),
        ("GRAPH_RESERVE", ("graph", "reserve"), None),
        ("PAGE_IMAGE_DPI", ("page_image_dpi",), None),
        ("ENABLE_EVIDENCE_GATING", ("enable_evidence_gating",), None),
        ("CROP_ENABLED", ("crop", "enabled"), None),
        ("CROP_DPI", ("crop", "dpi"), None),
        ("CROP_PADDING", ("crop", "padding"), None),
        ("CROP_MIN_AREA", ("crop", "min_area"), None),
        ("CROP_PREFER", ("crop", "prefer"), None),
        ("DISPLAY_MAX_FIGURES", ("display_max_figures",), None),
        ("CROP_VLM_MAX_AREA", ("crop", "vlm_max_area"), None),
        ("CROP_VLM_DEDUP_GUARD", ("crop", "vlm_dedup_guard"), None),
    ]
    for env_key, yaml_keys, _default in bridges:
        if os.getenv(env_key) is not None:
            continue
        val = _nested_get(cfg, *yaml_keys)
        if val is None:
            continue
        os.environ.setdefault(env_key, str(val))


def load_settings() -> Settings:
    if load_dotenv:
        load_dotenv(ROOT_DIR / ".env", encoding="utf-8-sig")

    cfg = _load_config_yaml()
    _bridge_config_to_env(cfg)

    pdf_path_env = os.getenv("NCCN_PDF_PATH")
    if pdf_path_env:
        pdf_path = _resolve_path(pdf_path_env, ROOT_DIR)
    else:
        pdf_path = _first_pdf(ROOT_DIR)

    crop_dpi_raw = _cfg_or_env(cfg, "CROP_DPI", None, "crop", "dpi")
    crop_dpi: Optional[int]
    if crop_dpi_raw is None or str(crop_dpi_raw).strip().lower() in ("", "null", "none"):
        crop_dpi = None
    else:
        crop_dpi = int(crop_dpi_raw)

    page_image_dpi = int(_cfg_or_env(cfg, "PAGE_IMAGE_DPI", "150", "page_image_dpi"))

    return Settings(
        root_dir=ROOT_DIR,
        pdf_path=pdf_path,
        knowledge_base_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "KNOWLEDGE_BASE_PATH",
                ROOT_DIR / "data" / "processed" / "dlbcl_knowledge_base.json",
                "paths",
                "knowledge_base",
            ),
            ROOT_DIR,
        ),
        bm25_index_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "BM25_INDEX_PATH",
                ROOT_DIR / "data" / "indexes" / "bm25_index.pkl",
                "paths",
                "bm25_index",
            ),
            ROOT_DIR,
        ),
        logs_dir=_resolve_path(
            _cfg_or_env(cfg, "TRACE_LOG_DIR", ROOT_DIR / "logs" / "runs", "paths", "logs"),
            ROOT_DIR,
        ),
        qwen_api_key=(
            os.getenv("QWEN_API_KEY")
            or os.getenv("QWEN_APIKEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DEEPSEEK_APIKEY")
        ),
        qwen_base_url=str(
            _cfg_or_env(
                cfg,
                "QWEN_BASE_URL",
                os.getenv("DEEPSEEK_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                "qwen",
                "base_url",
            )
        ),
        qwen_model=str(
            _cfg_or_env(
                cfg,
                "QWEN_MODEL",
                os.getenv("DEEPSEEK_MODEL", "qwen-plus"),
                "qwen",
                "model",
            )
        ),
        reranker_model=str(_cfg_or_env(cfg, "RERANKER_MODEL", "lexical", "reranker", "model")),
        bm25_top_k=int(_cfg_or_env(cfg, "BM25_TOP_K", "40", "retrieval", "bm25_top_k")),
        rerank_top_k=int(_cfg_or_env(cfg, "RERANK_TOP_K", "16", "retrieval", "rerank_top_k")),
        final_top_k=int(_cfg_or_env(cfg, "FINAL_TOP_K", "6", "retrieval", "final_top_k")),
        max_attached_refs=int(
            _cfg_or_env(cfg, "MAX_ATTACHED_REFS", "6", "retrieval", "max_attached_refs")
        ),
        vlm_api_key=os.getenv("VLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
        vlm_base_url=str(
            _cfg_or_env(
                cfg,
                "VLM_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "vlm",
                "base_url",
            )
        ),
        vlm_model=str(_cfg_or_env(cfg, "VLM_MODEL", "qwen-vl-max", "vlm", "model")),
        page_image_dir=_resolve_path(
            _cfg_or_env(
                cfg,
                "PAGE_IMAGE_DIR",
                ROOT_DIR / "data" / "cache" / "page_images",
                "paths",
                "page_images",
            ),
            ROOT_DIR,
        ),
        page_image_dpi=page_image_dpi,
        summary_cache_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "SUMMARY_CACHE_PATH",
                ROOT_DIR / "data" / "cache" / "page_summaries.json",
                "paths",
                "summary_cache",
            ),
            ROOT_DIR,
        ),
        max_images=int(
            _cfg_or_env(
                cfg,
                "MAX_IMAGES",
                _cfg_or_env(cfg, "FIGURE_CEILING", "4", "figure_ceiling"),
                "max_images",
            )
        ),
        figure_ceiling=int(
            _cfg_or_env(
                cfg,
                "FIGURE_CEILING",
                _cfg_or_env(cfg, "MAX_IMAGES", "4", "max_images"),
                "figure_ceiling",
            )
        ),
        routing_mode=str(
            _cfg_or_env(cfg, "ROUTING_MODE", "agentic", "routing_mode")
        ).strip().lower(),
        agent_max_steps=int(_cfg_or_env(cfg, "AGENT_MAX_STEPS", "4", "agent_max_steps")),
        graph_fanout=int(_cfg_or_env(cfg, "GRAPH_FANOUT", "3", "graph", "fanout")),
        graph_depth=int(_cfg_or_env(cfg, "GRAPH_DEPTH", "1", "graph", "depth")),
        graph_reserve=int(_cfg_or_env(cfg, "GRAPH_RESERVE", "2", "graph", "reserve")),
        enable_evidence_gating=_as_bool(
            _cfg_or_env(cfg, "ENABLE_EVIDENCE_GATING", "true", "enable_evidence_gating"),
            default=True,
        ),
        crop_enabled=_as_bool(_cfg_or_env(cfg, "CROP_ENABLED", "true", "crop", "enabled"), default=True),
        crop_dpi=crop_dpi,
        crop_padding=float(_cfg_or_env(cfg, "CROP_PADDING", "0.02", "crop", "padding")),
        crop_min_area=float(_cfg_or_env(cfg, "CROP_MIN_AREA", "0.05", "crop", "min_area")),
        crop_prefer=str(_cfg_or_env(cfg, "CROP_PREFER", "auto", "crop", "prefer")).strip().lower(),
        display_max_figures=int(_cfg_or_env(cfg, "DISPLAY_MAX_FIGURES", "4", "display_max_figures")),
        crop_vlm_max_area=float(_cfg_or_env(cfg, "CROP_VLM_MAX_AREA", "0.8", "crop", "vlm_max_area")),
        crop_vlm_dedup_guard=_as_bool(
            _cfg_or_env(cfg, "CROP_VLM_DEDUP_GUARD", "true", "crop", "vlm_dedup_guard"),
            default=True,
        ),
        knowledge_graph_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "KNOWLEDGE_GRAPH_PATH",
                ROOT_DIR / "data" / "processed" / "knowledge_graph.json",
                "paths",
                "knowledge_graph",
            ),
            ROOT_DIR,
        ),
        neo4j_uri=str(os.getenv("NEO4J_URI", "bolt://localhost:7687")),
        neo4j_user=str(os.getenv("NEO4J_USER", "neo4j")),
        neo4j_password=os.getenv("NEO4J_PASSWORD"),
        neo4j_database=str(os.getenv("NEO4J_DATABASE", "neo4j")),
        neo4j_clear=_as_bool(os.getenv("NEO4J_CLEAR", "0"), default=False),
        neo4j_batch_size=int(os.getenv("NEO4J_BATCH_SIZE", "500")),
        chunk_index_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "CHUNK_INDEX_PATH",
                ROOT_DIR / "data" / "indexes" / "knowledge_chunks.json",
                "paths",
                "chunk_index",
            ),
            ROOT_DIR,
        ),
        chunk_embedding_model=str(_cfg_or_env(cfg, "CHUNK_EMBEDDING_MODEL", "bge-m3", "embedding", "model")),
        chunk_embedding_index_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "CHUNK_EMBEDDING_INDEX_PATH",
                ROOT_DIR / "data" / "indexes" / "knowledge_chunks.faiss",
                "paths",
                "chunk_embedding_index",
            ),
            ROOT_DIR,
        ),
        chunk_embedding_meta_path=_resolve_path(
            _cfg_or_env(
                cfg,
                "CHUNK_EMBEDDING_META_PATH",
                ROOT_DIR / "data" / "indexes" / "knowledge_chunks_meta.json",
                "paths",
                "chunk_embedding_meta",
            ),
            ROOT_DIR,
        ),
    )
