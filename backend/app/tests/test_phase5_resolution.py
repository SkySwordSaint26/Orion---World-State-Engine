"""Phase 5: deterministic, constrained mention -> entity resolution and its World State integration."""
import ast
import json
import pathlib

import pytest

from app import resolution as resolution_pkg
from app.contracts import (EntityMention, Event, ExtractionResult, FactObservation, Relationship)
from app.models.entity import Entity, EntityAlias, EntityMention as EntityMentionRow
from app.models.relationship import Relationship as RelationshipRow
from app.pipeline import extractor as extractor_module
from app.pipeline.extractor import ExtractionOrchestrator
from app.pipeline.llm_client import llm_client
from app.preprocessing import preprocess_chapter
from app.resolution import (KnownEntity, ResolutionType, is_provisional, name_key, resolve_entities)
from app.services.world_state_service import WorldStateService

R = ResolutionType


def prov(**over):
    base = dict(source_chunk="chunk_0000", source_span=(0, 500), sentence_ids=("s0000",))
    base.update(over)
    return base


def mention(text, canonical=None, type="character", **over):
    return EntityMention(text=text, canonical_name=canonical or text, type=type, **prov(**over))


def resolve(mentions, known=(), document=None, **extra):
    return resolve_entities(ExtractionResult(entity_mentions=tuple(mentions), **extra), known, document)


def only(resolved, i=0):
    return resolved.resolution.resolutions[i]


ROBERT = KnownEntity("e-robert", "Robert", "character")
ALICE_S = KnownEntity("e-alice-s", "Alice Sterling", "character")
ALICE_J = KnownEntity("e-alice-j", "Alice Jones", "character")


# ============================================================================ A / B: exact and case
def test_exact_match_reuses_the_existing_entity():
    r = only(resolve([mention("Robert")], [ROBERT]))
    assert (r.resolved_entity_id, r.resolution_type, r.confidence) == ("e-robert", R.EXACT_MATCH, 1.0)
    assert "Robert" in r.evidence and not r.is_new


def test_surrounding_whitespace_is_still_an_exact_match():
    assert only(resolve([mention("  Robert ")], [ROBERT])).resolution_type is R.EXACT_MATCH


@pytest.mark.parametrize("surface", ["robert", "ROBERT", "Robert."])
def test_case_and_format_variants_resolve_to_the_same_entity(surface):
    r = only(resolve([mention(surface)], [ROBERT]))
    assert r.resolved_entity_id == "e-robert" and r.resolution_type is R.NORMALIZED_MATCH and r.confidence < 1.0


# ============================================================================ C: alias
def test_stored_alias_resolves():
    known = KnownEntity("e1", "Robert Stone", "character", aliases=("Bobby S",))
    r = only(resolve([mention("bobby s")], [known]))
    assert (r.resolved_entity_id, r.resolution_type) == ("e1", R.ALIAS)


def test_nickname_resolves_only_when_unique():
    r = only(resolve([mention("Rob")], [ROBERT]))
    assert (r.resolved_entity_id, r.resolution_type, r.confidence) == ("e-robert", R.ALIAS, 0.7)
    assert "nickname" in r.evidence
    two = resolve([mention("Rob")], [ROBERT, KnownEntity("e-robert-j", "Robert Jones", "character")])
    assert two.resolution.resolutions == () and "ambiguous" in two.resolution.unresolved[0].reason


def test_short_form_resolves_only_when_unique():
    assert only(resolve([mention("Alice")], [ALICE_S])).resolved_entity_id == "e-alice-s"
    amb = resolve([mention("Alice")], [ALICE_S, ALICE_J])
    assert amb.resolution.resolutions == () and amb.resolution.new_entities == ()   # neither guessed nor created
    assert "ambiguous" in amb.resolution.unresolved[0].reason


def test_longer_name_is_not_folded_into_a_shorter_entity():
    r = only(resolve([mention("Alice Sterling")], [KnownEntity("e-a", "Alice", "character")]))
    assert r.is_new   # "Alice Sterling" may be a different Alice: no aggressive merge


def test_title_only_names_are_not_treated_as_short_forms():
    assert only(resolve([mention("Captain")], [KnownEntity("e", "Captain Sterling", "character")])).is_new


def test_type_conflicts_never_merge():
    r = only(resolve([mention("Paris", type="location")], [KnownEntity("e", "Paris", "character")]))
    assert r.is_new
    assert only(resolve([mention("Paris", type="unknown")], [KnownEntity("e", "Paris", "character")])).resolved_entity_id == "e"


