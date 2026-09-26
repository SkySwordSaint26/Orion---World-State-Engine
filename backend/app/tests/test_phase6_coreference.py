"""Phase 6: document-level coreference clusters and cluster-based grounding."""
import ast
import json
import pathlib
from dataclasses import replace

import pytest

from app import coreference as coref_pkg
from app.contracts import (ContractError, CoreferenceCluster, EntityMention, Event, ExtractionResult,
                           FactObservation, Relationship, assign_ids)
from app.coreference import apply_coreference, build_clusters, locate_evidence
from app.models.event import EventParticipant
from app.models.relationship import Relationship as RelationshipRow
from app.models.entity import Entity
from app.pipeline.extractor import ExtractionOrchestrator
from app.pipeline.llm_client import llm_client
from app.preprocessing import preprocess_chapter
from app.resolution import KnownEntity, resolve_entities
from app.services.world_state_service import WorldStateService
from app.tests.test_phase5_resolution import mention, person, prov

ROBERT = KnownEntity("e-robert", "Robert", "character")
ALICE_S = KnownEntity("e-alice-s", "Alice Sterling", "character")
ALICE_J = KnownEntity("e-alice-j", "Alice Jones", "character")


def ms(*mentions):
    return assign_ids(ExtractionResult(entity_mentions=tuple(mentions))).entity_mentions


def ids(result):
    return [list(c.mentions) for c in result.clusters]


# ============================================================================ A: exact text
def test_same_normalized_text_clusters_without_any_entity_information():
    out = build_clusters(ms(mention("Zed"), mention("Yan"), mention("zed"), mention("ZED.")))
    assert ids(out) == [["M1", "M3", "M4"]]
    [c] = out.clusters
    assert (c.cluster_id, c.entity_id, c.canonical_name, c.rules) == ("C1", None, "Zed", ("exact_text",))
    assert out.mapping == {"M1": "C1", "M3": "C1", "M4": "C1"}


def test_singletons_and_different_texts_do_not_form_clusters():
    assert build_clusters(ms(mention("Zed"), mention("Yan"), mention("Eve"))).clusters == ()
    assert build_clusters(()).clusters == ()


def test_similar_but_different_texts_are_not_clustered():   # no fuzzy matching, no similarity
    assert build_clusters(ms(mention("Robert"), mention("Rob"), mention("Roberto"), mention("Robert Stone"))).clusters == ()


def test_pronoun_texts_never_cluster_by_text():
    he = lambda: mention("He", mention_kind="pronominal", start=0, end=2)   # noqa: E731
    assert build_clusters(ms(he(), he())).clusters == ()


def test_types_that_disagree_do_not_merge_and_unknown_type_is_left_out():
    out = build_clusters(ms(mention("Paris", type="location"), mention("Paris", type="character"),
                            mention("Paris", type="location"), mention("Paris", type="unknown")))
    assert ids(out) == [["M1", "M3"]]                       # only the two locations; the unknown one is not guessed


# ============================================================================ B: same resolved entity
def test_mentions_resolved_to_the_same_entity_cluster_together():
    r = resolve_entities(ExtractionResult(entity_mentions=(mention("Robert"), mention("robert"), mention("Rob"), mention("Zed"))), [ROBERT])
    out = build_clusters(r.result.entity_mentions)
    [c] = out.clusters
    assert c.mentions == ("M1", "M2", "M3") and c.entity_id == "e-robert"
    assert c.rules == ("exact_text", "same_entity")          # "Robert"/"robert" share text; "Rob" joins by entity only
    r2 = resolve_entities(ExtractionResult(entity_mentions=(mention("Robert"), mention("Rob"))), [ROBERT])
    assert build_clusters(r2.result.entity_mentions).clusters[0].rules == ("same_entity",)


def test_new_entities_cluster_by_their_provisional_id():
    r = resolve_entities(ExtractionResult(entity_mentions=(mention("Dana"), mention("DANA"), mention("Eve"))), [])
    [c] = build_clusters(r.result.entity_mentions).clusters
    assert c.mentions == ("M1", "M2") and c.entity_id.startswith("new:")


def test_same_text_but_different_entities_is_never_merged():
    a = replace(mention("Al"), entity_id="e-a")
    b = replace(mention("Al"), entity_id="e-b")
    assert build_clusters(ms(a, b)).clusters == ()


def test_a_mention_without_entity_is_not_merged_into_an_entity_cluster_by_text():
    resolved = replace(mention("Zed"), entity_id="e-z")
    assert build_clusters(ms(resolved, mention("Zed"))).clusters == ()                # cannot tell: no guess
    assert ids(build_clusters(ms(resolved, replace(mention("Zed"), entity_id="e-z"), mention("Zed")))) == [["M1", "M2"]]


