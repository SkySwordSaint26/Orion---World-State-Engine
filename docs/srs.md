## for

## World State Engine

Version 1.0 approved

Prepared by: `<author>`
Organization: `<organization>`
Date: `<date created>`

---

## Table of Contents

- Revision History
- 
    1. Introduction
    - 1.1 Purpose
    - 1.2 Document Conventions
    - 1.3 Intended Audience and Reading Suggestions
    - 1.4 Product Scope
    - 1.5 References
- 
    1. Overall Description
    - 2.1 Product Perspective
    - 2.2 Product Functions
    - 2.3 User Classes and Characteristics
    - 2.4 Operating Environment
    - 2.5 Design and Implementation Constraints
    - 2.6 User Documentation
    - 2.7 Assumptions and Dependencies
- 
    1. External Interface Requirements
    - 3.1 User Interfaces
    - 3.2 Hardware Interfaces
    - 3.3 Software Interfaces
    - 3.4 Communications Interfaces
- 
    1. System Features
- 
    1. Other Nonfunctional Requirements
    - 5.1 Performance Requirements
    - 5.2 Safety Requirements
    - 5.3 Security Requirements
    - 5.4 Software Quality Attributes
    - 5.5 Business Rules
- 
    1. Other Requirements
- Appendix A: Glossary
- Appendix B: Analysis Models
- Appendix C: To Be Determined List

---

## Revision History

| Name | Date | Reason For Changes | Version |
| --- | --- | --- | --- |
| `<author>` | `<date created>` | Initial draft | 1.0 |

---

## 1. Introduction

### 1.1 Purpose

This document describes the software requirements for the World State Engine, version 1.0. This SRS covers the full system: manuscript upload, information extraction, fact versioning, contradiction detection, timeline viewing, graph visualization, search, export, and character chat.

### 1.2 Document Conventions

Each requirement is listed under the system feature it belongs to and is numbered for reference (for example, REQ-1). Requirements are written in plain, simple language and do not describe how the system should be built.

### 1.3 Intended Audience and Reading Suggestions

This document is intended for developers, testers, and project managers working on the World State Engine. Readers should start with Section 2 (Overall Description) for a general understanding, then read Section 4 (System Features) for detailed requirements, and Section 5 for non-functional requirements.

### 1.4 Product Scope

