"""Aggregate experiment run folders into a markdown report."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from common.paths import REPORTS
from common.io import load_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--title", default="实验报告")
    args = parser.parse_args()
    run = args.run_dir
    lines = [f"# {args.title}", "", f"- 日期：{date.today().isoformat()}", f"- run：`{run}`", ""]
    meta = run / "meta.json"
    if meta.exists():
        lines += ["## meta", "", "```json", meta.read_text(encoding="utf-8")[:4000], "```", ""]
    for name in ("part1_summary.json", "part2_summary.json", "part3_summary.json", "summary.json"):
        p = run / name
        if p.exists():
            lines += [f"## {name}", "", "```json", p.read_text(encoding="utf-8")[:8000], "```", ""]
    out = REPORTS / f"v2_{run.name}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