# ============================================================================ C: pronouns
def coref_for(text, mentions, known=()):
    doc = preprocess_chapter(text)
    resolved = resolve_entities(ExtractionResult(entity_mentions=tuple(mentions)), known, doc)
    return apply_coreference(resolved, doc), doc


def test_resolved_pronoun_joins_its_antecedents_cluster():
    text = "Alice walked home. She smiled."
    (resolved, coref), _ = coref_for(text, [mention("Alice")])
    [c] = coref.clusters
    pron = [m for m in resolved.result.entity_mentions if m.mention_kind == "pronominal"]
    assert c.mentions == ("M1", pron[0].id) and c.rules == ("pronoun",) and c.canonical_name == "Alice"
    assert c.entity_id == pron[0].entity_id == resolved.result.entity_mentions[0].entity_id
    assert coref.mapping[pron[0].id] == "C1"
    assert resolved.result.coreference_clusters == coref.clusters


def test_each_pronoun_attaches_to_its_own_paragraphs_person():
    text = "Bob sat. He smiled.\n\nAlice stood. She left."
    (resolved, coref), _ = coref_for(text, [mention("Bob"), mention("Alice")])
    assert len(coref.clusters) == 2
    for c in coref.clusters:
        assert len({resolved.result.entity_mentions[[m.id for m in resolved.result.entity_mentions].index(i)].entity_id
                    for i in c.mentions}) == 1


def test_an_unresolved_pronoun_is_not_attached_anywhere():
    (resolved, coref), _ = coref_for("Alice met Bob. He smiled.", [mention("Alice"), mention("Bob")])
    assert coref.clusters == () and not any(m.mention_kind == "pronominal" for m in resolved.result.entity_mentions)


# ============================================================================ ambiguity
def test_ambiguous_mentions_are_never_clustered_even_with_identical_text():
    r = resolve_entities(ExtractionResult(entity_mentions=(mention("Alice"), mention("Alice"))), [ALICE_S, ALICE_J])
    assert len(r.resolution.unresolved) == 2
    resolved, coref = apply_coreference(r)
    assert coref.clusters == () and coref.mapping == {}
    # contrast: without the exclusion the same string WOULD cluster, so the exclusion is what protects us
    assert build_clusters(r.result.entity_mentions).clusters != ()


def test_excluded_mentions_are_dropped_from_otherwise_valid_clusters():
    ms_ = ms(mention("Zed"), mention("Zed"), mention("Zed"))
    assert ids(build_clusters(ms_, excluded=["M2"])) == [["M1", "M3"]]


# ============================================================================ consistency invariants
def scenario():
    text = "Robert sat. He smiled.\n\nAlice Sterling stood. She left. Zed waited. Rob saw Zed."
    mentions = [mention("Robert"), mention("Rob"), mention("Alice Sterling"), mention("Zed"), mention("zed"),
                mention("Alice"), mention("Paris", type="location"), mention("Paris", type="character")]
    return coref_for(text, mentions, [ROBERT])


def test_cluster_invariants_hold():
    (resolved, coref), doc = scenario()
    by_id = {m.id: m for m in resolved.result.entity_mentions}
    seen = set()
    for n, c in enumerate(coref.clusters, 1):
        assert c.cluster_id == f"C{n}"
        assert len(c.mentions) >= 2 and len(set(c.mentions)) == len(c.mentions)
        assert not seen & set(c.mentions)                                   # a mention is in at most one cluster
        seen |= set(c.mentions)
        assert list(c.mentions) == sorted(c.mentions, key=lambda i: int(i[1:]))
        entities = {by_id[i].entity_id for i in c.mentions}
        assert len(entities) == 1 and None not in entities and c.entity_id in entities   # one entity per cluster
        assert c.rules and set(c.rules) <= {"exact_text", "same_entity", "pronoun"}
    unresolved = {u.mention_id for u in resolved.resolution.unresolved}
    assert not unresolved & seen
    assert set(coref.mapping) == seen
    # the two Paris mentions (location vs character) never share a cluster
    paris = [m.id for m in resolved.result.entity_mentions if m.text == "Paris"]
    assert not any(set(paris) <= set(c.mentions) for c in coref.clusters)


def test_clustering_is_deterministic_and_serializable():
    (r1, c1), _ = scenario()
    (r2, c2), _ = scenario()
    assert c1 == c2 and c1.to_dict() == c2.to_dict()
    assert json.loads(json.dumps(c1.to_dict()))["clusters"][0]["cluster_id"] == "C1"


