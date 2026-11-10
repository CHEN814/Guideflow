"""Experiment directory layout. All caches stay on D:."""
from __future__ import annotations

import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = CODE_ROOT.parent
EXP_ROOT = CODE_ROOT / "experiments"
DESIGN_DIR = EXP_ROOT / "design"
DATASETS = EXP_ROOT / "datasets"
CONFIGS = EXP_ROOT / "configs"
SCRIPTS = EXP_ROOT / "scripts"
RUNS = EXP_ROOT / "runs"
REPORTS = EXP_ROOT / "reports"

TMP = Path(r"D:\Project\guideflow\.tmp")
HF = Path(r"D:\Project\guideflow\.cache\huggingface")


def pin_caches_to_d() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    HF.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TMP", str(TMP))
    os.environ.setdefault("TEMP", str(TMP))
    os.environ.setdefault("TMPDIR", str(TMP))
    os.environ.setdefault("HF_HOME", str(HF))
    os.environ.setdefault("HF_HUB_CACHE", str(HF / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(HF / "transformers"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(HF / "datasets"))


def ensure_sys_path() -> None:
    import sys

    root = str(CODE_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
