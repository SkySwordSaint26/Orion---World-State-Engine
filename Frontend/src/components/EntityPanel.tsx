import React, { useState, useEffect } from 'react';
import { useWorldStore } from '../store/useWorldStore';
import type { Entity } from '../types/world';
import { useNavigate, useParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { createRelationship, deleteRelationship } from '../api/relationships';
import { getEntityDescription } from '../utils/entityDescription';

interface EntityRelationshipDetail {
  id?: string;
  targetId: string;
  targetName: string;
  targetType: Entity['type'];
  relation: string;
  direction?: 'outgoing' | 'incoming';
  isNegative?: boolean;
  chapter_id?: string | null;
  chapter_number?: number | null;
}

interface EntityAppearanceDetail {
  id: string;
  chapter_number?: number | null;
  title: string;
  reason?: string;
}

interface EntityPanelProps {
  entityId: string;
  onClose: () => void;
}

export const EntityPanel: React.FC<EntityPanelProps> = ({ entityId, onClose }) => {
  const navigate = useNavigate();
  const { worldId } = useParams<{ worldId: string }>();
  const { 
    entities, 
    addFact, 
    deleteFact, 
    updateEntity, 
    addAlias, 
    removeAlias, 
    activeWorldId, 
    setActiveChapter, 
    setActiveManuscript,
    manuscripts,
    fetchManuscriptsForWorld,
    fetchEntitiesForWorld,
    relationshipRevision,
    notifyRelationshipsChanged
  } = useWorldStore();

  const currentWorldId = worldId || activeWorldId;
  const entity = entities.find((e) => e.id === entityId);

  const [activeTab, setActiveTab] = useState<'details' | 'relations' | 'history'>('details');
  const [detailData, setDetailData] = useState<{
    relationships: any[];
    appearances: any[];
    canonical_name?: string;
    entity_type?: Entity['type'];
    aliases?: string[];
    description: string;
  } | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isAddingRelation, setIsAddingRelation] = useState(false);
  const [relationTarget, setRelationTarget] = useState('');
  const [relationType, setRelationType] = useState('KNOWS');
  const [relationDirection, setRelationDirection] = useState<'outgoing' | 'incoming'>('outgoing');
  const [relationChapterId, setRelationChapterId] = useState('');
  const [relationBusy, setRelationBusy] = useState(false);
  const [relationError, setRelationError] = useState<string | null>(null);
  const [isEditingDescription, setIsEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState('');
  const [isSavingDescription, setIsSavingDescription] = useState(false);
  const [entityError, setEntityError] = useState<string | null>(null);

  const [factProperty, setFactProperty] = useState('');
  const [factValue, setFactValue] = useState('');
  const [factError, setFactError] = useState<string | null>(null);
  const [isSubmittingFact, setIsSubmittingFact] = useState(false);
  const [isAddingFact, setIsAddingFact] = useState(false);

  const [newAlias, setNewAlias] = useState('');
  const [isAddingAlias, setIsAddingAlias] = useState(false);
  const [aliasError, setAliasError] = useState<string | null>(null);

  const [newTrait, setNewTrait] = useState('');
  const [isAddingTrait, setIsAddingTrait] = useState(false);

  // Fetch full entity details (relationships & appearances) whenever entityId or currentWorldId changes
  useEffect(() => {
    if (!currentWorldId || !entityId) return;
    let isMounted = true;
    setLoadingDetails(true);
    setDetailError(null);

    apiFetch<any>(`/worlds/${currentWorldId}/entities/${entityId}`)
      .then((res) => {
        if (!isMounted) return;
        setDetailData({
          relationships: Array.isArray(res.relationships) ? res.relationships : [],
          appearances: Array.isArray(res.appearances) ? res.appearances : [],
          canonical_name: res.canonical_name,
          entity_type: res.entity_type,
          aliases: res.aliases,
          description: getEntityDescription(res),
        });
      })
      .catch((err) => {
        console.error('Failed to load entity detail data:', err);
        if (!isMounted) return;
        setDetailData(null);
        setDetailError('Could not load entity details. Please reopen the card to retry.');
      })
      .finally(() => {
        if (isMounted) setLoadingDetails(false);
      });

    return () => {
      isMounted = false;
    };
  }, [currentWorldId, entityId, relationshipRevision]);

  useEffect(() => {
    if (currentWorldId) fetchEntitiesForWorld(currentWorldId);
  }, [currentWorldId, fetchEntitiesForWorld]);

  // Ensure manuscripts are loaded so navigation to chapters works smoothly
  useEffect(() => {
    if (currentWorldId && (!manuscripts || manuscripts.length === 0)) {
      fetchManuscriptsForWorld(currentWorldId).catch(() => {});
    }
  }, [currentWorldId, manuscripts, fetchManuscriptsForWorld]);

  const displayEntity: Entity | null = entity || (detailData ? {
    id: entityId,
    name: detailData.canonical_name || 'Unnamed Entity',
    type: (detailData.entity_type as Entity['type']) || 'character',
    subtype: 'Ledger Entry',
    alias: (detailData.aliases || [])[0] || '',
    aliases: detailData.aliases || [],
    description: detailData.description,
    traits: [],
    facts: [],
    relationships: detailData.relationships || [],
    appearances: []
  } : null);

  const handleAddRelation = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentWorldId || !relationTarget || !relationType.trim() || relationBusy) return;
    setRelationBusy(true);
    setRelationError(null);
    try {
      await createRelationship(currentWorldId, {
        source_entity_id: relationDirection === 'outgoing' ? entityId : relationTarget,
        target_entity_id: relationDirection === 'outgoing' ? relationTarget : entityId,
        relationship_type: relationType.trim().toUpperCase().replace(/\s+/g, '_'),
        chapter_id: relationChapterId || null,
      });
      notifyRelationshipsChanged();
      setIsAddingRelation(false);
      setRelationTarget('');
    } catch (err) {
      setRelationError(err instanceof Error ? err.message : 'Failed to create relationship.');
    } finally {
      setRelationBusy(false);
    }
  };

  const handleRemoveRelation = async (id: string) => {
    if (!currentWorldId || relationBusy) return;
    if (!window.confirm('Delete this relationship and its historical versions?')) return;
    setRelationBusy(true);
    setRelationError(null);
    try {
      await deleteRelationship(currentWorldId, id);
      notifyRelationshipsChanged();
    } catch (err) {
      setRelationError(err instanceof Error ? err.message : 'Failed to delete relationship.');
    } finally {
      setRelationBusy(false);
    }
  };

  if (!displayEntity && loadingDetails) {
    return (
      <div className="flex flex-col h-full bg-surface-container-low/95 backdrop-blur-xl border-l border-starlight-white/10 p-6 items-center justify-center">
        <span className="material-symbols-outlined text-3xl text-primary animate-spin">progress_activity</span>
        <p className="font-label-sm text-xs uppercase tracking-wider text-on-surface-variant/60 mt-3">Loading Entity...</p>
      </div>
    );
  }

  if (!displayEntity) {
    return (
      <div className="p-6 text-center text-on-surface-variant/50">
        Entity not found.
      </div>
    );
  }

  const aliasList = (displayEntity.aliases && displayEntity.aliases.length > 0)
    ? displayEntity.aliases
    : (displayEntity.alias ? [displayEntity.alias] : []);

  // Normalize relationships into a consistent, safe schema
  const rawRelationships: any[] = (detailData && Array.isArray(detailData.relationships))
    ? detailData.relationships
    : (Array.isArray(displayEntity.relationships) ? displayEntity.relationships : []);

  const relList: EntityRelationshipDetail[] = rawRelationships.map((r: any, idx: number) => {
    const relType = String(r.relation || r.relationship_type || r.type || 'RELATED_TO');
    const targetName = String(r.targetName || r.target_name || 'Unknown Entity');
    const targetId = String(r.targetId || r.target_id || '');
    const targetType = (r.targetType || r.target_type || 'character') as Entity['type'];
    const direction = r.direction === 'incoming' ? 'incoming' : 'outgoing';
    const isNegative = r.isNegative ?? ['ENEMY_OF', 'RIVAL_OF', 'OPPOSES', 'HATES', 'DEAD_AT_HANDS_OF'].includes(relType);
    const chapterNumber = r.chapter_number ?? (r.chapter?.chapter_number ?? null);
    const chapterId = r.chapter_id ?? null;

    return {
      id: r.id || `rel-${idx}`,
      targetId,
      targetName,
      targetType,
      relation: relType,
      direction,
      isNegative,
      chapter_id: chapterId,
      chapter_number: chapterNumber,
    };
  });

  // Normalize appearances into a consistent, safe schema
  const rawAppearances: any[] = (detailData && Array.isArray(detailData.appearances))
    ? detailData.appearances
    : (Array.isArray((displayEntity as any).appearances) ? (displayEntity as any).appearances : []);

  const appearanceList: EntityAppearanceDetail[] = rawAppearances.map((app: any, idx: number) => {
    if (typeof app === 'string') {
      return {
        id: app,
        chapter_number: null,
        title: app,
        reason: 'Chapter Appearance',
      };
    }
    return {
      id: String(app.id || `app-${idx}`),
      chapter_number: app.chapter_number ?? null,
      title: String(app.title || (app.chapter_number ? `Chapter ${app.chapter_number}` : 'Chapter')),
      reason: app.reason ? String(app.reason) : undefined,
    };
  });

  const handleAddFact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!factProperty.trim() || !factValue.trim()) return;
    setFactError(null);
    setIsSubmittingFact(true);
    try {
      await addFact(displayEntity.id, factProperty.trim(), factValue.trim(), 'Manual Entry');
      setFactProperty('');
      setFactValue('');
      setIsAddingFact(false);
    } catch (err: any) {
      setFactError(err?.message || 'Failed to add fact.');
    } finally {
      setIsSubmittingFact(false);
    }
  };

  const handleAddAlias = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAlias.trim()) return;
    setAliasError(null);
    try {
      await addAlias(displayEntity.id, newAlias.trim());
      setNewAlias('');
      setIsAddingAlias(false);
    } catch (err: any) {
      setAliasError(err?.message || 'Failed to add alias.');
    }
  };

  const handleRemoveAlias = async (aliasToRemove: string) => {
    setAliasError(null);
    try {
      await removeAlias(displayEntity.id, aliasToRemove);
    } catch (err: any) {
      setAliasError(err?.message || 'Failed to remove alias.');
    }
  };

  const reportEntityError = (error: unknown) => {
    setEntityError(error instanceof Error ? error.message : 'Failed to update entity.');
  };

  const handleSaveDescription = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isSavingDescription) return;
    setIsSavingDescription(true);
    setEntityError(null);
    try {
      await updateEntity(displayEntity.id, { description: descriptionDraft.trim() });
      setIsEditingDescription(false);
    } catch (error) {
      reportEntityError(error);
    } finally {
      setIsSavingDescription(false);
    }
  };

  const handleAddTrait = async () => {
    if (newTrait.trim()) {
      setEntityError(null);
      const updatedTraits = [...(displayEntity.traits || []), newTrait.trim()];
      try {
        await updateEntity(displayEntity.id, { traits: updatedTraits });
        setNewTrait('');
        setIsAddingTrait(false);
      } catch (error) {
        reportEntityError(error);
      }
    }
  };

  const handleRemoveTrait = (traitIndex: number) => {
    if (displayEntity.traits) {
      setEntityError(null);
      const updatedTraits = displayEntity.traits.filter((_, idx) => idx !== traitIndex);
      updateEntity(displayEntity.id, { traits: updatedTraits }).catch(reportEntityError);
    }
  };

  const navigateToChapter = (chapterId: string) => {
    const manuscript = manuscripts.find((candidate) =>
      candidate.chapters?.some((chapter) => chapter.id === chapterId)
    );
    if (manuscript) {
      setActiveManuscript(manuscript.id);
      setActiveChapter(chapterId);
      navigate(`/worlds/${activeWorldId}/manuscripts/${manuscript.id}`);
    } else if (manuscripts.length > 0) {
      setActiveManuscript(manuscripts[0].id);
      setActiveChapter(chapterId);
      navigate(`/worlds/${activeWorldId}/manuscripts/${manuscripts[0].id}`);
    } else {
      navigate(`/worlds/${activeWorldId}/manuscripts`);
    }
  };

  // Color mapping based on entity type
  const getTypeColor = (type: Entity['type']) => {
    switch (type) {
      case 'character': return 'text-copper-glow border-copper-glow/20 bg-copper-glow/5';
      case 'location': return 'text-secondary border-secondary/20 bg-secondary/5';
      case 'object': return 'text-tertiary border-tertiary/20 bg-tertiary/5';
      case 'event': return 'text-error border-error/20 bg-error/5';
      default: return 'text-on-surface-variant border-starlight-white/5';
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

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface-container-low">
      {/* Decorative Blur Ambient */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>

      {/* Header */}
      <div className="p-6 border-b border-white/5">
        <div className="flex justify-between items-start mb-4 relative z-10">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`material-symbols-outlined text-sm font-light ${getTypeColor(displayEntity.type).split(' ')[0]}`}>
                {getTypeIcon(displayEntity.type)}
              </span>
              <label className="text-[10px] font-label-sm text-on-surface-variant/60 uppercase tracking-widest">Type:</label>
              <select
                aria-label="Entity type" value={displayEntity.type}
                onChange={(e) => updateEntity(displayEntity.id, { type: e.target.value as Entity['type'] }).catch(reportEntityError)}
                className={`font-label-sm text-[11px] uppercase tracking-wider py-0.5 px-2.5 rounded-full border bg-surface-container cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary ${getTypeColor(displayEntity.type)}`}
              >
                <option value="character" className="bg-void-black text-starlight-white">Character</option>
                <option value="location" className="bg-void-black text-starlight-white">Location</option>
                <option value="object" className="bg-void-black text-starlight-white">Object</option>
                <option value="event" className="bg-void-black text-starlight-white">Event</option>
              </select>
            </div>
            <h2 className="font-headline-md text-headline-md text-starlight-white leading-tight mt-1">{displayEntity.name}</h2>
          </div>
          <button aria-label="Close entity" onClick={onClose} className="text-on-surface-variant hover:text-white transition-colors p-1 hover:bg-white/5 rounded-full">
            <span className="material-symbols-outlined font-light">close</span>
          </button>
        </div>

        {/* Panel Tabs */}
        <div className="flex gap-4 border-b border-starlight-white/10 relative z-10 mt-6">
          <button 
            onClick={() => setActiveTab('details')}
            className={`font-label-sm text-label-sm pb-2 px-1 flex items-center gap-1.5 transition-all border-b-2 ${activeTab === 'details' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-primary-fixed-dim'}`}
          >
            <span className="material-symbols-outlined text-sm font-light">subject</span> Details
          </button>
          <button 
            onClick={() => setActiveTab('relations')}
            aria-label="Relations"
            className={`font-label-sm text-label-sm pb-2 px-1 flex items-center gap-1.5 transition-all border-b-2 ${activeTab === 'relations' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-primary-fixed-dim'}`}
          >
            <span className="material-symbols-outlined text-sm font-light">share</span> Relations
            {relList.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-primary/15 text-primary border border-primary/25 font-mono ml-0.5">
                {relList.length}
              </span>
            )}
          </button>
          <button 
            onClick={() => setActiveTab('history')}
            className={`font-label-sm text-label-sm pb-2 px-1 flex items-center gap-1.5 transition-all border-b-2 ${activeTab === 'history' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-primary-fixed-dim'}`}
          >
            <span className="material-symbols-outlined text-sm font-light">history</span> Appearances
            {appearanceList.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-primary/15 text-primary border border-primary/25 font-mono ml-0.5">
                {appearanceList.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {entityError && <p role="alert" className="text-sm text-error">{entityError}</p>}
        
        {activeTab === 'details' && (
          <>
            {/* Portrait Card */}
            {displayEntity.image && (
              <div className="bg-surface-container-high/50 border border-starlight-white/5 rounded-lg overflow-hidden p-1">
                <div className="w-full h-44 bg-surface-container-lowest rounded relative overflow-hidden group">
                  <img src={displayEntity.image} alt={displayEntity.name} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-500" />
                  <div className="absolute inset-0 bg-gradient-to-t from-void-black/85 via-void-black/20 to-transparent flex items-end p-3">
                    <span className="font-label-sm text-label-sm text-starlight-white/60 text-[10px] uppercase tracking-wider">Visual Reference</span>
                  </div>
                </div>
              </div>
            )}

            {/* Quick Meta: Subtype & Aliases */}
            <div className="space-y-4 bg-surface-container-lowest/40 p-4 rounded-lg border border-starlight-white/5">
              <div>
                <p className="font-label-sm text-label-sm text-on-surface-variant/60 uppercase text-[10px] mb-1">Subtype / Role</p>
                <p className="font-body-md text-body-md text-on-surface text-sm">{displayEntity.subtype || 'Supporting entry'}</p>
              </div>

              {/* Aliases Tag Manager */}
              <div className="pt-2 border-t border-starlight-white/5">
                <div className="flex justify-between items-center mb-2">
                  <p className="font-label-sm text-label-sm text-on-surface-variant/70 uppercase text-[10px] tracking-wider flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[12px]">sell</span>
                    Aliases
                  </p>
                  {!isAddingAlias && (
                    <button
                      onClick={() => setIsAddingAlias(true)}
                      className="font-label-sm text-[10px] text-primary hover:text-white flex items-center gap-1 uppercase tracking-wider transition-colors"
                    >
                      <span className="material-symbols-outlined text-[11px]">add</span> Add Alias
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {aliasList.length === 0 && !isAddingAlias && (
                    <span className="text-xs text-on-surface-variant/40 italic">No aliases recorded.</span>
                  )}
                  {aliasList.map((a, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-0.5 bg-surface-container text-on-surface-variant font-label-sm text-[11px] rounded-full border border-starlight-white/5 flex items-center gap-1.5 group/alias hover:border-primary/30"
                    >
                      "{a}"
                      <button
                        onClick={() => handleRemoveAlias(a)}
                        className="opacity-40 group-hover/alias:opacity-100 hover:text-error transition-opacity"
                        title={`Remove alias "${a}"`}
                      >
                        <span className="material-symbols-outlined text-[10px]">close</span>
                      </button>
                    </span>
                  ))}
                  {isAddingAlias && (
                    <form onSubmit={handleAddAlias} className="flex items-center gap-1 mt-1">
                      <input
                        type="text"
                        value={newAlias}
                        onChange={(e) => setNewAlias(e.target.value)}
                        aria-label="New alias" placeholder="New alias..."
                        autoFocus
                        className="bg-surface-container-high border border-outline-variant/30 text-xs rounded px-2 py-0.5 text-starlight-white focus:outline-none focus:ring-1 focus:ring-primary w-28"
                      />
                      <button type="submit" className="text-primary hover:text-white">
                        <span className="material-symbols-outlined text-sm">check</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsAddingAlias(false);
                          setAliasError(null);
                        }}
                        className="text-on-surface-variant"
                      >
                        <span className="material-symbols-outlined text-sm">close</span>
                      </button>
                    </form>
                  )}
                </div>
                {aliasError && (
                  <p className="text-[11px] text-error mt-1.5">{aliasError}</p>
                )}
              </div>
            </div>

            {/* Description */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="font-label-sm text-on-surface-variant/60 uppercase text-[10px]">Description / Synopsis</p>
                {!isEditingDescription && <button
                  aria-label="Edit description"
                  onClick={() => { setDescriptionDraft(displayEntity.description); setIsEditingDescription(true); setEntityError(null); }}
                  className="text-xs text-primary hover:underline"
                >Edit</button>}
              </div>
              {isEditingDescription ? (
                <form onSubmit={handleSaveDescription} className="space-y-3">
                  <textarea autoFocus aria-label="Entity description" value={descriptionDraft} onChange={event => setDescriptionDraft(event.target.value)} disabled={isSavingDescription} rows={5} className="w-full p-3 rounded border border-primary/30 bg-surface-container-lowest text-sm text-on-surface-variant leading-relaxed focus:outline-none focus:border-primary disabled:opacity-50" />
                  <div className="flex justify-end gap-3">
                    <button type="button" disabled={isSavingDescription} onClick={() => { setIsEditingDescription(false); setEntityError(null); }} className="text-xs text-on-surface-variant hover:text-white">Cancel</button>
                    <button type="submit" disabled={isSavingDescription} className="px-3 py-2 rounded bg-primary text-void-black text-xs disabled:opacity-50">{isSavingDescription ? 'Saving...' : 'Save description'}</button>
                  </div>
                </form>
              ) : <p className="font-body-md text-on-surface-variant text-sm leading-relaxed whitespace-pre-wrap bg-surface-container-lowest/30 p-3 rounded border border-starlight-white/5">
                {displayEntity.description || 'No description provided.'}
              </p>}
            </div>

            {/* Traits */}
            {displayEntity.type === 'character' && (
              <div className="space-y-3">
                <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm font-light">psychology</span>
                  Core Traits
                </p>
                <div className="flex flex-wrap gap-2">
                  {displayEntity.traits?.map((trait, idx) => (
                    <span 
                      key={idx} 
                      className="px-2.5 py-1 bg-surface-container text-on-surface-variant font-label-sm text-[11px] rounded border border-starlight-white/5 flex items-center gap-1.5 group/trait"
                    >
                      {trait}
                      <button 
                        onClick={() => handleRemoveTrait(idx)}
                        className="opacity-0 group-hover/trait:opacity-100 hover:text-error transition-opacity"
                        title="Remove trait" aria-label={`Remove trait ${trait}`}
                      >
                        <span className="material-symbols-outlined text-[10px]">close</span>
                      </button>
                    </span>
                  ))}
                  {isAddingTrait ? (
                    <div className="flex items-center gap-1">
                      <input 
                        type="text" 
                        value={newTrait}
                        onChange={(e) => setNewTrait(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddTrait()}
                        className="bg-surface-container-high border border-outline-variant/30 text-xs rounded px-2 py-0.5 text-starlight-white focus:outline-none focus:ring-1 focus:ring-primary w-24"
                        aria-label="New trait" placeholder="New trait..."
                        autoFocus
                      />
                      <button aria-label="Save trait" onClick={handleAddTrait} className="text-primary hover:text-white">
                        <span className="material-symbols-outlined text-sm">check</span>
                      </button>
                      <button onClick={() => setIsAddingTrait(false)} className="text-on-surface-variant">
                        <span className="material-symbols-outlined text-sm">close</span>
                      </button>
                    </div>
                  ) : (
                    <button 
                      aria-label="Add trait" onClick={() => setIsAddingTrait(true)}
                      className="px-2.5 py-1 bg-transparent text-primary/60 hover:text-primary font-label-sm text-[11px] rounded border border-dashed border-primary/30 hover:border-primary/60 transition-colors flex items-center gap-1"
                    >
                      <span className="material-symbols-outlined text-[10px]">add</span> Add
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Facts Ledger */}
            <div className="space-y-3 pt-2">
              <div className="flex justify-between items-center border-b border-starlight-white/5 pb-2">
                <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm font-light">format_list_bulleted</span>
                  Known Facts
                </p>
                <button 
                  onClick={() => setIsAddingFact(!isAddingFact)}
                  className="font-label-sm text-[10px] text-primary/80 hover:text-primary flex items-center gap-1 uppercase tracking-wider border border-primary/20 hover:border-primary/50 px-2 py-0.5 rounded transition-all"
                >
                  <span className="material-symbols-outlined text-[12px]">{isAddingFact ? 'close' : 'add'}</span> 
                  {isAddingFact ? 'Cancel' : 'Add Fact'}
                </button>
              </div>

              {isAddingFact && (
                <form onSubmit={handleAddFact} className="flex flex-col gap-2.5 p-3 bg-surface-container rounded border border-outline-variant/30 animate-fade-in-up">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[10px] font-label-sm text-on-surface-variant/70 uppercase mb-1">Property Name</label>
                      <input 
                        type="text"
                        value={factProperty}
                        onChange={(e) => setFactProperty(e.target.value)}
                        aria-label="Fact property" placeholder="e.g. status, title, weapon"
                        className="w-full bg-void-black text-xs text-starlight-white placeholder:text-on-surface-variant/40 rounded border border-starlight-white/10 p-2 focus:border-primary focus:ring-0 focus:outline-none"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-label-sm text-on-surface-variant/70 uppercase mb-1">Value</label>
                      <input 
                        type="text"
                        value={factValue}
                        onChange={(e) => setFactValue(e.target.value)}
                        aria-label="Fact value" placeholder="e.g. deceased, High Commander"
                        className="w-full bg-void-black text-xs text-starlight-white placeholder:text-on-surface-variant/40 rounded border border-starlight-white/10 p-2 focus:border-primary focus:ring-0 focus:outline-none"
                        required
                      />
                    </div>
                  </div>
                  {factError && (
                    <p className="text-[11px] text-error">{factError}</p>
                  )}
                  <div className="flex gap-2">
                    <button 
                      type="submit" 
                      disabled={isSubmittingFact}
                      className="flex-1 py-1.5 bg-primary text-void-black font-label-sm text-xs rounded hover:bg-copper-glow transition-all uppercase tracking-wider font-semibold disabled:opacity-50"
                    >
                      {isSubmittingFact ? 'Recording...' : 'Submit Fact'}
                    </button>
                    <button 
                      type="button" 
                      onClick={() => {
                        setIsAddingFact(false);
                        setFactError(null);
                      }}
                      className="px-3 py-1.5 border border-starlight-white/10 text-on-surface-variant font-label-sm text-xs rounded hover:text-white uppercase tracking-wider"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              <div className="space-y-3">
                {displayEntity.facts.length === 0 ? (
                  <p className="text-xs text-on-surface-variant/40 italic">No facts recorded yet.</p>
                ) : (
                  displayEntity.facts.map((fact) => (
                    <div 
                      key={fact.id} 
                      className="group relative pl-3.5 py-1.5 border-l border-outline-variant/35 hover:border-primary/50 transition-colors flex justify-between items-start"
                    >
                      <div className="absolute -left-[5px] top-[14px] w-2.5 h-2.5 rounded-full bg-outline-variant/80 group-hover:bg-primary transition-all"></div>
                      <div className="flex-1 pr-2">
                        <p className="font-body-md text-xs text-on-surface leading-relaxed">{fact.text}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[9px] uppercase tracking-wider font-label-sm px-1.5 py-0.2 rounded ${fact.type === 'extracted' ? 'bg-primary/10 text-primary border border-primary/20' : 'bg-surface-container text-on-surface-variant/60 border border-starlight-white/5'}`}>
                            {fact.type}
                          </span>
                          <span className="text-[10px] text-on-surface-variant/40">{fact.source}</span>
                        </div>
                      </div>
                      <button 
                        onClick={() => { setEntityError(null); Promise.resolve(deleteFact(displayEntity.id, fact.id)).catch(reportEntityError); }}
                        className="opacity-0 group-hover:opacity-100 text-on-surface-variant/40 hover:text-error transition-all p-1"
                        title="Delete fact" aria-label="Delete fact"
                      >
                        <span className="material-symbols-outlined text-sm font-light">delete</span>
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}

        {activeTab === 'relations' && (
          <div className="space-y-4">
            <button onClick={() => { setIsAddingRelation(!isAddingRelation); setRelationError(null); }} className="w-full px-3 py-2 rounded-lg border border-primary/30 text-primary text-xs hover:bg-primary/10">
              {isAddingRelation ? 'Cancel' : 'Add Relationship'}
            </button>
            {isAddingRelation && (
              <form onSubmit={handleAddRelation} className="space-y-3 p-4 rounded-xl border border-primary/20 bg-surface-container-lowest">
                <label className="block text-xs text-on-surface-variant">Direction
                  <select aria-label="Relationship direction" value={relationDirection} onChange={e => setRelationDirection(e.target.value as typeof relationDirection)} className="block w-full mt-1 p-2 rounded bg-surface-container-high text-starlight-white">
                    <option value="outgoing">This entity → Other entity</option>
                    <option value="incoming">Other entity → This entity</option>
                  </select>
                </label>
                <label className="block text-xs text-on-surface-variant">Other entity
                  <select required aria-label="Related entity" value={relationTarget} onChange={e => setRelationTarget(e.target.value)} className="block w-full mt-1 p-2 rounded bg-surface-container-high text-starlight-white">
                    <option value="">Select entity...</option>
                    {entities.filter(item => item.id !== entityId).map(item => <option key={item.id} value={item.id}>{item.name} ({item.type})</option>)}
                  </select>
                </label>
                <label className="block text-xs text-on-surface-variant">Relationship type
                  <input required maxLength={100} aria-label="Relationship type" list="entity-relation-types" value={relationType} onChange={e => setRelationType(e.target.value)} placeholder="e.g. MENTOR_OF" className="block w-full mt-1 p-2 rounded bg-surface-container-high text-starlight-white" />
                  <datalist id="entity-relation-types">{['KNOWS', 'ALLY_OF', 'ENEMY_OF', 'FRIEND_OF', 'LIVES_AT', 'MEMBER_OF', 'RELATED_TO'].map(type => <option key={type} value={type} />)}</datalist>
                </label>
                <label className="block text-xs text-on-surface-variant">Effective chapter
                  <select aria-label="Relationship chapter" value={relationChapterId} onChange={e => setRelationChapterId(e.target.value)} className="block w-full mt-1 p-2 rounded bg-surface-container-high text-starlight-white">
                    <option value="">Universal</option>
                    {manuscripts.flatMap(item => item.chapters.map(ch => <option key={ch.id} value={ch.id}>{item.title} · Chapter {ch.number}: {ch.title}</option>))}
                  </select>
                </label>
                <button disabled={relationBusy || !relationTarget || !relationType.trim()} className="px-4 py-2 rounded bg-primary text-void-black text-xs disabled:opacity-50">{relationBusy ? 'Saving...' : 'Create Relationship'}</button>
              </form>
            )}
            {(relationError || detailError) && <p role="alert" className="text-xs text-error">{relationError || detailError}</p>}
            <div className="flex items-center justify-between border-b border-starlight-white/5 pb-2">
              <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2">
                <span className="material-symbols-outlined text-sm font-light">hub</span>
                Web of Influence
              </p>
              <span className="text-[11px] font-mono text-on-surface-variant/60 bg-surface-container px-2 py-0.5 rounded-full border border-starlight-white/5">
                {relList.length} {relList.length === 1 ? 'connection' : 'connections'}
              </span>
            </div>

            {loadingDetails && relList.length === 0 ? (
              <div className="space-y-3 py-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-16 rounded-lg bg-surface-container-high/30 animate-pulse border border-starlight-white/5" />
                ))}
              </div>
            ) : relList.length === 0 ? (
              <div className="text-center py-10 px-4 rounded-xl bg-surface-container-lowest/40 border border-starlight-white/5">
                <div className="w-12 h-12 mx-auto rounded-full bg-surface-container flex items-center justify-center text-on-surface-variant/40 mb-3">
                  <span className="material-symbols-outlined text-2xl font-light">hub</span>
                </div>
                <p className="font-label-sm text-xs uppercase tracking-wider text-on-surface-variant/70 mb-1">No Active Relationships</p>
                <p className="font-body-md text-xs text-on-surface-variant/40 max-w-[260px] mx-auto leading-relaxed">
                  No direct incoming or outgoing relationships have been mapped to this entity yet.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {relList.map((rel, idx) => {
                  const isOutgoing = rel.direction !== 'incoming';
                  const initial = rel.targetName ? rel.targetName.trim().charAt(0).toUpperCase() : '?';
                  const formattedRelation = String(rel.relation || 'RELATED_TO').replace(/_/g, ' ');
                  return (
                    <div 
                      key={rel.id || idx} 
                      className="group p-3 rounded-lg bg-surface-container-lowest/80 hover:bg-surface-container/70 border border-starlight-white/5 hover:border-primary/40 transition-all cursor-pointer flex items-center justify-between gap-3 shadow-sm hover:shadow-md"
                      onClick={() => {
                        if (rel.targetId) {
                          useWorldStore.getState().setActiveEntity(rel.targetId);
                        }
                      }}
                      title={`Inspect ${rel.targetName || 'Entity'}`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Target Initial / Avatar */}
                        <div className={`w-9 h-9 rounded-full flex items-center justify-center font-headline-md text-sm shrink-0 border ${
                          rel.targetType === 'character' ? 'border-primary/30 text-primary bg-primary/5' : 
                          rel.targetType === 'location' ? 'border-secondary/30 text-secondary bg-secondary/5' : 
                          rel.targetType === 'event' ? 'border-error/30 text-error bg-error/5' :
                          'border-tertiary/30 text-tertiary bg-tertiary/5'
                        }`}>
                          {initial || '?'}
                        </div>

                        {/* Connection Details */}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="font-body-md text-xs font-semibold text-starlight-white group-hover:text-primary transition-colors truncate">
                              {rel.targetName || 'Unknown Entity'}
                            </span>
                            <span className={`inline-flex items-center gap-1 font-label-sm text-[9px] uppercase tracking-wider px-1.5 py-0.2 rounded-full border ${
                              isOutgoing
                                ? 'bg-primary/10 border-primary/20 text-primary'
                                : 'bg-surface-container-high border-starlight-white/10 text-on-surface-variant'
                            }`}>
                              <span className="material-symbols-outlined text-[10px]">
                                {isOutgoing ? 'arrow_forward' : 'arrow_back'}
                              </span>
                              {isOutgoing ? 'Outgoing' : 'Incoming'}
                            </span>
                          </div>

                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`font-label-sm text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded border ${
                              rel.isNegative 
                                ? 'bg-error/10 border-error/30 text-error' 
                                : 'bg-surface-container border-starlight-white/10 text-copper-glow'
                            }`}>
                              {formattedRelation}
                            </span>
                            {rel.chapter_number != null && (
                              <span className="font-mono text-[10px] text-on-surface-variant/60 flex items-center gap-0.5">
                                <span className="material-symbols-outlined text-[10px]">bookmark</span>
                                Ch. {rel.chapter_number}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <button
                        aria-label={`Delete relationship with ${rel.targetName}`}
                        title="Delete relationship"
                        disabled={relationBusy || loadingDetails || !rel.id || rel.id.startsWith('rel-')}
                        onClick={event => { event.stopPropagation(); if (rel.id) handleRemoveRelation(rel.id); }}
                        className="p-2 text-on-surface-variant/60 hover:text-error disabled:opacity-30"
                      ><span className="material-symbols-outlined text-base">delete</span></button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-starlight-white/5 pb-2">
              <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2">
                <span className="material-symbols-outlined text-sm font-light">auto_stories</span>
                Chapter Appearances
              </p>
              <span className="text-[11px] font-mono text-on-surface-variant/60 bg-surface-container px-2 py-0.5 rounded-full border border-starlight-white/5">
                {appearanceList.length} {appearanceList.length === 1 ? 'chapter' : 'chapters'}
              </span>
            </div>

            {loadingDetails && appearanceList.length === 0 ? (
              <div className="space-y-3 py-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 rounded-lg bg-surface-container-high/30 animate-pulse border border-starlight-white/5" />
                ))}
              </div>
            ) : appearanceList.length === 0 ? (
              <div className="text-center py-10 px-4 rounded-xl bg-surface-container-lowest/40 border border-starlight-white/5">
                <div className="w-12 h-12 mx-auto rounded-full bg-surface-container flex items-center justify-center text-on-surface-variant/40 mb-3">
                  <span className="material-symbols-outlined text-2xl font-light">auto_stories</span>
                </div>
                <p className="font-label-sm text-xs uppercase tracking-wider text-on-surface-variant/70 mb-1">No Chapter Appearances</p>
                <p className="font-body-md text-xs text-on-surface-variant/40 max-w-[260px] mx-auto leading-relaxed">
                  This entity has not been extracted or mentioned in any processed chapters yet.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {appearanceList.map((app) => (
                  <div 
                    key={app.id}
                    onClick={() => navigateToChapter(app.id)}
                    className="p-3 rounded-lg bg-surface-container-lowest/80 hover:bg-surface-container/70 border border-starlight-white/5 hover:border-primary/40 text-xs transition-all flex items-center justify-between gap-3 group cursor-pointer shadow-sm hover:shadow-md"
                    title={`Open ${app.title || `Chapter ${app.chapter_number}`} in Writing Room`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary group-hover:scale-105 transition-transform shrink-0">
                        <span className="material-symbols-outlined text-sm font-light">menu_book</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-mono text-[11px] font-bold text-primary shrink-0">
                            Ch. {app.chapter_number ?? '?'}
                          </span>
                          <span className="font-body-md text-xs font-semibold text-starlight-white group-hover:text-primary transition-colors truncate">
                            {app.title}
                          </span>
                        </div>
                        {app.reason && (
                          <p className="font-label-sm text-[10px] text-on-surface-variant/70 uppercase tracking-wider truncate">
                            {app.reason}
                          </p>
                        )}
                      </div>
                    </div>
                    <span className="material-symbols-outlined text-sm text-on-surface-variant/40 group-hover:text-primary group-hover:translate-x-1 transition-all shrink-0">
                      open_in_new
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Bottom info banner */}
      <div className="p-4 border-t border-starlight-white/5 bg-void-black/80 flex items-center justify-between text-[11px] font-label-sm text-on-surface-variant/40 uppercase tracking-widest">
        <span>ID: {displayEntity.id}</span>
        <span>Engine Ledger</span>
      </div>
    </div>
  );
};
