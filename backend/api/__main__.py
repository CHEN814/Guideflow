"""Run FastAPI with: python -m backend.api"""
from __future__ import annotations

import uvicorn


def main() -> None:
    # Default 8001 to match OpenEvidence frontend API_BASE.
    uvicorn.run("backend.api.server:app", host="127.0.0.1", port=8001, reload=False)


if __name__ == "__main__":
    main()
