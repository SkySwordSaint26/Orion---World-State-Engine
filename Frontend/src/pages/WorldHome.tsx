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
  const { worlds, addEntity, entities, contradictions, fetchEntitiesForWorld, fetchContradictionsForWorld } = useWorldStore();

  const world = worlds.find((w) => w.id === worldId);

  useEffect(() => {                   // the counts below come from this world's API data, not the store's leftovers
    if (worldId) {
      fetchEntitiesForWorld(worldId);
      fetchContradictionsForWorld(worldId);
    }
  }, [worldId, fetchEntitiesForWorld, fetchContradictionsForWorld]);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'character' | 'location' | 'object' | 'event'>('character');
  const [entityName, setEntityName] = useState('');
  const [entitySubtype, setEntitySubtype] = useState('');
  const [entityDesc, setEntityDesc] = useState('');

  // Activity logs: this session's actions only (the backend keeps no activity log)
  const [activityLogs, setActivityLogs] = useState<LogItem[]>([]);

  const handleOpenModal = (type: typeof modalType) => {
    setModalType(type);
    setEntityName('');
    setEntitySubtype('');
    setEntityDesc('');
    setIsModalOpen(true);
  };

  const handleForgeEntity = (e: React.FormEvent) => {
    e.preventDefault();
    if (entityName.trim() && entityDesc.trim()) {
      addEntity({
        id: `entity-${Date.now()}`,
        name: entityName.trim(),
        type: modalType,
        subtype: entitySubtype.trim() || undefined,
        description: entityDesc.trim()
      });

      // Add to activity log
      const newLog: LogItem = {
        id: `act-${Date.now()}`,
        type: 'create',
        title: `${modalType.charAt(0).toUpperCase() + modalType.slice(1)} Forged`,
        detail: entityName.trim(),
        time: 'Just now'
      };
      setActivityLogs((prev) => [newLog, ...prev]);

      setIsModalOpen(false);
    }
  };

  const activeContradictions = contradictions.filter(c => !c.resolved).length;

  return (
    <AppShell>
      {/* Background ambient lighting overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-surface-container-high/20 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="flex-1 min-h-screen overflow-y-auto px-8 md:px-12 py-10">
        <div className="max-w-7xl mx-auto flex flex-col gap-8 animate-fade-in-up">
          
          {/* Header Section */}
          <header className="flex flex-col gap-4 mt-4">
            <div>
              <span className="font-label-sm text-[10px] text-primary uppercase tracking-[0.2em] mb-1.5 block">Chronicle Workspace</span>
              <h1 className="font-display-lg text-display-lg text-on-surface tracking-tight leading-tight">{world?.name}</h1>
              <p className="font-body-lg text-body-lg text-on-surface-variant/80 max-w-3xl mt-3 leading-relaxed">
                {world?.description}
              </p>
            </div>

            {/* Stats Bar */}
            <div className="flex flex-wrap items-center gap-6 mt-4 p-4 rounded-xl border border-starlight-white/5 bg-surface-container-low/20 backdrop-blur-md">
              <div className="flex items-center gap-3">
                <span className="font-display-lg text-3xl text-primary leading-none">{world?.manuscriptCount}</span>
                <span className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-widest">Manuscripts</span>
              </div>
              <div className="h-6 w-px bg-starlight-white/10 hidden sm:block"></div>
              <div className="flex items-center gap-3">
                <span className="font-display-lg text-3xl text-primary leading-none">
                  {entities.filter(e => e.type === 'character').length}
                </span>
                <span className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-widest">Characters</span>
              </div>
              <div className="h-6 w-px bg-starlight-white/10 hidden sm:block"></div>
              <div className="flex items-center gap-3">
                <span className="font-display-lg text-3xl text-primary leading-none">
                  {entities.filter(e => e.type === 'location').length}
                </span>
                <span className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-widest">Locations</span>
              </div>
              <div className="h-6 w-px bg-starlight-white/10 hidden sm:block"></div>
              <div className="flex items-center gap-3">
                <span className="font-display-lg text-3xl text-primary leading-none">{entities.length}</span>
                <span className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-widest">Lore Nodes</span>
              </div>
              {activeContradictions > 0 && (
                <>
                  <div className="h-6 w-px bg-starlight-white/10 hidden sm:block"></div>
                  <div className="flex items-center gap-3 cursor-pointer group" onClick={() => navigate(`/worlds/${worldId}/contradictions`)}>
                    <span className="font-display-lg text-3xl text-error leading-none group-hover:scale-105 transition-transform">{activeContradictions}</span>
                    <span className="font-label-sm text-[11px] text-error uppercase tracking-widest group-hover:underline">Contradictions</span>
                  </div>
                </>
              )}
            </div>
          </header>

          {/* Main Dashboard Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-[480px]">
            
            {/* The Loom / Graph Preview */}
            <section className="lg:col-span-2 glass-panel rounded-xl flex flex-col relative overflow-hidden group border border-starlight-white/5">
              <div className="p-6 border-b border-starlight-white/5 flex justify-between items-center bg-surface-container-low/50 relative z-10">
                <div>
                  <h2 className="font-headline-md text-headline-md text-on-surface">The Loom</h2>
                  <p className="text-xs text-on-surface-variant/50 mt-1">Visualizing network topology of characters, locations, and ciphers.</p>
                </div>
                <button 
                  onClick={() => navigate(`/worlds/${worldId}/graph`)}
                  className="font-label-sm text-label-sm text-primary hover:text-copper-glow flex items-center gap-2 transition-colors border border-primary/20 hover:border-primary/50 px-3.5 py-1.5 rounded-lg"
                >
                  Expand Graph 
                  <span className="material-symbols-outlined text-[16px] font-light">open_in_new</span>
                </button>
              </div>
              
              <div 
                className="flex-1 relative inner-glow cursor-pointer min-h-[300px]"
                onClick={() => navigate(`/worlds/${worldId}/graph`)}
              >
                {/* Graph Image Background */}
                <div 
                  className="absolute inset-0 w-full h-full opacity-55 mix-blend-screen transition-opacity duration-700 group-hover:opacity-75 bg-cover bg-center"
                  style={{ backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuC1BKLczsdBe6p1CT8rbCPx_y9Mg7EbS7GsCO7LfWN5WwTvYh9PW5pRD7VC38msjoiMpVcCtBYC7E6oAbyZW1DZlWJrvmSQlaj2gFl-lE2Ra5YpaL6qmc-xFppDSL0ZSXDUMU9IbYdTlX-7vfsJhrjSXS8-xQhzGLMDxS6vdXE81PZMBPd5ve6pwDPoQHIvyb0B2vWR2GkeRMMDVggCbnaVZPoF_OesXnhebnc2Vpc07qbSGVeg7zF4lg')" }}
                />
                
                {/* Decorative overlay status tag */}
                <div className="absolute bottom-6 left-6 flex items-center gap-3 bg-void-black/85 backdrop-blur-sm px-4 py-2 rounded-full border border-starlight-white/10 shadow-lg">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse shadow-[0_0_8px_rgba(254,182,141,0.8)]"></div>
                  <span className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider">Live Topology</span>
                </div>
              </div>
            </section>

            {/* Side Column: Actions & Log */}
            <aside className="flex flex-col gap-6">
              
              {/* Forge Entity Actions */}
              <div className="glass-panel rounded-xl p-6 flex flex-col gap-4 border border-starlight-white/5">
                <h3 className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-widest border-b border-starlight-white/5 pb-2">Forge Entity</h3>
                <div className="grid grid-cols-2 gap-3">
                  <button 
                    onClick={() => handleOpenModal('character')}
                    className="flex flex-col items-center justify-center p-4 rounded-lg border border-primary/20 bg-surface-container-lowest hover:bg-primary hover:text-void-black text-primary transition-all duration-300 group focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <span className="material-symbols-outlined mb-2 group-hover:text-void-black text-2xl font-light">group</span>
                    <span className="font-label-sm text-xs font-semibold uppercase tracking-wider">Character</span>
                  </button>
                  <button 
                    onClick={() => handleOpenModal('location')}
                    className="flex flex-col items-center justify-center p-4 rounded-lg border border-primary/20 bg-surface-container-lowest hover:bg-primary hover:text-void-black text-primary transition-all duration-300 group focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <span className="material-symbols-outlined mb-2 group-hover:text-void-black text-2xl font-light">location_on</span>
                    <span className="font-label-sm text-xs font-semibold uppercase tracking-wider">Location</span>
                  </button>
                  <button 
                    onClick={() => handleOpenModal('object')}
                    className="flex flex-col items-center justify-center p-4 rounded-lg border border-primary/20 bg-surface-container-lowest hover:bg-primary hover:text-void-black text-primary transition-all duration-300 group focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <span className="material-symbols-outlined mb-2 group-hover:text-void-black text-2xl font-light">category</span>
                    <span className="font-label-sm text-xs font-semibold uppercase tracking-wider">Object</span>
                  </button>
                  <button 
                    onClick={() => handleOpenModal('event')}
                    className="flex flex-col items-center justify-center p-4 rounded-lg border border-primary/20 bg-surface-container-lowest hover:bg-primary hover:text-void-black text-primary transition-all duration-300 group focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <span className="material-symbols-outlined mb-2 group-hover:text-void-black text-2xl font-light">event_note</span>
                    <span className="font-label-sm text-xs font-semibold uppercase tracking-wider">Event</span>
                  </button>
                </div>
              </div>

              {/* Archive Log Activity list */}
              <div className="glass-panel rounded-xl flex-1 flex flex-col overflow-hidden border border-starlight-white/5 min-h-[250px]">
                <div className="p-6 border-b border-starlight-white/5 pb-4">
                  <h3 className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-widest">Archive Log</h3>
                </div>
                <div className="p-6 pt-4 flex flex-col gap-4 overflow-y-auto max-h-[300px]">
                  {activityLogs.map((log) => (
                    <div key={log.id} className="flex gap-4 relative">
                      <div className="absolute left-[11px] top-6 bottom-[-20px] w-[1px] bg-starlight-white/10 last:hidden"></div>
                      <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-1 border z-10 ${
                        log.type === 'create' 
                          ? 'bg-primary/10 border-primary/30 text-primary' 
                          : 'bg-surface-container border-starlight-white/10 text-on-surface-variant'
                      }`}>
                        <span className="material-symbols-outlined text-[13px] font-light">
                          {log.type === 'create' ? 'add' : log.type === 'edit' ? 'edit' : 'link'}
                        </span>
                      </div>
                      <div className="flex flex-col">
                        <p className="font-body-md text-xs text-on-surface">
                          <span className="text-primary font-medium mr-1.5">{log.title}</span> 
                          {log.detail}
                        </p>
                        <span className="font-label-sm text-[10px] text-on-surface-variant/40 mt-0.5">{log.time}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

            </aside>
          </div>

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
                  className="px-6 py-2 bg-primary hover:bg-copper-glow text-void-black font-label-sm text-xs uppercase tracking-widest font-semibold rounded shadow-lg hover:shadow-primary/10 transition-all"
                >
                  Forge Entity
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