The World State Engine is a system that helps writers keep track of characters, locations, objects, relationships, and events across a manuscript. The system reads uploaded chapters, extracts this information automatically, keeps a history of how facts change over time, and flags contradictions (for example, a character's age or eye colour changing without explanation). It also lets the user view a timeline of the story world, view a relationship graph, search extracted information, chat with a character based only on extracted facts, and export results.

The goal is to reduce the manual effort a writer spends tracking consistency across a long manuscript.

### 1.5 References

None at this time.

---

## 2. Overall Description

### 2.1 Product Perspective

The World State Engine is a new, self-contained system. It is not a replacement for an existing product.

### 2.2 Product Functions

At a high level, the system must let the user:

- Register, log in, and manage multiple writing projects
- Upload and manage manuscripts and chapters
- Automatically extract characters, locations, objects, relationships, and events from chapters
- Resolve aliases so the same character/entity is recognized under different names
- Store a version history of facts as they change across chapters
- Detect contradictions between fact versions
- View a report of detected contradictions
- View the world state at any point in the story timeline
- Chat with a character using only extracted information
- View a graph of characters, locations, and their connections
- Search extracted information
- Export results

### 2.3 User Classes and Characteristics

There is one primary user class:

- **Writer/Author** – uses the system to upload manuscripts, review extracted data, resolve or review contradictions, and use the timeline, graph, search, and chat features. No special technical knowledge is assumed.

### 2.4 Operating Environment

The system is a web-based application, accessible through a standard web browser. Further environment details (server platform, browser versions supported) are not yet defined.

### 2.5 Design and Implementation Constraints

None specified at this time. This document does not define how the system should be built, only what it must do.

### 2.6 User Documentation

Not yet defined.

### 2.7 Assumptions and Dependencies

- It is assumed that uploaded manuscripts are in English.
- It is assumed that manuscripts are divided into, or can be divided into, chapters.
- It is assumed contradiction detection does not rely on a language model for its core logic; detection must be rule-based, as stated in the acceptance criteria.

---

## 3. External Interface Requirements

### 3.1 User Interfaces

The system shall provide a graphical, browser-based interface. Specific screen layouts are not defined in this document.

### 3.2 Hardware Interfaces

None identified.

### 3.3 Software Interfaces

Not yet defined. (Details such as specific databases, libraries, or third-party services are implementation decisions and are outside the scope of this document.)

### 3.4 Communications Interfaces

The system shall use a secure communications protocol (HTTPS) for all data sent between the user's browser and the system, as noted in Section 5.3.

---

## 4. System Features

### 4.1 User Authentication and Project Management

#### 4.1.1 Description and Priority

Allows users to register, log in, and manage more than one writing project. Each project keeps its own manuscripts and extracted world data separate from other projects. Priority: High.

#### 4.1.2 Stimulus/Response Sequences

- When a user registers with account details, the system creates an account.
- When a user logs in with valid credentials, the system grants access to that user's projects.
- When a user creates a new project, the system creates an empty project space for it.

#### 4.1.3 Functional Requirements

- REQ-1: Users shall be able to register a new account.
- REQ-2: Users shall be able to log in and log out.
- REQ-3: Users shall be able to create, view, and manage multiple writing projects.
- REQ-4: Each project shall store its own manuscripts and world data, kept separate from other projects and other users.

---

### 4.2 Manuscript Management

#### 4.2.1 Description and Priority

Allows users to upload, organize, and edit manuscripts and chapters. Priority: High.

#### 4.2.2 Stimulus/Response Sequences

- When a user uploads a manuscript file, the system stores it and makes it available for chapter creation.
- When a user edits a chapter, the system saves the change and allows extraction to be re-run on that chapter.

#### 4.2.3 Functional Requirements

- REQ-5: Users shall be able to upload manuscripts in .txt, .docx, or .pdf format.
- REQ-6: Users shall be able to create chapters within a manuscript.
- REQ-7: Users shall be able to edit existing chapters.
- REQ-8: Users shall be able to delete chapters.
- REQ-9: Users shall be able to re-run extraction on a chapter after editing it.
- REQ-10: Users shall be able to view the edit history of a chapter.

---

### 4.3 Text Extraction

#### 4.3.1 Description and Priority

Automatically extracts characters, locations, objects, relationships, and events from chapter text. This is the core function the rest of the system depends on. Priority: High.

#### 4.3.2 Stimulus/Response Sequences

- When a user submits a chapter for extraction, the system returns a list of extracted characters, locations, objects, relationships, and events.

#### 4.3.3 Functional Requirements

- REQ-11: The system shall extract character names from chapter text.
- REQ-12: The system shall extract location names from chapter text.
- REQ-13: The system shall extract object names from chapter text.
- REQ-14: The system shall extract relationships between characters (for example, "Character A is the sister of Character B").
- REQ-15: The system shall extract events from chapter text (for example, battle, death, marriage, travel, discovery).
- REQ-16: Extraction of a single chapter shall complete within the time limit defined in Section 5.1.

---

### 4.4 Co reference Resolution

#### 4.4.1 Description and Priority

Recognizes when different names, titles, or pronouns in the text refer to the same character or entity. Priority: High.

#### 4.4.2 Stimulus/Response Sequences

- When the system encounters multiple references, such as a name, title, or pronoun, that refer to the same entity, it links them to a single entity record.

#### 4.4.3 Functional Requirements

- REQ-17: The system shall identify when different names, titles, or pronouns refer to the same entity.
- REQ-18: The system shall merge such references into a single entity record.

---

### 4.5 World Graph

#### 4.5.1 Description and Priority

Maintains a structured record of all extracted entities and their information. Priority: High.

#### 4.5.2 Stimulus/Response Sequences

- When a new entity is extracted, the system adds it to the world graph.
- When an existing entity is referenced again, the system updates its record.

#### 4.5.3 Functional Requirements

- REQ-19: The system shall maintain records of characters, locations, factions, objects, relationships, and events.
- REQ-20: Each record shall include an ID, a type, its attributes, and its version history.

---

### 4.6 State Versioning

#### 4.6.1 Description and Priority

Keeps every version of a fact instead of overwriting old information, so the writer can see how something changed over the course of the story. Priority: High.

#### 4.6.2 Stimulus/Response Sequences

- When a fact about an entity changes between chapters, the system stores the new value alongside the old value, rather than replacing it.

#### 4.6.3 Functional Requirements

- REQ-21: Every extracted fact shall record the entity, the property, the value, the chapter it appeared in, and the time it was recorded.
- REQ-22: The system shall never overwrite a previously stored fact; all versions shall be kept.

---

### 4.7 Consistency Detection

#### 4.7.1 Description and Priority

Detects contradictions between different versions of the same fact (for example, a character's age going down instead of up, or a character appearing in two places at once). Priority: High.

#### 4.7.2 Stimulus/Response Sequences

- When a new fact value is recorded that conflicts with an earlier one, the system flags it as a contradiction.

#### 4.7.3 Functional Requirements

- REQ-23: The system shall detect contradictions in a character's age across chapters.
- REQ-24: The system shall detect contradictions in a character's location across chapters.
- REQ-25: The system shall detect contradictions in relationships (for example, a character's stated father changing without explanation).
- REQ-26: The system shall detect contradictions in a character's status (for example, marked as dead, then shown speaking later).
- REQ-27: Contradiction detection shall be based on defined rules and shall not rely on a language model to decide whether a contradiction exists.
- REQ-28: Contradiction detection for a chapter shall complete within the time limit defined in Section 5.1.

---

### 4.8 Contradiction Report

#### 4.8.1 Description and Priority

Displays detected contradictions to the user in a clear, readable way. Priority: High.

#### 4.8.2 Stimulus/Response Sequences

- When a user opens the contradiction report, the system displays all detected contradictions along with their supporting details.

#### 4.8.3 Functional Requirements

- REQ-29: For each contradiction, the system shall display the entity, the property, the old value, the new value, and the chapter references involved.
- REQ-30: For each contradiction, the system shall display a confidence score.
- REQ-31: For each contradiction, the system shall display a plain-language explanation of the conflict.

---

### 4.9 Timeline Viewer

#### 4.9.1 Description and Priority

Lets the user view and compare the state of the story world at different chapters. Priority: Medium.

#### 4.9.2 Stimulus/Response Sequences

- When a user selects a chapter, the system displays the world state at that chapter.
- When a user selects two chapters to compare, the system displays the differences between them.

#### 4.9.3 Functional Requirements

- REQ-32: Users shall be able to move between chapters in the timeline view.
- REQ-33: Users shall be able to view the world state as it was at any given chapter.
- REQ-34: Users shall be able to compare the world state between two chapters.
- REQ-35: The system shall highlight what changed between the two compared chapters.

---

### 4.10 Character Chat

#### 4.10.1 Description and Priority

Lets the user ask what a character would do or say, with answers based only on information already extracted from the manuscript. Priority: Low.

#### 4.10.2 Stimulus/Response Sequences

- When a user asks a question about a character, the system responds using only that character's extracted dialogue, personality, relationships, and current chapter state.

#### 4.10.3 Functional Requirements

- REQ-36: Users shall be able to ask questions about a character.
- REQ-37: Responses shall be based only on extracted dialogue, personality, relationships, and the character's current chapter state.
- REQ-38: The system shall not generate facts about a character that are not supported by extracted information.
- REQ-39: Chat responses shall be returned within the time limit defined in Section 5.1.

---

### 4.11 Graph Visualization

#### 4.11.1 Description and Priority

Displays characters, locations, and their connections as a visual graph. Priority: Medium.

#### 4.11.2 Stimulus/Response Sequences

- When a user opens the graph view, the system displays the entities and the connections between them.
- When a user zooms, pans, searches, or filters, the system updates the view accordingly.

#### 4.11.3 Functional Requirements

- REQ-40: The system shall display characters, locations, and the connections between them.
- REQ-41: Users shall be able to zoom and pan the graph.
- REQ-42: Users shall be able to search within the graph.
- REQ-43: Users shall be able to filter what is shown in the graph.

---

### 4.12 Search

#### 4.12.1 Description and Priority

Lets the user search extracted information. Priority: Medium.

#### 4.12.2 Stimulus/Response Sequences

- When a user enters a search term, the system returns the matching results.

#### 4.12.3 Functional Requirements

- REQ-44: Users shall be able to search by character.
- REQ-45: Users shall be able to search by location.
- REQ-46: Users shall be able to search by event.
- REQ-47: Users shall be able to search by chapter.
- REQ-48: Users shall be able to search by relationship.

---

### 4.13 Export

#### 4.13.1 Description and Priority

Lets the user export data out of the system. Priority: Low.

#### 4.13.2 Stimulus/Response Sequences

- When a user requests an export, the system generates the file in the chosen format.

#### 4.13.3 Functional Requirements

- REQ-49: Users shall be able to export data as JSON.
- REQ-50: Users shall be able to export data as CSV.
- REQ-51: Users shall be able to export a report as PDF.

---

## 5. Other Nonfunctional Requirements

### 5.1 Performance Requirements

- Extraction of a single chapter shall take no more than 10 seconds.
- Character chat shall respond within 3 seconds.
- Contradiction detection shall complete within 5 seconds.

### 5.2 Safety Requirements

None identified.

### 5.3 Security Requirements

- Passwords shall be stored using a hashing method, not in plain text.
- All communication between the user's browser and the system shall use HTTPS.
- Users shall be authenticated using JWT (JSON Web Tokens).
- One user's project data shall not be accessible to another user.

### 5.4 Software Quality Attributes

- **Scalability**: the system shall support at least 500 chapters, 1000 characters, and 20,000 extracted facts per project.
- **Reliability**: the system shall not lose data, shall perform automatic backups, and shall keep updates transaction-safe (an update either fully completes or does not happen at all).
- **Availability**: the deployed system shall maintain 99% uptime.
- **Usability**: the system shall provide a simple dashboard, one-click extraction, an interactive graph, and a responsive interface that works on different screen sizes.
- **Maintainability**: the backend shall be built in a modular way, shall expose a REST API, shall include unit tests, and shall include API documentation.

### 5.5 Business Rules

None identified at this time.

---

## 6. Other Requirements

- The system shall permanently retain the full history of extracted facts, including all versions, for as long as the project exists. Facts shall not be deleted when a new version is recorded (see REQ-22).
- The system shall preserve historical world states even after a manuscript has been edited and re-extracted.

---

## Appendix A: Glossary

| Term | Definition |
| --- | --- |
| Entity | A character, location, object, faction, or event recognized by the system. |
| World Graph | The system's structured record of all entities and their relationships. |
| Fact | A single piece of information about an entity (for example, a character's age) recorded at a specific chapter. |
| Contradiction | Two recorded facts about the same entity and property that conflict with each other. |
| Coreference Resolution | The process of recognizing that different names or pronouns refer to the same entity. |
| Timeline | A view of how the world state changes chapter by chapter. |

## Appendix B: Analysis Models

Not included in this document.

## Appendix C: To Be Determined List

| # | Item | Section |
| --- | --- | --- |
| 1 | Specific browser/OS support | 2.4 |
| 2 | User documentation deliverables | 2.6 |
| 3 | Specific software interfaces (third-party tools, libraries) | 3.3 |
| 4 | Detailed UI screen layouts | 3.1 |