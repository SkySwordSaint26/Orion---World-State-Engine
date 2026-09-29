"""WSE extraction pipeline v2: story text -> `orion_gold_v1` document. Plan: docs/wse_extraction_plan.md.

The backend's dependency-free modules (preprocessing, gold vocabularies, evaluation) are imported, never copied.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
