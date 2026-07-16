"""On-demand PDF page rendering with a hot disk cache."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


class PageImageRenderer:
    """Render individual PDF pages to PNG on demand, cached on disk."""

    def __init__(self, pdf_path: Path, cache_dir: Path, dpi: int = 150):
        self.pdf_path = Path(pdf_path)
        self.cache_dir = Path(cache_dir)
        self.dpi = dpi
        self._doc = None

    def _ensure_doc(self):
        if self._doc is None:
            if fitz is None:
                raise RuntimeError(
                    "PyMuPDF is required for page rendering. Install with: pip install -r requirements.txt"
                )
            if not self.pdf_path.exists():
                raise FileNotFoundError(f"PDF not found: {self.pdf_path}")
            self._doc = fitz.open(str(self.pdf_path))
        return self._doc

    def cache_path(self, pdf_page: int) -> Path:
        stem = self.pdf_path.stem
        return self.cache_dir / f"{stem}_p{pdf_page}_{self.dpi}.png"

    def crop_cache_path(
        self,
        pdf_page: int,
        bbox_norm: List[float],
        padding: float,
        dpi: int,
    ) -> Path:
        stem = self.pdf_path.stem
        bbox_key = "_".join(f"{v:.4f}" for v in bbox_norm)
        pad_key = f"{padding:.4f}"
        return self.cache_dir / f"{stem}_p{pdf_page}_crop_{bbox_key}_pad{pad_key}_{dpi}.png"

    def get_page(self, pdf_page: int):
        if pdf_page <= 0:
            return None
        try:
            doc = self._ensure_doc()
        except (RuntimeError, FileNotFoundError):
            return None
        if pdf_page > len(doc):
            return None
        return doc[pdf_page - 1]

    def render(self, pdf_page: int) -> Optional[Path]:
        """Render a 1-based PDF page to PNG, returning the cached path."""
        if pdf_page <= 0:
            return None
        out = self.cache_path(pdf_page)
        if out.exists():
            return out
        page = self.get_page(pdf_page)
        if page is None:
            return None
        pix = page.get_pixmap(dpi=self.dpi)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        pix.save(str(out))
        return out

    def render_crop(
        self,
        pdf_page: int,
        bbox_norm: List[float],
        padding: float = 0.02,
        dpi: Optional[int] = None,
    ) -> Optional[Path]:
        """Render a normalized bbox region of a page to PNG."""
        if pdf_page <= 0 or len(bbox_norm) != 4:
            return None
        crop_dpi = dpi or self.dpi
        out = self.crop_cache_path(pdf_page, bbox_norm, padding, crop_dpi)
        if out.exists():
            return out

        page = self.get_page(pdf_page)
        if page is None:
            return None

        page_rect = page.rect
        x0, y0, x1, y1 = bbox_norm
        x0 = max(0.0, x0 - padding)
        y0 = max(0.0, y0 - padding)
        x1 = min(1.0, x1 + padding)
        y1 = min(1.0, y1 + padding)
        clip = fitz.Rect(
            page_rect.x0 + x0 * page_rect.width,
            page_rect.y0 + y0 * page_rect.height,
            page_rect.x0 + x1 * page_rect.width,
            page_rect.y0 + y1 * page_rect.height,
        )
        if clip.width <= 1 or clip.height <= 1:
            return None

        pix = page.get_pixmap(clip=clip, dpi=crop_dpi)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        pix.save(str(out))
        return out

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None
