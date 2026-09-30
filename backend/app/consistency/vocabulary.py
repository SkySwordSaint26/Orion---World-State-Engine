"""
Controlled vocabulary for the deterministic consistency engine.

Rules only ever look at properties and predicates listed here. Anything else (arbitrary
LLM-generated property names or relationship types) is UNKNOWN: it is stored and versioned as usual
but can never produce a contradiction. Mapping synonyms ("eye colour" -> eye_color, "father" ->
FATHER_OF) is the job of a future observation-normalization stage; this module only normalizes case
and separators.
"""
import re
from enum import Enum
from typing import Any, Optional


class PropertyKind(str, Enum):
    IMMUTABLE = "immutable"   # one value for the whole story; a different later value is a contradiction
    MUTABLE = "mutable"       # may legitimately change; only specific rules (age, status) constrain it
    UNKNOWN = "unknown"       # not in the vocabulary: no rule applies


# Carried over unchanged from the original resolve_fact_update implementation.
IMMUTABLE_PROPERTIES = frozenset({"birth_place", "date_of_birth", "origin", "eye_color", "species"})

# Properties the SRS names as changing over time. `location` has no rule yet (REQ-24 is deferred).
MUTABLE_PROPERTIES = frozenset({"age", "location", "status"})

AGE_PROPERTY = "age"
STATUS_PROPERTY = "status"

# Status values that have a defined meaning for REQ-26. Any other status value is ignored.
DEAD_STATUS_VALUES = frozenset({"dead", "deceased"})
ALIVE_STATUS_VALUES = frozenset({"alive", "living"})

# Explicitly incompatible predicate pairs (order of the two predicates does not matter).
# Carried over unchanged from the original implementation; "A KNOWS B" etc. are NOT in this set.
INCOMPATIBLE_PREDICATE_PAIRS = frozenset({
    frozenset({"ENEMY_OF", "FRIEND_OF"}),
    frozenset({"ENEMY_OF", "MARRIED_TO"}),
    frozenset({"DEAD_AT_HANDS_OF", "ALLY_OF"}),
})

# Predicates where a target entity can have only ONE source (REQ-25: "a character's stated father
# changing"). FATHER_OF: (source)-[FATHER_OF]->(target) means source is target's father.
SINGLE_VALUED_INCOMING_PREDICATES = frozenset({"FATHER_OF"})


# TODO(property-normalization): NOT IMPLEMENTED. normalize_property() only lowercases and unifies separators.
# The future normalization stage (before storage) will map synonyms/variants to these controlled names; it
# should reuse IMMUTABLE_PROPERTIES / MUTABLE_PROPERTIES as the target vocabulary rather than duplicate them.
def normalize_property(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")


def property_kind(name: Any) -> PropertyKind:
    normalized = normalize_property(name)
    if normalized in IMMUTABLE_PROPERTIES:
        return PropertyKind.IMMUTABLE
    if normalized in MUTABLE_PROPERTIES:
        return PropertyKind.MUTABLE
    return PropertyKind.UNKNOWN


# TODO(relationship-normalization): NOT IMPLEMENTED. normalize_predicate() only uppercases and unifies
# separators. Synonym/inverse mapping and symmetry metadata (which predicates are symmetric) will live next to
# INCOMPATIBLE_PREDICATE_PAIRS; today no predicate is treated as symmetric.
def normalize_predicate(predicate: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(predicate or "").strip().upper()).strip("_")


def values_equal(old_value: Any, new_value: Any) -> bool:
    """True if two fact values represent the same information (case/whitespace-insensitive)."""
    if old_value == new_value:
        return True
    return str(old_value).strip().lower() == str(new_value).strip().lower()


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


_AGE_RE = re.compile(r"^\s*(\d{1,3})\s*(?:years?(?:\s*old)?)?\s*$", re.IGNORECASE)
_AGE_WORDS_RE = re.compile(r"^\s*([a-z]+)(?:[\s-]+([a-z]+))?\s*(?:years?(?:\s*old)?)?\s*$", re.IGNORECASE)
_UNITS = {w: n for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                     "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * n for n, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}


def _age_in_words(text: str) -> Optional[int]:
    """"twenty four", "twenty-four years old", "seven" -> 24, 24, 7; anything else (incl. over 99) -> None."""
    match = _AGE_WORDS_RE.match(text)
    if not match:
        return None
    first, second = match.group(1).lower(), (match.group(2) or "").lower()
    if not second:
        return _UNITS.get(first, _TENS.get(first))
    return _TENS[first] + _UNITS[second] if first in _TENS and 0 < _UNITS.get(second, 0) < 10 else None


def parse_age(value: Any) -> Optional[int]:
    """Returns an integer age in [0, 150], or None when the value is not an unambiguous number."""
    if isinstance(value, bool):
        return None
    number: Optional[int] = None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str):
        match = _AGE_RE.match(value)
        number = int(match.group(1)) if match else _age_in_words(value)
    if number is None or not 0 <= number <= 150:
        return None
    return number


def normalize_status(value: Any) -> Optional[str]:
    """Maps a status value to "DEAD" / "ALIVE", or None if it is outside the controlled values."""
    text = str(value or "").strip().lower()
    if text in DEAD_STATUS_VALUES:
        return "DEAD"
    if text in ALIVE_STATUS_VALUES:
        return "ALIVE"
    return None
