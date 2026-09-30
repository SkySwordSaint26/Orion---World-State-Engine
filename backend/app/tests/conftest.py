"""
Fixtures for the Phase 1 execution-safety tests (extraction failure handling, atomic integration,
chapter ordering, job/run error handling).

`phase1_env` is opt-in (not autouse), so the older tests are unaffected. It uses a FILE-backed SQLite
database so every session gets its own connection: a rollback or a missing commit is then visible
exactly as it would be to another worker process.
"""
import re
from typing import Callable, Dict, List, Optional, Set, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.core.database import Base
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.contradiction import Contradiction
from app.models.entity import Entity, EntityAlias, EntityMention
from app.models.event import Event, EventParticipant
from app.models.extraction_run import ExtractionRun
from app.models.fact import Fact, FactVersion
from app.models.processing_job import ProcessingJob
from app.models.relationship import Relationship, RelationshipVersion
from app.models.world import World
from app.pipeline import extractor
from app.services.manuscript_service import ManuscriptService
from app.services.world_state_service import WorldStateService
from app.workers.tasks import extraction_task, job_update_task


class Phase1Env:
    def __init__(self, tmp_path, monkeypatch):
        self.engine = create_engine(
            f"sqlite:///{tmp_path / 'phase1.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.monkeypatch = monkeypatch

        # The worker and the job rollup open their own sessions through these factories.
        monkeypatch.setattr(extraction_task, "SessionLocal", self.Session)
        monkeypatch.setattr(job_update_task, "SessionLocal", self.Session)
        monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "storage"))

        self.extract_calls: List[Tuple[str, int]] = []      # (world tag, chapter number) per extraction
        self.extract_fail: Set[Tuple[str, int]] = set()      # (world tag, chapter number) that must fail
        self.integration_order: List[int] = []               # chapter numbers, in integration order
        self._worlds: Dict[str, str] = {}

    # ---- fake extractor (stands in for the extraction pipeline, which needs the GPU) -------------------------------
    def install_fake_extractor(self) -> None:
        env = self

        def fake_extract_chapter(text, chapter_number):
            tag = re.search(r"\[(\w+)\]", text).group(1)
            env.extract_calls.append((tag, chapter_number))
            if (tag, chapter_number) in env.extract_fail:
                raise RuntimeError(f"simulated extraction failure for {tag} chapter {chapter_number}")
            hero = f"Hero{tag}{'ABCDEFGHIJ'[chapter_number]}"
            shared = f"Shared{tag}"
            return {
                "chapter_number": chapter_number,
                "entities": [
                    {"canonical_name": hero, "type": "character", "mention": hero, "aliases": [],
                     "attributes": {"age": str(30 + chapter_number)}},
                    {"canonical_name": shared, "type": "character", "mention": shared, "aliases": [],
                     "attributes": {"rank": f"Rank{chapter_number}"}},
                ],
                "relationships": [{"subject": hero, "predicate": "KNOWS", "object": shared}],
                "events": [
                    {"id": "e1", "type": "MEETING", "participants": [hero, shared], "evidence": f"{hero} met {shared}"},
                    {"id": "e2", "type": "TRAVEL", "participants": [hero], "evidence": f"{hero} travelled"},
                ],
                "temporal_relations": [],
            }

        self.monkeypatch.setattr(extractor, "extract_chapter", fake_extract_chapter)

        original = WorldStateService.integrate_extraction_result

        def spy(service, world_id, extraction_data, chapter_id=None, *args, **kwargs):
            with env.Session() as s:
                chapter = s.get(Chapter, chapter_id)
                env.integration_order.append(chapter.chapter_number if chapter else -1)
            return original(service, world_id, extraction_data, chapter_id, *args, **kwargs)

        self.monkeypatch.setattr(WorldStateService, "integrate_extraction_result", spy)

    # ---- data builders --------------------------------------------------------------------
    def make_world(self, tag: str, chapters: int = 3) -> Dict:
        """Creates a world and uploads a real chapter-split manuscript through ManuscriptService."""
        with self.Session() as s:
            world = World(name=f"World {tag}", description="")
            s.add(world)
            s.commit()
            world_id = world.id
            text = "\n\n".join(
                f"Chapter {n}: Title {n}\nAlice Sterling walked to Silver Haven. [{tag}]" for n in range(1, chapters + 1)
            )
            result = ManuscriptService(s).upload_manuscript(world_id, f"{tag}.txt", text.encode("utf-8"))
        self._worlds[tag] = world_id
        return {"world_id": world_id, **result, "runs": self.runs_by_chapter(result["job_id"])}

    def runs_by_chapter(self, job_id: str) -> Dict[int, dict]:
        with self.Session() as s:
            rows = s.query(ExtractionRun, Chapter).join(
                ChapterVersion, ExtractionRun.chapter_version_id == ChapterVersion.id
            ).join(Chapter, ChapterVersion.chapter_id == Chapter.id).filter(
                ExtractionRun.processing_job_id == job_id
            ).all()
            return {
                ch.chapter_number: {
                    "run_id": run.id, "chapter_id": ch.id, "chapter_version_id": run.chapter_version_id
                } for run, ch in rows
            }

    def execute(self, world_id: str, job_id: str, info: dict, **kwargs):
        return extraction_task.execute_chapter_extraction(
            world_id=world_id, job_id=job_id, extraction_run_id=info["run_id"],
            chapter_id=info["chapter_id"], chapter_version_id=info["chapter_version_id"], **kwargs
        )

    # ---- observations (always through a FRESH session = what another process would see) ------
    def world_rows(self, world_id: str) -> Dict[str, int]:
        with self.Session() as s:
            entity_ids = [e.id for e in s.query(Entity).filter(Entity.world_id == world_id)]
            fact_ids = [f.id for f in s.query(Fact).filter(Fact.entity_id.in_(entity_ids))] if entity_ids else []
            event_ids = [e.id for e in s.query(Event).filter(Event.world_id == world_id)]
            rel_ids = [r.id for r in s.query(Relationship).filter(Relationship.world_id == world_id)]
            return {
                "entities": len(entity_ids),
                "aliases": s.query(EntityAlias).filter(EntityAlias.entity_id.in_(entity_ids)).count() if entity_ids else 0,
                "mentions": s.query(EntityMention).filter(EntityMention.entity_id.in_(entity_ids)).count() if entity_ids else 0,
                "facts": len(fact_ids),
                "fact_versions": s.query(FactVersion).filter(FactVersion.fact_id.in_(fact_ids)).count() if fact_ids else 0,
                "relationships": len(rel_ids),
                "relationship_versions": s.query(RelationshipVersion).filter(RelationshipVersion.relationship_id.in_(rel_ids)).count() if rel_ids else 0,
                "events": len(event_ids),
                "event_participants": s.query(EventParticipant).filter(EventParticipant.event_id.in_(event_ids)).count() if event_ids else 0,
                "contradictions": s.query(Contradiction).filter(Contradiction.world_id == world_id).count(),
            }

    def fact_statuses(self, world_id: str, entity_name: str, prop: str) -> List[Tuple[str, str]]:
        with self.Session() as s:
            ent = s.query(Entity).filter(Entity.world_id == world_id, Entity.canonical_name == entity_name).first()
            if ent is None:
                return []
            fact = s.query(Fact).filter(Fact.entity_id == ent.id, Fact.property_name == prop).first()
            if fact is None:
                return []
            versions = s.query(FactVersion).filter(FactVersion.fact_id == fact.id).order_by(FactVersion.created_at, FactVersion.id).all()
            return [(v.value, v.status) for v in versions]

    def run(self, run_id: str) -> Tuple[str, Optional[str]]:
        with self.Session() as s:
            r = s.get(ExtractionRun, run_id)
            return r.status, r.error_message

    def job(self, job_id: str) -> Dict:
        with self.Session() as s:
            j = s.get(ProcessingJob, job_id)
            return {"status": j.status, "completed": j.chapters_completed, "total": j.chapters_total,
                    "error": j.error_message, "completed_at": j.completed_at}


@pytest.fixture
def phase1_env(tmp_path, monkeypatch):
    return Phase1Env(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def independent_of_env(monkeypatch, tmp_path):
    """Uploaded files go to a temporary folder, not the running app's backend/storage."""
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "storage"))
