"""How contradictions reach the API: the contradictions list serializes, and an entity's current fact value is never
the contradicted claim."""
from datetime import datetime

from types import SimpleNamespace

from app.api.v1.routes.entities import current_version
from app.models.contradiction import Contradiction
from app.schemas.contradiction import ContradictionResponse


def test_a_contradiction_row_serializes():
    row = Contradiction(id="c1", world_id="w1", contradiction_type="FACT_FACT", confidence=0.7, status="DETECTED",
                        explanation="[AGE_MONOTONIC] Age of 'Evelyn' decreased", created_at=datetime(2026, 9, 30))
    out = ContradictionResponse.model_validate(row).model_dump()
    assert out["explanation"].startswith("[AGE_MONOTONIC]") and "metadata" not in out


def test_the_current_value_is_the_newest_active_version_not_a_newer_contradicted_one():
    v = lambda value, status: SimpleNamespace(value=value, status=status)
    fact = SimpleNamespace(versions=[v("nineteen", "CONTRADICTED"), v("twenty four", "ACTIVE"), v("20", "SUPERSEDED")])
    assert current_version(fact).value == "twenty four"
    assert current_version(SimpleNamespace(versions=[v("x", "CONTRADICTED")])).value == "x"
    assert current_version(SimpleNamespace(versions=[])) is None
