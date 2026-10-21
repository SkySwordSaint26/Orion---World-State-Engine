import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { apiFetch } from '../api/client';
import { getProposals } from '../api/proposals';
import type { ProposalsResponse } from '../api/proposals';
import { ProposalReviewModal } from '../components/ProposalReviewModal';
import { ChapterSelectionActions } from '../components/ChapterSelectionActions';
import { Dialog } from '../components/Dialog';
import { getChapterVersions, getChapterVersion, type ChapterVersion, type ChapterVersionContent } from '../api/chapters';
import { getJobStatus, cancelJob } from '../api/jobs';

export const WritingRoom: React.FC = () => {
  const navigate = useNavigate();
  const { worldId, manuscriptId } = useParams<{ worldId: string; manuscriptId: string }>();

  const {
    manuscripts,
    activeManuscriptId,
    activeChapterId,
    setActiveChapter,
    entities,
    setActiveEntity,
    updateChapterContent,
    fetchManuscriptsForWorld,
    deleteChapter,
    fetchEntitiesForWorld
  } = useWorldStore();

  const currentWorldId = worldId;
  const currentManuscriptId = manuscriptId || activeManuscriptId;

  useEffect(() => {
    if (currentWorldId && currentManuscriptId) {
      const exists = manuscripts.some((m) => m.id === currentManuscriptId);
      if (!exists || manuscripts.length === 0) {
        fetchManuscriptsForWorld(currentWorldId);
      }
    }
  }, [currentWorldId, currentManuscriptId, manuscripts, fetchManuscriptsForWorld]);

  // A link from a contradiction: ?chapter=<id>&start=<offset>&end=<offset> opens that chapter at the cited words
  const [searchParams] = useSearchParams();
  const linkedChapterId = searchParams.get('chapter');
  const linkStart = Number(searchParams.get('start'));
  const linkEnd = Number(searchParams.get('end'));
  useEffect(() => {
    if (linkedChapterId) setActiveChapter(linkedChapterId);
  }, [linkedChapterId, setActiveChapter]);

  const manuscript = manuscripts.find((m) => m.id === currentManuscriptId);
  const activeChapter = manuscript?.chapters.find((ch) => ch.id === activeChapterId) || manuscript?.chapters[0];

  const [isEditing, setIsEditing] = useState(false);
  const [editorContent, setEditorContent] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionStatus, setExtractionStatus] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyVersions, setHistoryVersions] = useState<ChapterVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<ChapterVersionContent | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [extractionJobId, setExtractionJobId] = useState<string | null>(null);
  const [chaptersOpen, setChaptersOpen] = useState(() => window.innerWidth >= 768);
  const [passageOpen, setPassageOpen] = useState(() => window.innerWidth >= 1280);
  const [focusMode, setFocusMode] = useState(false);
  const dirty = useRef(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [review, setReview] = useState<ProposalsResponse | null>(null);

  useEffect(() => {
    if (!activeChapter || !currentWorldId || !currentManuscriptId) return;
    const controller = new AbortController();
    dirty.current = false;
    setEditorContent(activeChapter.content);
    setSaveError(null);
    apiFetch<{ content: string }>(`/worlds/${currentWorldId}/chapters/${activeChapter.id}`, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return;
        if (!dirty.current) setEditorContent(data.content ?? '');
        updateChapterContent(currentManuscriptId, activeChapter.id, data.content ?? '');
      }).catch(error => { if (!controller.signal.aborted) setSaveError(`Could not load chapter: ${error.message}`); });
    return () => controller.abort();
  }, [activeChapter?.id, currentWorldId, currentManuscriptId, updateChapterContent]);

  useEffect(() => {
    if (currentWorldId) fetchEntitiesForWorld(currentWorldId);
  }, [currentWorldId, fetchEntitiesForWorld]);

  useEffect(() => {
    if (!extractionJobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const status = await getJobStatus(extractionJobId, controller.signal);
        if (controller.signal.aborted) return;
        if (status.status === 'done') {
          const found = await getProposals(extractionJobId);
          if (controller.signal.aborted) return;
          setReview(found);
          setExtractionStatus(null);
          setIsExtracting(false);
          setExtractionJobId(null);
          return;
        }
        if (status.status === 'failed' || status.status === 'cancelled') {
          setExtractionStatus(status.status === 'cancelled' ? 'Extraction cancelled. Saved chapter versions have been kept.' : `Extraction failed: ${status.error_message || 'Unknown error'}`);
          setIsExtracting(false);
          setExtractionJobId(null);
          return;
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setExtractionStatus(`Could not load extraction status or proposals. Retrying: ${error instanceof Error ? error.message : 'Connection error'}`);
      }
      timer = setTimeout(poll, 1500);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [extractionJobId]);

  useEffect(() => {
    if (linkedChapterId && activeChapter?.id === linkedChapterId) {
      document.getElementById('orion-cited')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [linkedChapterId, activeChapter?.id, activeChapter?.content]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const readingRef = useRef<HTMLDivElement>(null);

  const adjustTextareaHeight = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.max(400, el.scrollHeight)}px`;
    }
  };

  useEffect(() => {
    if (isEditing) {
      adjustTextareaHeight();
    }
  }, [isEditing, editorContent]);

  const handleStartEdit = () => {
    if (activeChapter) {
      setEditorContent(activeChapter.content);
      setIsEditing(true);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    if (activeChapter) {
      setEditorContent(activeChapter.content);
    }
  };

  const persistChapter = async (content: string, versionId?: string) => {
    if (!activeChapter || !manuscript || !currentWorldId || isSaving) return;
    setIsSaving(true);
    setSaveError(null);
    setHistoryError(null);
    try {
      const path = `/worlds/${currentWorldId}/chapters/${activeChapter.id}`;
      const res = await apiFetch<{ job_id?: string }>(versionId ? `${path}/versions/${versionId}/restore` : path, {
        method: versionId ? 'POST' : 'PUT',
        ...(versionId ? {} : { body: JSON.stringify({ title: activeChapter.title, content }) }),
      });
      const confirmed = await apiFetch<{ content: string }>(path);
      if (confirmed.content !== content) throw new Error('The backend did not confirm this chapter text. Your draft has been kept.');
      updateChapterContent(manuscript.id, activeChapter.id, confirmed.content);
      setEditorContent(confirmed.content);
      dirty.current = false;
      setIsEditing(false);
      setShowHistory(false);
      if (res.job_id) {
        setIsExtracting(true);
        setExtractionStatus('Chapter saved. Re-extracting proposed changes…');
        setExtractionJobId(res.job_id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not confirm the saved chapter.';
      if (versionId) setHistoryError(message);
      else { setSaveError(message); setIsEditing(true); }
    } finally { setIsSaving(false); }
  };
  const handleSaveEdit = () => persistChapter(editorContent);
  const handleRerunExtraction = () => persistChapter(isEditing ? editorContent : activeChapter?.content || '');

  const handleCreateChapter = async () => {
    const title = prompt('Enter new chapter title:');
    if (title && title.trim()) {
      const nextNum = (manuscript?.chapters.length || 0) + 1;
      let newChapter = {
        id: '',
        number: nextNum,
        title: title.trim(),
        content: '',
        wordCount: 0
      };

      if (currentWorldId && currentManuscriptId) {
        try {
          const res = await apiFetch<any>(`/worlds/${currentWorldId}/manuscripts/${currentManuscriptId}/chapters`, {
            method: 'POST',
            body: JSON.stringify({
              chapter_number: nextNum,
              title: title.trim(),
              content: ''
            })
          });
          newChapter.id = res.id;
          newChapter.number = res.chapter_number;
          newChapter.title = res.title;
          if (res.content) newChapter.content = res.content;
        } catch (err: any) {
          alert('Failed to create chapter: ' + err.message);
          return;
        }
      }

      if (manuscript) {
        const updated = [...manuscript.chapters, newChapter];
        const updatedManuscripts = manuscripts.map(m =>
          m.id === manuscript.id ? { ...m, chapters: updated } : m
        );
        useWorldStore.setState({ manuscripts: updatedManuscripts, activeChapterId: newChapter.id });
      }
    }
  };

  const handleDeleteChapter = (e: React.MouseEvent, chapterId: string) => {
    e.stopPropagation();
    setDeleteConfirmId(chapterId);
  };

  const executeDeleteChapter = async () => {
    if (!deleteConfirmId) return;
    const chapterId = deleteConfirmId;

    if (currentWorldId) {
      try {
        await apiFetch(`/worlds/${currentWorldId}/chapters/${chapterId}`, {
          method: 'DELETE'
        });
      } catch (err: any) {
        alert('Failed to delete chapter: ' + err.message);
        setDeleteConfirmId(null);
        return;
      }
    }

    if (manuscript) {
      const remaining = manuscript.chapters.filter(c => c.id !== chapterId);
      deleteChapter(manuscript.id, chapterId);
      if (remaining.length === 0) {
        navigate(`/worlds/${currentWorldId}/manuscripts`);
      } else if (activeChapterId === chapterId) {
        setActiveChapter(remaining[0]?.id || null);
      }
    }
    setDeleteConfirmId(null);
  };

  const handleViewHistory = async () => {
    if (!activeChapter || !currentWorldId) return;
    setShowHistory(true);
    setSelectedVersion(null);
    setHistoryError(null);
    setHistoryLoading(true);
    try { setHistoryVersions(await getChapterVersions(currentWorldId, activeChapter.id)); }
    catch (error) { setHistoryError(error instanceof Error ? error.message : 'Could not load history.'); }
    finally { setHistoryLoading(false); }
  };
  const inspectVersion = async (version: ChapterVersion) => {
    if (!currentWorldId || !activeChapter) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try { setSelectedVersion(await getChapterVersion(currentWorldId, activeChapter.id, version.id)); }
    catch (error) { setHistoryError(error instanceof Error ? error.message : 'Could not load version text.'); }
    finally { setHistoryLoading(false); }
  };

  // Helper to split text by entity names and inject interactive highlight tags
  const renderTextWithHighlights = (text: string) => {
    if (!text) return null;
    const activeEntities = entities;

    if (activeEntities.length === 0) return <span>{text}</span>;

    const sortedEntityNames = [...activeEntities]
      .map(e => e.name)
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);

    if (sortedEntityNames.length === 0) return <span>{text}</span>;

    const escapedNames = sortedEntityNames.map(name =>
      name.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')
    );

    const regex = new RegExp(`\\b(${escapedNames.join('|')})\\b`, 'gi');
    const parts = text.split(regex);
    if (parts.length <= 1) return <span>{text}</span>;

    return (
      <span>
        {parts.map((part, index) => {
          const matchedEntity = activeEntities.find(
            e => e.name.toLowerCase() === part.toLowerCase()
          );

          if (matchedEntity) {
            return (
              <span
                key={index}
                className="entity-highlight text-starlight-white font-medium cursor-pointer hover:underline"
                title={`${matchedEntity.type.toUpperCase()}: Click to view profile`}
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.getSelection()?.toString().trim()) return;
                  setActiveEntity(matchedEntity.id);
                }}
              >
                {part}
              </span>
            );
          }
          return part;
        })}
      </span>
    );
  };

  return (
    <AppShell>
      {/* Editor Main Section */}
      <main className="writing-layout">

        {/* Left internal sidebar: Chapters List */}
        {chaptersOpen && <aside aria-label="Chapter index" className="writing-chapters">
          <div className="p-4 border-b border-starlight-white/5 flex items-center justify-between bg-gradient-to-b from-surface-container-highest/20 to-transparent">
            <h2 className="font-headline-md text-xl text-on-surface">Codex Folio</h2><button aria-label="Close chapter index" className="text-on-surface-variant md:hidden" onClick={() => setChaptersOpen(false)}><span className="material-symbols-outlined text-base">close</span></button>
            <button
              aria-label="Create chapter" onClick={handleCreateChapter}
              className="text-on-surface-variant/65 hover:text-primary transition-colors p-1"
            >
              <span className="material-symbols-outlined text-sm font-light">add</span>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {manuscript?.chapters.map((ch) => {
              const isActive = ch.id === (activeChapterId || activeChapter?.id);
              return (
                <div
                  key={ch.id}
                  onClick={() => {
                    if (isSaving) return;
                    if (isEditing && dirty.current && !window.confirm('Discard the unsaved changes in this chapter?')) return;
                    setActiveChapter(ch.id);
                    setIsEditing(false);
                    if (window.innerWidth < 768) setChaptersOpen(false);
                  }}
                  className={`group px-4 py-3 rounded-lg relative overflow-hidden cursor-pointer transition-all duration-300 border ${
                    isActive
                      ? 'bg-surface-container-low border-starlight-white/10 text-starlight-white'
                      : 'border-transparent text-on-surface-variant/75 hover:bg-surface-container-lowest/50 hover:text-on-surface'
                  }`}
                >
                  {isActive && (
                    <>
                      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/5 via-transparent to-transparent opacity-50"></div>
                      <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary"></div>
                    </>
                  )}
                  <div className={`font-label-sm text-[10px] uppercase tracking-wider mb-1 flex justify-between items-center ${isActive ? 'text-primary' : 'text-on-surface-variant/40'}`}>
                    <span>Chapter {ch.number}</span>
                    <button
                      onClick={(e) => handleDeleteChapter(e, ch.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-red-400"
                      title="Delete Chapter"
                    >
                      <span className="material-symbols-outlined text-[14px]">delete</span>
                    </button>
                  </div>
                  <div className="font-body-md text-sm font-medium pr-4">{ch.title}</div>
                </div>
              );
            })}
          </div>
        </aside>}

        {/* Right main panel: Editor Canvas */}
        <section className="flex-1 flex flex-col relative overflow-hidden">



          {/* Action Bar */}
          <div className="writing-toolbar">
            <div className="flex flex-wrap items-center gap-2">
              <button className="studio-secondary" aria-label="Toggle chapters" aria-expanded={chaptersOpen} onClick={() => setChaptersOpen(value => !value)}><span className="material-symbols-outlined text-base">menu_book</span></button>
              {isEditing ? (
                <>
                  <button
                    disabled={isSaving} onClick={handleSaveEdit}
                    className="px-5 py-1.5 rounded-full bg-primary hover:bg-copper-glow text-void-black font-label-sm text-xs font-semibold uppercase tracking-widest transition-all duration-300 shadow-md"
                  >
                    {isSaving ? 'Saving…' : 'Save Changes'}
                  </button>
                  <button
                    disabled={isSaving} onClick={handleCancelEdit}
                    className="px-4 py-1.5 rounded-full border border-starlight-white/10 text-on-surface-variant/80 hover:text-starlight-white hover:border-starlight-white/30 font-label-sm text-xs font-semibold uppercase tracking-widest transition-all duration-300"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  disabled={isSaving} onClick={handleStartEdit}
                  className="px-5 py-1.5 rounded-full border border-copper-glow/50 text-copper-glow font-label-sm text-xs font-semibold uppercase tracking-widest hover:bg-copper-glow hover:text-void-black transition-all duration-300"
                >
                  Edit Text
                </button>
              )}

              <button
                onClick={handleRerunExtraction}
                disabled={isExtracting || isSaving}
                className="px-4 py-1.5 rounded-full text-on-surface-variant/80 font-label-sm text-xs uppercase tracking-wider hover:text-primary hover:bg-primary/5 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                <span className={`material-symbols-outlined text-[16px] font-light ${isExtracting ? 'animate-spin' : ''}`}>
                  {isExtracting ? 'sync' : 'refresh'}
                </span>
                {isExtracting ? 'Extracting...' : 'Re-run Extraction'}
              </button>

              {!isEditing && (
                <button
                  aria-label="History" onClick={handleViewHistory}
                  className="px-4 py-1.5 rounded-full text-on-surface-variant/80 font-label-sm text-xs uppercase tracking-wider hover:text-primary hover:bg-primary/5 transition-all flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-[16px] font-light">history</span>
                  History
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3 text-on-surface-variant/60 text-[10px]">
              <button className="hover:text-primary" aria-pressed={focusMode} onClick={() => { setFocusMode(value => !value); setChaptersOpen(focusMode); setPassageOpen(focusMode); }}>Sanctuary Focus</button>
              <button className="hover:text-primary" aria-expanded={passageOpen} onClick={() => setPassageOpen(value => !value)}>Astrolabe</button>
              <span>Words: {activeChapter?.wordCount.toLocaleString()}</span>
              <span>•</span>
              <span>{isSaving ? 'Saving' : isEditing ? 'Unsaved draft' : isExtracting ? 'Re-extracting' : 'Saved'}</span>
            </div>
          </div>

          {saveError && <p role="alert" className="border-b border-error/20 bg-error/5 px-6 py-3 text-sm text-error">{saveError}</p>}
          {/* Reading/Editing Area */}
          {currentWorldId && activeChapter && <ChapterSelectionActions key={`${currentWorldId}:${activeChapter.id}`} worldId={currentWorldId} chapterId={activeChapter.id} readingRef={readingRef} textareaRef={textareaRef} isEditing={isEditing} />}
          <div className="writing-paper">
            <article className="max-w-3xl mx-auto pb-48">

              {/* Header Title */}
              <header className="mb-12 select-none">
                <span className="font-label-sm text-[10px] text-primary uppercase tracking-[0.2em] mb-3 block">
                  Chapter {activeChapter?.number}
                </span>
                <h1 className="font-display-lg text-display-lg text-starlight-white mb-6">
                  {activeChapter?.title}
                </h1>
                <div className="h-px w-24 bg-gradient-to-r from-copper-glow to-transparent opacity-50"></div>
              </header>

              {/* Editable Textbox or Formatted View */}
              {isEditing ? (
                <textarea
                  aria-label="Chapter text" disabled={isSaving} ref={textareaRef}
                  value={editorContent}
                  onChange={(e) => {
                    dirty.current = true;
                    setEditorContent(e.target.value);
                    adjustTextareaHeight();
                  }}
                  className="w-full bg-transparent border-0 text-body-lg text-on-surface-variant leading-relaxed focus:ring-0 focus:outline-none resize-none overflow-hidden"

                />
              ) : (
                <div
                  ref={readingRef}
                  className="prose prose-invert prose-lg font-body-lg text-body-lg text-on-surface-variant leading-relaxed space-y-8 select-text"

                >
                  {(() => {
                    const cited = activeChapter && activeChapter.id === linkedChapterId && linkEnd > linkStart
                      ? { start: linkStart, end: linkEnd } : null;
                    let offset = 0;                                   // each '\n\n' separator is 2 characters
                    return activeChapter?.content.split('\n\n').map((paragraph, index) => {
                      const from = offset;
                      offset += paragraph.length + 2;
                      if (!cited || cited.start >= from + paragraph.length || cited.end <= from) {
                        return <p key={index}>{renderTextWithHighlights(paragraph)}</p>;
                      }
                      const a = Math.max(0, cited.start - from), b = Math.min(paragraph.length, cited.end - from);
                      return (
                        <p key={index} id="orion-cited">
                          {renderTextWithHighlights(paragraph.slice(0, a))}
                          <mark className="bg-error/20 text-starlight-white border-b-2 border-error rounded-sm px-0.5">
                            {paragraph.slice(a, b)}
                          </mark>
                          {renderTextWithHighlights(paragraph.slice(b))}
                        </p>
                      );
                    });
                  })()}
                </div>
              )}

            </article>
          </div>

        </section>
        {passageOpen && <aside aria-label="Passage astrolabe" className="absolute inset-y-0 right-0 z-30 w-72 max-w-[90vw] overflow-y-auto border-l border-white/5 bg-surface-container-lowest p-5 xl:static xl:shrink-0">
          <div className="mb-6 flex items-center justify-between"><span className="studio-eyebrow mb-0">Passage Astrolabe</span><button aria-label="Close passage astrolabe" onClick={() => setPassageOpen(false)}><span className="material-symbols-outlined text-base">close</span></button></div>
          <p className="mb-5 text-xs text-on-surface-variant/60">Entities named in this chapter</p>
          {entities.filter(entity => activeChapter?.content.toLowerCase().includes(entity.name.toLowerCase())).map(entity => <button key={entity.id} onClick={() => setActiveEntity(entity.id)} className="mb-3 block w-full rounded border border-white/5 bg-surface-container p-4 text-left hover:border-primary/30"><span className="text-[10px] uppercase tracking-widest text-primary">{entity.type}</span><span className="mt-2 block font-headline-md text-xl">{entity.name}</span><span className="mt-2 line-clamp-3 block text-xs leading-relaxed text-on-surface-variant/70">{entity.description || 'Open the codex to inspect facts and relationships.'}</span></button>)}
          <button className="studio-secondary mt-5 w-full" onClick={() => navigate(`/worlds/${currentWorldId}/assistant`)}><span className="material-symbols-outlined text-base">forum</span>Character dialogue</button>
        </aside>}
      </main>

      {showHistory && <Dialog title="Chapter History" onClose={() => { if (!isSaving) setShowHistory(false); }}>
        <p className="mb-5 text-sm leading-relaxed text-on-surface-variant/70">Inspect a saved version, then restore it as a new version. Existing history stays intact; extracted changes still need your review.</p>
        {historyError && <p role="alert" className="mb-4 text-sm text-error">{historyError}</p>}
        {historyLoading && <p role="status" className="mb-3 text-sm text-on-surface-variant">Loading version…</p>}
        {!historyLoading && historyVersions.length === 0 && <p>No history available.</p>}
        <div className="space-y-2">{historyVersions.map(version => <button disabled={isSaving || historyLoading} key={version.id} onClick={() => inspectVersion(version)} className="studio-secondary flex w-full justify-between text-left"><span>Version {version.version_number} {version.is_current ? '(Current)' : ''}</span><span className="text-[11px] text-on-surface-variant/60">{new Date(version.created_at).toLocaleString()}</span></button>)}</div>
        {selectedVersion && <section className="mt-6 border-t border-white/10 pt-5"><h3 className="mb-3 font-headline-md text-xl">Version {selectedVersion.version_number} text</h3><pre className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded bg-surface-container-lowest p-4 font-body-lg text-lg leading-relaxed text-on-surface-variant">{selectedVersion.content}</pre><button disabled={isSaving || selectedVersion.is_current || historyLoading} className="studio-primary mt-5" onClick={() => persistChapter(selectedVersion.content, selectedVersion.id)}>{isSaving ? 'Restoring…' : `Restore Version ${selectedVersion.version_number}`}</button></section>}
      </Dialog>}

      {review && (
        <ProposalReviewModal
          worldId={currentWorldId}
          chapterNumber={review.chapter_number}
          proposals={review.proposals}
          onClose={(applied) => {
            setReview(null);
            if (applied) {
              useWorldStore.getState().fetchEntitiesForWorld(currentWorldId);
              setExtractionStatus('Changes applied to your world.');
              setTimeout(() => setExtractionStatus(null), 3000);
            }
          }}
        />
      )}

      {/* Floating Extraction Toast */}
      <div
        className={`fixed bottom-8 right-8 z-50 flex items-center gap-3 px-5 py-3 rounded-xl bg-surface-container-high/90 backdrop-blur-md border border-primary/30 shadow-[0_8px_32px_rgba(235,166,134,0.15)] transition-all duration-500 transform ${
          extractionStatus ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0 pointer-events-none'
        }`}
      >
<span className={`material-symbols-outlined text-primary text-xl ${isExtracting ? 'animate-spin' : ''}`}>{isExtracting ? 'refresh' : 'info'}</span>
        <span role={extractionStatus ? 'status' : undefined} className="max-w-lg text-sm text-starlight-white">{extractionStatus}</span>
        {extractionJobId ? <button className="shrink-0 text-xs text-primary" onClick={() => cancelJob(extractionJobId).catch(error => setSaveError(error.message))}>Cancel extraction</button> : <button aria-label="Dismiss extraction status" onClick={() => setExtractionStatus(null)}><span className="material-symbols-outlined text-base">close</span></button>}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-void-black/80 backdrop-blur-sm">
          <div className="bg-surface-container-high border border-primary/30 rounded-xl shadow-[0_8px_32px_rgba(235,166,134,0.15)] max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="font-headline-sm text-starlight-white flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">warning</span>
              Delete Chapter
            </h3>
            <p className="text-on-surface-variant text-sm leading-relaxed">
              Are you sure you want to delete this chapter? This action cannot be undone and will permanently remove its content.
            </p>
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="px-4 py-2 rounded-lg font-label-sm text-sm text-starlight-white/70 hover:text-starlight-white hover:bg-surface-container-highest transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={executeDeleteChapter}
                className="px-4 py-2 rounded-lg font-label-sm text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors shadow-md"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
};

