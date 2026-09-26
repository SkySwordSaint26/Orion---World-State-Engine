from typing import Dict, Any, Optional, Tuple

from app.consistency import ConsistencyEngine
from app.consistency import vocabulary as vocab
from app.consistency.types import RelationshipCheck, RelationshipVersionView
from app.core.constants import RelationshipStatus

_engine = ConsistencyEngine()


def resolve_relationship_update(
    old_type: str,
    new_type: str,
    subj_name: str,
    obj_name: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Compatibility wrapper: evaluates a relationship type change for one entity pair using the
    deterministic rule engine and the controlled predicate vocabulary.
    Returns: (status, optional_contradiction_info)
    """
    if not old_type:
        return RelationshipStatus.ACTIVE.value, None

    active = RelationshipStatus.ACTIVE.value
    check = RelationshipCheck(
        subject_name=subj_name,
        object_name=obj_name,
        new=RelationshipVersionView(None, vocab.normalize_predicate(new_type), active),
        pair_history=(RelationshipVersionView(None, vocab.normalize_predicate(old_type), active),),
    )
    findings = _engine.check_relationship(check)
    if not findings:
        return RelationshipStatus.ACTIVE.value, None

    finding = findings[0]
    return RelationshipStatus.CONTRADICTED.value, {
        "contradiction_type": finding.contradiction_type,
        "old_type": old_type,
        "new_type": new_type,
        "explanation": finding.explanation,
    }
