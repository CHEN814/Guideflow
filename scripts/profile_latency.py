"""Temporary latency profiler for QA pipeline stages.

Does NOT modify core service logic: wraps methods via monkey-patch,
runs one question, writes a JSON + markdown summary under docs/.

Usage:
  python scripts/profile_latency.py "DLBCL 诊断需要哪些病理检查？"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.services.qa import QAService
from backend.app.settings import load_settings


class StageTimer:
    def __init__(self) -> None:
        self.stages: List[Dict[str, Any]] = []
        self._t0 = time.perf_counter()

    def record(self, name: str, elapsed_ms: float, extra: Optional[Dict[str, Any]] = None) -> None:
        row = {
            "stage": name,
            "elapsed_ms": round(elapsed_ms, 1),
            "since_start_ms": round((time.perf_counter() - self._t0) * 1000, 1),
        }
        if extra:
            row["extra"] = extra
        self.stages.append(row)
        print(f"  [{row['elapsed_ms']:8.1f} ms] {name}" + (f"  {extra}" if extra else ""))

    def wrap(self, name: str, fn: Callable, extra_fn: Optional[Callable] = None) -> Callable:
        timer = self

        @wraps(fn)
        def _wrapped(*args, **kwargs):
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            extra = extra_fn(result, *args, **kwargs) if extra_fn else None
            timer.record(name, elapsed, extra)
            return result

        return _wrapped


def _install_hooks(service: QAService, timer: StageTimer) -> None:
    """Monkey-patch hot path methods on this service instance only."""

    # Page render / crop (often cached; still measure)
    renderer = service.page_renderer
    orig_render = renderer.render
    orig_crop = renderer.render_crop

    def timed_render(pdf_page: int):
        t0 = time.perf_counter()
        out = orig_render(pdf_page)
        cached = out is not None and Path(out).exists()
        # If file existed before call we can't know cheaply; approximate via mtime age
        timer.record(
            "page_render",
            (time.perf_counter() - t0) * 1000,
            {"pdf_page": pdf_page, "path": str(out) if out else None},
        )
        return out

    def timed_crop(pdf_page: int, bbox_norm, padding: float = 0.02, dpi=None):
        t0 = time.perf_counter()
        out = orig_crop(pdf_page, bbox_norm, padding=padding, dpi=dpi)
        timer.record(
            "page_crop_render",
            (time.perf_counter() - t0) * 1000,
            {"pdf_page": pdf_page, "path": str(out) if out else None},
        )
        return out

    renderer.render = timed_render  # type: ignore[method-assign]
    renderer.render_crop = timed_crop  # type: ignore[method-assign]

    # Retrieval stack
    service.retriever.retrieve = timer.wrap(  # type: ignore[method-assign]
        "retrieve",
        service.retriever.retrieve,
        extra_fn=lambda result, *a, **k: {
            "hit_count": len(result[0]) if isinstance(result, tuple) else None,
            "route": (result[1] or {}).get("route") if isinstance(result, tuple) else None,
        },
    )

    # Evidence gate (Qwen text call)
    service.qwen.gate_evidence = timer.wrap(  # type: ignore[method-assign]
        "evidence_gate_qwen",
        service.qwen.gate_evidence,
    )

    # Reference + KG
    service.reference_resolver.resolve_references = timer.wrap(  # type: ignore[method-assign]
        "resolve_references",
        service.reference_resolver.resolve_references,
    )
    service.kg_retriever.retrieve = timer.wrap(  # type: ignore[method-assign]
        "kg_retrieve",
        service.kg_retriever.retrieve,
        extra_fn=lambda result, *a, **k: {"triple_hits": len(result) if result is not None else 0},
    )

    # Figure gather (includes renders)
    service._gather_figures = timer.wrap(  # type: ignore[method-assign]
        "gather_figures",
        service._gather_figures,
        extra_fn=lambda result, *a, **k: {
            "figure_count": len(result[0]) if isinstance(result, tuple) else None,
            "seed": (result[1] or {}).get("seed_page_code") if isinstance(result, tuple) else None,
        },
    )

    # Generators — the likely bottleneck
    def vlm_extra(result, *a, **k):
        answer, degraded, summaries, bboxes = result
        return {
            "answer_chars": len(answer or ""),
            "degraded": degraded,
            "summary_pages": sorted((summaries or {}).keys()),
            "bbox_pages": sorted((bboxes or {}).keys()),
            "figure_count": len(a[1].figures) if len(a) > 1 else None,
        }

    service.vlm.generate = timer.wrap(  # type: ignore[method-assign]
        "vlm_generate",
        service.vlm.generate,
        extra_fn=vlm_extra,
    )
    service.qwen.generate = timer.wrap(  # type: ignore[method-assign]
        "qwen_generate",
        service.qwen.generate,
        extra_fn=lambda result, *a, **k: {
            "answer_chars": len(result[0] or "") if isinstance(result, tuple) else None,
            "degraded": result[1] if isinstance(result, tuple) else None,
        },
    )

    # Post-generation
    service._apply_figure_crops = timer.wrap(  # type: ignore[method-assign]
        "figure_crops",
        service._apply_figure_crops,
        extra_fn=lambda result, *a, **k: {
            "figure_count": len(result[0]) if isinstance(result, tuple) else None,
            "crop_summary": {
                key: (result[1] or {}).get(key)
                for key in ("vlm_count", "deterministic_count", "none_count", "prefer")
            }
            if isinstance(result, tuple)
            else None,
        },
    )

    # Image encode inside VLM path
    import backend.app.services.multimodal_client as mm

    orig_encode = mm._encode_image

    def timed_encode(path: Path):
        t0 = time.perf_counter()
        out = orig_encode(path)
        timer.record(
            "vlm_image_encode",
            (time.perf_counter() - t0) * 1000,
            {"path": str(path), "bytes_b64": len(out) if out else 0},
        )
        return out

    mm._encode_image = timed_encode


def _aggregate(stages: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_name: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for row in stages:
        name = row["stage"]
        by_name[name] = by_name.get(name, 0.0) + float(row["elapsed_ms"])
        counts[name] = counts.get(name, 0) + 1
    ranked = sorted(by_name.items(), key=lambda x: x[1], reverse=True)
    total = sum(by_name.values())
    # Note: nested stages (page_render inside gather_figures) double-count if summed.
    # Provide both raw sum and top-level exclusive estimate.
    nested = {"page_render", "page_crop_render", "vlm_image_encode"}
    exclusive = {k: v for k, v in by_name.items() if k not in nested}
    exclusive_total = sum(exclusive.values())
    return {
        "by_stage_ms": {k: round(v, 1) for k, v in ranked},
        "call_counts": counts,
        "raw_sum_ms": round(total, 1),
        "exclusive_sum_ms": round(exclusive_total, 1),
        "ranked_exclusive": [
            {"stage": k, "elapsed_ms": round(v, 1), "pct": round(100 * v / exclusive_total, 1) if exclusive_total else 0}
            for k, v in sorted(exclusive.items(), key=lambda x: x[1], reverse=True)
        ],
        "nested_detail_ms": {k: round(by_name.get(k, 0.0), 1) for k in nested if k in by_name},
    }


def _write_report(question: str, result, timer: StageTimer, wall_ms: float, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    agg = _aggregate(timer.stages)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "wall_clock_ms": round(wall_ms, 1),
        "run_id": getattr(result, "run_id", None),
        "trace_path": getattr(result, "trace_path", None),
        "generation_mode": None,
        "figure_count": len(result.figures) if result.figures else 0,
        "figure_pages": [f.page_code for f in (result.figures or [])],
        "degraded": list(result.degraded or []),
        "stages": timer.stages,
        "aggregate": agg,
    }
    # Infer generation mode from stages
    if any(s["stage"] == "vlm_generate" for s in timer.stages):
        payload["generation_mode"] = "multimodal"
    elif any(s["stage"] == "qwen_generate" for s in timer.stages):
        payload["generation_mode"] = "text"

    json_path = out_dir / f"latency_profile_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out_dir / "性能测试报告.md"
    lines = [
        "# QA 流水线耗时测试报告",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"> 测试脚本：`scripts/profile_latency.py`（临时 monkey-patch，未改核心逻辑）  ",
        f"> 原始数据：`{json_path.name}`",
        "",
        "## 1. 测试设置",
        "",
        f"- **问题**：{question}",
        f"- **墙钟总耗时**：{wall_ms/1000:.2f}s（{wall_ms:.0f} ms）",
        f"- **生成模式**：{payload['generation_mode']}",
        f"- **输出图片数**：{payload['figure_count']} — {payload['figure_pages']}",
        f"- **run_id / trace**：`{payload['run_id']}` / `{payload['trace_path']}`",
        f"- **降级标记**：{payload['degraded'] or '无'}",
        "",
        "## 2. 结论（先看这个）",
        "",
    ]

    ranked = agg["ranked_exclusive"]
    top = ranked[0] if ranked else None
    if top:
        lines.extend(
            [
                f"**最慢阶段：`{top['stage']}`，约 {top['elapsed_ms']/1000:.2f}s"
                f"（占互斥阶段合计的 {top['pct']}%）。**",
                "",
            ]
        )
        if top["stage"] == "vlm_generate":
            lines.extend(
                [
                    "这与「图片输出路径上视觉大模型阻塞流水线」的猜测一致：",
                    "当前架构在 `use_vlm=True` 时用 **同步阻塞** 的 `vlm.generate()` 同时完成看图回答 + 页摘要 + bbox，",
                    "文本答案必须等 VLM HTTP 返回后才能进入裁剪/校验/响应。",
                    "",
                ]
            )
        elif top["stage"] == "evidence_gate_qwen":
            lines.append("当前最慢的是证据门控（Qwen 文本调用），而非 VLM。\n")
        elif top["stage"] == "qwen_generate":
            lines.append("当前走文本生成路径；最慢的是 Qwen 生成，而非 VLM。\n")

    lines.extend(
        [
            "## 3. 阶段耗时排行（互斥顶层阶段）",
            "",
            "| 阶段 | 耗时 (ms) | 占比 |",
            "|---|---:|---:|",
        ]
    )
    for row in ranked:
        lines.append(f"| `{row['stage']}` | {row['elapsed_ms']:.1f} | {row['pct']}% |")

    lines.extend(
        [
            "",
            f"互斥合计：{agg['exclusive_sum_ms']:.1f} ms；墙钟：{wall_ms:.1f} ms"
            f"（差值含 normalize / format / verify / prune 等未单独打点的轻量步骤）。",
            "",
            "### 嵌套细节（已计入父阶段，勿再与上表相加）",
            "",
            "| 子步骤 | 耗时 (ms) |",
            "|---|---:|",
        ]
    )
    for k, v in agg.get("nested_detail_ms", {}).items():
        lines.append(f"| `{k}` | {v:.1f} |")
    if not agg.get("nested_detail_ms"):
        lines.append("| （无） | — |")

    lines.extend(
        [
            "",
            "## 4. 流水线时序（按发生顺序）",
            "",
            "| # | 阶段 | 本段 ms | 距起点 ms | 备注 |",
            "|---:|---|---:|---:|---|",
        ]
    )
    for i, row in enumerate(timer.stages, start=1):
        extra = row.get("extra") or {}
        note = ", ".join(f"{k}={v}" for k, v in list(extra.items())[:4])
        lines.append(
            f"| {i} | `{row['stage']}` | {row['elapsed_ms']:.1f} | {row['since_start_ms']:.1f} | {note} |"
        )

    lines.extend(
        [
            "",
            "## 5. 架构阻塞点说明",
            "",
            "当前 `QAService.ask()` 是串行同步流水线：",
            "",
            "```text",
            "normalize → retrieve → evidence_gate(Qwen) → refs/KG",
            "  → gather_figures(render PNG) → [VLM 或 Qwen] generate",
            "  → format → prune → crop → verify → return",
            "```",
            "",
            "- **有图时**：`use_vlm = bool(figures) and vlm.available`，走 `vlm.generate()`（`requests.post`，timeout=90s）。",
            "- **VLM 职责过重**：一次调用同时产出答案、页摘要、bbox；裁剪与前端响应都排在其后。",
            "- **证据门控**也是一次独立 Qwen HTTP，可能成为第二瓶颈。",
            "- 页渲染有磁盘缓存；冷启动会多出 `page_render`，热路径通常很小。",
            "",
            "## 6. 可能的调整方案（按收益/风险）",
            "",
            "### A. 高收益：拆开「先出字、后出图」",
            "",
            "1. 有图问题时先用 **文本 Qwen** 生成答案并立即返回/流式输出。",
            "2. 图片展示用确定性裁剪（PyMuPDF）或预缓存页图，**不阻塞**首包。",
            "3. VLM 改为可选后台任务：补 bbox / 页摘要 / 图文校验。",
            "",
            "**预期**：首字/完整文本延迟接近纯文本路径；总墙钟可能仍高，但用户感知延迟大幅下降。",
            "",
            "### B. 中收益：缩小 VLM 输入",
            "",
            "- 降低 `max_images` / DPI，或只送 seed 页而非邻居页。",
            "- 先裁剪再送 VLM（更小图），减少上传与推理时间。",
            "- 页摘要命中缓存时跳过 VLM 摘要段，缩短输出。",
            "",
            "### C. 中收益：并行化串行 HTTP",
            "",
            "- `evidence_gate` 与 `gather_figures`（本地渲染）可并行。",
            "- 若仍需 VLM：gate 与「渲染+编码」并行，再调 VLM。",
            "",
            "### D. 低风险：流式输出",
            "",
            "- 即使仍用 VLM，若 API 支持 stream，可边生成边推前端，改善「卡住 30s」体感。",
            "",
            "### E. 路由收紧",
            "",
            "- 「诊断/检查」经归一化含 `workup` → 常进 `hybrid` → 强制选图+VLM。",
            "- 可对「病理检查清单」类问题走 evidence+表格页展示，避免不必要的 VLM。",
            "",
            "## 7. 建议下一步验证",
            "",
            "1. 同问题再跑一轮（热缓存）对比 `page_render` 是否已可忽略。",
            "2. 对比纯文本题（无图）确认 `qwen_generate` 基线。",
            "3. 若确认 VLM 占 >60%，优先试方案 A（文本先出 + 图后挂）。",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile QA pipeline stage latency.")
    parser.add_argument(
        "question",
        nargs="?",
        default="DLBCL 诊断需要哪些病理检查？",
        help="Question to profile.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "docs",
        help="Directory for report + JSON dump.",
    )
    args = parser.parse_args()

    print("Loading settings / QAService (cold start not counted in stage table)...")
    t_load = time.perf_counter()
    settings = load_settings()
    service = QAService(settings)
    load_ms = (time.perf_counter() - t_load) * 1000
    print(f"Service ready in {load_ms:.0f} ms\n")

    timer = StageTimer()
    _install_hooks(service, timer)

    print(f"Profiling: {args.question}\n")
    t0 = time.perf_counter()
    result = service.ask(args.question, trace_enabled=True)
    wall_ms = (time.perf_counter() - t0) * 1000

    print(f"\nWall clock: {wall_ms/1000:.2f}s")
    print(f"Figures: {len(result.figures or [])}  degraded={result.degraded}")
    print(f"Answer preview: {(result.answer or '')[:200].replace(chr(10), ' ')}...")

    report = _write_report(args.question, result, timer, wall_ms, args.out_dir)
    print(f"\nReport written: {report}")


if __name__ == "__main__":
    main()
