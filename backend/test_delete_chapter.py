import os
import sys

from app.core.database import SessionLocal
from app.services.chapter_service import ChapterService
from app.models.world import World
from app.models.manuscript import Manuscript
from app.models.entity import Entity
from app.models.fact import Fact, FactVersion

if __name__ == "__main__":
    db = SessionLocal()
    world = db.query(World).first()
    if world:
        if not world.manuscripts:
            ms = Manuscript(world_id=world.id, title="Test Manuscript")
            db.add(ms)
            db.commit()
            db.refresh(ms)
        else:
            ms = world.manuscripts[0]

        service = ChapterService(db)
        ch = service.create_chapter(ms.id, "Test Chapter with Fact", "Content")
        print(f"Created chapter {ch.id}")

        # Create an entity
        ent = Entity(world_id=world.id, canonical_name="Test Entity", entity_type="character")
        db.add(ent)
        db.commit()

        # Create a fact
        fact = Fact(entity_id=ent.id, property_name="test_prop")
        db.add(fact)
        db.commit()

        # Create a fact version linked to the chapter and chapter version
        ch_version = ch.versions[0]
        fv = FactVersion(fact_id=fact.id, chapter_id=ch.id, chapter_version_id=ch_version.id, value={"test": "test"})
        db.add(fv)
        db.commit()

        print(f"Created fact version linked to chapter {ch.id}")

        try:
            service.delete_chapter(ch.id)
            print("Success deleting chapter with fact!")
        except Exception as e:
            print("Failed to delete chapter with fact!")
            import traceback
            traceback.print_exc()