def test_the_contract_rejects_malformed_clusters():
    for bad in (dict(cluster_id="C1", mentions=("M1",)), dict(cluster_id="C1", mentions=("M1", "M1")),
                dict(cluster_id="X1", mentions=("M1", "M2")), dict(cluster_id="C1", mentions=("M1", "E2")),
                dict(cluster_id="C1", mentions=("M1", "M2"), canonical_name=" "),
                dict(cluster_id="C1", mentions=("M1", "M2"), entity_id="")):
        with pytest.raises(ContractError):
            CoreferenceCluster(**bad)
    c = CoreferenceCluster(cluster_id="C1", mentions=("M1", "M2"), entity_id="e", canonical_name="A", rules=("pronoun",))
    assert c.to_gold_dict() == {"cluster_id": "C1", "mentions": ["M1", "M2"]}      # gold shape stays strict


def test_build_clusters_requires_ids():
    with pytest.raises(ValueError):
        build_clusters([mention("Zed"), mention("Zed")])


# ============================================================================ grounding through clusters
HIT = "Robert arrived at the gate. He hit John."


def grounded(text, mentions, relationships=(), events=(), facts=(), known=()):
    doc = preprocess_chapter(text)
    n = len(text)
    fix = lambda o: replace(o, source_span=(0, n), sentence_ids=tuple(s.id for s in doc.sentences))   # noqa: E731
    result = ExtractionResult(entity_mentions=tuple(fix(m) for m in mentions), relationships=tuple(fix(r) for r in relationships),
                              events=tuple(fix(e) for e in events), facts=tuple(fix(f) for f in facts))
    resolved = resolve_entities(result, known, doc)
    return resolved, *apply_coreference(resolved, doc)


def rel(subject, obj, evidence="", **kw):
    return Relationship(subject=subject, predicate="ENEMY_OF", object=obj, raw_text=evidence, **prov(**kw))


def test_he_hit_john_resolves_the_subject_through_the_pronouns_cluster():
    before, after, coref = grounded(HIT, [mention("Robert"), mention("John")], [rel("He", "John", "He hit John")])
    assert before.result.relationships[0].subject_entity_id is None          # Phase 5 alone cannot do it
    r = after.result.relationships[0]
    robert = after.result.entity_mentions[0].entity_id
    assert r.subject_entity_id == robert and r.object_entity_id == after.result.entity_mentions[1].entity_id
    assert coref.cluster_of("M1").entity_id == robert


def test_pronoun_reference_is_refused_when_the_pronoun_is_ambiguous_or_unresolved():
    # two people in the paragraph: the pronoun mention is never created, so nothing can be grounded
    _, after, _ = grounded("Robert met Zed. He hit John.", [mention("Robert"), mention("Zed"), mention("John")],
                           [rel("He", "John", "He hit John")])
    assert after.result.relationships[0].subject_entity_id is None


def test_an_unresolved_pronoun_elsewhere_in_the_chunk_is_never_mistaken_for_the_resolved_one():
    text = "Bob sat. He smiled.\n\nAlice met Bob. He hit John."
    mentions = [mention("Bob"), mention("Alice"), mention("John")]
    for evidence in ("He hit John", ""):    # located exactly / not located (falls back to the whole chunk)
        _, after, _ = grounded(text, mentions, [rel("He", "John", evidence)])
        assert after.result.relationships[0].subject_entity_id is None, evidence


def test_ambiguous_named_reference_blocks_grounding():
    text = "Alice smiled."
    _, after, _ = grounded(text, [mention("Alice")], [rel("Alice", "Alice")], known=[ALICE_S, ALICE_J])
    assert after.result.relationships[0].subject_entity_id is None


def test_one_ambiguous_candidate_among_resolved_ones_blocks_grounding():
    from app.coreference import ground_references
    text = "Alice smiled. Alice frowned."
    doc = preprocess_chapter(text)
    n, sids = len(text), tuple(s.id for s in doc.sentences)
    kw = dict(source_chunk="c0", source_span=(0, n), sentence_ids=sids)
    mentions = (EntityMention(text="Alice", type="character", id="M1", entity_id="e-1", **kw),
                EntityMention(text="Alice", type="character", id="M2", **kw),           # ambiguous: no entity
                EntityMention(text="Alice", type="character", id="M3", entity_id="e-1", **kw))
    result = ExtractionResult(entity_mentions=mentions,
                              relationships=(Relationship(subject="Alice", predicate="KNOWS", object="Alice", **kw),))
    coref = build_clusters(mentions, excluded=["M2"])
    assert ids(coref) == [["M1", "M3"]]
    assert ground_references(result, coref, doc).relationships[0].subject_entity_id is None       # blocked by M2
    # control: the same reference grounds to e-1 when the ambiguous mention is absent
    without = replace(result, entity_mentions=(mentions[0], mentions[2]))
    grounded_ = ground_references(without, build_clusters(without.entity_mentions), doc)
    assert grounded_.relationships[0].subject_entity_id == "e-1"


