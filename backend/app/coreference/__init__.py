"""Document-level coreference clusters and cluster-based grounding (Phase 6). See clusterer.py for the rules."""
from app.coreference.clusterer import CoreferenceResult, build_clusters
from app.coreference.grounding import apply_coreference, ground_references, locate_evidence

__all__ = ["CoreferenceResult", "build_clusters", "apply_coreference", "ground_references", "locate_evidence"]
