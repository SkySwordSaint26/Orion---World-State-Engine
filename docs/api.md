# Orion World State Engine: REST API Documentation

**Version:** 1.0.0  
**Base URL:** `http://localhost:8000/api/v1`  
*(Note: All routes are also mirrored at the root level `/` for backward and frontend compatibility).*  
**Interactive Documentation:**
- **Swagger UI:** [`/api/v1/docs`](http://localhost:8000/api/v1/docs)
- **ReDoc:** [`/api/v1/redoc`](http://localhost:8000/api/v1/redoc)
- **OpenAPI Schema:** [`/api/v1/openapi.json`](http://localhost:8000/api/v1/openapi.json)

---

## 1. Overview & Conventions

### 1.1 Headers
- **Content-Type**: `application/json` (except manuscript upload which is `multipart/form-data`).
- **Authorization**: `Bearer <access_token>` (for authenticated routes).
- **Process Time Header**: All HTTP responses include `X-Process-Time: <seconds>` indicating server execution latency.

### 1.2 Status Codes
- `200 OK`: Request succeeded.
- `201 Created`: Resource successfully created.
- `202 Accepted`: Asynchronous job queued (e.g., manuscript parsing, chapter re-extraction).
- `204 No Content`: Resource successfully deleted.
- `400 Bad Request`: Validation failure or duplicate business identifier.
- `401 Unauthorized`: Invalid or expired JWT token.
- `404 Not Found`: Requested resource does not exist.
- `422 Unprocessable Entity`: Request body failed schema validation.
- `500 Internal Server Error`: Unhandled server exception.

### 1.3 Error Envelope
```json
{
  "detail": "Error description message"
}
```

---

## 2. Authentication (`/api/v1/auth`)

### 2.1 Register User
- **Method / Endpoint**: `POST /api/v1/auth/register`
- **Auth Required**: No
- **Request Body**:
  ```json
  {
    "email": "author@example.com",
    "password": "strongpassword123"
  }
  ```
- **Response** (`201 Created`):
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "author@example.com",
    "created_at": "2026-09-11T10:00:00Z",
    "updated_at": "2026-09-11T10:00:00Z"
  }
  ```

### 2.2 User Login
- **Method / Endpoint**: `POST /api/v1/auth/login`
- **Auth Required**: No
- **Request Body**:
  ```json
  {
    "email": "author@example.com",
    "password": "strongpassword123"
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```

### 2.3 Current User Profile
- **Method / Endpoint**: `GET /api/v1/auth/me`
- **Auth Required**: Yes (`Bearer <token>`)
- **Response** (`200 OK`):
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "author@example.com",
    "created_at": "2026-09-11T10:00:00Z",
    "updated_at": "2026-09-11T10:00:00Z"
  }
  ```

---

## 3. Worlds / Projects (`/api/v1/worlds`)

Worlds represent isolated narrative world-state universes. All entities, manuscripts, relationships, and contradictions belong to a specific world.

### 3.1 Create World
- **Method / Endpoint**: `POST /api/v1/worlds`
- **Auth Required**: Optional (associated with authenticated user if provided)
- **Request Body**:
  ```json
  {
    "name": "Eldoria Chronicles",
    "description": "High fantasy setting with ancient magical factions."
  }
  ```
- **Response** (`201 Created`):
  ```json
  {
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "name": "Eldoria Chronicles",
    "description": "High fantasy setting with ancient magical factions.",
    "created_at": "2026-09-11T10:05:00Z",
    "updated_at": "2026-09-11T10:05:00Z",
    "stats": {
      "entities_count": 0,
      "characters_count": 0,
      "locations_count": 0,
      "objects_count": 0,
      "relationships_count": 0,
      "events_count": 0,
      "contradictions_count": 0
    }
  }
  ```

### 3.2 List Worlds
- **Method / Endpoint**: `GET /api/v1/worlds`
- **Auth Required**: Optional
- **Response** (`200 OK`): Array of World objects with current aggregated statistics.

### 3.3 Get World Details
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}`
- **Auth Required**: Optional
- **Response** (`200 OK`): Single World object with stats.

### 3.4 Update World
- **Method / Endpoint**: `PUT /api/v1/worlds/{world_id}`
- **Request Body**:
  ```json
  {
    "name": "Eldoria Chronicles (Revised)",
    "description": "Updated lore setting."
  }
  ```
- **Response** (`200 OK`): Updated World object.

### 3.5 Delete World
- **Method / Endpoint**: `DELETE /api/v1/worlds/{world_id}`
- **Response** (`204 No Content`)

---

## 4. Manuscripts & Chapter Processing

### 4.1 Upload Manuscript
Uploads a novel manuscript (`.txt`, `.docx`, `.pdf`), splits it into chapters, creates tracking database entries, and enqueues Celery background extraction tasks.

- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/manuscripts`
- **Content-Type**: `multipart/form-data`
- **Form Data**:
  - `file`: File binary upload
- **Response** (`202 Accepted`):
  ```json
  {
    "job_id": "e0a29482-1678-43d9-a78b-d535b91b5c90",
    "manuscript_id": "f51950d2-97b7-4a0b-9ffb-20164c8d5045",
    "chapters_total": 8,
    "message": "Manuscript accepted for processing"
  }
  ```

### 4.2 List Manuscripts
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/manuscripts`
- **Response** (`200 OK`):
  ```json
  [
    {
      "id": "f51950d2-97b7-4a0b-9ffb-20164c8d5045",
      "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "title": "Book_One_Manuscript.txt",
      "original_file_path": "./storage/manuscripts/...",
      "file_type": "text/plain",
      "chapter_count": 8,
      "created_at": "2026-09-11T10:10:00Z",
      "updated_at": "2026-09-11T10:10:00Z"
    }
  ]
  ```

### 4.3 Get Manuscript Details
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/manuscripts/{manuscript_id}`
- **Response** (`200 OK`): Includes full list of chapters with sequence indices and titles.

---

## 5. Chapters & Chapter Versions

### 5.1 List Chapters
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/manuscripts/{manuscript_id}/chapters`
- **Response** (`200 OK`): Array of chapters ordered by `chapter_number`.

### 5.2 Get Chapter Details & Content
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/chapters/{chapter_id}`
- **Response** (`200 OK`):
  ```json
  {
    "id": "ch-101",
    "manuscript_id": "ms-456",
    "chapter_number": 1,
    "title": "Chapter 1: The Gathering Storm",
    "created_at": "2026-09-11T10:10:00Z",
    "updated_at": "2026-09-11T10:10:00Z",
    "latest_version": {
      "id": "ver-1",
      "chapter_id": "ch-101",
      "version_number": 1,
      "is_current": true,
      "content_path": "./storage/chapters/...",
      "content_hash": "a1b2c3d4...",
      "created_at": "2026-09-11T10:10:00Z"
    },
    "content": "Full raw text of Chapter 1..."
  }
  ```

### 5.3 Update Chapter Content (Versioned Edit)
Modifying chapter prose triggers a new immutable `ChapterVersion`, increments version number, and queues an asynchronous re-extraction job for that chapter.

- **Method / Endpoint**: `PUT /api/v1/worlds/{world_id}/chapters/{chapter_id}`
- **Request Body**:
  ```json
  {
    "title": "Chapter 1: The Gathering Storm (Revised)",
    "content": "New updated prose text for the chapter..."
  }
  ```
- **Response** (`202 Accepted`):
  ```json
  {
    "chapter_id": "ch-101",
    "version_id": "ver-2",
    "job_id": "job-999",
    "status": "re_extraction_queued"
  }
  ```

---

## 6. Processing Jobs (`/api/v1/jobs`)

Asynchronous background extraction jobs are tracked through Celery and database state.

### 6.1 Get Job Details
- **Method / Endpoint**: `GET /api/v1/jobs/{job_id}`
- **Response** (`200 OK`): Full job metadata including input parameters, step tracking, and execution timestamps.

### 6.2 Get Job Progress (Polling)
- **Method / Endpoint**: `GET /api/v1/jobs/{job_id}/status`
- **Response** (`200 OK`):
  ```json
  {
    "id": "e0a29482-1678-43d9-a78b-d535b91b5c90",
    "status": "processing",
    "progress_current": 5,
    "progress_total": 8,
    "progress_percent": 64,
    "current_stage": "Extracting relationships",
    "current_chapter": 6,
    "error_message": null
  }
  ```
  *Status Values:* `queued`, `processing`, `done`, `failed`, `cancelled`. `progress_current` and `progress_total` remain completed-chapter counts; `progress_percent` and the current stage provide finer-grained extraction progress.

---

## 7. Entities & Facts (`/api/v1/worlds/{world_id}/entities`)

Entities represent characters, locations, and objects. In compliance with **SRS REQ-22**, fact records are append-only; property values are versioned and never destructively updated in place.

Merge, bulk delete and aliases: see §13.

### 7.1 List Entities
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/entities`
- **Query Parameters**:
  - `entity_type` *(optional)*: Filter by `character`, `location`, `object`, or `concept`.
- **Response** (`200 OK`):
  ```json
  [
    {
      "id": "ent-001",
      "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "entity_type": "character",
      "canonical_name": "Valen Thorne",
      "source_extraction_id": "run-01",
      "provenance": "Chapter 1, Paragraph 3",
      "aliases": ["The Shadow Blade", "Valen"],
      "facts": [
        {
          "id": "fact-10",
          "property_name": "eye_color",
          "created_at": "2026-09-11T10:10:00Z",
          "current_version": {
            "id": "fver-100",
            "fact_id": "fact-10",
            "chapter_id": "ch-101",
            "value": "violet",
            "status": "ACTIVE",
            "confidence": 0.95,
            "created_at": "2026-09-11T10:10:00Z"
          }
        }
      ],
      "created_at": "2026-09-11T10:10:00Z",
      "updated_at": "2026-09-11T10:10:00Z"
    }
  ]
  ```

### 7.2 Create Entity Manually
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/entities`
- **Request Body**:
  ```json
  {
    "canonical_name": "Lady Seraphina",
    "entity_type": "character",
    "aliases": ["The White Rose"],
    "attributes": {
      "hair_color": "silver",
      "allegiance": "House Baratheon"
    }
  }
  ```
- **Response** (`201 Created`): Returns created Entity object.

### 7.3 Get Detailed Entity View
Returns the entity with all active facts, outgoing relationship edges, and participant timeline events.
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/entities/{entity_id}`
- **Response** (`200 OK`):
  ```json
  {
    "id": "ent-001",
    "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "entity_type": "character",
    "canonical_name": "Valen Thorne",
    "source_extraction_id": "run-01",
    "provenance": "Chapter 1",
    "aliases": ["The Shadow Blade"],
    "facts": [],
    "relationships": [
      {
        "id": "rel-01",
        "target_id": "ent-002",
        "target_name": "Lady Seraphina",
        "type": "ALLY_OF"
      }
    ],
    "events": [
      {
        "id": "ev-01",
        "type": "BATTLE",
        "role": "commander",
        "description": "Valen leads the defense of the fortress."
      }
    ],
    "created_at": "2026-09-11T10:10:00Z",
    "updated_at": "2026-09-11T10:10:00Z"
  }
  ```

### 7.4 Update Entity
- **Method / Endpoint**: `PUT /api/v1/worlds/{world_id}/entities/{entity_id}`
- **Request Body**:
  ```json
  {
    "canonical_name": "Valen Thorne (Archmage)",
    "entity_type": "character",
    "attributes": {
      "rank": "Grand Magus"
    }
  }
  ```
- **Response** (`200 OK`): Updated Entity object.

### 7.5 Delete Entity
- **Method / Endpoint**: `DELETE /api/v1/worlds/{world_id}/entities/{entity_id}`
- **Response** (`204 No Content`)

### 7.6 Add Fact to Entity
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/entities/{entity_id}/facts`
- **Request Body**:
  ```json
  {
    "property_name": "status",
    "value": "deceased",
    "confidence": 1.0
  }
  ```
- **Response** (`201 Created`):
  ```json
  {
    "id": "fver-102",
    "property": "status",
    "value": "deceased",
    "status": "ACTIVE"
  }
  ```

### 7.7 Delete Fact
- **Method / Endpoint**: `DELETE /api/v1/worlds/{world_id}/entities/{entity_id}/facts/{fact_id}`
- **Response** (`204 No Content`)

---

## 8. Knowledge Graph (`/api/v1/worlds/{world_id}/graph`)

Generates a node-edge network representation formatted for graph visualization libraries (e.g. Cytoscape.js, D3 force-directed graphs).

The graph at a chosen chapter (`?as_of_chapter=N`): see §16.

### 8.1 Get World Knowledge Graph
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/graph`
- **Response** (`200 OK`):
  ```json
  {
    "nodes": [
      {
        "id": "ent-001",
        "label": "Valen Thorne",
        "type": "character",
        "degree": 3,
        "properties": {
          "eye_color": "violet",
          "rank": "Grand Magus"
        }
      },
      {
        "id": "ent-002",
        "label": "Fortress of Dawn",
        "type": "location",
        "degree": 1,
        "properties": {}
      }
    ],
    "edges": [
      {
        "id": "rel-001",
        "source": "ent-001",
        "target": "ent-002",
        "type": "LOCATED_AT",
        "confidence": 1.0,
        "status": "ACTIVE"
      }
    ]
  }
  ```

---

## 9. Timeline (`/api/v1/worlds/{world_id}/timeline`)

Returns the narrative sequence of events with participant roles and chapter provenance.

Event create, update, delete and reorder, and the event ordering rule: see §15.

### 9.1 Get World Timeline
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/timeline`
- **Response** (`200 OK`):
  ```json
  {
    "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "total_events": 2,
    "events": [
      {
        "id": "ev-001",
        "event_type": "MEETING",
        "description": "Council of Lords convenes at the Citadel.",
        "chapter_number": 1,
        "temporal_order": 1,
        "participants": [
          {
            "entity_id": "ent-001",
            "entity_name": "Valen Thorne",
            "role": "speaker"
          }
        ]
      },
      {
        "id": "ev-002",
        "event_type": "BATTLE",
        "description": "Fortress breach under the eclipse.",
        "chapter_number": 2,
        "temporal_order": 2,
        "participants": [
          {
            "entity_id": "ent-001",
            "entity_name": "Valen Thorne",
            "role": "defender"
          }
        ]
      }
    ]
  }
  ```

---

## 10. Contradictions & Consistency (`/api/v1/worlds/{world_id}/contradictions`)

In compliance with **SRS REQ-27**, contradictions are detected via deterministic Python rules (immutable facts, age monotonicity, dead-then-alive status, incompatible relationships, temporal cycles). Location-clash and acting-after-death detection are not implemented yet. Each `explanation` begins with a `[RULE_ID]` tag.

### 10.1 List Contradictions
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/contradictions`
- **Query Parameters**:
  - `status` *(optional)*: Filter by `DETECTED`, `RESOLVED`, or `DISMISSED`.
- **Response** (`200 OK`):
  ```json
  [
    {
      "id": "con-001",
      "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "contradiction_type": "PHYSICAL_IMPOSSIBILITY",
      "severity": "CRITICAL",
      "description": "Entity 'Valen Thorne' is reported at two different locations simultaneously in Chapter 3.",
      "status": "DETECTED",
      "entity_id": "ent-001",
      "fact_id": "fact-10",
      "conflicting_version_a_id": "fver-100",
      "conflicting_version_b_id": "fver-101",
      "preferred_version_id": null,
      "created_at": "2026-09-11T10:15:00Z"
    }
  ]
  ```

### 10.2 Resolve Contradiction
Allows the author to resolve a conflict by picking a preferred canonical version.
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/contradictions/{contradiction_id}/resolve`
- **Request Body**:
  ```json
  {
    "status": "RESOLVED",
    "preferred_fact_version_id": "fver-100"
  }
  ```
- **Response** (`200 OK`): Updated Contradiction object reflecting status `RESOLVED` and the chosen preferred version.

---

## 11. World & Character Chat (`/api/v1/worlds/{world_id}/chat`)

Retrieves answers grounded strictly in the world state, entity registry, and timeline events, complete with citations.

### 11.1 Query World Chat
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/chat`
- **Request Body**:
  ```json
  {
    "message": "What were Valen's actions during the Council of Lords?",
    "entity_focus": "Valen Thorne",
    "timeline_event_focus": "ev-001",
    "history": [
      {
        "role": "user",
        "content": "Tell me about the council."
      },
      {
        "role": "assistant",
        "content": "The Council of Lords convened in Chapter 1."
      }
    ]
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "response": "According to Chapter 1 chronicles, Valen Thorne acted as a speaker during the Council of Lords convened at the Citadel.",
    "citations": [
      {
        "source_type": "event",
        "source_id": "ev-001",
        "title": "Council of Lords convenes at the Citadel.",
        "snippet": "Valen Thorne participated as speaker."
      }
    ],
    "suggested_actions": [
      "View Valen Thorne's full event participation timeline",
      "Check active relationships with other council attendees"
    ]
  }
  ```

---

## 12. System & Health (`/health`, `/`)

### 12.1 Health Check
- **Method / Endpoint**: `GET /health`
- **Response** (`200 OK`):
  ```json
  {
    "status": "healthy",
    "app": "Orion World State Engine",
    "version": "1.0.0",
    "environment": "development"
  }
  ```

### 12.2 Root Greeting
- **Method / Endpoint**: `GET /`
- **Response** (`200 OK`):
  ```json
  {
    "message": "Welcome to Orion World State Engine",
    "version": "1.0.0",
    "docs": "/api/v1/docs"
  }
  ```

---

## Step 0 Contracts (§13–§17)

The sections below are the contracts the three feature branches build against. They were frozen with this file at
the `step0` tag (see `backend/.ai/SPLIT.md`). Endpoints marked **(planned)** don't exist yet; the owner named in each
section implements them. Typed client stubs live in `Frontend/src/api/entities.ts`, `relationships.ts`, `events.ts`
and `proposals.ts`.

Shared conventions for §13–§17:

- **Auth and tenancy:** every endpoint requires `Authorization: Bearer <token>`. A world, job, entity, relationship,
  event or chapter that doesn't exist, or belongs to another user's world, returns `404 Not Found`. A missing or
  invalid token returns `401 Unauthorized` (RULES.md 1.2, 6.3).
- **Status codes:** `201 Created` when a resource is created, `202 Accepted` while async work is still running,
  `204 No Content` on delete, `200 OK` otherwise (RULES.md 6.3). `400 Bad Request` for a business-rule rejection,
  `422 Unprocessable Entity` for a malformed body (§1.2).
- **Versioning:** manual edits to fact values and relationship types append a new version and supersede the previous
  `ACTIVE` one. They never update a stored value in place. Author-initiated deletes are allowed (RULES.md 3.4).
- **Orphan contradictions:** any delete in §13–§15 also deletes the contradictions that reference the removed fact
  versions, relationship versions or events, so the Contradictions page never shows a row with nothing behind it.
  This applies to the existing `DELETE /entities/{entity_id}` (§7.5) and `DELETE .../facts/{fact_id}` (§7.7) too.

---

## 13. Entity Merge, Bulk Delete & Aliases (`/api/v1/worlds/{world_id}/entities`)

**Owner:** Person A (`feature/manual-entities`). **Client:** `Frontend/src/api/entities.ts`.

### 13.1 Merge Entities (planned)
Merges `source_id` into `target_id` in one transaction. The target survives, and the source is deleted.
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/entities/merge`
- **Request Body**:
  ```json
  {
    "source_id": "ent-007",
    "target_id": "ent-001"
  }
  ```
- **Response** (`200 OK`): the surviving target as an Entity object (same shape as §7.1).
- **Merge rules** (all inside one transaction):
  1. The source's `canonical_name` and aliases become aliases of the target, deduplicated case-insensitively and
     skipping any that equal the target's `canonical_name`. This stops re-extraction from proposing the merged-away
     name again.
  2. The source's mentions are repointed to the target.
  3. Facts with the same `property_name` are folded into the target's fact. If both have an `ACTIVE` version with
     different values, the target's stays `ACTIVE` and the source's becomes `SUPERSEDED`. Facts only the source has
     move to the target unchanged.
  4. Event participations are repointed. If the target already participates in that event, the duplicate row is
     dropped.
  5. Relationships between source and target are deleted (they would become self-loops). If repointing creates a
     directed pair the target already has, the moved relationship's versions are added to the existing row and the
     empty row is deleted.
  6. Stored values and relationship types are never rewritten. Only foreign keys and version `status` change
     (RULES.md 3.4).
- **Errors**:
  - `400 Bad Request`: `source_id` equals `target_id`, or a job for this world is `queued` or `processing`.
  - `404 Not Found`: either entity isn't in this world. This also covers entities in different worlds.

### 13.2 Bulk Delete Entities (planned)
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/entities/bulk-delete`
- **Request Body**:
  ```json
  {
    "entity_ids": ["ent-007", "ent-008"]
  }
  ```
  `entity_ids` must contain at least one id; duplicates are ignored.
- **Response** (`204 No Content`)
- **Behavior**: all-or-nothing. If any id isn't in this world, nothing is deleted. Each entity's facts, versions,
  aliases, mentions, relationships and event participations are removed by the existing cascades, and orphan
  contradictions are deleted (see the shared conventions).
- **Errors**: `404 Not Found` if any id isn't in this world. `422 Unprocessable Entity` if `entity_ids` is empty.

### 13.3 Add Alias (planned)
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/entities/{entity_id}/aliases`
- **Request Body**:
  ```json
  {
    "alias": "The Shadow Blade"
  }
  ```
  `alias` is trimmed and must not be empty.
- **Response** (`201 Created`): the updated Entity object (same shape as §7.1). `aliases` stays a list of strings.
- **Errors**: `400 Bad Request` if the entity already has this alias or this canonical name (case-insensitive).

### 13.4 Remove Alias (planned)
- **Method / Endpoint**: `DELETE /api/v1/worlds/{world_id}/entities/{entity_id}/aliases?alias=The%20Shadow%20Blade`
- The alias goes in a query parameter rather than the path, so aliases containing `/` work. Matching is
  case-insensitive after trimming.
- **Response** (`204 No Content`)
- **Errors**: `404 Not Found` if the entity has no such alias.

### 13.5 Retype Entity
No new endpoint. Inline type edits use `PUT /entities/{entity_id}` (§7.4) with `{"entity_type": "location"}`.

---

## 14. Relationships (`/api/v1/worlds/{world_id}/relationships`)

**Owner:** Person B (`feature/graph-timeline`). **Client:** `Frontend/src/api/relationships.ts`.

There is one relationship row per directed pair (source → target). The relationship type lives on its versions, so
a type change appends a version instead of creating a second row.

**Relationship object:**
```json
{
  "id": "rel-001",
  "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "source_entity_id": "ent-001",
  "source_name": "Valen Thorne",
  "target_entity_id": "ent-002",
  "target_name": "Lady Seraphina",
  "created_at": "2026-09-11T10:10:00Z",
  "current_version": {
    "id": "rver-002",
    "relationship_id": "rel-001",
    "relationship_type": "ENEMY_OF",
    "status": "ACTIVE",
    "chapter_id": "ch-103",
    "chapter_number": 3,
    "confidence": 1.0,
    "created_at": "2026-09-12T09:00:00Z"
  },
  "versions": [
    { "id": "rver-002", "relationship_type": "ENEMY_OF", "status": "ACTIVE", "chapter_number": 3, "...": "..." },
    { "id": "rver-001", "relationship_type": "ALLY_OF", "status": "SUPERSEDED", "chapter_number": 1, "...": "..." }
  ]
}
```
- `current_version` is the latest `ACTIVE` version, or `null` if none is active.
- `versions` lists every version, newest first. Each has the same fields as `current_version`.
- `chapter_id` and `chapter_number` are `null` for a version with no chapter. Such a version is visible at every
  point on the time axis (§16).

### 14.1 List Relationships (planned)
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/relationships`
- **Query Parameters**:
  - `entity_id` *(optional)*: only relationships where this entity is the source or the target.
- **Response** (`200 OK`): a list of Relationship objects.

### 14.2 Get Relationship (planned)
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/relationships/{relationship_id}`
- **Response** (`200 OK`): a Relationship object.

### 14.3 Create Relationship or Add a Type (planned)
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/relationships`
- **Request Body**:
  ```json
  {
    "source_entity_id": "ent-001",
    "target_entity_id": "ent-002",
    "relationship_type": "ALLY_OF",
    "chapter_id": "ch-101",
    "confidence": 1.0
  }
  ```
  `chapter_id` and `confidence` are optional (defaults `null` and `1.0`). The UI form always sends a `chapter_id`,
  because a relationship with no chapter has no place on the time axis.
- **Response**:
  - `201 Created` with the new Relationship object if the directed pair didn't exist. It has one `ACTIVE` version.
  - `200 OK` with the updated Relationship object if the pair already existed. A new version is appended and the
    previous `ACTIVE` version becomes `SUPERSEDED`.
- **Consistency (P1):** the new version is passed to `evaluate_relationship_version`. If a rule flags it, it is stored
  as `CONTRADICTED`, the previous version stays `ACTIVE`, and a contradiction is recorded, as during extraction.
- **Errors**:
  - `400 Bad Request`: `source_entity_id` equals `target_entity_id`, or the pair's `ACTIVE` version already has this
    `relationship_type`.
  - `404 Not Found`: either entity, or the chapter, isn't in this world.

### 14.4 Change Relationship Type (planned)
- **Method / Endpoint**: `PUT /api/v1/worlds/{world_id}/relationships/{relationship_id}`
- **Request Body**:
  ```json
  {
    "relationship_type": "ENEMY_OF",
    "chapter_id": "ch-103",
    "confidence": 1.0
  }
  ```
  `chapter_id` and `confidence` are optional, as in §14.3.
- **Response** (`200 OK`): the updated Relationship object. This works the same as §14.3 on an existing pair: it
  appends a version and supersedes the old one.
- **Errors**: `400 Bad Request` if the `ACTIVE` version already has this type. `404 Not Found` if the relationship or
  chapter isn't in this world.

### 14.5 Delete Relationship (planned)
- **Method / Endpoint**: `DELETE /api/v1/worlds/{world_id}/relationships/{relationship_id}`
- **Response** (`204 No Content`). The row and all its versions are removed (author-initiated delete, RULES.md 3.4),
  and orphan contradictions are deleted.

---

## 15. Events (`/api/v1/worlds/{world_id}/events`)

**Owner:** Person B (`feature/graph-timeline`). **Client:** `Frontend/src/api/events.ts`.

The Event object has the same shape as a timeline event (`TimelineEventResponse`, §9.1): `id`, `world_id`,
`chapter_id`, `chapter_number`, `event_type`, `description`, `start_position`, `end_position`, `sequence_index`,
`confidence`, `created_at` and `participants` (`entity_id`, `entity_name`, `role`). Events have no version table, so
event edits update the row in place. RULES.md 3.1 covers only fact values and relationship types.

**Ordering** (timeline §9.1 and reorder §15.5): by `chapter_number`, then `sequence_index`, then `start_position`,
then `created_at`. Events with no chapter come first, and a `null` in any of these fields sorts after non-null values.

### 15.1 Create Event (planned)
- **Method / Endpoint**: `POST /api/v1/worlds/{world_id}/events`
- **Request Body**:
  ```json
  {
    "description": "Valen leads the defense of the fortress.",
    "event_type": "BATTLE",
    "chapter_id": "ch-102",
    "sequence_index": null,
    "participants": [
      { "entity_id": "ent-001", "role": "commander" }
    ]
  }
  ```
  Only `description` is required. Defaults: `event_type` `"EVENT"`, `chapter_id` `null`, `sequence_index` `null`,
  `participants` `[]`, each `role` `"PARTICIPANT"`.
- **Response** (`201 Created`): the Event object.
- **Errors**: `400 Bad Request` if the same `entity_id` appears twice in `participants`. `404 Not Found` if the
  chapter or a participant entity isn't in this world.

### 15.2 Get Event (planned)
- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/events/{event_id}`
- **Response** (`200 OK`): the Event object. To list events, use the timeline (§9.1).

### 15.3 Update Event (planned)
- **Method / Endpoint**: `PUT /api/v1/worlds/{world_id}/events/{event_id}`
- **Request Body**: any subset of `description`, `event_type`, `chapter_id` and `participants`. If `participants` is
  sent, it replaces the whole list. If `chapter_id` changes, `sequence_index` resets to `null`.
- **Response** (`200 OK`): the updated Event object.
- **Errors**: the same as §15.1.

### 15.4 Delete Event (planned)
- **Method / Endpoint**: `DELETE /api/v1/worlds/{world_id}/events/{event_id}`
- **Response** (`204 No Content`). Participants are removed by cascade, and orphan contradictions are deleted.

### 15.5 Reorder Events Within a Chapter (planned)
The timeline's up/down buttons send the chapter's full event order. There is no drag-and-drop.
- **Method / Endpoint**: `PATCH /api/v1/worlds/{world_id}/events/reorder`
- **Request Body**:
  ```json
  {
    "chapter_id": "ch-102",
    "event_ids": ["ev-005", "ev-003", "ev-004"]
  }
  ```
  `event_ids` must list every event in that chapter exactly once. `chapter_id: null` reorders the events that have no
  chapter.
- **Response** (`200 OK`): `{"events": [...], "total": 3}` (the §9.1 shape), holding only that chapter's events in
  their new order. The server sets `sequence_index` to `0..n-1` in the order given.
- **Errors**: `400 Bad Request` if `event_ids` has duplicates, is missing an event in the chapter, or contains an
  event from another chapter. `404 Not Found` if the chapter isn't in this world.
- Declare this route before `/events/{event_id}` so `reorder` is never read as an event id.

---

## 16. Time-Slice Graph (`GET /api/v1/worlds/{world_id}/graph?as_of_chapter=N`)

**Owner:** Person B (`feature/graph-timeline`). This extends §8.1 and reuses the §8.1 response shape.

- **Method / Endpoint**: `GET /api/v1/worlds/{world_id}/graph?as_of_chapter=N` (planned)
- **Query Parameters**:
  - `as_of_chapter` *(optional, integer ≥ 1)*: show the world as it stood at the end of chapter `N`. If omitted, the
    response is exactly what §8.1 returns today ("latest").
- **Response** (`200 OK`): the §8.1 Graph object. An edge's `type`, `status` and `chapter_id` come from the version
  chosen for chapter `N`, and node `properties` come from the fact versions chosen for chapter `N`. An `N` beyond the
  last chapter returns the state after the last chapter.
- **Errors**: `422 Unprocessable Entity` if `as_of_chapter` isn't an integer ≥ 1.

**As-of rules:**
- **Edges:** for each directed pair, take the versions with chapter number ≤ `N` (a version with no chapter always
  counts). The latest such version wins. Ignore `ACTIVE`/`SUPERSEDED` here, because those describe "now", not
  "then". Exclude:
  - versions in an unresolved (`DETECTED`) contradiction that are `CONTRADICTED`, and
  - versions the author rejected: the new-side version of a `RESOLVED` contradiction that ended up `SUPERSEDED`.

  Otherwise the slider would show claims the author threw out. A pair with no qualifying version has no edge.
- **Node properties:** the same rule, applied to each fact's versions.
- **Nodes:** a node is shown if it has an as-of fact or edge, a mention in chapter ≤ `N` (mention → extraction run →
  chapter version → chapter), or no chapter-tagged data at all (a manually created entity).
- **Limitation:** chapter numbers are per manuscript. In a world with more than one manuscript, `N` matches chapter `N`
  of every manuscript. The demo world has one manuscript.

---

## 17. Re-extraction Proposals (`GET /api/v1/jobs/{job_id}/proposals`)

**Owner:** Extraction (`feature/extraction-review`). **Client:** `Frontend/src/api/proposals.ts`.

Editing a chapter starts a `RE_EXTRACTION` job (§5.3). With propose-then-apply, the job runs the extractor only,
compares the result with the current world, and saves the proposals as a JSON file keyed by job id. It doesn't write
to the world tables. The first upload (`INITIAL_EXTRACTION`) still writes directly and has no proposals.

### 17.1 Get Proposals (planned)
- **Method / Endpoint**: `GET /api/v1/jobs/{job_id}/proposals`
- **Response**:
  - `200 OK` when the job is `done`: the Proposals object below with `"status": "ready"`.
  - `202 Accepted` while the job is `queued` or `processing`: the same shape with `"status": "pending"` and an empty
    `proposals` list. Keep polling `GET /jobs/{job_id}/status` (§6.2).
- **Errors**: `404 Not Found` if the job doesn't exist or isn't the user's, the job isn't a `RE_EXTRACTION` job, or it
  `failed`.

**Proposals object:**
```json
{
  "job_id": "e0a29482-1678-43d9-a78b-d535b91b5c90",
  "world_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "chapter_id": "ch-102",
  "chapter_number": 2,
  "status": "ready",
  "generated_at": "2026-10-12T14:03:00Z",
  "proposals": [
    {
      "id": "p-001",
      "kind": "entity",
      "change": "new",
      "summary": "New character: Mara Venn",
      "confidence": 0.9,
      "match_entity_id": null,
      "proposed": { "canonical_name": "Mara Venn", "entity_type": "character", "aliases": [] }
    },
    {
      "id": "p-002",
      "kind": "fact",
      "change": "changed",
      "summary": "Valen Thorne status: alive → dead",
      "confidence": 0.8,
      "entity": { "entity_id": "ent-001" },
      "current": { "fact_version_id": "fver-100", "value": "alive" },
      "proposed": { "property_name": "status", "value": "dead", "confidence": 0.8 }
    },
    {
      "id": "p-003",
      "kind": "relationship",
      "change": "new",
      "summary": "Mara Venn ALLY_OF Valen Thorne",
      "confidence": 0.7,
      "source": { "entity_ref": "p-001" },
      "target": { "entity_id": "ent-001" },
      "current": null,
      "proposed": { "relationship_type": "ALLY_OF", "chapter_id": "ch-102", "confidence": 0.7 }
    }
  ]
}
```

**Proposal fields:**
- `id`: unique within this response. Other proposals point at it through `entity_ref`.
- `change`: `new` (the modal shows it with a tick box to add it), `changed` (the author chooses old or new) or
  `known` (already in the world; the modal hides it).
- **Entity references** (`entity`, `source`, `target`, `participants[].entity`): either `{"entity_id": "..."}` for an
  existing entity, or `{"entity_ref": "p-001"}` for the entity created by a `new` entity proposal in the same response.

| `kind` | Kind-specific fields | `change` values | Applied with |
| --- | --- | --- | --- |
| `entity` | `match_entity_id` (set when `known`), `proposed`: §7.2 body | `new`, `known` | `POST /entities` (§7.2) |
| `alias` | `entity_id`, `proposed`: `{"alias": "..."}` | `new`, `known` | `POST /entities/{id}/aliases` (§13.3) |
| `fact` | `entity`, `current`: `{fact_version_id, value}` or `null`, `proposed`: §7.6 body | `new`, `changed`, `known` | `POST /entities/{id}/facts` (§7.6) |
| `relationship` | `source`, `target`, `current`: `{relationship_id, relationship_version_id, relationship_type}` or `null`, `proposed`: `{relationship_type, chapter_id, confidence}` | `new`, `changed`, `known` | `POST /relationships` (§14.3) |
| `event` | `participants`: `[{entity, role}]`, `proposed`: §15.1 body without `participants` | `new`, `known` | `POST /events` (§15.1) |

**Applying (frontend, `WritingRoom.tsx` review modal):**
- There is no apply endpoint. The modal calls the manual endpoints in the table, so every accepted change goes through
  the same write path as a manual edit and becomes a new version (RULES.md 3.4).
- Apply in this order: `entity` → `alias` → `fact` → `relationship` → `event`. Replace each `entity_ref` with the id
  returned when that entity proposal was applied.
- If the author rejects a `new` entity proposal, also skip every proposal that references it through `entity_ref`.
- For a `changed` proposal, "keep old" sends nothing. "Keep new" sends `proposed` to the endpoint, which appends a
  version and supersedes the old one.