def test_grounding_fills_only_missing_ids_and_never_overrides_phase5():
    before, after, _ = grounded(HIT, [mention("Robert"), mention("John")], [rel("Robert", "John", "He hit John")])
    b, a = before.result.relationships[0], after.result.relationships[0]
    assert (b.subject_entity_id, b.object_entity_id) == (a.subject_entity_id, a.object_entity_id)
    assert a.subject_entity_id is not None


def test_events_and_facts_ground_through_clusters_too():
    _, after, _ = grounded(
        HIT, [mention("Robert"), mention("John")],
        events=[Event(local_id="e1", participants=("He", "John", "Ghost"), raw_text="He hit John", **prov())],
        facts=[FactObservation(entity="He", property="mood", value="angry", raw_text="He hit John", **prov())])
    robert, john = (m.entity_id for m in after.result.entity_mentions[:2])
    assert after.result.events[0].participant_entity_ids == (robert, john, None)
    assert after.result.facts[0].entity_id == robert


def test_locate_evidence_requires_exactly_one_verbatim_occurrence():
    text = "He hit John. Later he hit John. Bye."
    assert locate_evidence(text, "Later he hit John", (0, len(text))) == (13, 30)
    assert locate_evidence(text, "hit John", (0, len(text))) is None          # twice
    assert locate_evidence(text, "hit John", (0, 12)) == (3, 11)               # once inside the narrowed span
    assert locate_evidence(text, "nothing", (0, len(text))) is None
    assert locate_evidence(text, "", (0, len(text))) is None
    assert locate_evidence(text, "Bye.", (0, 20)) is None                      # outside the span


# ============================================================================ World State integration
def extract(monkeypatch, body, payload):
    monkeypatch.setattr(llm_client, "generate", lambda **kw: json.dumps(payload))
    return ExtractionOrchestrator().extract_chapter(body, 1)


def integrate(env, w, data, chapter=1):
    with env.Session() as s:
        svc = WorldStateService(s)
        svc.integrate_extraction_result(w["world_id"], data, chapter_id=w["runs"][chapter]["chapter_id"],
                                        chapter_version_id=w["runs"][chapter]["chapter_version_id"])
        s.commit()
        return svc


PAYLOAD = {
    "entities": [person("Robert"), person("John")],
    "relationships": [{"subject": "He", "predicate": "ENEMY_OF", "object": "John", "evidence": "He hit John"}],
    "events": [{"id": "e1", "type": "ATTACK", "participants": ["He", "John"], "evidence": "He hit John"}],
}


def test_relationship_and_event_resolve_via_the_pronoun_cluster_end_to_end(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("C", chapters=1)
    svc = integrate(env, w, extract(monkeypatch, HIT, PAYLOAD))
    with env.Session() as s:
        robert = s.query(Entity).filter_by(canonical_name="Robert").one()
        john = s.query(Entity).filter_by(canonical_name="John").one()
        assert s.query(Entity).count() == 2                                   # no entity named "He"
        [rel_row] = s.query(RelationshipRow).all()
        assert (rel_row.source_entity_id, rel_row.target_entity_id) == (robert.id, john.id)
        assert {p.entity_id for p in s.query(EventParticipant)} == {robert.id, john.id}
    [c] = svc.last_coreference.clusters
    assert c.entity_id == robert.id and c.rules == ("pronoun",) and len(c.mentions) == 2
    assert svc.last_resolution.result.coreference_clusters == svc.last_coreference.clusters


def test_unresolvable_pronoun_subject_still_creates_no_relationship(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("U", chapters=1)
    integrate(env, w, extract(monkeypatch, "Robert met Zed. He hit John.", {
        "entities": [person("Robert"), person("Zed"), person("John")], "relationships": PAYLOAD["relationships"]}))
    with env.Session() as s:
        assert s.query(RelationshipRow).count() == 0


def test_stale_pairing_between_legacy_lists_and_observations_is_ignored(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("S", chapters=1)
    data = extract(monkeypatch, HIT, PAYLOAD)
    data["relationships"][0]["subject"] = "She"        # the dict no longer matches the observation it came from
    integrate(env, w, data)
    with env.Session() as s:
        assert s.query(RelationshipRow).count() == 0


def test_hand_built_dicts_never_touch_clustering(phase1_env):
    env = phase1_env
    w = env.make_world("H", chapters=1)
    svc = integrate(env, w, {"entities": [person("Robert")]})
    assert svc.last_coreference is None and svc.last_resolution is None


# ============================================================================ layering
def test_coreference_package_is_pure():
    root = pathlib.Path(coref_pkg.__file__).parent
    banned = ("llm_client", "httpx", "requests", "openai", "spacy", "nltk", "numpy", "sqlalchemy", "torch", "sklearn",
              "difflib", "app.models", "app.repositories", "app.services", "app.pipeline")
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                assert not any(m == b or m.startswith(b + ".") for b in banned), (path.name, m)