def test_duplicate_canonical_names_in_the_world_are_ambiguous():
    known = [KnownEntity("a", "Alice", "character"), KnownEntity("b", "Alice", "character")]
    out = resolve([mention("Alice")], known)
    assert out.resolution.resolutions == () and out.resolution.unresolved


def test_conflicting_canonical_and_surface_are_left_unresolved():
    out = resolve([mention("Alice Jones", canonical="Alice Sterling")], [ALICE_S, ALICE_J])
    assert out.resolution.resolutions == () and "conflicting" in out.resolution.unresolved[0].reason


# ============================================================================ E: new entities
def test_new_entity_is_planned_with_a_provisional_id_and_reused_within_the_batch():
    out = resolve([mention("Dana"), mention("dana"), mention("DANA"), mention("Eve")], [ROBERT])
    r = out.resolution
    assert [x.resolution_type for x in r.resolutions] == [R.NEW_ENTITY, R.NORMALIZED_MATCH, R.NORMALIZED_MATCH, R.NEW_ENTITY]
    ids = [x.resolved_entity_id for x in r.resolutions]
    assert ids[0] == ids[1] == ids[2] != ids[3] and all(is_provisional(i) for i in ids)
    assert [(n.canonical_name, n.first_mention_id) for n in r.new_entities] == [("Dana", "M1"), ("Eve", "M4")]


def test_results_do_not_depend_on_mention_order():
    known = [KnownEntity("s", "Alice Sterling", "character")]
    a = resolve([mention("Alice"), mention("Alice Jones")], known)
    b = resolve([mention("Alice Jones"), mention("Alice")], known)
    for out in (a, b):   # "Alice" is ambiguous between the known Sterling and the batch's Jones, in either order
        assert [u.reason.startswith("ambiguous") for u in out.resolution.unresolved] == [True]
        assert "s" not in out.resolution.mapping.values()
        assert len(out.resolution.new_entities) == 1 and out.resolution.new_entities[0].canonical_name == "Alice Jones"


def test_batch_only_names_are_never_heuristic_targets():
    for order in (["Alice", "Alice Jones"], ["Alice Jones", "Alice"]):
        out = resolve([mention(n) for n in order])
        assert not out.resolution.unresolved and len(out.resolution.new_entities) == 2   # two entities, no merge


def test_resolution_is_deterministic_and_serializable():
    ms = [mention("Rob"), mention("robert"), mention("Zed")]
    a, b = resolve(ms, [ROBERT]), resolve(ms, [ROBERT])
    assert a.resolution == b.resolution
    assert json.loads(a.resolution.to_json())["resolutions"][0]["resolution_type"] == "alias"
    assert a.resolution.mapping == {"M1": "e-robert", "M2": "e-robert", "M3": a.resolution.mapping["M3"]}


# ============================================================================ D: pronouns
def doc(text):
    return preprocess_chapter(text)


def pronouns(text, mentions, known=()):
    out = resolve(mentions, known, doc(text))
    return [(m.text, m.entity_id, m.start, m.end) for m in out.result.entity_mentions if m.mention_kind == "pronominal"], out


def test_pronoun_resolves_to_the_only_person_in_the_paragraph():
    text = "Alice walked home. She smiled."
    got, out = pronouns(text, [mention("Alice")])
    [(t, eid, s, e)] = got
    assert t == "She" and text[s:e] == "She" and eid == only(out).resolved_entity_id
    p = out.resolution.get("M2")
    assert p.resolution_type is R.PRONOUN and p.confidence == 0.5 and "Alice" in p.evidence


def test_pronoun_offsets_are_exact_in_a_multi_paragraph_chapter():
    text = "Chapter 1\n\nBob left early. He was tired.\n\nAlice stayed. They said nothing."
    got, _ = pronouns(text, [mention("Bob"), mention("Alice")])
    assert [(t, text[s:e]) for t, _, s, e in got] == [("He", "He"), ("They", "They")]
    assert got[0][1] != got[1][1]                       # each paragraph has its own single antecedent


def test_a_paragraph_with_two_people_blocks_the_pronoun():
    text = "Chapter 1\n\nBob left early. He was tired.\n\nAlice met Bob. They said nothing."
    got, _ = pronouns(text, [mention("Bob"), mention("Alice")])
    assert [t for t, *_ in got] == ["He"]


def test_ambiguous_pronoun_is_not_resolved():
    got, _ = pronouns("Alice met Bob. He smiled.", [mention("Alice"), mention("Bob")])
    assert got == []


