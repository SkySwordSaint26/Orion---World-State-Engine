"""Deterministic (LLM-free) consistency engine: vocabulary, rules, engine and contradiction recorder."""
from app.consistency.engine import ConsistencyEngine
from app.consistency.recorder import ContradictionRecorder
from app.consistency.types import Finding

__all__ = ["ConsistencyEngine", "ContradictionRecorder", "Finding"]
