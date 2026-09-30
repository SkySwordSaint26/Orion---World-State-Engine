"""
Vocabularies of `orion_gold_v1.schema.json`, used by ../extractor. They are copies of the schema's enums; a test
compares them with the schema file.
"""

GOLD_SCHEMA_VERSION = "1.0"
MENTION_TYPES = ("character", "location", "object", "organization", "other")
MENTION_KINDS = ("proper", "nominal", "pronominal")
EVENT_TYPES = ("ARRIVAL", "DEPARTURE", "TRAVEL", "MEETING", "CONVERSATION", "DISCOVERY", "ATTACK", "DEATH",
               "CONFLICT", "CREATION", "DESTRUCTION", "OTHER")
PARTICIPANT_ROLES = ("agent", "patient", "target", "recipient", "location", "instrument", "participant")
PREDICATES = ("FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "PARENT_OF", "CHILD_OF", "MARRIED_TO", "ALLY_OF",
              "WORKS_FOR", "MEMBER_OF", "OWNS", "KNOWS", "RELATED_TO")
FACT_PROPERTIES = ("birth_place", "date_of_birth", "origin", "eye_color", "hair_color", "species", "age",
                   "occupation", "title", "status", "location")
TEMPORAL_EXPRESSION_TYPES = ("absolute_time", "relative_time", "duration", "sequence_marker", "other")
TEMPORAL_RELATIONS = ("BEFORE", "AFTER", "DURING")