def test_pronoun_needs_an_antecedent_in_the_same_paragraph():
    got, _ = pronouns("Alice walked home.\n\nShe smiled.", [mention("Alice")])
    assert got == []


@pytest.mark.parametrize("text", [
    "Alice said that he was late.",             # not sentence-initial: could be anyone
    '"Alice is here. He is late," said Bob.',   # inside a quotation
    "The house was old. He smiled.",           # no person named
])
def test_unsafe_pronoun_positions_are_left_alone(text):
    mentions = [mention("Alice")] if "Alice" in text else [mention("Zed")]
    got, _ = pronouns(text, mentions)
    assert got == []


def test_pronoun_never_targets_non_person_entities():
    got, _ = pronouns("The tower fell. It rose. He watched.", [mention("The tower", type="location")])
    assert got == []


def test_pronoun_uses_existing_world_state_entities():
    known = [KnownEntity("e-robert", "Robert", "character")]
    got, out = pronouns("Robert waited. She never came.", [mention("Rob", canonical="Rob")], known)
    # the antecedent "Robert" is found through the resolved entity's canonical name, not just the mention text
    assert got and got[0][1] == "e-robert"


# ============================================================================ attach entity ids
def test_entity_ids_attach_to_mentions_relationships_events_and_facts():
    out = resolve(
        [mention("Robert"), mention("Zed")], [ROBERT],
        relationships=(Relationship(subject="robert", predicate="KNOWS", object="Zed", **prov()),
                       Relationship(subject="Robert", predicate="KNOWS", object="Nobody", **prov())),
        events=(Event(local_id="e1", participants=("Robert", "Zed", "Ghost"), **prov()),),
        facts=(FactObservation(entity="ROBERT", property="age", value="3", **prov()),
               FactObservation(entity="Ghost", property="age", value="3", **prov())))
    zed = out.resolution.mapping["M2"]
    r = out.result
    assert [m.entity_id for m in r.entity_mentions] == ["e-robert", zed]
    assert (r.relationships[0].subject_entity_id, r.relationships[0].object_entity_id) == ("e-robert", zed)
    assert r.relationships[1].object_entity_id is None                     # unknown name: not invented
    assert r.events[0].participant_entity_ids == ("e-robert", zed, None)
    assert [f.entity_id for f in r.facts] == ["e-robert", None]
    for o in r.observations():                                              # spans / sentence ids untouched
        assert o.source_span == (0, 500) and o.sentence_ids == ("s0000",)


def test_ambiguous_names_do_not_attach_ids():
    out = resolve([mention("Alice")], [ALICE_S, ALICE_J],
                  relationships=(Relationship(subject="Alice", predicate="KNOWS", object="Alice", **prov()),))
    assert out.result.relationships[0].subject_entity_id is None and out.result.entity_mentions[0].entity_id is None


def test_a_name_that_maps_to_two_entities_is_dropped_from_the_lookup():
    known = [KnownEntity("a", "Alice", "character"), KnownEntity("b", "Bob", "character")]
    out = resolve([mention("Al", canonical="Alice"), mention("Al", canonical="Bob")], known)
    assert out.resolution.mapping == {"M1": "a", "M2": "b"}
    assert name_key("Al") not in out.name_map and out.name_map[name_key("Alice")] == "a" and out.name_map[name_key("Bob")] == "b"


def test_rebind_replaces_provisional_ids_everywhere():
    out = resolve([mention("Zed")], [], relationships=(Relationship(subject="Zed", predicate="KNOWS", object="Zed", **prov()),))
    p = out.resolution.mapping["M1"]
    bound = out.rebind({p: "real-1"})
    assert bound.resolution.mapping["M1"] == "real-1" and bound.result.entity_mentions[0].entity_id == "real-1"
    assert bound.result.relationships[0].subject_entity_id == "real-1" and bound.name_map[name_key("Zed")] == "real-1"


# ============================================================================ World State integration
TEXT = "Chapter {n}\n\n{body}"


def extract(monkeypatch, body, payload):
    monkeypatch.setattr(llm_client, "generate", lambda **kw: json.dumps(payload))
    return ExtractionOrchestrator().extract_chapter(body, 1)


def integrate(env, w, chapter, data):
    with env.Session() as s:
        svc = WorldStateService(s)
        counts = svc.integrate_extraction_result(
            w["world_id"], data, chapter_id=w["runs"][chapter]["chapter_id"],
            chapter_version_id=w["runs"][chapter]["chapter_version_id"])
        s.commit()
        return counts, svc.last_resolution


