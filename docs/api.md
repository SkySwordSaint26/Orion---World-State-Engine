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
    "error_message": null
  }
  ```
  *Status Values:* `queued`, `processing`, `done`, `failed`.

---

## 7. Entities & Facts (`/api/v1/worlds/{world_id}/entities`)

Entities represent characters, locations, and objects. In compliance with **SRS REQ-22**, fact records are append-only; property values are versioned and never destructively updated in place.

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
