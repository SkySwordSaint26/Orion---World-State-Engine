import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { useAuthStore } from '../store/useAuthStore';
import { apiFetch } from '../api/client';
import type { World } from '../data/mockData';

export const Worlds: React.FC = () => {
  const navigate = useNavigate();
  const { worlds, setActiveWorld, setWorlds } = useWorldStore();
  const { user, logout } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchWorlds = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<any[]>('/worlds');
      const mapped: World[] = data.map((w: any) => ({
        id: w.id,
        name: w.name,
        description: w.description || '',
        status: 'active',
        coverImage: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAuBUQknn_uISnwdR-0unHTT5VRn-yce6HhfPUnOIG_Ony7WbXISoUWuWh5wyVeqSOLTYFIiAP74lHr0RUBulB0dCbAuA9H3-tAAOjJyR81Mq8O6R3RvmKn59tBm-9l7GCG4SfTilfGXtrFZCYZB8exnTe1_mAXZFow2X7Xc6mLFUmxt3pgQ06mqEa2md5K7Pjv_DD0xt27x6wjj1JqQ9A-zVBTwdoBwbbKRPLuYWojrHy2j6YDRs9kHg',
        entryCount: 0,                                  // not reported by the API (no fact count in the stats)
        entityCount: w.stats?.entities_count || 0,      // keys as in backend WorldRepository.get_world_stats
        manuscriptCount: w.stats?.manuscripts_count || 0,
        characterCount: w.stats?.characters_count || 0,
        locationCount: w.stats?.locations_count || 0,
        objectCount: w.stats?.objects_count || 0,
        eventCount: w.stats?.events_count || 0,
      }));

      setWorlds(mapped);
    } catch (e: any) {
      console.error("Failed to fetch worlds via API:", e);
      setError(e.message || "Could not connect to server archives.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorlds();
  }, []);

  const handleSelectWorld = (worldId: string) => {
    setActiveWorld(worldId);
    navigate(`/worlds/${worldId}`);
  };

  const handleCreateNewWorld = () => {
    navigate('/worlds/new');
  };

  const handleDeleteWorld = async (e: React.MouseEvent, worldId: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this world chronicle?')) return;

    try {
      await apiFetch(`/worlds/${worldId}`, { method: 'DELETE' });
      await fetchWorlds();
    } catch (err: any) {
      alert(err.message || 'Failed to delete world');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/signin');
  };

  const getStatusBadge = (status: 'active' | 'archived' | 'drafting') => {
    switch (status) {
      case 'active':
        return <span className="font-label-sm text-label-sm text-copper-glow uppercase tracking-widest">Active Manuscript</span>;
      case 'archived':
        return <span className="font-label-sm text-label-sm text-on-surface-variant/50 uppercase tracking-widest">Archived</span>;
      case 'drafting':
        return <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest">Drafting</span>;
    }
  };

  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center relative font-body-md text-on-surface bg-void-black selection:bg-primary/20 select-none">
      
      {/* Background radial glow */}
      <div className="ambient-glow fixed inset-0 w-full h-full opacity-60"></div>
      
      {/* Header Section */}
      <header className="absolute top-12 left-0 right-0 text-center z-10 flex flex-col items-center gap-3">
        <h1 className="font-display-lg text-display-lg text-starlight-white tracking-tight animate-fade-in-up">Where will you go?</h1>
        <p className="font-body-lg text-body-lg text-on-surface-variant/80 max-w-2xl text-center opacity-80 px-gutter animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          Select a chronicle from the archive or forge a new realm in the dark.
        </p>
        {user && (
          <p className="text-xs text-copper-glow/80 font-label-sm uppercase tracking-widest mt-1">
            Logged in as {user.email}
          </p>
        )}
      </header>

      {/* Main Grid */}
      <main className="w-full max-w-7xl px-gutter pt-48 pb-24 z-10 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
        {error && (
          <div className="mb-8 max-w-md mx-auto p-4 rounded bg-amber-950/40 border border-amber-500/30 text-amber-300 text-xs text-center">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <span className="material-symbols-outlined text-4xl text-copper-glow animate-spin mb-4">refresh</span>
            <p className="text-sm text-on-surface-variant/70">Fetching archive records...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 md:gap-12">
            
            {/* Render worlds dynamically */}
            {worlds.map((world) => (
              <div 
                key={world.id}
                onClick={() => handleSelectWorld(world.id)}
                className="book-cover-hover relative group flex flex-col text-left h-[420px] rounded-lg border border-starlight-white/10 bg-surface-container-low overflow-hidden focus:outline-none focus:ring-1 focus:ring-copper-glow cursor-pointer"
              >
                {/* Cover Art Background */}
                {world.coverImage && (
                  <div 
                    className={`absolute inset-0 w-full h-full transition-all duration-700 ease-out bg-cover bg-center ${
                      world.status === 'active' 
                        ? 'opacity-50 group-hover:opacity-75' 
                        : world.status === 'archived'
                          ? 'opacity-25 grayscale group-hover:opacity-40 group-hover:grayscale-0'
                          : 'opacity-45 group-hover:opacity-65'
                    }`}
                    style={{ backgroundImage: `url('${world.coverImage}')` }}
                  />
                )}

                {/* Cover Art Shadow overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-void-black via-void-black/75 to-transparent z-10" />
                
                {/* Delete action button */}
                <button
                  type="button"
                  onClick={(e) => handleDeleteWorld(e, world.id)}
                  title="Delete World"
                  className="absolute top-4 right-4 z-30 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-full bg-void-black/60 border border-starlight-white/20 text-on-surface-variant/70 hover:text-red-400 hover:border-red-400/50"
                >
                  <span className="material-symbols-outlined text-base">delete</span>
                </button>

                {/* Card Contents */}
                <div className="relative mt-auto p-6 z-20 flex flex-col gap-2 w-full">
                  {getStatusBadge(world.status)}
                  <h2 className="font-headline-lg text-headline-lg text-starlight-white group-hover:text-primary transition-colors">
                    {world.name}
                  </h2>
                  <p className="line-clamp-2 text-xs text-on-surface-variant/70">
                    {world.description}
                  </p>
                  
                  {/* Stats */}
                  <div className="flex items-center gap-4 mt-2">
                    <span className="flex items-center gap-1 font-label-sm text-[11px] text-on-surface-variant/80">
                      <span className="material-symbols-outlined text-[15px] font-light">menu_book</span>
                      {world.manuscriptCount} {world.manuscriptCount === 1 ? 'Manuscript' : 'Manuscripts'}
                    </span>
                    <span className="flex items-center gap-1 font-label-sm text-[11px] text-on-surface-variant/80">
                      <span className="material-symbols-outlined text-[15px] font-light">group</span>
                      {world.entityCount} Entities
                    </span>
                  </div>
                </div>
              </div>
            ))}

            {/* Forge New World Tile */}
            <button 
              onClick={handleCreateNewWorld}
              className="book-cover-hover relative group flex flex-col items-center justify-center text-center h-[420px] rounded-lg border border-dashed border-starlight-white/20 bg-transparent hover:bg-surface-container-low/30 hover:border-copper-glow/50 focus:outline-none focus:ring-1 focus:ring-copper-glow transition-all duration-300"
            >
              <div className="w-16 h-16 rounded-full border border-starlight-white/20 flex items-center justify-center mb-6 group-hover:border-copper-glow/50 group-hover:bg-copper-glow/10 transition-colors">
                <span className="material-symbols-outlined text-3xl text-starlight-white/60 group-hover:text-copper-glow transition-colors font-light">add</span>
              </div>
              <h2 className="font-headline-md text-headline-md text-starlight-white/80 group-hover:text-starlight-white transition-colors">
                Forge New World
              </h2>
              <p className="mt-2 font-label-sm text-label-sm text-on-surface-variant/60 max-w-[200px]">
                Initialize a blank canvas in the archive.
              </p>
            </button>

          </div>
        )}
      </main>

      {/* Bottom utility links */}
      <footer className="absolute bottom-8 left-0 right-0 text-center z-10 flex justify-center gap-8 animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
        <button onClick={handleLogout} className="font-label-sm text-label-sm text-on-surface-variant/60 hover:text-primary transition-colors flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px] font-light">lock_open</span>
          Lock Archive (Logout)
        </button>
      </footer>

    </div>
  );
};
