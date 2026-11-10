"""v3 formal driver: hybrid system only. Resume-safe."""
from __future__ import annotations

import argparse
import subprocess
import sys

from common.paths import CODE_ROOT, CONFIGS, DATASETS, RUNS, SCRIPTS

PY = sys.executable
V2_P1 = DATASETS / "part1" / "v2_all.json"
V2_P2 = DATASETS / "part2" / "v3_nccn_questions.json"
SAFETY = DATASETS / "part2" / "v3_nccn_safety.json"
RUN = "2026-10-13_v3"
LOG = RUNS / RUN / "formal.log"


def step(args: list[str]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    print("RUN", " ".join(args), flush=True)
    with LOG.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(args) + "\n")
        log.flush()
        proc = subprocess.run(
            args,
            cwd=str(CODE_ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if proc.returncode != 0:
        raise SystemExit(f"step failed rc={proc.returncode}: {args}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--run-name", default=RUN)
    args = parser.parse_args()

    extra: list[str] = ["--resume", "--run-name", args.run_name, "--workers", str(args.workers)]
    if args.limit:
        extra += ["--limit", str(args.limit)]

    p1 = [PY, str(SCRIPTS / "run_part1.py"), "--system", "guideflow", "--questions", str(V2_P1), *extra]
    # qwen2-7b-instruct 在本账号 404；中档底座改用 qwen-turbo。
    for arm in ("hybrid_qwen_plus.yaml", "hybrid_qwen_turbo.yaml", "hybrid_ds_1p5b.yaml"):
        step(p1 + ["--arm", str(CONFIGS / arm)])

    p2_qs = [str(V2_P2)]
    if SAFETY.exists():
        p2_qs.append(str(SAFETY))
    p2 = [
        PY,
        str(SCRIPTS / "run_part2.py"),
        "--system",
        "guideflow",
        "--arm",
        str(CONFIGS / "hybrid_qwen_plus.yaml"),
        "--run-name",
        f"{args.run_name}_part2",
        "--resume",
        "--workers",
        str(args.workers),
        "--questions",
        *p2_qs,
    ]
    if args.limit:
        p2 += ["--limit", str(args.limit)]
    step(p2)
    print("FORMAL_DONE", flush=True)


if __name__ == "__main__":
    main()