def entities(env, world_id):
    with env.Session() as s:
        return sorted(e.canonical_name for e in s.query(Entity).filter_by(world_id=world_id))


def person(name, mention=None, **kw):
    return {"mention": mention or name, "canonical_name": name, "type": "character", "attributes": {}, **kw}


def test_existing_entity_is_reused_for_a_nickname_instead_of_creating_a_duplicate(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("N", chapters=2)
    integrate(env, w, 1, extract(monkeypatch, "Robert walked to the tower.", {"entities": [person("Robert")]}))
    data = extract(monkeypatch, "Rob met Zed at the gate.", {
        "entities": [person("Rob"), person("Zed")],
        "relationships": [{"subject": "Rob", "predicate": "KNOWS", "object": "Zed"}],
        "events": [{"id": "e1", "type": "MEETING", "participants": ["Rob", "Zed"]}]})
    counts, res = integrate(env, w, 2, data)

    assert entities(env, w["world_id"]) == ["Robert", "Zed"]            # no "Rob" duplicate
    assert counts["entities_created"] == 1
    with env.Session() as s:
        robert = s.query(Entity).filter_by(canonical_name="Robert").one()
        zed = s.query(Entity).filter_by(canonical_name="Zed").one()
        rel = s.query(RelationshipRow).one()
        assert (rel.source_entity_id, rel.target_entity_id) == (robert.id, zed.id)
        assert s.query(EntityAlias).count() == 0                         # heuristic matches persist no alias
    r = res.result
    assert r.entity_mentions[0].entity_id == robert.id and r.entity_mentions[1].entity_id == zed.id
    assert (r.relationships[0].subject_entity_id, r.relationships[0].object_entity_id) == (robert.id, zed.id)
    assert r.events[0].participant_entity_ids == (robert.id, zed.id)
    assert res.resolution.get("M1").resolution_type is R.ALIAS
    assert not any(is_provisional(i) for i in res.resolution.mapping.values())   # all rebound to real rows


def test_ambiguous_short_form_falls_back_to_legacy_behavior_without_a_merge(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("A", chapters=2)
    integrate(env, w, 1, extract(monkeypatch, "Alice Sterling and Alice Jones met.",
                                 {"entities": [person("Alice Sterling"), person("Alice Jones")]}))
    counts, res = integrate(env, w, 2, extract(monkeypatch, "Alice smiled.", {"entities": [person("Alice")]}))
    assert entities(env, w["world_id"]) == ["Alice", "Alice Jones", "Alice Sterling"]  # legacy: new entity, no guess
    assert res.resolution.unresolved and res.result.entity_mentions[0].entity_id is None


def test_pronoun_mentions_are_persisted_with_exact_offsets(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("P", chapters=1)
    body = "Robert climbed the stairs. He was tired.\n\nZed waited below."
    counts, res = integrate(env, w, 1, extract(monkeypatch, body, {"entities": [person("Robert"), person("Zed")]}))
    with env.Session() as s:
        robert = s.query(Entity).filter_by(canonical_name="Robert").one()
        rows = s.query(EntityMentionRow).filter(EntityMentionRow.start_position.isnot(None)).all()
        [row] = rows
        assert (row.entity_id, row.surface_text, row.confidence) == (robert.id, "He", 0.5)
        assert body[row.start_position:row.end_position] == "He"
        assert s.query(EntityMentionRow).filter_by(entity_id=robert.id).count() == 2   # "Robert" + "He"


def test_hand_built_dicts_keep_the_legacy_path(phase1_env):
    env = phase1_env
    w = env.make_world("L", chapters=1)
    with env.Session() as s:
        svc = WorldStateService(s)
        svc.integrate_extraction_result(w["world_id"], {"entities": [person("Robert")]},
                                        chapter_id=w["runs"][1]["chapter_id"],
                                        chapter_version_id=w["runs"][1]["chapter_version_id"])
        assert svc.last_resolution is None


# ============================================================================ layering
def test_resolution_package_is_pure():
    root = pathlib.Path(resolution_pkg.__file__).parent
    banned = ("llm_client", "httpx", "requests", "openai", "spacy", "nltk", "numpy", "sqlalchemy", "torch", "sklearn",
              "app.models", "app.repositories", "app.services", "app.pipeline")
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                assert not any(m == b or m.startswith(b + ".") for b in banned), (path.name, m)
