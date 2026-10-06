import { create } from 'zustand';
import type { 
  World, 
  Entity, 
  TimelineEvent, 
  Contradiction, 
  Manuscript 
} from '../data/mockData';
import { apiFetch } from '../api/client';

// Everything shown comes from the API: no sample data, and a failed or empty fetch shows nothing rather than
// something invented (the demo must show what extraction actually produced).
const titleCase = (code: string) => code.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

interface WorldState {
  worlds: World[];
  entities: Entity[];
  timelineEvents: TimelineEvent[];
  contradictions: Contradiction[];
  manuscripts: Manuscript[];
  
  activeWorldId: string | null;
  activeManuscriptId: string | null;
  activeChapterId: string | null;
  activeEntityId: string | null;
  activeTimelineEventId: string | null;
  
  // Navigation / Panel states
  isEntityPanelOpen: boolean;
  
  // Actions
  setActiveWorld: (id: string | null) => void;
  setActiveManuscript: (id: string | null) => void;
  setActiveChapter: (id: string | null) => void;
  setActiveEntity: (id: string | null) => void;
  setActiveTimelineEvent: (id: string | null) => void;
  setEntityPanelOpen: (isOpen: boolean) => void;
  
  // World Actions
  setWorlds: (worlds: World[]) => void;
  addWorld: (world: World) => void;
  
  // Entity Actions
  fetchEntitiesForWorld: (worldId: string) => Promise<void>;
  addEntity: (entity: Omit<Entity, 'facts' | 'relationships' | 'appearances'>) => Promise<void>;
  updateEntity: (id: string, updated: Partial<Entity>) => void;
  deleteEntity: (id: string) => void;
  
  // Fact Actions
  addFact: (entityId: string, text: string, type?: 'manual' | 'extracted', source?: string) => void;
  deleteFact: (entityId: string, factId: string) => void;

  // Timeline & Contradictions Actions
  fetchTimelineForWorld: (worldId: string) => Promise<void>;
  fetchContradictionsForWorld: (worldId: string) => Promise<void>;
  resolveContradictionInBackend: (worldId: string, contradictionId: string) => Promise<void>;
  resolveContradiction: (id: string) => void;
  
  // Manuscript Actions
  fetchManuscriptsForWorld: (worldId: string) => Promise<Manuscript[]>;
  updateChapterContent: (manuscriptId: string, chapterId: string, content: string) => void;
  deleteChapter: (manuscriptId: string, chapterId: string) => void;
  deleteManuscript: (manuscriptId: string) => void;
}

