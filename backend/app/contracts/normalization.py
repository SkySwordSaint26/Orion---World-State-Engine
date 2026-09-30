"""
Normalization entry points (Phase 4): explicit hooks, PASS-THROUGH ONLY.

No normalization logic exists yet. These functions mark the exact places where a later phase will map raw
LLM strings onto the controlled vocabulary; today each returns its input unchanged, so wiring them in
changes no behavior.

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


def normalize_entity_name(name: str) -> str:
    """TODO(entity-normalization): canonicalize an entity surface form (titles, case, aliases). Pass-through."""
    return name
