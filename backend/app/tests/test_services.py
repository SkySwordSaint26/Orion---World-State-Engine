import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.world_state_service import WorldStateService
from app.services.entity_service import EntityService
from app.services.consistency_service import ConsistencyService
from app.services.graph_service import GraphService
from app.services.timeline_service import TimelineService
from app.services.chapter_service import ChapterService
from app.repositories.manuscript_repo import ManuscriptRepository

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_world_state_service(db_session):
    service = WorldStateService(db_session)
    world = service.create_world("Terra Nova", "A frontier planet")
    assert world.id is not None
    assert world.name == "Terra Nova"

    stats = service.get_world_stats(world.id)
    assert stats["entities_count"] == 0

def test_entity_service(db_session):
    ws_service = WorldStateService(db_session)
    world = ws_service.create_world("Avalon", "Mythical realm")

    ent_service = EntityService(db_session)
    entity = ent_service.create_entity(
        world_id=world.id,
        canonical_name="King Arthur",
        entity_type="character",
        aliases=["Arthur Pendragon", "Warden of Britain"],
        attributes={"status": "King", "weapon": "Excalibur"}
    )
    assert entity.canonical_name == "King Arthur"
    assert len(entity.aliases) == 2

    # Add fact
    fact_ver = ent_service.add_fact(entity.id, "realm", "Camelot")
    assert fact_ver.value == "Camelot"

def test_consistency_service_cycle_detection(db_session):
    ws_service = WorldStateService(db_session)
    world = ws_service.create_world("Temporal Void")

    con_service = ConsistencyService(db_session)
    events = [
        {"id": "ev_1", "description": "Departure"},
        {"id": "ev_2", "description": "Arrival"}
    ]
    # Cycle: ev_1 BEFORE ev_2, and ev_2 BEFORE ev_1
    temporal_relations = [
        {"event_1": "ev_1", "relation": "BEFORE", "event_2": "ev_2"},
        {"event_1": "ev_2", "relation": "BEFORE", "event_2": "ev_1"}
    ]
    # Check
    cons = con_service.run_checks(world.id, events, temporal_relations)
    assert len(cons) >= 1
    assert "cycle" in cons[0].explanation.lower()

def test_graph_and_timeline_services(db_session):
    ws_service = WorldStateService(db_session)
    world = ws_service.create_world("Nexus")

    ent_service = EntityService(db_session)
    e1 = ent_service.create_entity(world.id, "Dr. John", "character")
    e2 = ent_service.create_entity(world.id, "Neo Tokyo", "location")

    # Connect relationship
    ws_service.integrate_extraction_result(
        world_id=world.id,
        extraction_data={
            "entities": [],
            "relationships": [
                {"subject": "Dr. John", "predicate": "LOCATED_IN", "object": "Neo Tokyo"}
            ],
            "events": [
                {"id": "ev_lab", "type": "DISCOVERY", "description": "New energy source found", "participants": ["Dr. John"]}
            ]
        }
    )

    graph_service = GraphService(db_session)
    graph = graph_service.get_world_graph(world.id)
    assert len(graph.nodes) >= 2
    assert len(graph.edges) == 1
    assert graph.edges[0].type == "LOCATED_IN"

    timeline_service = TimelineService(db_session)
    timeline = timeline_service.get_world_timeline(world.id)
    assert timeline.total == 1
    assert timeline.events[0].event_type == "DISCOVERY"

def test_delete_chapter_removes_empty_manuscript(db_session):
    ws_service = WorldStateService(db_session)
    world = ws_service.create_world("Manuscript Realm")

    ms_repo = ManuscriptRepository(db_session)
    manuscript = ms_repo.create({
        "world_id": world.id,
        "title": "Test Book",
        "file_type": "text/plain"
    })

    ch_service = ChapterService(db_session)
    ch1 = ch_service.create_chapter(manuscript.id, "Chapter 1", "Content 1")
    ch2 = ch_service.create_chapter(manuscript.id, "Chapter 2", "Content 2")

    # Delete first chapter - manuscript should still exist
    ch_service.delete_chapter(ch1.id)
    assert ms_repo.get(manuscript.id) is not None
    assert len(ch_service.list_chapters(manuscript.id)) == 1

    # Delete second chapter - chapter count reaches 0, so manuscript should be automatically deleted
    ch_service.delete_chapter(ch2.id)
    assert ms_repo.get(manuscript.id) is None
