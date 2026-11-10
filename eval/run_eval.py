"""Compatibility wrapper. Prefer experiments/scripts/run_part1.py and run_part2.py."""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "experiments" / "scripts"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["1", "2", "all"], default="all")
    parser.add_argument("--system", choices=["guideflow", "baseline", "both"], default="both")
    parser.add_argument("--resume", action="store_true")
    args, rest = parser.parse_known_args()
    common = ["--system", args.system]
    if args.resume:
        common.append("--resume")
    if args.part in {"1", "all"}:
        sys.argv = [str(SCRIPTS / "run_part1.py"), *common, *rest]
        runpy.run_path(str(SCRIPTS / "run_part1.py"), run_name="__main__")
    if args.part in {"2", "all"}:
        sys.argv = [str(SCRIPTS / "run_part2.py"), *common, *rest]
        runpy.run_path(str(SCRIPTS / "run_part2.py"), run_name="__main__")


if __name__ == "__main__":
    main()
