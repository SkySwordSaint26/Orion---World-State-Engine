import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';

interface LogItem {
  id: string;
  type: 'create' | 'edit' | 'link';
  title: string;
  detail: string;
  time: string;
}

export const WorldHome: React.FC = () => {
  const navigate = useNavigate();
  const { worldId } = useParams<{ worldId: string }>();
  const { worlds, addEntity, entities, contradictions, fetchEntitiesForWorld, fetchContradictionsForWorld, manuscripts, fetchManuscriptsForWorld, setActiveManuscript, setActiveChapter } = useWorldStore();

  const world = worlds.find((w) => w.id === worldId);

  useEffect(() => {                   // the counts below come from this world's API data, not the store's leftovers
    if (worldId) {
      fetchEntitiesForWorld(worldId);
      fetchContradictionsForWorld(worldId);
      fetchManuscriptsForWorld(worldId);
    }
  }, [worldId, fetchEntitiesForWorld, fetchContradictionsForWorld, fetchManuscriptsForWorld]);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'character' | 'location' | 'object'>('character');
  const [entityName, setEntityName] = useState('');
  const [entitySubtype, setEntitySubtype] = useState('');
  const [entityDesc, setEntityDesc] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Activity logs: this session's actions only (the backend keeps no activity log)
  const [activityLogs, setActivityLogs] = useState<LogItem[]>([]);

  const handleOpenModal = (type: typeof modalType) => {
    setModalType(type);
    setEntityName('');
    setEntitySubtype('');
    setEntityDesc('');
    setCreateError(null);
    setIsModalOpen(true);
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
          type: modalType,
          subtype: entitySubtype.trim() || undefined,
          description: entityDesc.trim()
        });

        // Add to activity log after the API confirms the write.
        const newLog: LogItem = {
          id: `act-${Date.now()}`,
          type: 'create',
          title: `${modalType.charAt(0).toUpperCase() + modalType.slice(1)} Forged`,
          detail: entityName.trim(),
          time: 'Just now'
        };
        setActivityLogs((prev) => [newLog, ...prev]);

        setIsModalOpen(false);
      } catch (err) {
        setCreateError(err instanceof Error ? err.message : 'Failed to create entity.');
      } finally {
        setIsCreating(false);
      }
    }
  };

  const activeContradictions = contradictions.filter(c => !c.resolved && c.status !== 'DISMISSED').length;
  const latestManuscript = manuscripts[0];
  const latestChapter = latestManuscript?.chapters[0];
  const openWritingRoom = () => {
    if (!latestManuscript || !latestChapter) { navigate(`/worlds/${worldId}/manuscripts`); return; }
    setActiveManuscript(latestManuscript.id); setActiveChapter(latestChapter.id);
    navigate(`/worlds/${worldId}/manuscripts/${latestManuscript.id}`);
  };

  return (
    <AppShell>
      {/* Background ambient lighting overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-surface-container-high/20 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="studio-page">
        <div className="studio-page-inner space-y-9">
          <header className="studio-world-cover rounded-lg border border-white/5 p-7 md:p-9">
            <span className="studio-eyebrow">Archival codex · Your sovereign world</span>
            <div className="flex flex-wrap items-end justify-between gap-6"><div className="max-w-3xl"><h1 className="studio-title">{world?.name || 'Your world'}</h1><p className="studio-intro">{world?.description || 'An unwritten horizon, ready for the first pages of its history.'}</p></div><button className="studio-primary" onClick={openWritingRoom}><span className="material-symbols-outlined text-base">history_edu</span>Open writing room</button></div>
            <div className="mt-7 flex flex-wrap gap-x-7 gap-y-3 border-t border-white/5 pt-5 text-xs text-on-surface-variant/80"><span>{manuscripts.length} manuscripts</span><span>{entities.filter(entity => entity.type === 'character').length} characters</span><span>{entities.filter(entity => entity.type === 'location').length} locations</span><span>{entities.length} lore nodes</span><button className="text-error hover:underline" onClick={() => navigate(`/worlds/${worldId}/contradictions`)}>{activeContradictions} open contradictions</button></div>
          </header>
          <section><span className="studio-eyebrow">Codex portals · The pillars of memory</span><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { path: 'manuscripts', icon: 'history_edu', title: 'Manuscripts', note: `${manuscripts.length} bound manuscripts` },
              { path: 'graph', icon: 'hub', title: 'World Graph', note: 'Relationships, covenants and connections' },
              { path: 'timeline', icon: 'hourglass_empty', title: 'Timeline', note: 'The narrative, chapter by chapter' },
              { path: 'contradictions', icon: 'balance', title: 'Contradictions', note: `${activeContradictions} awaiting your decision` },
            ].map((portal, index) => <button key={portal.path} onClick={() => navigate(`/worlds/${worldId}/${portal.path}`)} className="studio-card p-6 text-left transition-colors hover:border-primary/30"><div className="flex items-center justify-between text-primary"><span className="material-symbols-outlined">{portal.icon}</span><span className="text-[10px] text-on-surface-variant/40">0{index + 1} ↗</span></div><h2 className="mt-6 font-headline-md text-2xl">{portal.title}</h2><p className="mt-2 text-xs leading-relaxed text-on-surface-variant/60">{portal.note}</p></button>)}
          </div></section>
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,1fr)]">
            <section className="studio-card p-7"><span className="studio-eyebrow">The manuscript hearth</span><h2 className="font-headline-md text-3xl">{latestChapter ? `Chapter ${latestChapter.number}: ${latestChapter.title}` : 'Every legend begins with a page.'}</h2><p className="mt-4 font-body-lg text-xl leading-relaxed text-on-surface-variant/80">{latestChapter?.content ? latestChapter.content.slice(0, 500) : latestManuscript ? `Open ${latestManuscript.title} and continue shaping your chronicle.` : 'Bring your manuscript into the archive, or start by inscribing its characters, places and objects.'}</p><div className="mt-7 flex flex-wrap gap-3"><button className="studio-primary" onClick={openWritingRoom}>{latestManuscript ? 'Continue writing' : 'Import manuscript'}<span className="material-symbols-outlined text-base">arrow_forward</span></button><button className="studio-secondary" onClick={() => navigate(`/worlds/${worldId}/world`)}>World Ledger</button></div></section>
            <section className="studio-card p-6"><span className="studio-eyebrow">Inscribe the world</span><h2 className="mb-5 font-headline-md text-2xl">A name, a place, a possibility.</h2><div className="grid grid-cols-2 gap-3">{(['character', 'location', 'object'] as const).map(type => <button key={type} onClick={() => handleOpenModal(type)} className="studio-secondary capitalize">{type}</button>)}<button className="studio-secondary" onClick={() => navigate(`/worlds/${worldId}/timeline`)}>Timeline</button></div><button className="studio-secondary mt-5 w-full" onClick={() => navigate(`/worlds/${worldId}/assistant`)}><span className="material-symbols-outlined text-base">forum</span>Character dialogue</button></section>
          </div>
          <section className="border-t border-white/5 pt-6"><div className="mb-4 flex items-center justify-between"><h2 className="font-headline-md text-2xl">Archive Log</h2><span className="text-[10px] uppercase tracking-widest text-on-surface-variant/50">This session</span></div>{activityLogs.length === 0 ? <p className="text-sm text-on-surface-variant/50">New inscriptions from this session will appear here.</p> : <ul className="space-y-3">{activityLogs.map(log => <li key={log.id} className="flex items-center gap-4 text-sm"><span className="material-symbols-outlined text-base text-primary">add</span><span>{log.title} · {log.detail}</span><span className="ml-auto text-xs text-on-surface-variant/50">{log.time}</span></li>)}</ul>}</section>
        </div>
      </main>

      {/* Creation Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-void-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-gutter">
          <div className="bg-surface-container-low border border-starlight-white/10 rounded-xl max-w-lg w-full p-6 shadow-2xl relative animate-fade-in-up">
            <button 
              onClick={() => setIsModalOpen(false)}
              className="absolute top-4 right-4 text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5"
            >
              <span className="material-symbols-outlined font-light">close</span>
            </button>
            
            <h2 className="font-headline-md text-headline-md text-primary mb-2 capitalize">
              Forge New {modalType}
            </h2>
            <p className="text-xs text-on-surface-variant/60 mb-6">
              Create a new entity in the ledger. It will instantly link with manuscripts, timelines, and graphs.
            </p>

            <form onSubmit={handleForgeEntity} className="space-y-4">
              <div>
                <label className="block text-xs font-label-sm text-on-surface-variant/80 uppercase mb-2">Name</label>
                <input 
                  type="text"
                  required
                  maxLength={255}
                  value={entityName}
                  onChange={(e) => setEntityName(e.target.value)}
                  placeholder={`e.g. ${modalType === 'character' ? 'Valerius Thorne' : modalType === 'location' ? 'The Iron Valley' : 'Aetheric compass'}`}
                  className="w-full bg-void-black text-sm text-starlight-white border border-starlight-white/10 rounded p-2.5 focus:border-primary focus:ring-0 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-label-sm text-on-surface-variant/80 uppercase mb-2">Subtype / Role</label>
                <input 
                  type="text"
                  value={entitySubtype}
                  onChange={(e) => setEntitySubtype(e.target.value)}
                  placeholder={`e.g. ${modalType === 'character' ? 'Antagonist / Trader' : modalType === 'location' ? 'Syndicate Outpost' : 'Key Lore Item'}`}
                  className="w-full bg-void-black text-sm text-starlight-white border border-starlight-white/10 rounded p-2.5 focus:border-primary focus:ring-0 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-label-sm text-on-surface-variant/80 uppercase mb-2">Description / Synopsis</label>
                <textarea 
                  required
                  value={entityDesc}
                  onChange={(e) => setEntityDesc(e.target.value)}
                  placeholder="Enter a brief history or description..."
                  rows={3}
                  className="w-full bg-void-black text-sm text-starlight-white border border-starlight-white/10 rounded p-2.5 focus:border-primary focus:ring-0 focus:outline-none"
                />
              </div>

              {createError && <p role="alert" className="text-sm text-error">{createError}</p>}
              <div className="flex justify-end gap-3 pt-4 border-t border-starlight-white/5">
                <button 
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-label-sm uppercase tracking-widest text-on-surface-variant hover:text-white"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  disabled={isCreating}
                  className="px-6 py-2 bg-primary hover:bg-copper-glow text-void-black font-label-sm text-xs uppercase tracking-widest font-semibold rounded shadow-lg hover:shadow-primary/10 transition-all"
                >
                  {isCreating ? 'Creating...' : 'Forge Entity'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
