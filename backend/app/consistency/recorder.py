from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.consistency.types import Finding
from app.models.contradiction import Contradiction
from app.repositories.contradiction_repo import ContradictionRepository


class ContradictionRecorder:
    """
    Contradiction persistence. Writes with commit=False (flush only), so rows join the caller's
    transaction, and skips findings that were already recorded (same rule, same conflicting rows).
    """

    def __init__(self, db: Session):
        self.repo = ContradictionRepository(db)

    def record(
        self,
        world_id: str,
        finding: Finding,
        event_db_ids: Optional[Dict[str, str]] = None
    ) -> Optional[Contradiction]:
        """Returns the newly created row, or None if an equivalent contradiction already exists."""
        event_ids = [(event_db_ids or {}).get(ref) for ref in finding.event_refs]
        event_id_a = event_ids[0] if len(event_ids) > 0 else None
        event_id_b = event_ids[1] if len(event_ids) > 1 else None

        common = dict(
            contradiction_type=finding.contradiction_type,
            explanation=finding.stored_explanation,
            old_fact_version_id=finding.old_fact_version_id,
            new_fact_version_id=finding.new_fact_version_id,
            old_relationship_version_id=finding.old_relationship_version_id,
            new_relationship_version_id=finding.new_relationship_version_id,
            event_id_a=event_id_a,
            event_id_b=event_id_b,
        )
        if self.repo.find_existing(
            world_id=world_id, rule_prefix=f"[{finding.rule_id}]", **common
        ) is not None:
            return None
        return self.repo.create_contradiction(
            world_id=world_id, confidence=finding.confidence, commit=False, **common
        )

    def record_all(
        self,
        world_id: str,
        findings: List[Finding],
        event_db_ids: Optional[Dict[str, str]] = None
    ) -> List[Contradiction]:
        created = []
        for finding in findings:
            row = self.record(world_id, finding, event_db_ids)
            if row is not None:
                created.append(row)
        return created
