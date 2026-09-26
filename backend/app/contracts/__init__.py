"""Pipeline data contracts (Phase 4). See models.py for the contract and its provenance rules."""
from app.contracts.gold import GoldProjection, project_to_gold
from app.contracts.ids import assign_ids
from app.contracts.mapping import (
    extract_observations, observations_from_parsed, validate_observation, validate_result,
)
from app.contracts.models import (
    ContractError, CoreferenceCluster, EntityMention, Event, EventParticipant, ExtractionResult, ExtractorInput, FactObservation,
    FactOrigin, Observation, ObservationKind, Relationship, TemporalExpression,
    TemporalRelation,
)
from app.contracts.normalization import normalize_entity_name, normalize_predicate, normalize_property

__all__ = [
    "ContractError", "CoreferenceCluster", "EntityMention", "Event", "EventParticipant", "TemporalExpression", "GoldProjection", "project_to_gold", "assign_ids", "ExtractionResult", "ExtractorInput",
    "FactObservation", "FactOrigin", "Observation", "ObservationKind", "Relationship", "TemporalRelation",
    "extract_observations", "observations_from_parsed", "validate_observation", "validate_result",
    "normalize_entity_name", "normalize_predicate", "normalize_property",
]
