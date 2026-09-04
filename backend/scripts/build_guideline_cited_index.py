"""Build backend/data/guideline_cited_pmids.json from processed knowledge bases."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    # parents[2] = code/ when script is code/backend/scripts/...
    pass
CODE_ROOT = Path(__file__).resolve().parents[2]
# script at code/backend/scripts → parents[2] = code
sys.path.insert(0, str(CODE_ROOT))

from backend.app.services.guideline_cited import write_guideline_cited_index  # noqa: E402


def main() -> None:
    out = write_guideline_cited_index()
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
