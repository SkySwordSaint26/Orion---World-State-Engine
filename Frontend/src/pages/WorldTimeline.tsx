import React, { useEffect, useState, useMemo, useRef } from 'react';
import { AppShell } from '../components/AppShell';
import { Dialog } from '../components/Dialog';
import { useWorldStore } from '../store/useWorldStore';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import {
  getTimeline,
  reorderEvents,
  deleteEvent,
  createEvent,
  updateEvent,
  type EventResponse,
  type EventParticipantInput,
} from '../api/events';

interface ModalParticipantItem {
  entity_id: string;
  role: string;
  entity_name?: string;
}

const COMMON_ROLES = [
  'PARTICIPANT',
  'PROTAGONIST',
  'ANTAGONIST',
  'LEADER',
  'WITNESS',
  'ACCUSER',
  'ACCUSED',
  'VICTIM',
  'OBSERVER',
  'KEEPER',
  'COMMANDER',
  'DECKHAND',
  'RECRUITER',
];

export const WorldTimeline: React.FC = () => {
  const navigate = useNavigate();
  const {
    activeWorldId,
    setActiveManuscript,
    setActiveChapter,
    manuscripts,
    fetchManuscriptsForWorld,
  } = useWorldStore();

  const [events, setEvents] = useState<EventResponse[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(() => window.innerWidth >= 1024);
  const [collapsedChapters, setCollapsedChapters] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Chapter filter state: null = All, 'unassigned' = No Chapter, or specific chapter_id
  const [selectedChapterFilter, setSelectedChapterFilter] = useState<string | null>(null);

  // Per-character timeline filter state
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(null);

  // Keyword text search
  const [searchQuery, setSearchQuery] = useState('');

  // Available world entities for tagging participants
  const [availableEntities, setAvailableEntities] = useState<any[]>([]);

  // New event modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newDescription, setNewDescription] = useState('');
  const [newEventType, setNewEventType] = useState('EVENT');
  const [newChapterId, setNewChapterId] = useState<string>('');
  const [creating, setCreating] = useState(false);

  // Edit event modal state
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editDescription, setEditDescription] = useState('');
  const [editEventType, setEditEventType] = useState('EVENT');
  const [editChapterId, setEditChapterId] = useState<string>('');
  const [updating, setUpdating] = useState(false);

  // Modal participant picker state (shared for Add and Edit)
  const [modalParticipants, setModalParticipants] = useState<ModalParticipantItem[]>([]);
  const [modalSelectedEntityId, setModalSelectedEntityId] = useState('');
  const [modalRoleInput, setModalRoleInput] = useState('PARTICIPANT');
  const chapterRefs = useRef<Record<string, HTMLElement | null>>({});
  const timelineRequestRef = useRef(0);
  const entityRequestRef = useRef(0);

  const chapters = manuscripts.flatMap((m) => m.chapters || []).sort((a, b) => a.number - b.number);
  const chapterLocations = useMemo(() => {
    const locations = new Map<string, { manuscriptId: string; chapter: (typeof chapters)[number] }>();
    manuscripts.forEach((manuscript) => {
      manuscript.chapters?.forEach((chapter) => {
        locations.set(chapter.id, { manuscriptId: manuscript.id, chapter });
      });
    });
    return locations;
  }, [manuscripts]);

  const loadTimeline = async (worldId: string, requestId = ++timelineRequestRef.current) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getTimeline(worldId);
      if (requestId !== timelineRequestRef.current) return;
      setEvents(data.events || []);
      if (data.events?.length > 0 && !selectedEventId) {
        setSelectedEventId(data.events[0].id);
      }
    } catch (err: any) {
      if (requestId !== timelineRequestRef.current) return;
      console.error('Failed to load timeline:', err);
      setError(err?.message || 'Failed to load timeline');
    } finally {
      if (requestId === timelineRequestRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    const timelineRequestId = ++timelineRequestRef.current;
    const entityRequestId = ++entityRequestRef.current;
    if (activeWorldId) {
      loadTimeline(activeWorldId, timelineRequestId);
      fetchManuscriptsForWorld(activeWorldId);
      apiFetch<any[]>(`/worlds/${activeWorldId}/entities`)
        .then((data) => {
          if (entityRequestId === entityRequestRef.current) setAvailableEntities(data || []);
        })
        .catch((err) => { if (entityRequestId === entityRequestRef.current) setError(err.message || 'Could not load participants.'); });
    }
  }, [activeWorldId, fetchManuscriptsForWorld]);

  // Derive per-character narrative statistics from all timeline events
  const timelineCharacters = useMemo(() => {
    const map = new Map<
      string,
      {
        id: string;
        name: string;
        count: number;
        roles: Set<string>;
        chapters: Set<number>;
        coStarMap: Map<string, string>;
      }
    >();

    events.forEach((ev) => {
      ev.participants.forEach((p) => {
        let entry = map.get(p.entity_id);
        if (!entry) {
          entry = {
            id: p.entity_id,
            name: p.entity_name || 'Unknown Entity',
            count: 0,
            roles: new Set<string>(),
            chapters: new Set<number>(),
            coStarMap: new Map<string, string>(),
          };
          map.set(p.entity_id, entry);
        }
        entry.count += 1;
        if (p.role) entry.roles.add(p.role.toLowerCase());
        if (ev.chapter_number !== null && ev.chapter_number !== undefined) {
          entry.chapters.add(ev.chapter_number);
        }
        // Co-stars in this event
        ev.participants.forEach((other) => {
          if (other.entity_id !== p.entity_id) {
            entry!.coStarMap.set(other.entity_id, other.entity_name || other.entity_id);
          }
        });
      });
    });

    return Array.from(map.values())
      .map((c) => ({
        id: c.id,
        name: c.name,
        count: c.count,
        roles: Array.from(c.roles),
        chapters: Array.from(c.chapters).sort((a, b) => a - b),
        coStars: Array.from(c.coStarMap.values()),
      }))
      .sort((a, b) => b.count - a.count);
  }, [events]);

  const selectedCharacter = timelineCharacters.find((c) => c.id === selectedCharacterId) || null;

  const selectedEvent = events.find((e) => e.id === selectedEventId) || events[0];

  const handleSelectEvent = (id: string) => {
    setSelectedEventId(id);
    setIsDetailsOpen(true);
  };

  const navigateToChapter = (chapterId: string) => {
    const location = chapterLocations.get(chapterId);
    if (!location) return;
    setActiveManuscript(location.manuscriptId);
    setActiveChapter(chapterId);
    navigate(`/worlds/${activeWorldId}/manuscripts/${location.manuscriptId}`);
  };

  const handleMoveUp = async (e: React.MouseEvent, event: EventResponse) => {
    e.stopPropagation();
    if (!activeWorldId) return;

    const chapterEvents = events.filter((ev) => ev.chapter_id === event.chapter_id);
    const idx = chapterEvents.findIndex((ev) => ev.id === event.id);
    if (idx <= 0) return;

    const newOrder = [...chapterEvents];
    const temp = newOrder[idx - 1];
    newOrder[idx - 1] = newOrder[idx];
    newOrder[idx] = temp;
    const eventIds = newOrder.map((ev) => ev.id);

    try {
      await reorderEvents(activeWorldId, {
        chapter_id: event.chapter_id,
        event_ids: eventIds,
      });
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to reorder events:', err);
      setError(err?.message || 'Failed to reorder events');
    }
  };

  const handleMoveDown = async (e: React.MouseEvent, event: EventResponse) => {
    e.stopPropagation();
    if (!activeWorldId) return;

    const chapterEvents = events.filter((ev) => ev.chapter_id === event.chapter_id);
    const idx = chapterEvents.findIndex((ev) => ev.id === event.id);
    if (idx < 0 || idx >= chapterEvents.length - 1) return;

    const newOrder = [...chapterEvents];
    const temp = newOrder[idx + 1];
    newOrder[idx + 1] = newOrder[idx];
    newOrder[idx] = temp;
    const eventIds = newOrder.map((ev) => ev.id);

    try {
      await reorderEvents(activeWorldId, {
        chapter_id: event.chapter_id,
        event_ids: eventIds,
      });
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to reorder events:', err);
      setError(err?.message || 'Failed to reorder events');
    }
  };

  const handleDeleteEvent = async (e: React.MouseEvent, eventId: string) => {
    e.stopPropagation();
    if (!activeWorldId) return;
    if (!confirm('Are you sure you want to delete this event?')) return;

    try {
      await deleteEvent(activeWorldId, eventId);
      if (selectedEventId === eventId) {
        setSelectedEventId(null);
      }
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to delete event:', err);
      setError(err?.message || 'Failed to delete event');
    }
  };

  // Participant picker modal helpers
  const handleAddParticipantToModal = () => {
    if (!modalSelectedEntityId) return;
    if (modalParticipants.some((p) => p.entity_id === modalSelectedEntityId)) return;
    const ent = availableEntities.find((e) => e.id === modalSelectedEntityId);
    setModalParticipants((prev) => [
      ...prev,
      {
        entity_id: modalSelectedEntityId,
        role: modalRoleInput.trim() || 'PARTICIPANT',
        entity_name: ent ? ent.canonical_name : undefined,
      },
    ]);
    setModalSelectedEntityId('');
    setModalRoleInput('PARTICIPANT');
  };

  const handleRemoveParticipantFromModal = (entityId: string) => {
    setModalParticipants((prev) => prev.filter((p) => p.entity_id !== entityId));
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorldId || !newDescription.trim()) return;

    setCreating(true);
    setError(null);
    try {
      const participantsPayload: EventParticipantInput[] = modalParticipants.map((p) => ({
        entity_id: p.entity_id,
        role: p.role,
      }));

      await createEvent(activeWorldId, {
        description: newDescription.trim(),
        event_type: newEventType.trim().toUpperCase() || 'EVENT',
        chapter_id: newChapterId || null,
        participants: participantsPayload,
      });

      setNewDescription('');
      setNewEventType('EVENT');
      setNewChapterId('');
      setModalParticipants([]);
      setIsModalOpen(false);
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to create event:', err);
      setError(err?.message || 'Failed to create event');
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorldId || !selectedEventId || !editDescription.trim()) return;

    setUpdating(true);
    setError(null);
    try {
      const participantsPayload: EventParticipantInput[] = modalParticipants.map((p) => ({
        entity_id: p.entity_id,
        role: p.role,
      }));

      await updateEvent(activeWorldId, selectedEventId, {
        description: editDescription.trim(),
        event_type: editEventType.trim().toUpperCase() || 'EVENT',
        chapter_id: editChapterId || null,
        participants: participantsPayload,
      });

      setIsEditModalOpen(false);
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to update event:', err);
      setError(err?.message || 'Failed to update event');
    } finally {
      setUpdating(false);
    }
  };

  // Multi-condition filtering: Chapter + Character + Keyword Search
  const displayedEvents = events.filter((e) => {
    // Chapter filter
    if (selectedChapterFilter !== null) {
      if (selectedChapterFilter === 'unassigned') {
        if (e.chapter_id) return false;
      } else {
        if (e.chapter_id !== selectedChapterFilter) return false;
      }
    }

    // Character filter
    if (selectedCharacterId !== null) {
      const hasChar = e.participants.some((p) => p.entity_id === selectedCharacterId);
      if (!hasChar) return false;
    }

    // Keyword search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchDesc = e.description.toLowerCase().includes(q);
      const matchType = e.event_type.toLowerCase().includes(q);
      const matchPart = e.participants.some(
        (p) =>
          (p.entity_name && p.entity_name.toLowerCase().includes(q)) ||
          p.role.toLowerCase().includes(q)
      );
      if (!matchDesc && !matchType && !matchPart) return false;
    }

    return true;
  });

  const eventsByChapter = useMemo(() => {
    const groups = new Map<string, EventResponse[]>();
    events.forEach((event) => {
      const key = event.chapter_id || 'unassigned';
      const group = groups.get(key) || [];
      group.push(event);
      groups.set(key, group);
    });
    return groups;
  }, [events]);

  const chapterGroups = useMemo(() => {
    const groups = new Map<string, EventResponse[]>();
    displayedEvents.forEach((event) => {
      const key = event.chapter_id || 'unassigned';
      const group = groups.get(key) || [];
      group.push(event);
      groups.set(key, group);
    });
    return Array.from(groups.entries()).map(([key, group]) => {
      const chapter = chapterLocations.get(key)?.chapter;
      return {
        key,
        events: group,
        number: chapter?.number ?? null,
        title: chapter?.title || 'Loose Fragments',
      };
    });
  }, [chapterLocations, displayedEvents]);

  const scrollToChapter = (key: string) => {
    chapterRefs.current[key]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <AppShell>
      {/* Background radial effects */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-surface-container-high/20 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <header className="absolute inset-x-0 top-0 h-14 bg-surface-dim/85 backdrop-blur-md border-b border-starlight-white/5 z-40 flex items-center justify-between px-6 pointer-events-none">
        <div className="flex items-center gap-4">
          <span className="font-headline-md text-xl text-primary whitespace-nowrap">World Timeline</span>
          <span className="text-on-surface-variant/50">/</span>
          <span className="hidden sm:inline text-xs uppercase tracking-widest text-on-surface-variant/60">Chronicle sequence</span>
        </div>
        <span className="font-label-sm uppercase tracking-widest text-on-surface-variant/60">{displayedEvents.length} events</span>
      </header>

      <main className="flex-1 h-full min-w-0 pt-14 flex relative overflow-hidden select-none">
        {/* Timeline Canvas (Scrollable) */}
        <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden relative scroll-smooth px-5 md:px-8 py-8">
          <div className="max-w-6xl mx-auto relative min-h-full pb-32 pt-4 flex gap-6">
            {/* Archive index */}
            <aside className="hidden lg:block w-44 shrink-0 sticky top-4 self-start pt-2">
              <div className="border-r border-starlight-white/10 pr-4">
                <div className="flex items-center justify-between mb-4">
                  <span className="font-label-sm text-[10px] uppercase tracking-widest text-primary">Archive index</span>
                  <span className="text-[10px] text-on-surface-variant/50">{chapterGroups.length}</span>
                </div>
                <nav className="space-y-1" aria-label="Timeline chapters">
                  <button
                    onClick={() => scrollToChapter('all')}
                    className="w-full text-left rounded-lg px-3 py-2 text-xs text-on-surface-variant hover:bg-white/5 hover:text-primary transition-colors"
                  >
                    <span className="block font-semibold">Complete archive</span>
                    <span className="text-[10px] text-on-surface-variant/50">{events.length} events</span>
                  </button>
                  {chapters.map((chapter) => {
                    const count = eventsByChapter.get(chapter.id)?.length || 0;
                    const visible = chapterGroups.some((group) => group.key === chapter.id);
                    return (
                      <button
                        key={chapter.id}
                        onClick={() => scrollToChapter(chapter.id)}
                        className={`w-full text-left rounded-lg px-3 py-2 transition-colors ${
                          visible ? 'text-on-surface-variant hover:bg-white/5 hover:text-primary' : 'text-on-surface-variant/35'
                        }`}
                      >
                        <span className="block font-label-sm text-[10px] uppercase tracking-wider">Ch. {chapter.number}</span>
                        <span className="block truncate text-xs mt-0.5">{chapter.title}</span>
                        <span className="block text-[10px] text-on-surface-variant/50 mt-0.5">{count} {count === 1 ? 'event' : 'events'}</span>
                      </button>
                    );
                  })}
                  {events.some((event) => !event.chapter_id) && (
                    <button
                      onClick={() => scrollToChapter('unassigned')}
                      className="w-full text-left rounded-lg px-3 py-2 text-on-surface-variant hover:bg-white/5 hover:text-primary transition-colors"
                    >
                      <span className="block font-label-sm text-[10px] uppercase tracking-wider">Fragments</span>
                      <span className="block text-[10px] text-on-surface-variant/50 mt-0.5">{eventsByChapter.get('unassigned')?.length || 0} unassigned</span>
                    </button>
                  )}
                </nav>
              </div>
            </aside>

            <div className="min-w-0 flex-1">
            {/* Page Header */}
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 mb-1.5">
                  <span className="material-symbols-outlined text-copper-glow text-2xl font-light">timeline</span>
                  <h1 className="font-display-lg text-display-lg text-starlight-white">The Deep Tapestry of Time</h1>
                </div>
                <p className="font-body-lg text-body-lg text-on-surface-variant/80 leading-relaxed max-w-xl text-sm">
                  Follow world milestones and character journeys through the manuscript. Ordered by chapter and narrative sequence.
                </p>
              </div>

              <div className="flex items-center gap-3">
                {/* Search Bar */}
                <div className="relative group">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-base group-focus-within:text-primary transition-colors font-light">
                    search
                  </span>
                  <input
                    type="text"
                    placeholder="Search events, characters..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    aria-label="Search timeline" className="w-full sm:w-52 bg-surface-container-high/60 border border-outline-variant/30 rounded-lg pl-9 pr-3 py-1.5 text-xs text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary/50 transition-all"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant/60 hover:text-starlight-white text-xs"
                    >
                      <span className="material-symbols-outlined text-sm">close</span>
                    </button>
                  )}
                </div>

                <button
                  onClick={() => {
                    setNewDescription('');
                    setNewEventType('EVENT');
                    setNewChapterId(
                      selectedChapterFilter && selectedChapterFilter !== 'unassigned'
                        ? selectedChapterFilter
                        : ''
                    );
                    setModalParticipants(
                      selectedCharacterId
                        ? [
                            {
                              entity_id: selectedCharacterId,
                              role: 'PARTICIPANT',
                              entity_name: selectedCharacter?.name,
                            },
                          ]
                        : []
                    );
                    setIsModalOpen(true);
                  }}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/40 rounded-lg text-xs font-semibold transition-colors shadow-sm whitespace-nowrap"
                >
                  <span className="material-symbols-outlined text-base">add</span>
                  Add Event
                </button>
              </div>
            </header>

            {error && (
              <div className="mb-6 p-4 rounded-lg bg-error/10 border border-error/30 text-error text-sm flex items-center justify-between">
                <span>{error}</span>
                <button onClick={() => setError(null)} className="text-xs hover:underline">
                  Dismiss
                </button>
              </div>
            )}

            {/* Filter Section: Chapters & Characters */}
            <div className="mb-8 space-y-3 sticky top-0 z-30 -mx-2 px-2 py-2 bg-void-black/85 backdrop-blur-md">
              {/* Chapter Filter Pill Bar */}
              {chapters.length > 0 && (
                <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-hide">
                  <span className="text-[10px] uppercase tracking-wider text-on-surface-variant/70 font-semibold shrink-0 mr-1">
                    Chapters:
                  </span>
                  <button
                    onClick={() => setSelectedChapterFilter(null)}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors border whitespace-nowrap ${
                      selectedChapterFilter === null
                        ? 'bg-primary text-surface-container font-semibold border-primary shadow-sm'
                        : 'bg-surface-container-high/60 text-on-surface-variant border-starlight-white/10 hover:border-starlight-white/20 hover:text-starlight-white'
                    }`}
                  >
                    All Chapters ({events.length})
                  </button>
                  {chapters.map((ch) => {
                    const count = eventsByChapter.get(ch.id)?.length || 0;
                    return (
                      <button
                        key={ch.id}
                        onClick={() => setSelectedChapterFilter(ch.id)}
                        className={`px-3 py-1 rounded-full text-xs font-medium transition-colors border whitespace-nowrap ${
                          selectedChapterFilter === ch.id
                            ? 'bg-primary text-surface-container font-semibold border-primary shadow-sm'
                            : 'bg-surface-container-high/60 text-on-surface-variant border-starlight-white/10 hover:border-starlight-white/20 hover:text-starlight-white'
                        }`}
                      >
                        Ch. {ch.number}: {ch.title} ({count})
                      </button>
                    );
                  })}
                  {events.some((e) => !e.chapter_id) && (
                    <button
                      onClick={() => setSelectedChapterFilter('unassigned')}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors border whitespace-nowrap ${
                        selectedChapterFilter === 'unassigned'
                          ? 'bg-primary text-surface-container font-semibold border-primary shadow-sm'
                          : 'bg-surface-container-high/60 text-on-surface-variant border-starlight-white/10 hover:border-starlight-white/20 hover:text-starlight-white'
                      }`}
                    >
                      No Chapter ({eventsByChapter.get('unassigned')?.length || 0})
                    </button>
                  )}
                </div>
              )}

              {/* Per-Character Arc Filter Pill Bar */}
              {timelineCharacters.length > 0 && (
                <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-hide">
                  <span className="text-[10px] uppercase tracking-wider text-copper-glow font-semibold shrink-0 mr-1 flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs">person</span>
                    Characters:
                  </span>
                  <button
                    onClick={() => setSelectedCharacterId(null)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors border whitespace-nowrap ${
                      selectedCharacterId === null
                        ? 'bg-copper-glow text-surface-container font-semibold border-copper-glow shadow-sm'
                        : 'bg-surface-container-high/60 text-on-surface-variant border-starlight-white/10 hover:border-copper-glow/40 hover:text-starlight-white'
                    }`}
                  >
                    All Characters
                  </button>
                  {timelineCharacters.map((char) => (
                    <button
                      key={char.id}
                      onClick={() =>
                        setSelectedCharacterId(selectedCharacterId === char.id ? null : char.id)
                      }
                      className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all border whitespace-nowrap flex items-center gap-1.5 ${
                        selectedCharacterId === char.id
                          ? 'bg-copper-glow text-surface-container font-bold border-copper-glow shadow-[0_0_10px_rgba(230,162,126,0.3)]'
                          : 'bg-surface-container-high/60 text-on-surface-variant border-starlight-white/10 hover:border-copper-glow/40 hover:text-starlight-white'
                      }`}
                    >
                      <span>{char.name}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                          selectedCharacterId === char.id
                            ? 'bg-black/20 text-surface-container'
                            : 'bg-white/10 text-on-surface-variant/70'
                        }`}
                      >
                        {char.count}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {(selectedChapterFilter !== null || selectedCharacterId !== null || searchQuery.trim()) && (
              <div className="-mt-4 mb-6 flex items-center justify-between gap-3 text-xs text-on-surface-variant/70">
                <span>
                  Showing {displayedEvents.length} of {events.length} events
                  {selectedCharacter ? ` · ${selectedCharacter.name}'s arc` : ''}
                </span>
                <button
                  onClick={() => { setSelectedChapterFilter(null); setSelectedCharacterId(null); setSearchQuery(''); }}
                  className="text-primary hover:underline focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary"
                >
                  Reset filters
                </button>
              </div>
            )}

            {/* Character Arc Spotlight Banner */}
            {selectedCharacter && (
              <div className="mb-10 p-4 rounded-xl bg-gradient-to-r from-copper-glow/15 via-surface-container/90 to-surface-container/60 border border-copper-glow/30 shadow-lg">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3.5">
                    <div className="w-10 h-10 rounded-full bg-copper-glow/20 border border-copper-glow/50 text-copper-glow flex items-center justify-center font-bold text-base shadow-[0_0_12px_rgba(230,162,126,0.25)]">
                      {selectedCharacter.name.charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] uppercase tracking-wider text-copper-glow font-semibold">
                          Character Narrative Arc
                        </span>
                        <span className="text-[9px] bg-copper-glow/15 text-copper-glow border border-copper-glow/30 px-1.5 py-0.2 rounded font-mono font-bold">
                          {selectedCharacter.count}{' '}
                          {selectedCharacter.count === 1 ? 'appearance' : 'appearances'}
                        </span>
                      </div>
                      <h2 className="text-base font-bold text-starlight-white mt-0.5">
                        {selectedCharacter.name}
                      </h2>
                    </div>
                  </div>

                  <button
                    onClick={() => setSelectedCharacterId(null)}
                    className="text-xs text-on-surface-variant hover:text-starlight-white bg-white/5 hover:bg-white/10 px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 border border-white/5"
                  >
                    <span className="material-symbols-outlined text-xs">close</span>
                    Clear Character Filter
                  </button>
                </div>

                <div className="mt-3.5 grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-3 border-t border-starlight-white/10 text-xs">
                  <div>
                    <span className="text-[10px] text-on-surface-variant/60 uppercase block">
                      Chapter Span
                    </span>
                    <span className="text-starlight-white font-medium">
                      {selectedCharacter.chapters.length > 0
                        ? selectedCharacter.chapters.map((n) => `Ch. ${n}`).join(', ')
                        : 'Unassigned'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-on-surface-variant/60 uppercase block">
                      Narrative Roles
                    </span>
                    <span className="text-starlight-white font-medium capitalize">
                      {selectedCharacter.roles.length > 0
                        ? selectedCharacter.roles.join(', ')
                        : 'Participant'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-on-surface-variant/60 uppercase block">
                      Co-Stars / Interacted With
                    </span>
                    <span className="text-starlight-white font-medium truncate block">
                      {selectedCharacter.coStars.length > 0
                        ? selectedCharacter.coStars.join(', ')
                        : 'Solo scenes'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Chapter folios */}
            {displayedEvents.length === 0 && !loading ? (
              <div className="text-center py-24 text-on-surface-variant/60">
                <span className="material-symbols-outlined text-4xl mb-2 opacity-50">menu_book</span>
                <p>{events.length === 0 ? 'This archive has no events yet.' : 'No events match the current lens.'}</p>
                {(selectedChapterFilter || selectedCharacterId || searchQuery) && (
                  <button
                    onClick={() => {
                      setSelectedChapterFilter(null);
                      setSelectedCharacterId(null);
                      setSearchQuery('');
                    }}
                    className="mt-3 text-xs text-primary hover:underline"
                  >
                    Reset filters
                  </button>
                )}
              </div>
            ) : (
              <div ref={(node) => { chapterRefs.current.all = node; }} className="space-y-8">
                {chapterGroups.map((group) => (
                  <section
                    key={group.key}
                    ref={(node) => { chapterRefs.current[group.key] = node; }}
                    className="scroll-mt-20"
                    aria-labelledby={`chapter-${group.key}`}
                  >
                    <div className="flex items-end gap-4 mb-4 border-b border-starlight-white/10 pb-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/10 font-label-sm text-xs text-primary">
                          {group.number ?? '·'}
                        </span>
                        <div className="min-w-0">
                          <span className="block font-label-sm text-[10px] uppercase tracking-widest text-primary/70">
                            {group.number !== null ? `Chapter ${group.number}` : 'Loose Fragments'}
                          </span>
                          <h2 id={`chapter-${group.key}`} className="font-headline-md text-headline-md text-starlight-white truncate">
                            {group.title}
                          </h2>
                        </div>
                      </div>
                      <div className="ml-auto flex shrink-0 items-center gap-2">
                        <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant/50">
                          {group.events.length} {group.events.length === 1 ? 'entry' : 'entries'}
                        </span>
                        <button
                          onClick={() => setCollapsedChapters((current) => ({ ...current, [group.key]: !current[group.key] }))}
                          aria-expanded={!collapsedChapters[group.key]}
                          aria-label={`${collapsedChapters[group.key] ? 'Expand' : 'Collapse'} ${group.title}`}
                          className="rounded p-1 text-on-surface-variant/60 hover:bg-white/5 hover:text-primary focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary"
                        >
                          <span className="material-symbols-outlined text-base">
                            {collapsedChapters[group.key] ? 'expand_more' : 'expand_less'}
                          </span>
                        </button>
                      </div>
                    </div>

                    {!collapsedChapters[group.key] && <div className="relative space-y-3 pl-4 before:absolute before:bottom-3 before:left-[7px] before:top-3 before:w-px before:bg-gradient-to-b before:from-primary/40 before:via-outline-variant/30 before:to-transparent">
                      {group.events.map((event) => {
                        const isActive = event.id === selectedEventId;
                        const targetParticipant = selectedCharacterId
                          ? event.participants.find((p) => p.entity_id === selectedCharacterId)
                          : null;
                        const chapterEvents = eventsByChapter.get(event.chapter_id || 'unassigned') || [];
                        const idxInChapter = chapterEvents.findIndex((candidate) => candidate.id === event.id);
                        const canMoveUp = idxInChapter > 0;
                        const canMoveDown = idxInChapter >= 0 && idxInChapter < chapterEvents.length - 1;

                        return (
                          <article
                            key={event.id}
                            onClick={() => handleSelectEvent(event.id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                handleSelectEvent(event.id);
                              }
                            }}
                            tabIndex={0}
                            className={`group relative cursor-pointer rounded-xl border p-4 pl-5 transition-all focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary ${
                              isActive
                                ? 'border-primary/50 bg-primary/[0.08] shadow-[0_0_28px_rgba(254,182,141,0.08)]'
                                : targetParticipant
                                ? 'border-copper-glow/35 bg-copper-glow/[0.05] hover:border-copper-glow/60'
                                : 'border-starlight-white/[0.08] bg-surface-container-low/55 hover:border-starlight-white/20 hover:bg-surface-container/70'
                            }`}
                          >
                            <span className={`absolute -left-[21px] top-6 h-3.5 w-3.5 rounded-full border-2 border-void-black ${
                              isActive ? 'bg-primary shadow-[0_0_14px_rgba(254,182,141,0.8)]' : targetParticipant ? 'bg-copper-glow' : 'bg-outline-variant'
                            }`} />
                            <div className="flex items-start gap-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                  <span className="font-label-sm text-[10px] uppercase tracking-widest text-primary/75">
                                    {event.sequence_index !== null ? `Sequence ${event.sequence_index}` : 'Unsequenced'}
                                  </span>
                                  {event.confidence < 0.7 && (
                                    <span className="rounded-full border border-outline-variant/40 px-2 py-0.5 font-label-sm text-[9px] uppercase tracking-wider text-on-surface-variant/60">
                                      Low confidence
                                    </span>
                                  )}
                                </div>
                                <h3 className="mt-1 font-headline-md text-headline-md text-starlight-white group-hover:text-primary">
                                  {event.event_type.replace(/_/g, ' ')}
                                </h3>
                              </div>
                              <div className="flex shrink-0 items-center gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-within:opacity-100" onClick={(e) => e.stopPropagation()}>
                                <button disabled={!canMoveUp} onClick={(e) => handleMoveUp(e, event)} className="rounded p-1 text-on-surface-variant hover:bg-white/10 hover:text-primary disabled:opacity-20" title="Move earlier in chapter" aria-label="Move earlier in chapter">
                                  <span className="material-symbols-outlined text-sm">arrow_upward</span>
                                </button>
                                <button disabled={!canMoveDown} onClick={(e) => handleMoveDown(e, event)} className="rounded p-1 text-on-surface-variant hover:bg-white/10 hover:text-primary disabled:opacity-20" title="Move later in chapter" aria-label="Move later in chapter">
                                  <span className="material-symbols-outlined text-sm">arrow_downward</span>
                                </button>
                                <button onClick={(e) => handleDeleteEvent(e, event.id)} className="rounded p-1 text-on-surface-variant hover:bg-white/10 hover:text-error" title="Delete event" aria-label="Delete event">
                                  <span className="material-symbols-outlined text-sm">delete</span>
                                </button>
                              </div>
                            </div>

                            <p className="mt-2 max-w-3xl font-body-md text-sm leading-relaxed text-on-surface-variant/80">
                              {event.description}
                            </p>

                            {event.participants.length > 0 && (
                              <div className="mt-3 flex flex-wrap gap-1.5">
                                {event.participants.map((participant, participantIndex) => {
                                  const isTarget = selectedCharacterId === participant.entity_id;
                                  return (
                                    <button
                                      key={`${participant.entity_id}-${participantIndex}`}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setSelectedCharacterId(isTarget ? null : participant.entity_id);
                                      }}
                                      className={`rounded-full border px-2.5 py-1 font-label-sm text-[10px] transition-colors ${
                                        isTarget
                                          ? 'border-copper-glow/70 bg-copper-glow/20 text-copper-glow'
                                          : 'border-starlight-white/10 bg-surface-container/70 text-on-surface-variant hover:border-copper-glow/40 hover:text-starlight-white'
                                      }`}
                                      title={`Show ${participant.entity_name || participant.entity_id}'s arc`}
                                    >
                                      {participant.entity_name || participant.entity_id}
                                      <span className="ml-1 opacity-60">· {participant.role.toLowerCase()}</span>
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </article>
                        );
                      })}
                    </div>}
                  </section>
                ))}
              </div>
            )}
            </div>
          </div>
        </div>

        {/* Dynamic World State Changes wing inside the main stage (Right side wing) */}
        {isDetailsOpen ? (
        <aside className="timeline-details flex h-full flex-col z-20">
          {/* Header */}
          <div className="p-6 border-b border-starlight-white/5 bg-gradient-to-b from-surface-container-highest/20 to-transparent pt-14">
            <span className="font-label-sm text-[10px] text-primary/70 block mb-1 tracking-wider uppercase font-semibold">
              Event Chronicle
            </span>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-headline-md text-headline-md text-starlight-white leading-tight text-lg">
                  {selectedEvent ? selectedEvent.event_type.replace(/_/g, ' ') : 'No Selection'}
                </h2>
                <p className="font-label-sm text-[10px] text-on-surface-variant/50 uppercase tracking-widest mt-1">
                  {selectedEvent?.chapter_number !== null && selectedEvent?.chapter_number !== undefined
                    ? `Chapter ${selectedEvent.chapter_number}`
                    : 'No Chapter'}
                  {selectedEvent?.sequence_index !== null && selectedEvent?.sequence_index !== undefined
                    ? ` • Sequence #${selectedEvent.sequence_index}`
                    : ''}
                </p>
              </div>
              <button
                onClick={() => setIsDetailsOpen(false)}
                aria-label="Close event details"
                className="w-8 h-8 rounded-lg text-on-surface-variant hover:text-primary hover:bg-white/5 flex items-center justify-center focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>
          </div>

          {/* Details Scroll */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {selectedEvent ? (
              <>
                {/* Description */}
                <div className="space-y-2">
                  <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider border-b border-starlight-white/5 pb-2">
                    Description
                  </h3>
                  <p className="font-body-md text-xs text-on-surface leading-relaxed">
                    {selectedEvent.description}
                  </p>
                </div>

                {/* Participants */}
                <div className="space-y-3">
                  <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider flex items-center justify-between border-b border-starlight-white/5 pb-2">
                    <span className="flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] font-light">group</span>
                      Participants ({selectedEvent.participants.length})
                    </span>
                    <span className="text-[9px] text-on-surface-variant/50 lowercase">
                      click name to isolate arc
                    </span>
                  </h3>

                  {selectedEvent.participants.length === 0 ? (
                    <p className="text-xs text-on-surface-variant/40 italic">No participants tagged.</p>
                  ) : (
                    <div className="space-y-2">
                      {selectedEvent.participants.map((p, idx) => {
                        const isTarget = selectedCharacterId === p.entity_id;
                        return (
                          <div
                            key={idx}
                            onClick={() =>
                              setSelectedCharacterId(isTarget ? null : p.entity_id)
                            }
                            className={`p-3 rounded-lg border flex items-center justify-between text-xs cursor-pointer transition-all ${
                              isTarget
                                ? 'bg-copper-glow/15 border-copper-glow shadow-sm'
                                : 'bg-surface-container/40 border-starlight-white/5 hover:border-copper-glow/30 hover:bg-surface-container/60'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <span
                                className={`material-symbols-outlined text-sm ${
                                  isTarget ? 'text-copper-glow' : 'text-primary'
                                }`}
                              >
                                person
                              </span>
                              <span
                                className={`font-medium ${
                                  isTarget ? 'text-copper-glow font-bold' : 'text-starlight-white'
                                }`}
                              >
                                {p.entity_name || p.entity_id}
                              </span>
                            </div>
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded uppercase ${
                                isTarget
                                  ? 'bg-copper-glow/20 text-copper-glow font-bold'
                                  : 'bg-primary/10 text-primary'
                              }`}
                            >
                              {p.role}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Source Manuscript / Chapter */}
                {selectedEvent.chapter_id && (
                  <div className="space-y-3">
                    <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider border-b border-starlight-white/5 pb-2">
                      Linked Chapter
                    </h3>
                    <button
                      onClick={() => navigateToChapter(selectedEvent.chapter_id!)}
                      className="w-full text-left p-3 rounded-lg border border-starlight-white/5 hover:border-primary/30 hover:bg-white/5 transition-all flex items-center gap-3 group"
                    >
                      <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors text-lg font-light">
                        menu_book
                      </span>
                      <div className="min-w-0">
                        <span className="block font-body-md text-xs text-starlight-white group-hover:text-primary transition-colors truncate">
                          Chapter {selectedEvent.chapter_number ?? ''}
                        </span>
                        <span className="block font-label-sm text-[10px] text-on-surface-variant/50 mt-0.5 truncate">
                          ID: {selectedEvent.chapter_id}
                        </span>
                      </div>
                    </button>
                  </div>
                )}

                {/* Actions zone */}
                <div className="pt-4 border-t border-starlight-white/5 space-y-2">
                  <button
                    onClick={() => {
                      setEditDescription(selectedEvent.description);
                      setEditEventType(selectedEvent.event_type);
                      setEditChapterId(selectedEvent.chapter_id || '');
                      setModalParticipants(
                        selectedEvent.participants.map((p) => ({
                          entity_id: p.entity_id,
                          role: p.role,
                          entity_name: p.entity_name || undefined,
                        }))
                      );
                      setIsEditModalOpen(true);
                    }}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 text-xs font-semibold transition-colors"
                  >
                    <span className="material-symbols-outlined text-sm">edit</span>
                    Edit Event (§15.3)
                  </button>

                  <button
                    onClick={(e) => handleDeleteEvent(e, selectedEvent.id)}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-error/10 hover:bg-error/20 text-error border border-error/30 text-xs font-medium transition-colors"
                  >
                    <span className="material-symbols-outlined text-sm">delete</span>
                    Delete Event (§15.4)
                  </button>
                </div>
              </>
            ) : (
              <p className="text-xs text-on-surface-variant/40 italic">Select an event to view details.</p>
            )}
          </div>
        </aside>
        ) : (
          <button
            onClick={() => setIsDetailsOpen(true)}
            className="absolute right-4 top-4 z-30 px-3 py-2 rounded-lg bg-surface-container-high/90 border border-starlight-white/10 text-xs text-primary hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary"
          >
            Open event details
          </button>
        )}
      </main>

      {isModalOpen && <Dialog title="Add Chronicle Event" onClose={() => { if (!creating) setIsModalOpen(false); }}>
            <form onSubmit={handleCreateEvent} className="space-y-4">
              {error && <p role="alert" className="text-sm text-error">{error}</p>}
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Description *
                </label>
                <textarea
                  rows={3}
                  required
                  aria-label="Event description" value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe what occurs at this milestone..."
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                    Event Type
                  </label>
                  <input
                    type="text"
                    aria-label="Event type" value={newEventType}
                    onChange={(e) => setNewEventType(e.target.value)}
                    placeholder="e.g. BATTLE, ARRIVAL, DISCOVERY"
                    className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                    Chapter
                  </label>
                  <select
                    aria-label="Event chapter" value={newChapterId}
                    onChange={(e) => setNewChapterId(e.target.value)}
                    className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  >
                    <option value="">No chapter (unassigned)</option>
                    {chapters.map((ch) => (
                      <option key={ch.id} value={ch.id}>
                        Chapter {ch.number}: {ch.title}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Participant Management Section */}
              <div className="space-y-2 pt-2 border-t border-starlight-white/10">
                <label className="block text-xs font-medium text-copper-glow uppercase tracking-wider flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm">person_add</span>
                    Tagged Participants ({modalParticipants.length})
                  </span>
                </label>

                {/* Current Tagged Participants Pills */}
                {modalParticipants.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 p-2 rounded-lg bg-surface-container-high/40 border border-starlight-white/5">
                    {modalParticipants.map((p) => {
                      const ent = availableEntities.find((e) => e.id === p.entity_id);
                      return (
                        <span
                          key={p.entity_id}
                          className="px-2.5 py-1 rounded-md bg-copper-glow/15 border border-copper-glow/30 text-xs text-starlight-white flex items-center gap-1.5"
                        >
                          <span className="font-medium">{p.entity_name || ent?.canonical_name || p.entity_id}</span>
                          <span className="text-[10px] text-copper-glow uppercase">({p.role})</span>
                          <button
                            type="button"
                            onClick={() => handleRemoveParticipantFromModal(p.entity_id)}
                            className="hover:text-error ml-0.5"
                          >
                            <span className="material-symbols-outlined text-xs">close</span>
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Add Participant Row */}
                <div className="flex items-center gap-2">
                  <select
                    aria-label="Event participant" value={modalSelectedEntityId}
                    onChange={(e) => setModalSelectedEntityId(e.target.value)}
                    className="flex-1 rounded-lg bg-surface-container-high border border-starlight-white/10 px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50"
                  >
                    <option value="">Choose entity to tag...</option>
                    {availableEntities
                      .filter((ent) => !modalParticipants.some((p) => p.entity_id === ent.id))
                      .map((ent) => (
                        <option key={ent.id} value={ent.id}>
                          {ent.canonical_name} ({ent.entity_type})
                        </option>
                      ))}
                  </select>

                  <input
                    type="text"
                    list="role-options"
                    aria-label="Participant role" value={modalRoleInput}
                    onChange={(e) => setModalRoleInput(e.target.value)}
                    placeholder="Role"
                    className="w-28 rounded-lg bg-surface-container-high border border-starlight-white/10 px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50 uppercase"
                  />
                  <datalist id="role-options">
                    {COMMON_ROLES.map((r) => (
                      <option key={r} value={r} />
                    ))}
                  </datalist>

                  <button
                    type="button"
                    onClick={handleAddParticipantToModal}
                    disabled={!modalSelectedEntityId}
                    className="px-3 py-1.5 rounded-lg bg-copper-glow/20 text-copper-glow hover:bg-copper-glow/30 text-xs font-semibold disabled:opacity-40 transition-colors whitespace-nowrap"
                  >
                    Add
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-starlight-white/5">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-sm text-on-surface-variant hover:text-starlight-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !newDescription.trim()}
                  className="px-4 py-2 rounded-lg text-sm bg-primary text-surface-container font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Event'}
                </button>
              </div>
            </form>
      </Dialog>}

      {isEditModalOpen && <Dialog title="Edit Chronicle Event" onClose={() => { if (!updating) setIsEditModalOpen(false); }}>
            <form onSubmit={handleUpdateEvent} className="space-y-4">
              {error && <p role="alert" className="text-sm text-error">{error}</p>}
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Description *
                </label>
                <textarea
                  rows={3}
                  required
                  aria-label="Event description" value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="Describe what occurs at this milestone..."
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                    Event Type
                  </label>
                  <input
                    type="text"
                    aria-label="Event type" value={editEventType}
                    onChange={(e) => setEditEventType(e.target.value)}
                    placeholder="e.g. BATTLE, ARRIVAL, MEETING"
                    className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                    Chapter
                  </label>
                  <select
                    aria-label="Event chapter" value={editChapterId}
                    onChange={(e) => setEditChapterId(e.target.value)}
                    className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                  >
                    <option value="">No chapter (unassigned)</option>
                    {chapters.map((ch) => (
                      <option key={ch.id} value={ch.id}>
                        Chapter {ch.number}: {ch.title}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Participant Management Section */}
              <div className="space-y-2 pt-2 border-t border-starlight-white/10">
                <label className="block text-xs font-medium text-copper-glow uppercase tracking-wider flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm">person_add</span>
                    Tagged Participants ({modalParticipants.length})
                  </span>
                </label>

                {/* Current Tagged Participants Pills */}
                {modalParticipants.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 p-2 rounded-lg bg-surface-container-high/40 border border-starlight-white/5">
                    {modalParticipants.map((p) => {
                      const ent = availableEntities.find((e) => e.id === p.entity_id);
                      return (
                        <span
                          key={p.entity_id}
                          className="px-2.5 py-1 rounded-md bg-copper-glow/15 border border-copper-glow/30 text-xs text-starlight-white flex items-center gap-1.5"
                        >
                          <span className="font-medium">{p.entity_name || ent?.canonical_name || p.entity_id}</span>
                          <span className="text-[10px] text-copper-glow uppercase">({p.role})</span>
                          <button
                            type="button"
                            onClick={() => handleRemoveParticipantFromModal(p.entity_id)}
                            className="hover:text-error ml-0.5"
                          >
                            <span className="material-symbols-outlined text-xs">close</span>
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Add Participant Row */}
                <div className="flex items-center gap-2">
                  <select
                    aria-label="Event participant" value={modalSelectedEntityId}
                    onChange={(e) => setModalSelectedEntityId(e.target.value)}
                    className="flex-1 rounded-lg bg-surface-container-high border border-starlight-white/10 px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50"
                  >
                    <option value="">Choose entity to tag...</option>
                    {availableEntities
                      .filter((ent) => !modalParticipants.some((p) => p.entity_id === ent.id))
                      .map((ent) => (
                        <option key={ent.id} value={ent.id}>
                          {ent.canonical_name} ({ent.entity_type})
                        </option>
                      ))}
                  </select>

                  <input
                    type="text"
                    list="role-options-edit"
                    aria-label="Participant role" value={modalRoleInput}
                    onChange={(e) => setModalRoleInput(e.target.value)}
                    placeholder="Role"
                    className="w-28 rounded-lg bg-surface-container-high border border-starlight-white/10 px-2.5 py-1.5 text-xs text-starlight-white focus:outline-none focus:border-primary/50 uppercase"
                  />
                  <datalist id="role-options-edit">
                    {COMMON_ROLES.map((r) => (
                      <option key={r} value={r} />
                    ))}
                  </datalist>

                  <button
                    type="button"
                    onClick={handleAddParticipantToModal}
                    disabled={!modalSelectedEntityId}
                    className="px-3 py-1.5 rounded-lg bg-copper-glow/20 text-copper-glow hover:bg-copper-glow/30 text-xs font-semibold disabled:opacity-40 transition-colors whitespace-nowrap"
                  >
                    Add
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-starlight-white/5">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-sm text-on-surface-variant hover:text-starlight-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updating || !editDescription.trim()}
                  className="px-4 py-2 rounded-lg text-sm bg-primary text-surface-container font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {updating ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
      </Dialog>}
    </AppShell>
  );
};
