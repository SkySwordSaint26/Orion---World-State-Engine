# SRS Requirements Traceability Matrix (SRS v1.0)

This matrix maps every functional requirement (REQ-1 through REQ-51) and non-functional quality attribute from [`docs/srs.md`](../../../docs/srs.md) directly to the backend architecture components.

---

## 1. Functional Requirements Matrix

| Req ID | Title / Description | Primary Modules & Files | Status / Implementation |
|---|---|---|---|
| **REQ-1** | Account Registration | [`models/user.py`](../../app/models/user.py), [`routes/auth.py`](../../app/api/v1/routes/auth.py) | `POST /api/v1/auth/register` with bcrypt hash |
| **REQ-2** | Login and Logout | [`core/security.py`](../../app/core/security.py), [`routes/auth.py`](../../app/api/v1/routes/auth.py) | `POST /api/v1/auth/login` returning Bearer JWT |
| **REQ-3** | Create and manage projects ("Worlds") | [`models/world.py`](../../app/models/world.py), [`services/world_state_service.py`](../../app/services/world_state_service.py), [`routes/worlds.py`](../../app/api/v1/routes/worlds.py) | Full CRUD on `/api/v1/worlds` with stats rollup |
| **REQ-4** | Project Data Isolation across users | [`api/deps.py`](../../app/api/deps.py), [`models/world.py`](../../app/models/world.py) | `user_id` FK filtering on all project queries |
| **REQ-5** | Upload .txt, .docx, .pdf manuscripts | [`utils/file_handler.py`](../../app/utils/file_handler.py), [`routes/manuscripts.py`](../../app/api/v1/routes/manuscripts.py) | `POST /api/v1/worlds/{id}/manuscripts` (multipart) |
| **REQ-6** | Create chapters within manuscript | [`models/chapter.py`](../../app/models/chapter.py), [`utils/text_splitter.py`](../../app/utils/text_splitter.py) | Auto-detected from headings or created manually |
| **REQ-7** | Edit existing chapters | [`services/chapter_service.py`](../../app/services/chapter_service.py), [`routes/chapters.py`](../../app/api/v1/routes/chapters.py) | `PUT /api/v1/worlds/{id}/chapters/{id}` |
| **REQ-8** | Delete chapters | [`repositories/chapter_repo.py`](../../app/repositories/chapter_repo.py), [`routes/chapters.py`](../../app/api/v1/routes/chapters.py) | Cascade deletion of child versions & runs |
| **REQ-9** | Re-run extraction on edited chapter | [`services/chapter_service.py`](../../app/services/chapter_service.py), [`workers/tasks/extraction_task.py`](../../app/workers/tasks/extraction_task.py) | Spawns `RE_EXTRACTION` job and child run |
| **REQ-10**| View edit history of a chapter | [`models/chapter_version.py`](../../app/models/chapter_version.py), [`routes/chapters.py`](../../app/api/v1/routes/chapters.py) | Versioned content path and SHA256 hashes |
| **REQ-11**| Extract characters from chapter text | [`pipeline/extractor.py`](../../app/pipeline/extractor.py), [`prompts/extraction_prompt.txt`](../../app/pipeline/prompts/extraction_prompt.txt) | LLM extraction prompt entity type `character` |
| **REQ-12**| Extract locations from chapter text | [`pipeline/extractor.py`](../../app/pipeline/extractor.py), [`prompts/extraction_prompt.txt`](../../app/pipeline/prompts/extraction_prompt.txt) | LLM extraction prompt entity type `location` |
| **REQ-13**| Extract objects from chapter text | [`pipeline/extractor.py`](../../app/pipeline/extractor.py), [`prompts/extraction_prompt.txt`](../../app/pipeline/prompts/extraction_prompt.txt) | LLM extraction prompt entity type `object` |
| **REQ-14**| Extract relationships between characters| [`pipeline/extractor.py`](../../app/pipeline/extractor.py), [`models/relationship.py`](../../app/models/relationship.py) | Subject, predicate, object, certainty, quote |
| **REQ-15**| Extract narrative events | [`pipeline/extractor.py`](../../app/pipeline/extractor.py), [`models/event.py`](../../app/models/event.py) | Event type, participants, location, evidence |
| **REQ-16**| Chapter extraction latency ≤ 10s | [`pipeline/extractor.py`](../../app/pipeline/extractor.py), [`utils/text_splitter.py`](../../app/utils/text_splitter.py) | ~8000 char token-safe chunks, fast local LLM |
| **REQ-17**| Identify multiple references (aliases) | [`pipeline/resolution/entity_resolution.py`](../../app/pipeline/resolution/entity_resolution.py) | Token similarity, Jaccard overlap, substring check |
| **REQ-18**| Merge references into entity record | [`models/entity.py`](../../app/models/entity.py), [`services/world_state_service.py`](../../app/services/world_state_service.py) | Entity clustering, canonical naming, `entity_aliases` |
| **REQ-19**| Maintain structured records | [`models/`](../../app/models/) | Entities, facts, relationships, events tables |
| **REQ-20**| Record ID, type, attributes, history | [`models/entity.py`](../../app/models/entity.py), [`models/fact.py`](../../app/models/fact.py) | UUID PKs, JSON attributes, version timestamp rows |
| **REQ-21**| Fact metadata (entity, property, val, ch)| [`models/fact.py`](../../app/models/fact.py) | `fact_versions` table with chapter & run FKs |
| **REQ-22**| Never overwrite stored facts | [`services/world_state_service.py`](../../app/services/world_state_service.py), [`models/fact.py`](../../app/models/fact.py) | Append-only versions (`ACTIVE`, `SUPERSEDED`, `CONTRADICTED`) |
| **REQ-23**| Character age contradiction check | [`services/consistency_service.py`](../../app/services/consistency_service.py) | Rule: non-monotonic age decrease flagged |
| **REQ-24**| Character location contradiction check | [`services/consistency_service.py`](../../app/services/consistency_service.py) | Rule: simultaneous multi-location presence |
| **REQ-25**| Relationship contradiction check | [`pipeline/resolution/relationship_resolution.py`](../../app/pipeline/resolution/relationship_resolution.py) | Incompatible relationship transitions flagged |
| **REQ-26**| Character status contradiction check | [`services/consistency_service.py`](../../app/services/consistency_service.py) | Rule: post-mortem actions/speech flagged |
| **REQ-27**| Rule-based detection (no LLM) | [`services/consistency_service.py`](../../app/services/consistency_service.py) | 100% deterministic Python rule algorithms |
| **REQ-28**| Contradiction check latency ≤ 5s | [`services/consistency_service.py`](../../app/services/consistency_service.py) | In-memory DFS and dictionary hash lookups |
| **REQ-29**| Display contradiction details | [`routes/contradictions.py`](../../app/api/v1/routes/contradictions.py), [`schemas/contradiction.py`](../../app/schemas/contradiction.py) | Entity, property, old_val, new_val, chapters |
| **REQ-30**| Display contradiction confidence score | [`models/contradiction.py`](../../app/models/contradiction.py) | `confidence: Float` field on all contradictions |
| **REQ-31**| Plain-language conflict explanation | [`services/consistency_service.py`](../../app/services/consistency_service.py) | Formatted explanatory string generated per rule |
| **REQ-32**| Move between chapters on timeline | [`routes/timeline.py`](../../app/api/v1/routes/timeline.py), [`schemas/timeline.py`](../../app/schemas/timeline.py) | Events ordered by chapter and creation timestamp |
| **REQ-33**| View world state at specific chapter | [`services/world_state_service.py`](../../app/services/world_state_service.py) | Query active versions up to chapter N |
| **REQ-34**| Compare world state between 2 chapters | [`services/world_state_service.py`](../../app/services/world_state_service.py) | Chapter state diffing logic |
| **REQ-35**| Highlight changes between chapters | [`schemas/timeline.py`](../../app/schemas/timeline.py) | State transitions (`SUPERSEDED`) highlighted |
| **REQ-36**| Ask questions about a character | [`services/chat_service.py`](../../app/services/chat_service.py), [`routes/chat.py`](../../app/api/v1/routes/chat.py) | `POST /api/v1/worlds/{id}/chat` |
| **REQ-37**| Response grounded in extracted facts | [`services/chat_service.py`](../../app/services/chat_service.py), [`prompts/chat_prompt.txt`](../../app/pipeline/prompts/chat_prompt.txt) | Strict closed-world system prompt instructions |
| **REQ-38**| Never invent unsupported facts | [`services/chat_service.py`](../../app/services/chat_service.py) | Zero-hallucination constraint & citations |
| **REQ-39**| Chat response latency ≤ 3s | [`pipeline/llm_client.py`](../../app/pipeline/llm_client.py) | Filtered context window (top 25 entities) |
| **REQ-40**| Display characters, locations, edges | [`services/graph_service.py`](../../app/services/graph_service.py), [`routes/graph.py`](../../app/api/v1/routes/graph.py) | `GET /api/v1/worlds/{id}/graph` |
| **REQ-41**| Zoom & pan graph support | Frontend / [`schemas/graph.py`](../../app/schemas/graph.py) | Node degrees & edge metadata for UI canvas |
| **REQ-42**| Search within graph | [`schemas/graph.py`](../../app/schemas/graph.py), [`routes/graph.py`](../../app/api/v1/routes/graph.py) | Filtered graph queries by entity type or query |
| **REQ-43**| Filter graph elements | [`routes/entities.py`](../../app/api/v1/routes/entities.py) | Query param `entity_type` filter |
| **REQ-44**| Search by character | [`repositories/entity_repo.py`](../../app/repositories/entity_repo.py) | Search API endpoint |
| **REQ-45**| Search by location | [`repositories/entity_repo.py`](../../app/repositories/entity_repo.py) | Search API endpoint |
| **REQ-46**| Search by event | [`repositories/event_repo.py`](../../app/repositories/event_repo.py) | Search API endpoint |
| **REQ-47**| Search by chapter | [`repositories/chapter_repo.py`](../../app/repositories/chapter_repo.py) | Search API endpoint |
| **REQ-48**| Search by relationship | [`repositories/relationship_repo.py`](../../app/repositories/relationship_repo.py) | Search API endpoint |
| **REQ-49**| Export data as JSON | [`services/world_state_service.py`](../../app/services/world_state_service.py) | Export API endpoint (`format=json`) |
| **REQ-50**| Export data as CSV | [`services/world_state_service.py`](../../app/services/world_state_service.py) | Export API endpoint (`format=csv`) |
| **REQ-51**| Export report as PDF | Export Service | Export API endpoint (`format=pdf`) |

---

## 2. Non-Functional Quality Attributes Matrix (SRS Section 5)

| Category | Requirement | Architectural Enforcement |
|---|---|---|
| **5.1 Performance** | Chapter extraction ≤ 10s | Quantized local LLM (`llama3.1:8b-instruct-q4_K_M`), ~8k token chunks. |
| **5.1 Performance** | Contradiction check ≤ 5s | Algorithmic in-memory checks in Python (zero LLM calls). |
| **5.1 Performance** | Chat response ≤ 3s | Lean context injection, low temperature (0.3). |
| **5.3 Security** | Bcrypt password hashing | Passwords hashed using bcrypt salt rounds in [`core/security.py`](../../app/core/security.py). |
| **5.3 Security** | JWT Authentication | Bearer access tokens signed with HMAC-SHA256. |
| **5.3 Security** | Strict Tenant Isolation | All queries filter by `user_id` to prevent cross-account leaks. |
| **5.4 Scalability** | ≥500 chapters, 1k characters, 20k facts | PostgreSQL index optimization, pagination, joined loads. |
| **5.4 Reliability** | ACID Transaction safety | SQLAlchemy atomic commit/rollback wrappers across all operations. |
