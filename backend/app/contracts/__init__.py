"""Gold-schema vocabularies (used by ../extractor) and the normalization hooks of the integration."""
from app.contracts.normalization import normalize_entity_name, normalize_predicate, normalize_property

__all__ = ["normalize_entity_name", "normalize_predicate", "normalize_property"]
