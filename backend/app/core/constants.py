from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobType(str, Enum):
    INITIAL_EXTRACTION = "INITIAL_EXTRACTION"
    RE_EXTRACTION = "RE_EXTRACTION"

class FactStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONTRADICTED = "CONTRADICTED"

class RelationshipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONTRADICTED = "CONTRADICTED"

class ContradictionType(str, Enum):
    FACT_FACT = "FACT_FACT"
    RELATIONSHIP_RELATIONSHIP = "RELATIONSHIP_RELATIONSHIP"
    TEMPORAL = "TEMPORAL"
    EVENT_LOCATION = "EVENT_LOCATION"
    CYCLE = "CYCLE"

class ContradictionStatus(str, Enum):
    DETECTED = "DETECTED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"

class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    OBJECT = "object"
    ORGANIZATION = "organization"
    EVENT = "event"
    UNKNOWN = "unknown"

class ExtractionRunStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
