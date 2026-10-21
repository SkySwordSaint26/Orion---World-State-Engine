import React, { useState, useEffect } from 'react';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import type { Entity } from '../types/world';
import { useNavigate, useParams } from 'react-router-dom';
import { getTimeline } from '../api/events';

export const EntityLedger: React.FC = () => {
  const navigate = useNavigate();
  const { worldId } = useParams<{ worldId: string }>();
  const { 
    entities, 
    activeWorldId, 
    fetchEntitiesForWorld, 
    setActiveEntity, 
    addEntity,
    mergeEntities,
    bulkDeleteEntities 
  } = useWorldStore();

  useEffect(() => {
    if (worldId && activeWorldId === worldId) {
      fetchEntitiesForWorld(worldId);
    }
  }, [worldId, activeWorldId, fetchEntitiesForWorld]);

  const [eventSummary, setEventSummary] = useState<{ worldId: string; count?: number; error?: boolean } | null>(null);
  const eventCount = eventSummary?.worldId === worldId ? eventSummary.count : null;
  const eventCountError = eventSummary?.worldId === worldId && eventSummary.error;
  useEffect(() => {
    let cancelled = false;
    if (worldId) getTimeline(worldId).then(data => {
      if (!cancelled) setEventSummary({ worldId, count: data.total });
    }).catch(() => {
      if (!cancelled) setEventSummary({ worldId, error: true });
    });
    return () => { cancelled = true; };
  }, [worldId]);
  
  const [activeTab, setActiveTab] = useState<'all' | 'character' | 'location' | 'object'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Selection mode states
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Merge Modal states
  const [isMergeModalOpen, setIsMergeModalOpen] = useState(false);
  const [survivorId, setSurvivorId] = useState<string>('');
  const [isMerging, setIsMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  // Bulk Delete Modal states
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Forge Entity Form Drawer states
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = useState(false);
  const [createType, setCreateType] = useState<'character' | 'location' | 'object'>('character');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [entityName, setEntityName] = useState('');
  const [entitySubtype, setEntitySubtype] = useState('');
  const [entityAlias, setEntityAlias] = useState('');
  const [entityDesc, setEntityDesc] = useState('');

  const filteredEntities = entities.filter((e) => {
    const matchesTab = activeTab === 'all' || e.type === activeTab;
    const matchesSearch = e.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          e.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          e.subtype?.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesTab && matchesSearch;
  });

  const toggleSelect = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedIds.length === filteredEntities.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filteredEntities.map(e => e.id));
    }
  };

  const handleOpenMergeModal = () => {
    if (selectedIds.length !== 2) return;
    setSurvivorId(selectedIds[0]);
    setMergeError(null);
    setIsMergeModalOpen(true);
  };

  const handleExecuteMerge = async () => {
    if (selectedIds.length !== 2) return;
    const sourceId = selectedIds.find(id => id !== survivorId);
    if (!sourceId || !survivorId) return;

    setIsMerging(true);
    setMergeError(null);
    try {
      await mergeEntities(sourceId, survivorId);
      setIsMergeModalOpen(false);
      setSelectedIds([]);
      setIsSelectMode(false);
    } catch (err: any) {
      setMergeError(err?.message || 'Failed to merge entities.');
    } finally {
      setIsMerging(false);
    }
  };

  const handleOpenDeleteModal = () => {
    if (selectedIds.length === 0) return;
    setDeleteError(null);
    setIsDeleteModalOpen(true);
  };

  const handleExecuteBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await bulkDeleteEntities(selectedIds);
      setIsDeleteModalOpen(false);
      setSelectedIds([]);
      setIsSelectMode(false);
    } catch (err: any) {
      setDeleteError(err?.message || 'Failed to delete entities.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleOpenCreateDrawer = (type: typeof createType = 'character') => {
    setCreateType(type);
    setEntityName('');
    setEntitySubtype('');
    setEntityAlias('');
    setEntityDesc('');
    setCreateError(null);
    setIsCreateDrawerOpen(true);
  };

  const handleForgeEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (entityName.trim() && entityDesc.trim()) {
      setIsCreating(true);
      setCreateError(null);
      try {
        await addEntity({
          id: `entity-${Date.now()}`,
          name: entityName.trim(),
          type: createType,
          subtype: entitySubtype.trim() || undefined,
          alias: entityAlias.trim() || undefined,
          description: entityDesc.trim()
        });
        setIsCreateDrawerOpen(false);
      } catch (err) {
        setCreateError(err instanceof Error ? err.message : 'Failed to create entity.');
      } finally {
        setIsCreating(false);
      }
    }
  };

  const getTypeIcon = (type: Entity['type']) => {
    switch (type) {
      case 'character': return 'group';
      case 'location': return 'location_on';
      case 'object': return 'category';
      case 'event': return 'event_note';
      default: return 'help';
    }
  };

  const getTypeColor = (type: Entity['type']) => {
    switch (type) {
      case 'character': return 'text-copper-glow border-copper-glow/30 bg-copper-glow/10';
      case 'location': return 'text-secondary border-secondary/30 bg-secondary/10';
      case 'object': return 'text-tertiary border-tertiary/30 bg-tertiary/10';
      case 'event': return 'text-error border-error/30 bg-error/10';
      default: return 'text-on-surface-variant border-starlight-white/10 bg-white/5';
    }
  };

  return (
    <AppShell>
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,_var(--tw-gradient-stops))] from-surface-container-high/10 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="studio-page">
        <div className="studio-page-inner flex flex-col gap-7">
          
          {/* Header */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 border-b border-starlight-white/5 pb-6">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                <span className="font-label-sm text-[10px] text-primary uppercase tracking-[0.25em] font-medium">World Archive</span>
              </div>
              <h1 className="studio-title mb-2">
                The World’s Register
              </h1>
              <p className="font-body-md text-sm md:text-base text-on-surface-variant/70 leading-relaxed max-w-2xl">
                Browse, search, and manage the canon characters, landmarks, artifacts, and events of your universe.
              </p>
            </div>
            
            {/* Quick Actions: Selection Mode Toggle & Unified Forge Entity */}
            <div className="flex flex-wrap items-center gap-3 shrink-0">
              <button 
                onClick={() => {
                  setIsSelectMode(!isSelectMode);
                  setSelectedIds([]);
                }}
                className={`flex items-center gap-1.5 font-label-sm text-[11px] px-3.5 py-2.5 rounded-lg uppercase tracking-wider font-semibold border transition-all ${
                  isSelectMode 
                    ? 'bg-primary text-void-black border-primary shadow-[0_0_12px_rgba(230,162,126,0.3)]' 
                    : 'text-on-surface-variant border-starlight-white/10 hover:border-primary/40 hover:text-white bg-surface-container-lowest/40'
                }`}
              >
                <span className="material-symbols-outlined text-sm font-light">
                  {isSelectMode ? 'check_box' : 'checklist'}
                </span>
                {isSelectMode ? 'Exit Selection' : 'Select / Merge'}
              </button>

              <button 
                onClick={() => handleOpenCreateDrawer('character')}
                aria-label="Forge Entity"
                className="flex items-center gap-2 font-label-sm text-xs px-4 py-2.5 rounded-lg uppercase tracking-wider font-semibold bg-primary-container hover:bg-primary text-on-primary-container shadow-lg shadow-primary/10 hover:shadow-primary/25 transition-all duration-300"
              >
                <span className="material-symbols-outlined text-base font-medium">add</span>
                Forge Entity
              </button>
            </div>
          </div>

          {/* Search and Filters Bar */}
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
            
            {/* Tabs with Counts */}
            <div className="flex flex-wrap bg-surface-container-lowest/80 border border-starlight-white/10 p-1 rounded-xl gap-1">
              {([
                { id: 'all', label: 'All Entries', icon: 'list', count: entities.length },
                { id: 'character', label: 'Characters', icon: 'group', count: entities.filter(e => e.type === 'character').length },
                { id: 'location', label: 'Locations', icon: 'location_on', count: entities.filter(e => e.type === 'location').length },
                { id: 'object', label: 'Objects', icon: 'category', count: entities.filter(e => e.type === 'object').length }
              ] as const).map(tab => (
                <button
                  key={tab.id}
                  aria-pressed={activeTab === tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-label-sm text-xs uppercase tracking-wider transition-all ${
                    activeTab === tab.id 
                      ? 'bg-surface-container-high text-primary font-medium'
                      : 'text-on-surface-variant hover:text-white hover:bg-white/5'
                  }`}
                >
                  <span className="material-symbols-outlined text-[15px] font-light">{tab.icon}</span>
                  <span>{tab.label}</span>
                  <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                    activeTab === tab.id ? 'bg-primary/10 text-primary' : 'bg-white/5 text-on-surface-variant/60'
                  }`}>
                    {tab.count}
                  </span>
                </button>
              ))}
              <button
                onClick={() => navigate(`/worlds/${worldId}/timeline`)}
                title={eventCountError ? 'Could not load event count. Open Timeline to retry.' : 'View and manage events in Timeline'}
                className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs uppercase tracking-wider text-on-surface-variant hover:text-white hover:bg-white/5"
              >
                <span className="material-symbols-outlined text-[15px]">event_note</span>
                Events <span className="text-[10px]">{eventCount ?? '—'}</span>
                <span className="material-symbols-outlined text-sm">arrow_forward</span>
              </button>
            </div>

            {/* Search Input */}
            <div className="relative group min-w-0 lg:min-w-[280px]">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/40 text-lg group-focus-within:text-primary transition-colors font-light">search</span>
              <input 
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search ledger" placeholder="Search ledger entries by name or lore..."
                className="w-full bg-surface-container-lowest border border-starlight-white/10 rounded-xl px-10 py-2.5 font-body-md text-xs text-on-surface placeholder:text-on-surface-variant/30 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all"
              />
              {searchQuery && (
                <button 
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant/40 hover:text-white"
                  title="Clear search"
                >
                  <span className="material-symbols-outlined text-sm">close</span>
                </button>
              )}
            </div>

          </div>

          {/* Batch Actions Bar (shown when in Selection Mode) */}
          {isSelectMode && (
            <div className="flex flex-wrap items-center justify-between gap-4 bg-surface-container-high/60 border border-primary/20 p-3.5 rounded-xl backdrop-blur-md animate-fade-in-up">
              <div className="flex items-center gap-3">
                <button 
                  onClick={handleSelectAll}
                  className="flex items-center gap-1.5 text-xs text-on-surface-variant hover:text-white font-label-sm uppercase tracking-wider"
                >
                  <span className="material-symbols-outlined text-base text-primary">
                    {selectedIds.length === filteredEntities.length && filteredEntities.length > 0
                      ? 'check_box' 
                      : selectedIds.length > 0 
                        ? 'indeterminate_check_box' 
                        : 'check_box_outline_blank'}
                  </span>
                  {selectedIds.length === filteredEntities.length ? 'Deselect All' : 'Select All'}
                </button>
                <span className="h-4 w-px bg-starlight-white/10" />
                <span className="text-xs text-starlight-white font-semibold">
                  {selectedIds.length} {selectedIds.length === 1 ? 'entity' : 'entities'} selected
                </span>
                {selectedIds.length === 2 && (
                  <span className="text-[11px] text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
                    Ready to merge
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2.5">
                <button
                  onClick={handleOpenMergeModal}
                  disabled={selectedIds.length !== 2}
                  className="flex items-center gap-1.5 font-label-sm text-xs px-3.5 py-1.5 rounded uppercase tracking-wider font-semibold border transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-primary/10 border-primary/40 text-primary hover:bg-primary hover:text-void-black"
                  title={selectedIds.length !== 2 ? 'Select exactly 2 entities to merge' : 'Merge the 2 selected entities'}
                >
                  <span className="material-symbols-outlined text-sm">merge</span>
                  Merge Entities (2)
                </button>
                <button
                  onClick={handleOpenDeleteModal}
                  disabled={selectedIds.length === 0}
                  className="flex items-center gap-1.5 font-label-sm text-xs px-3.5 py-1.5 rounded uppercase tracking-wider font-semibold border transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-error/10 border-error/30 text-error hover:bg-error hover:text-void-black"
                >
                  <span className="material-symbols-outlined text-sm">delete</span>
                  Bulk Delete ({selectedIds.length})
                </button>
                <button
                  onClick={() => {
                    setIsSelectMode(false);
                    setSelectedIds([]);
                  }}
                  className="text-xs text-on-surface-variant hover:text-white px-2 py-1 uppercase tracking-wider"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Grid List */}
          {filteredEntities.length === 0 ? (
            <div className="py-24 text-center text-sm text-on-surface-variant/40 italic bg-surface-container-low/20 rounded-2xl border border-dashed border-starlight-white/10 flex flex-col items-center justify-center gap-3">
              <span className="material-symbols-outlined text-3xl text-on-surface-variant/30">search_off</span>
              <p>No chronicle ledger entries match your filter or search query.</p>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-xs text-primary hover:underline uppercase tracking-wider font-label-sm"
                >
                  Clear search query
                </button>
              )}
            </div>
          ) : (
            <div className="ledger-list">
              {filteredEntities.map((e) => {
                const isSelected = selectedIds.includes(e.id);

                return (
                  <article 
                    key={e.id}
                    onClick={() => {
                      if (isSelectMode) {
                        toggleSelect(e.id);
                      } else {
                        setActiveEntity(e.id);
                      }
                    }}
                    tabIndex={0} role="button" onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (isSelectMode) toggleSelect(e.id); else setActiveEntity(e.id); } }} className={`ledger-entry group relative flex flex-col justify-between cursor-pointer overflow-hidden ${
                      isSelected 
                        ? 'bg-primary/10 border-2 border-primary ring-1 ring-primary/40 shadow-[0_0_25px_rgba(254,182,141,0.2)]' 
                        : 'bg-surface-container-low hover:border-primary/40'
                    }`}
                  >
                    {/* Checkbox badge when in selection mode */}
                    {isSelectMode && (
                      <div 
                        onClick={(evt) => toggleSelect(e.id, evt)}
                        className="absolute top-4 right-4 z-20 cursor-pointer text-primary"
                        title={isSelected ? 'Deselect entity' : 'Select entity'}
                      >
                        <span className="material-symbols-outlined text-xl">
                          {isSelected ? 'check_box' : 'check_box_outline_blank'}
                        </span>
                      </div>
                    )}

                    {/* Subtle hover glow accent */}
                    <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

                    <div>
                      {/* Card Header: Type Badge & Action */}
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <span className={`inline-flex items-center gap-1.5 font-label-sm text-[10px] uppercase tracking-widest px-2.5 py-1 rounded-full border font-semibold ${getTypeColor(e.type)}`}>
                          <span className="material-symbols-outlined text-[13px] font-light">{getTypeIcon(e.type)}</span>
                          {e.type}
                        </span>
                        
                        {!isSelectMode && (
                          <span className="text-[10px] font-label-sm uppercase tracking-wider text-on-surface-variant/30 group-hover:text-primary transition-colors flex items-center gap-0.5">
                            <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">Inspect</span>
                            <span className="material-symbols-outlined text-sm font-light group-hover:translate-x-0.5 transition-transform">arrow_forward</span>
                          </span>
                        )}
                      </div>

                      {/* Entity Name */}
                      <h3 className="font-headline-md text-xl text-starlight-white group-hover:text-primary transition-colors tracking-tight font-medium line-clamp-1 mb-1">
                        {e.name}
                      </h3>

                      {/* Subtype & Alias */}
                      {(e.subtype || e.alias) && <div className="flex flex-wrap items-center gap-1.5 mb-3">
                        {e.subtype && (
                          <span className="text-[10px] font-label-sm uppercase tracking-wider text-on-surface-variant/70 bg-white/5 border border-white/5 px-2 py-0.5 rounded">
                            {e.subtype}
                          </span>
                        )}
                        {e.alias && (
                          <span className="text-[11px] font-body-md text-on-surface-variant/50 italic">
                            aka "{e.alias}"
                          </span>
                        )}
                      </div>}

                      {/* Synopsis */}
                      <p className="font-body-md text-xs text-on-surface-variant/80 leading-relaxed line-clamp-3 mb-4">
                        {e.description || 'No synopsis recorded.'}
                      </p>

                      {/* Facts preview if any */}
                      {e.facts && e.facts.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-4">
                          {e.facts.slice(0, 2).map((f) => (
                            <span key={f.id} className="text-[10px] font-label-sm bg-surface-container-high/60 border border-starlight-white/5 text-on-surface-variant/70 px-2 py-0.5 rounded-full truncate max-w-[180px]">
                              {f.property_name ? `${f.property_name}: ` : ''}{String(f.value ?? f.text)}
                            </span>
                          ))}
                          {e.facts.length > 2 && (
                            <span className="text-[10px] font-label-sm text-on-surface-variant/40 self-center">
                              +{e.facts.length - 2} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Card Footer: Rich stats */}
                    <footer className="pt-3 border-t border-starlight-white/5 flex items-center justify-between text-[11px] font-label-sm text-on-surface-variant/50">
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1 hover:text-on-surface-variant transition-colors" title={`${e.facts.length} Facts recorded`}>
                          <span className="material-symbols-outlined text-[13px] text-primary/70">format_list_bulleted</span>
                          {e.facts.length}
                        </span>
                        <span className="flex items-center gap-1 hover:text-on-surface-variant transition-colors" title={`${e.relationships.length} Relationships mapped`}>
                          <span className="material-symbols-outlined text-[13px] text-secondary/70">hub</span>
                          {e.relationships.length}
                        </span>
                        {e.appearances.length > 0 && (
                          <span className="flex items-center gap-1 hover:text-on-surface-variant transition-colors" title={`${e.appearances.length} Chapter appearances`}>
                            <span className="material-symbols-outlined text-[13px] text-tertiary/70">auto_stories</span>
                            {e.appearances.length}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-on-surface-variant/40 font-mono">
                        {e.appearances.length > 0 ? `${e.appearances.length} ch.` : 'canon'}
                      </span>
                    </footer>
                  </article>
                );
              })}
            </div>
          )}

        </div>
      </main>

      {/* Merge Confirmation Modal */}
      {isMergeModalOpen && selectedIds.length === 2 && (
        <div className="fixed inset-0 bg-void-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container border border-primary/20 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative animate-fade-in-up">
            <button 
              onClick={() => {
                setIsMergeModalOpen(false);
                setMergeError(null);
              }}
              className="absolute top-4 right-4 text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5"
            >
              <span className="material-symbols-outlined font-light">close</span>
            </button>

            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-primary text-xl">merge</span>
              <h2 className="font-headline-md text-starlight-white text-lg font-bold">
                Merge Entities
              </h2>
            </div>
            <p className="text-xs text-on-surface-variant/80 mb-6">
              Select which entity will be the <span className="text-emerald-400 font-semibold">Surviving Target</span>. The other entity will be merged into it and permanently deleted.
            </p>

            {mergeError && (
              <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/30 text-error text-xs flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">error</span>
                {mergeError}
              </div>
            )}

            {/* Side-by-side selection */}
            {(() => {
              const entityA = entities.find(e => e.id === selectedIds[0]);
              const entityB = entities.find(e => e.id === selectedIds[1]);
              if (!entityA || !entityB) return null;

              const survivor = survivorId === entityB.id ? entityB : entityA;
              const source = survivor.id === entityA.id ? entityB : entityA;

              return (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Entity A */}
                    <div 
                      onClick={() => setSurvivorId(entityA.id)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        survivor.id === entityA.id 
                          ? 'border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/50' 
                          : 'border-error/40 bg-error/5 hover:border-error/60'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-[10px] font-label-sm uppercase tracking-wider px-2 py-0.5 rounded-full font-bold ${
                          survivor.id === entityA.id 
                            ? 'bg-emerald-500/20 text-emerald-300' 
                            : 'bg-error/20 text-error'
                        }`}>
                          {survivor.id === entityA.id ? 'Surviving Target' : 'Source (Will Delete)'}
                        </span>
                        <span className="material-symbols-outlined text-base">
                          {survivor.id === entityA.id ? 'check_circle' : 'delete'}
                        </span>
                      </div>
                      <h3 className="font-semibold text-starlight-white text-sm mb-1">{entityA.name}</h3>
                      <p className="text-[11px] text-on-surface-variant/70 line-clamp-2">{entityA.description}</p>
                      <div className="mt-3 pt-2 border-t border-starlight-white/5 text-[10px] text-on-surface-variant/50">
                        {entityA.facts.length} facts • Type: {entityA.type}
                      </div>
                    </div>

                    {/* Entity B */}
                    <div 
                      onClick={() => setSurvivorId(entityB.id)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        survivor.id === entityB.id 
                          ? 'border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/50' 
                          : 'border-error/40 bg-error/5 hover:border-error/60'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-[10px] font-label-sm uppercase tracking-wider px-2 py-0.5 rounded-full font-bold ${
                          survivor.id === entityB.id 
                            ? 'bg-emerald-500/20 text-emerald-300' 
                            : 'bg-error/20 text-error'
                        }`}>
                          {survivor.id === entityB.id ? 'Surviving Target' : 'Source (Will Delete)'}
                        </span>
                        <span className="material-symbols-outlined text-base">
                          {survivor.id === entityB.id ? 'check_circle' : 'delete'}
                        </span>
                      </div>
                      <h3 className="font-semibold text-starlight-white text-sm mb-1">{entityB.name}</h3>
                      <p className="text-[11px] text-on-surface-variant/70 line-clamp-2">{entityB.description}</p>
                      <div className="mt-3 pt-2 border-t border-starlight-white/5 text-[10px] text-on-surface-variant/50">
                        {entityB.facts.length} facts • Type: {entityB.type}
                      </div>
                    </div>
                  </div>

                  {/* Summary of what merge rules execute */}
                  <div className="bg-void-black/60 p-3.5 rounded-lg border border-starlight-white/5 text-xs text-on-surface-variant/80 space-y-1.5">
                    <p className="font-semibold text-starlight-white text-[11px] uppercase tracking-wider flex items-center gap-1.5 text-primary">
                      <span className="material-symbols-outlined text-sm">info</span>
                      Merge Transaction Details
                    </p>
                    <ul className="list-disc pl-4 space-y-1 text-[11px] text-on-surface-variant/70">
                      <li>"<span className="text-starlight-white font-medium">{source.name}</span>" will be added as an alias to "<span className="text-emerald-300 font-medium">{survivor.name}</span>".</li>
                      <li>All mentions, facts, relationships, and event appearances will fold into the survivor.</li>
                      <li>Any self-loops and duplicate participations are automatically pruned.</li>
                    </ul>
                  </div>

                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setIsMergeModalOpen(false)}
                      className="px-4 py-2 border border-starlight-white/10 rounded text-xs text-on-surface-variant hover:text-white uppercase tracking-wider"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={isMerging}
                      onClick={handleExecuteMerge}
                      className="px-5 py-2 bg-primary-container hover:bg-primary text-on-primary-container font-semibold text-xs rounded uppercase tracking-wider transition-all disabled:opacity-50"
                    >
                      {isMerging ? 'Merging...' : 'Confirm & Execute Merge'}
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Bulk Delete Modal */}
      {isDeleteModalOpen && selectedIds.length > 0 && (
        <div className="fixed inset-0 bg-void-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container border border-error/30 rounded-2xl max-w-md w-full p-6 shadow-2xl relative animate-fade-in-up">
            <button 
              onClick={() => {
                setIsDeleteModalOpen(false);
                setDeleteError(null);
              }}
              className="absolute top-4 right-4 text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5"
            >
              <span className="material-symbols-outlined font-light">close</span>
            </button>

            <div className="flex items-center gap-2 mb-2 text-error">
              <span className="material-symbols-outlined text-xl">warning</span>
              <h2 className="font-headline-md text-starlight-white text-lg font-bold">
                Delete {selectedIds.length} {selectedIds.length === 1 ? 'Entity' : 'Entities'}?
              </h2>
            </div>
            <p className="text-xs text-on-surface-variant/80 mb-4">
              This action cannot be undone. All selected entities and their facts, aliases, mentions, and participations will be removed.
            </p>

            {deleteError && (
              <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/30 text-error text-xs flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">error</span>
                {deleteError}
              </div>
            )}

            <div className="max-h-40 overflow-y-auto bg-void-black/50 rounded-lg p-3 border border-starlight-white/5 mb-6 divide-y divide-starlight-white/5">
              {selectedIds.map(id => {
                const ent = entities.find(e => e.id === id);
                return (
                  <div key={id} className="py-1.5 flex items-center justify-between text-xs">
                    <span className="text-starlight-white font-medium">{ent?.name || id}</span>
                    <span className="text-[10px] uppercase text-on-surface-variant/50">{ent?.type}</span>
                  </div>
                );
              })}
            </div>

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(false)}
                className="px-4 py-2 border border-starlight-white/10 rounded text-xs text-on-surface-variant hover:text-white uppercase tracking-wider"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleExecuteBulkDelete}
                className="px-5 py-2 bg-error hover:bg-red-400 text-void-black font-semibold text-xs rounded uppercase tracking-wider transition-all disabled:opacity-50"
              >
                {isDeleting ? 'Deleting...' : 'Delete Selected'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Creation Slide-Over Drawer */}
      {isCreateDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop blur */}
          <div 
            onClick={() => setIsCreateDrawerOpen(false)}
            className="fixed inset-0 bg-void-black/60 backdrop-blur-sm transition-opacity cursor-pointer animate-fade-in"
          />

          {/* Drawer Content */}
          <aside className="relative w-[440px] sm:w-[480px] max-w-[100vw] h-full bg-surface-container-low/95 backdrop-blur-2xl border-l border-starlight-white/10 shadow-2xl flex flex-col justify-between z-10 animate-fade-in-up">
            
            {/* Header */}
            <div className="p-6 border-b border-starlight-white/5 bg-gradient-to-b from-surface-container-highest/30 to-transparent pt-8">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                    <span className="text-[10px] font-label-sm text-primary uppercase tracking-[0.2em] font-medium">
                      World Archive • Creation
                    </span>
                  </div>
                  <h2 className="font-headline-md text-2xl text-starlight-white leading-tight font-medium mt-1">
                    Forge New Entity
                  </h2>
                  <p className="text-xs text-on-surface-variant/70 mt-1">
                    Register a new canon entity into the world ledger and knowledge graph.
                  </p>
                </div>
                <button 
                  onClick={() => setIsCreateDrawerOpen(false)}
                  className="text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5 transition-colors"
                  title="Close Drawer"
                  aria-label="Close Drawer"
                >
                  <span className="material-symbols-outlined font-light text-xl">close</span>
                </button>
              </div>
            </div>

            {/* Scrollable Form Body */}
            <form id="forge-entity-form" onSubmit={handleForgeEntity} className="flex-1 overflow-y-auto p-6 space-y-6">
              
              {/* Entity Type Selector */}
              <div>
                <label className="block text-[10px] font-label-sm text-on-surface-variant/80 uppercase tracking-widest mb-2.5">
                  Select Entity Type
                </label>
                <div className="grid grid-cols-2 gap-2.5">
                  {([
                    { type: 'character', label: 'Character', icon: 'group', color: 'text-copper-glow', border: 'border-copper-glow/40 bg-copper-glow/5 ring-copper-glow/30' },
                    { type: 'location', label: 'Location', icon: 'location_on', color: 'text-secondary', border: 'border-secondary/40 bg-secondary/5 ring-secondary/30' },
                    { type: 'object', label: 'Object', icon: 'category', color: 'text-tertiary', border: 'border-tertiary/40 bg-tertiary/5 ring-tertiary/30' }
                  ] as const).map(item => {
                    const isSelected = createType === item.type;
                    return (
                      <button
                        type="button"
                        key={item.type}
                        onClick={() => setCreateType(item.type)}
                        className={`p-3 rounded-xl border flex items-center gap-2.5 transition-all text-left ${
                          isSelected 
                            ? `${item.border} ring-1 shadow-md bg-white/5` 
                            : 'border-starlight-white/5 bg-surface-container-lowest/40 hover:border-starlight-white/20 text-on-surface-variant'
                        }`}
                      >
                        <span className={`material-symbols-outlined text-lg ${isSelected ? item.color : 'text-on-surface-variant/60'}`}>
                          {item.icon}
                        </span>
                        <div>
                          <p className={`text-xs font-semibold ${isSelected ? 'text-starlight-white' : 'text-on-surface-variant'}`}>
                            {item.label}
                          </p>
                          <p className="text-[10px] text-on-surface-variant/50 capitalize font-label-sm">
                            {item.type}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-on-surface-variant/60 mt-3">Create and manage events in the Timeline section.</p>
              </div>

              {/* Name Field */}
              <div>
                <label className="block text-[10px] font-label-sm text-on-surface-variant/80 uppercase tracking-widest mb-1.5">
                  Entity Name <span className="text-primary">*</span>
                </label>
                <input 
                  type="text"
                  required
                  maxLength={255}
                  value={entityName}
                  onChange={(e) => setEntityName(e.target.value)}
                  placeholder={
                    createType === 'character' ? 'e.g. Valerius Thorne' :
                    createType === 'location' ? 'e.g. The Iron Valley' :
                    'e.g. Aetheric Compass'
                  }
                  className="w-full bg-void-black text-sm text-starlight-white placeholder:text-on-surface-variant/30 border border-starlight-white/10 rounded-lg p-3 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all"
                />
              </div>

              {/* Subtype / Role / Classification */}
              <div>
                <label className="block text-[10px] font-label-sm text-on-surface-variant/80 uppercase tracking-widest mb-1.5">
                  Subtype / Role <span className="text-on-surface-variant/40">(Optional)</span>
                </label>
                <input 
                  type="text"
                  value={entitySubtype}
                  onChange={(e) => setEntitySubtype(e.target.value)}
                  placeholder={
                    createType === 'character' ? 'e.g. High Commander / Inquisitor' :
                    createType === 'location' ? 'e.g. Ancient Ruins / Fortified Citadel' :
                    'e.g. Legendary Relic / Arcane Tome'
                  }
                  className="w-full bg-void-black text-sm text-starlight-white placeholder:text-on-surface-variant/30 border border-starlight-white/10 rounded-lg p-3 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all"
                />
              </div>

              {/* Primary Alias */}
              <div>
                <label className="block text-[10px] font-label-sm text-on-surface-variant/80 uppercase tracking-widest mb-1.5">
                  Primary Alias <span className="text-on-surface-variant/40">(Optional)</span>
                </label>
                <input 
                  type="text"
                  value={entityAlias}
                  onChange={(e) => setEntityAlias(e.target.value)}
                  placeholder="e.g. The Silver Blade, The Sunken Spire"
                  className="w-full bg-void-black text-sm text-starlight-white placeholder:text-on-surface-variant/30 border border-starlight-white/10 rounded-lg p-3 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all"
                />
              </div>

              {/* Description / Synopsis */}
              <div>
                <label className="block text-[10px] font-label-sm text-on-surface-variant/80 uppercase tracking-widest mb-1.5">
                  Lore Synopsis / Description <span className="text-primary">*</span>
                </label>
                <textarea 
                  required
                  value={entityDesc}
                  onChange={(e) => setEntityDesc(e.target.value)}
                  placeholder="Provide background lore, significance, attributes, or historical context..."
                  rows={4}
                  className="w-full bg-void-black text-sm text-starlight-white placeholder:text-on-surface-variant/30 border border-starlight-white/10 rounded-lg p-3 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all resize-none leading-relaxed"
                />
              </div>

              {createError && <p role="alert" className="text-sm text-error">{createError}</p>}
            </form>

            {/* Footer Actions */}
            <div className="p-6 border-t border-starlight-white/5 bg-surface-container-lowest/60 flex items-center justify-end gap-3">
              <button 
                type="button"
                onClick={() => setIsCreateDrawerOpen(false)}
                className="px-4 py-2.5 text-xs font-label-sm uppercase tracking-widest text-on-surface-variant hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button 
                type="submit"
                form="forge-entity-form"
                disabled={isCreating}
                className="px-6 py-2.5 bg-primary-container hover:bg-primary text-on-primary-container font-label-sm text-xs uppercase tracking-widest font-semibold rounded-lg shadow-lg hover:shadow-primary/20 transition-all duration-300"
              >
                {isCreating ? 'Creating...' : 'Forge Entity'}
              </button>
            </div>

          </aside>
        </div>
      )}
    </AppShell>
  );
};
