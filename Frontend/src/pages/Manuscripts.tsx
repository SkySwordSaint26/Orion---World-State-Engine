import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { apiFetch } from '../api/client';

export const Manuscripts: React.FC = () => {
  const navigate = useNavigate();
  const { worldId } = useParams<{ worldId: string }>();
  const { 
    manuscripts, 
    setActiveManuscript, 
    setActiveChapter,
    fetchManuscriptsForWorld,
    deleteChapter
  } = useWorldStore();

  const [expandedManuscriptId, setExpandedManuscriptId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadToast, setUploadToast] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{manuscriptId: string, chapterId: string} | null>(null);

  useEffect(() => {
    if (worldId) {
      if (manuscripts.length === 0) {
        setLoading(true);
      }
      fetchManuscriptsForWorld(worldId).finally(() => setLoading(false));
    }
  }, [worldId, fetchManuscriptsForWorld]);

  const displayedList = manuscripts.filter(m => m.chapters.length > 0);

  useEffect(() => {
    if (displayedList.length > 0) {
      if (!expandedManuscriptId || !displayedList.some(m => m.id === expandedManuscriptId)) {
        setExpandedManuscriptId(displayedList[0].id);
      }
    } else {
      setExpandedManuscriptId(null);
    }
  }, [displayedList, expandedManuscriptId]);

  const handleToggleManuscript = (id: string) => {
    setExpandedManuscriptId(expandedManuscriptId === id ? null : id);
  };

  const handleOpenChapter = (manuscriptId: string, chapterId: string) => {
    setActiveManuscript(manuscriptId);
    setActiveChapter(chapterId);
    navigate(`/worlds/${worldId}/manuscripts/${manuscriptId}`);
  };

  const handleAddManuscript = async () => {
    if (isUploading) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.pdf,.docx,.epub';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file && worldId) {
        setIsUploading(true);
        const formData = new FormData();
        formData.append('file', file);
        try {
          const res = await apiFetch<any>(`/worlds/${worldId}/manuscripts`, {
            method: 'POST',
            body: formData,
          });
          const fresh = await fetchManuscriptsForWorld(worldId);
          if (res.manuscript_id) {
            setExpandedManuscriptId(res.manuscript_id);
          } else if (fresh.length > 0) {
            setExpandedManuscriptId(fresh[fresh.length - 1].id);
          }
          setUploadToast(`"${file.name}" uploaded successfully. Chapters are ready!`);
          setTimeout(() => {
            setUploadToast(null);
          }, 5000);
        } catch (err: any) {
          alert(err.message || "Upload failed");
        } finally {
          setIsUploading(false);
        }
      }
    };
    input.click();
  };

  const handleDeleteChapter = (e: React.MouseEvent, manuscriptId: string, chapterId: string) => {
    e.stopPropagation();
    setDeleteConfirm({ manuscriptId, chapterId });
  };

  const executeDeleteChapter = async () => {
    if (!deleteConfirm) return;
    const { manuscriptId, chapterId } = deleteConfirm;
    
    if (worldId && !worldId.startsWith('terra-')) {
      try {
        await apiFetch(`/worlds/${worldId}/chapters/${chapterId}`, {
          method: 'DELETE'
        });
      } catch (err: any) {
        alert('Failed to delete chapter: ' + err.message);
        setDeleteConfirm(null);
        return;
      }
    }

    deleteChapter(manuscriptId, chapterId);
    setDeleteConfirm(null);
  };

  return (
    <AppShell>
      {/* Background elements */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-deep-charcoal/40 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="flex-1 min-h-screen overflow-y-auto px-8 md:px-12 py-10">
        <div className="max-w-5xl mx-auto flex flex-col gap-8 animate-fade-in-up">
          
          {/* Header */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 border-b border-starlight-white/5 pb-6">
            <div>
              <span className="font-label-sm text-[10px] text-primary uppercase tracking-[0.2em] mb-1.5 block">Chronicle Library</span>
              <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-starlight-white mb-2">Manuscripts Archive</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant/80 max-w-2xl leading-relaxed">
                Organize your primary texts. Extract entities into the world ledger automatically.
              </p>
            </div>
            <div className="flex items-center gap-4 shrink-0">
              <button 
                onClick={handleAddManuscript}
                disabled={isUploading}
                className="flex items-center gap-2 font-label-sm text-xs text-copper-glow border border-copper-glow/50 rounded px-5 py-2.5 hover:bg-copper-glow hover:text-void-black transition-all uppercase tracking-wider font-semibold shadow-lg hover:shadow-primary/10 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span className={`material-symbols-outlined text-sm font-light ${isUploading ? 'animate-spin' : ''}`}>
                  {isUploading ? 'refresh' : 'add'}
                </span>
                {isUploading ? 'Uploading...' : 'Upload Manuscript'}
              </button>
            </div>
          </div>

          {loading ? (
            <div className="py-20 text-center text-sm text-copper-glow flex items-center justify-center gap-2">
              <span className="material-symbols-outlined animate-spin">refresh</span>
              <span>Loading manuscripts archive...</span>
            </div>
          ) : displayedList.length === 0 ? (
            <div className="py-20 text-center text-on-surface-variant/60 flex flex-col items-center justify-center gap-3 border border-dashed border-starlight-white/10 rounded-xl p-8">
              <span className="material-symbols-outlined text-4xl text-on-surface-variant/30 font-light">menu_book</span>
              <p className="font-body-md text-sm text-on-surface-variant/70">No manuscripts in archive.</p>
              <p className="font-label-sm text-xs text-on-surface-variant/40">Upload a manuscript text file to extract chapters and begin building your world ledger.</p>
            </div>
          ) : (
            /* Tree list */
            <div className="flex flex-col gap-6 w-full">
              {displayedList.map((ms) => {
                const isExpanded = expandedManuscriptId === ms.id;
                const totalWords = ms.chapters.reduce((sum, ch) => sum + ch.wordCount, 0);

                return (
                  <div 
                    key={ms.id}
                    className="bg-surface-container-low/50 border border-starlight-white/10 rounded-lg overflow-hidden hover-glow transition-all duration-300 shadow-md"
                  >
                    {/* Folder Header */}
                    <div 
                      onClick={() => handleToggleManuscript(ms.id)}
                      className="flex items-center justify-between p-4 cursor-pointer group border-b border-starlight-white/5 bg-gradient-to-b from-surface-container-highest/20 to-transparent"
                    >
                      <div className="flex items-center gap-4">
                        <span className="material-symbols-outlined text-primary text-xl font-light">
                          {isExpanded ? 'folder_open' : 'folder'}
                        </span>
                        <div>
                          <h3 className="font-headline-md text-headline-md text-starlight-white group-hover:text-primary transition-colors text-lg">
                            {ms.title}
                          </h3>
                          <p className="font-label-sm text-[10px] text-on-surface-variant/40 uppercase tracking-widest mt-1">
                            {ms.chapters.length} {ms.chapters.length === 1 ? 'Chapter' : 'Chapters'} • {totalWords.toLocaleString()} words total
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Chapters List */}
                    {isExpanded && (
                      <div className="py-2 px-6 ml-6 relative">
                        <div className="absolute left-0 top-0 bottom-0 w-px bg-starlight-white/10" />

                        {ms.chapters.map((ch) => (
                          <div 
                            key={ch.id} 
                            onClick={() => handleOpenChapter(ms.id, ch.id)}
                            className="flex items-center justify-between py-3 relative group cursor-pointer"
                          >
                            <div className="absolute -left-6 top-1/2 w-6 h-px bg-starlight-white/10" />
                            
                            <div className="flex items-center gap-4 pl-4">
                              <span className="material-symbols-outlined text-on-surface-variant/60 text-lg font-light">description</span>
                              <div>
                                <h4 className="font-body-md text-sm text-inverse-surface group-hover:text-primary transition-colors">
                                  Chapter {ch.number}: {ch.title}
                                </h4>
                                <p className="font-label-sm text-[10px] text-on-surface-variant/50 uppercase tracking-wider mt-0.5">
                                  {ch.wordCount.toLocaleString()} words
                                </p>
                              </div>
                            </div>

                            <div className="flex items-center gap-4">
                              <div className="flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] uppercase font-label-sm bg-emerald-500/5 text-emerald-400/80 border-emerald-500/20">
                                <span className="w-1 h-1 rounded-full bg-current"></span>
                                Extracted
                              </div>
                              <button 
                                onClick={(e) => handleDeleteChapter(e, ms.id, ch.id)}
                                className="text-on-surface-variant/30 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 p-1"
                                title="Delete Chapter"
                              >
                                <span className="material-symbols-outlined text-sm">delete</span>
                              </button>
                              <span className="material-symbols-outlined text-sm text-on-surface-variant/30 group-hover:text-primary transition-colors">edit</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

        </div>
      </main>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
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
                onClick={() => setDeleteConfirm(null)}
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

      {/* Upload Toast */}
      <div 
        className={`fixed bottom-8 right-8 z-50 flex items-center gap-3 px-5 py-3 rounded-xl bg-surface-container-high/90 backdrop-blur-md border border-primary/30 shadow-[0_8px_32px_rgba(235,166,134,0.15)] transition-all duration-500 transform ${
          uploadToast ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0 pointer-events-none'
        }`}
      >
        <span className="material-symbols-outlined text-primary text-xl">check_circle</span>
        <span className="font-label-sm text-sm text-starlight-white tracking-wide">{uploadToast}</span>
      </div>
    </AppShell>
  );
};
