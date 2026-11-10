"""Run a fresh, fully traced example for algorithm figure preparation."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.app.settings import load_settings
from backend.app.services.qa import QAService

print("Initializing QA service...", flush=True)
service = QAService(load_settings())
# Require fresh PubMed requests rather than reusing earlier cached results.
service.literature_service.pubmed.query_cache_ttl_s = 0
service.literature_service.pubmed.article_cache_ttl_s = 0
print("Running question with PubMed enabled...", flush=True)
result = service.ask("DLBCL 一线治疗如何推荐？", trace_enabled=True, enable_literature=True)
output = ROOT / "logs" / "runs" / f"{result.run_id}.result.json"
output.write_text(json.dumps(result.to_web_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"run_id": result.run_id, "trace": result.trace_path,
    "result": str(output), "sources": len(result.sources), "figures": len(result.figures),
    "literature": len(result.literature), "degraded": result.degraded,
    "generation_mode": result.generation_mode}, ensure_ascii=False), flush=True)
