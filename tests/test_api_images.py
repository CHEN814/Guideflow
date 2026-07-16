from __future__ import annotations

from backend.api.server import _is_safe_image_filename


def test_safe_image_filename_allows_fullwidth_colon() -> None:
    name = "（2026.V3）NCCN临床 实践指南：B细胞淋巴瘤_p77_crop_0.0800_0.2200_0.9200_0.7500_pad0.0200_150.png"
    assert _is_safe_image_filename(name)


def test_safe_image_filename_rejects_path_traversal() -> None:
    assert not _is_safe_image_filename("../secret.png")
    assert not _is_safe_image_filename("foo/bar.png")
    assert not _is_safe_image_filename("..\\secret.png")


def test_safe_image_filename_requires_png_suffix() -> None:
    assert not _is_safe_image_filename("image.jpg")
    assert _is_safe_image_filename("image.png")