export const useWorldStore = create<WorldState>((set, get) => ({
  worlds: [],
  entities: [],
  timelineEvents: [],
  contradictions: [],
  manuscripts: [],
  
  activeWorldId: null,
  activeManuscriptId: null,
  activeChapterId: null,
  activeEntityId: null,
  activeTimelineEventId: null,
  
  isEntityPanelOpen: false,
  
  setActiveWorld: (id) => set({ 
    activeWorldId: id,
    activeManuscriptId: null,
    activeChapterId: null,
    activeEntityId: null,
    activeTimelineEventId: null,
    isEntityPanelOpen: false,
    manuscripts: [],
    entities: [],                     // never show the previous world's data while this one loads
    timelineEvents: [],
    contradictions: []
  }),
  
  setActiveManuscript: (id) => set((state) => {
    const manuscript = state.manuscripts.find((m) => m.id === id);
    const firstChapterId = manuscript?.chapters[0]?.id || null;
    return {
      activeManuscriptId: id,
      activeChapterId: firstChapterId
    };
  }),
  
  setActiveChapter: (id) => set({ activeChapterId: id }),
  
  setActiveEntity: (id) => set(() => ({
    activeEntityId: id,
    isEntityPanelOpen: id !== null
  })),
  
  setActiveTimelineEvent: (id) => set((state) => {
    const updatedWorlds = state.worlds.map((w) => {
      if (w.id === state.activeWorldId && id) {
        const ev = state.timelineEvents.find((e) => e.id === id);
        if (ev) {
          return {
            ...w,
            description: `${ev.title} (${ev.period} • Year ${ev.year}): ${ev.description}`
          };
        }
      }
      return w;
    });
    return {
      activeTimelineEventId: id,
      worlds: updatedWorlds
    };
  }),
  
  setEntityPanelOpen: (isOpen) => set((state) => ({ 
    isEntityPanelOpen: isOpen,
    activeEntityId: isOpen ? state.activeEntityId : null
  })),
  
  setWorlds: (worlds) => set({ worlds }),
  
  addWorld: (world) => set((state) => ({
    worlds: [...state.worlds, world]
  })),

  fetchEntitiesForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any[]>(`/worlds/${worldId}/entities`);
      const mapped: Entity[] = data.map((ent: any) => ({
        id: ent.id,
        name: ent.canonical_name,
        type: ent.entity_type as any,
        description: (ent.aliases || []).length ? `Also called: ${ent.aliases.join(', ')}` : '',
        facts: (ent.facts || []).map((f: any) => ({
          id: f.id,
          text: `${f.property_name}: ${f.current_version?.value ?? ''}`,
          source: f.current_version?.chapter_id || 'System',
          type: 'extracted'
        })),
        relationships: [],
        appearances: []
      }));

      set({ entities: mapped });
    } catch (e) {
      console.error("Could not fetch entities from API", e);
    }
  },

  fetchTimelineForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any>(`/worlds/${worldId}/timeline`);
      const mapped: TimelineEvent[] = (data?.events || []).map((ev: any) => ({
        id: ev.id,
        year: ev.chapter_number ?? 0,           // the backend orders by chapter; there are no in-story years
        period: (ev.participants || []).map((p: any) => p.entity_name).filter(Boolean).join(', ') || 'No participants',
        title: titleCase(ev.event_type || 'EVENT'),
        description: ev.description || '',
        stateChanges: [],
        chapters: []
      }));
      set({ timelineEvents: mapped });
    } catch (e) {
      console.error("Could not fetch timeline from API", e);
    }
  },

  fetchContradictionsForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any[]>(`/worlds/${worldId}/contradictions`);
      // explanation = "[RULE_ID] what the rule found" (app/consistency); confidence is the rule's own
      const mapped: Contradiction[] = (data || []).map((c: any) => {
        const [, rule = c.contradiction_type, text = c.explanation] = /^\[(\w+)\]\s*(.*)$/s.exec(c.explanation || '') || [];
        return {
          id: c.id,
          title: titleCase(rule || 'CONTRADICTION'),
          category: titleCase(c.contradiction_type || ''),
          targetEntityId: '',
          severity: c.confidence >= 0.85 ? 'high' : c.confidence >= 0.6 ? 'medium' : 'low',
          summary: text || '',
          resolved: c.status === 'RESOLVED',
          sources: []
        };
      });
      set({ contradictions: mapped });
    } catch (e) {
      console.error("Could not fetch contradictions from API", e);
    }
  },

  resolveContradictionInBackend: async (worldId: string, contradictionId: string) => {
    try {
      await apiFetch(`/worlds/${worldId}/contradictions/${contradictionId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ status: 'RESOLVED' })
      });
      get().resolveContradiction(contradictionId);   // only once the backend has it
    } catch (e) {
      console.error("Could not resolve the contradiction on the API", e);
    }
  },
  
  addEntity: async (entityData) => {
    const activeWorldId = get().activeWorldId;
    let newId = `entity-${Date.now()}`;
    let createdEntity: Entity = {
      ...entityData,
      id: newId,
      facts: [],
      relationships: [],
      appearances: []
    };

    if (!activeWorldId) return;                      // nowhere to save it
    try {
      const res = await apiFetch<any>(`/worlds/${activeWorldId}/entities`, {
        method: 'POST',
        body: JSON.stringify({
          canonical_name: entityData.name,
          entity_type: entityData.type,
          aliases: entityData.alias ? [entityData.alias] : [],
          attributes: { description: entityData.description, subtype: entityData.subtype }
        })
      });
      createdEntity.id = res.id;
    } catch (err) {
      console.error("Failed to create entity on API; not added", err);
      return;                                        // a local-only entity would look saved but isn't
    }

    set((state) => {
      const updatedWorlds = state.worlds.map((w) => {
        if (w.id === state.activeWorldId) {
          return {
            ...w,
            entityCount: w.entityCount + 1,
            characterCount: entityData.type === 'character' ? w.characterCount + 1 : w.characterCount,
            locationCount: entityData.type === 'location' ? w.locationCount + 1 : w.locationCount,
            objectCount: entityData.type === 'object' ? w.objectCount + 1 : w.objectCount,
            eventCount: entityData.type === 'event' ? w.eventCount + 1 : w.eventCount
          };
        }
        return w;
      });

      return {
        entities: [...state.entities, createdEntity],
        worlds: updatedWorlds,
        activeEntityId: createdEntity.id,
        isEntityPanelOpen: true
      };
    });
  },
  
  updateEntity: (id, updated) => set((state) => ({
    entities: state.entities.map((e) => e.id === id ? { ...e, ...updated } : e)
  })),
  
  deleteEntity: (id) => set((state) => {
    const entityToDelete = state.entities.find((e) => e.id === id);
    const updatedWorlds = state.worlds.map((w) => {
      if (w.id === state.activeWorldId && entityToDelete) {
        return {
          ...w,
          entityCount: Math.max(0, w.entityCount - 1),
          characterCount: entityToDelete.type === 'character' ? Math.max(0, w.characterCount - 1) : w.characterCount,
          locationCount: entityToDelete.type === 'location' ? Math.max(0, w.locationCount - 1) : w.locationCount,
          objectCount: entityToDelete.type === 'object' ? Math.max(0, w.objectCount - 1) : w.objectCount,
          eventCount: entityToDelete.type === 'event' ? Math.max(0, w.eventCount - 1) : w.eventCount
        };
      }
      return w;
    });

    return {
      entities: state.entities.filter((e) => e.id !== id),
      worlds: updatedWorlds,
      activeEntityId: state.activeEntityId === id ? null : state.activeEntityId,
      isEntityPanelOpen: state.activeEntityId === id ? false : state.isEntityPanelOpen
    };
  }),
  
  addFact: (entityId, text, type = 'manual', source = 'Manual') => set((state) => ({
    entities: state.entities.map((e) => {
      if (e.id === entityId) {
        const newFact = {
          id: `fact-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          text,
          source,
          type
        };
        return {
          ...e,
          facts: [...e.facts, newFact]
        };
      }
      return e;
    })
  })),
  
  deleteFact: (entityId, factId) => set((state) => ({
    entities: state.entities.map((e) => {
      if (e.id === entityId) {
        return {
          ...e,
          facts: e.facts.filter((f) => f.id !== factId)
        };
      }
      return e;
    })
  })),
  
  resolveContradiction: (id) => set((state) => {
    const updatedContradictions = state.contradictions.map((c) => 
      c.id === id ? { ...c, resolved: true } : c
    );
    return {
      contradictions: updatedContradictions
    };
  }),
  
  updateChapterContent: (manuscriptId, chapterId, content) => set((state) => {
    const updatedManuscripts = state.manuscripts.map((m) => {
      if (m.id === manuscriptId) {
        const updatedChapters = m.chapters.map((ch) => {
          if (ch.id === chapterId) {
            const wordCount = content.trim() ? content.trim().split(/\s+/).length : 0;
            return {
              ...ch,
              content,
              wordCount
            };
          }
          return ch;
        });
        return { ...m, chapters: updatedChapters };
      }
      return m;
    });
    return { manuscripts: updatedManuscripts };
  }),

  deleteChapter: (manuscriptId, chapterId) => set((state) => {
    const updatedManuscripts = state.manuscripts
      .map(m => {
        if (m.id === manuscriptId) {
          return { ...m, chapters: m.chapters.filter(c => c.id !== chapterId) };
        }
        return m;
      })
      .filter(m => m.chapters.length > 0);

    const activeManuscriptRemoved = !updatedManuscripts.some(m => m.id === state.activeManuscriptId);

    return {
      manuscripts: updatedManuscripts,
      activeManuscriptId: activeManuscriptRemoved
        ? (updatedManuscripts[0]?.id || null)
        : state.activeManuscriptId,
      activeChapterId: state.activeChapterId === chapterId || activeManuscriptRemoved
        ? (activeManuscriptRemoved ? (updatedManuscripts[0]?.chapters[0]?.id || null) : null)
        : state.activeChapterId
    };
  }),

  deleteManuscript: (manuscriptId) => set((state) => {
    const updatedManuscripts = state.manuscripts.filter(m => m.id !== manuscriptId);
    const activeManuscriptRemoved = state.activeManuscriptId === manuscriptId;

    return {
      manuscripts: updatedManuscripts,
      activeManuscriptId: activeManuscriptRemoved
        ? (updatedManuscripts[0]?.id || null)
        : state.activeManuscriptId,
      activeChapterId: activeManuscriptRemoved
        ? (updatedManuscripts[0]?.chapters[0]?.id || null)
        : state.activeChapterId
    };
  }),

  fetchManuscriptsForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any[]>(`/worlds/${worldId}/manuscripts`);
      const mapped: Manuscript[] = await Promise.all(
        data.map(async (m: any) => {
          let chapters: any[] = [];
          try {
            const chs = await apiFetch<any[]>(`/worlds/${worldId}/manuscripts/${m.id}/chapters`);
            chapters = chs.map(ch => ({
              id: ch.id,
              number: ch.chapter_number,
              title: ch.title,
              content: ch.content || '',
              wordCount: ch.word_count ?? (ch.content ? ch.content.trim().split(/\s+/).length : 0)
            }));
          } catch (_) {}

          return {
            id: m.id,
            title: m.title,
            chapters
          };
        })
      );
      // Filter out manuscripts that have 0 chapters so empty manuscripts are not displayed
      const validManuscripts = mapped.filter(m => m.chapters.length > 0);
      set({ manuscripts: validManuscripts });
      
      // Select the first manuscript/chapter if nothing is selected or if previously active manuscript was removed
      const currentState = get();
      if ((!currentState.activeManuscriptId || !validManuscripts.some(m => m.id === currentState.activeManuscriptId)) && validManuscripts.length > 0) {
        set({
          activeManuscriptId: validManuscripts[0].id,
          activeChapterId: validManuscripts[0].chapters.length > 0 ? validManuscripts[0].chapters[0].id : null
        });
      } else if (validManuscripts.length === 0) {
        set({
          activeManuscriptId: null,
          activeChapterId: null
        });
      }
      return validManuscripts;
    } catch (err) {
      console.warn("Failed to fetch manuscripts", err);
      return [];
    }
  }
}));
