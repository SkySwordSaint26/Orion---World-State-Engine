from typing import Any, Dict, Optional, Tuple

from app.consistency import ConsistencyEngine
from app.consistency import vocabulary as vocab
from app.consistency.types import FactCheck, FactVersionView
from app.core.constants import FactStatus

_engine = ConsistencyEngine()


def compare_fact_values(old_val: Any, new_val: Any) -> bool:
    """Returns True if values represent the same information."""
    return vocab.values_equal(old_val, new_val)


def resolve_fact_update(
    property_name: str,
    old_value: Any,
    new_value: Any,
    entity_name: str = "Entity"
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Compatibility wrapper: evaluates one attribute update against a single known ACTIVE value using the
    deterministic rule engine (no chapter information, so order-dependent rules such as age do not apply).
    Returns: (new_status, optional_contradiction_info)
    """
    if old_value is None or old_value == "":
        return FactStatus.ACTIVE.value, None

    check = FactCheck(
        entity_name=entity_name,
        property_name=vocab.normalize_property(property_name),
        new=FactVersionView(None, new_value, FactStatus.ACTIVE.value),
        history=(FactVersionView(None, old_value, FactStatus.ACTIVE.value),),
    )
    findings = _engine.check_fact(check)
    if not findings:
        return FactStatus.ACTIVE.value, None

    finding = findings[0]
    return FactStatus.CONTRADICTED.value, {
        "contradiction_type": finding.contradiction_type,
        "property_name": property_name,
        "old_value": old_value,
        "new_value": new_value,
        "explanation": finding.explanation,
    }
