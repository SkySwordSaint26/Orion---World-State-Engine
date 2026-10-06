"""
Normalization entry points (Phase 4). Property and predicate hooks are still PASS-THROUGH: they mark where a
later phase will map raw LLM strings onto the controlled vocabulary. Entity names are normalized (titles
dropped) and compared word-wise, so "Captain Brandt" and "Mara" reach the entity stored as "Elias Brandt" /
"Mara Quinn".

Where they are called:
  * the integration / consistency boundaries that carry TODO(property|relationship-normalization) markers
    (`WorldStateService`, `ConsistencyService`).

Note: `app.consistency.vocabulary.normalize_property/normalize_predicate` (case/separator folding used by
the rules) are a different, older layer and are intentionally left as they are.
"""


def normalize_property(name: str) -> str:
    """TODO(property-normalization): map a raw property name ("Eye Color") to the controlled vocabulary. Pass-through."""
    return name


def normalize_predicate(predicate: str) -> str:
    """TODO(relationship-normalization): map synonyms / inverse phrasings to a controlled predicate. Pass-through."""
    return predicate


# ponytail: fixed English title list; extend it (or read titles from the extractor) when a story uses others
TITLES = frozenset({"captain", "capt", "doctor", "dr", "mr", "mrs", "ms", "miss", "sir", "lady", "lord", "professor",
                    "prof", "uncle", "aunt", "general", "sergeant", "lieutenant", "detective", "inspector"})
_NAME_CONNECTORS = frozenset({"of", "the", "de", "van", "von", "la", "le", "du", "da"})


def normalize_entity_name(name: str) -> str:
    """Drops leading titles ("Captain Elias Brandt" -> "Elias Brandt"), keeping a bare title ("Doctor") as it is."""
    words = name.split()
    while len(words) > 1 and words[0].rstrip(".").lower() in TITLES:
        words = words[1:]
    return " ".join(words)


def name_words(name: str) -> frozenset:
    """The lower-case words of a normalized name: what short and full names are compared on ("Mara" in "Mara Quinn")."""
    return frozenset(normalize_entity_name(name).lower().split())


def is_proper_name(name: str) -> bool:
    """True for a name ("Mara Quinn", "Port of Averly"), False for a role phrase ("mother", "Mara's oldest friend"),
    which is not the same person from one chapter to the next and so must never be matched by name."""
    words = normalize_entity_name(name).split()
    return bool(words) and all(w[:1].isupper() or w.lower() in _NAME_CONNECTORS for w in words) \
        and not any(w.endswith(("'s", "’s")) for w in words)
