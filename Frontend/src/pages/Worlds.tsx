import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { useAuthStore } from '../store/useAuthStore';
import { apiFetch } from '../api/client';
import type { World } from '../types/world';
import { AppShell } from '../components/AppShell';

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

  const featured = worlds[0];
  return (
    <AppShell>
      <main className="studio-page">
        <div className="studio-page-inner space-y-9">
          <header className="flex flex-wrap items-end justify-between gap-5">
            <div><span className="studio-eyebrow">Sanctum · Nocturne Register</span>
              <h1 className="studio-title">Return to your worlds.</h1>
              <p className="studio-intro">A name, a place, a universe taking shape. Pick up a chronicle or begin another.</p>
            </div>
            <button className="studio-primary" onClick={handleCreateNewWorld}><span className="material-symbols-outlined text-base">add</span>Inscribe New World</button>
          </header>
          {error && <div role="alert" className="studio-card flex items-center justify-between gap-4 p-4 text-error">{error}<button className="studio-secondary" onClick={fetchWorlds}>Retry</button></div>}
          {loading ? <p role="status" className="py-16 text-center text-on-surface-variant">Fetching archive records…</p> : <>
            {featured && <section className="studio-card studio-world-cover relative overflow-hidden p-7 md:p-12">
              <div className="pointer-events-none absolute right-16 top-16 hidden opacity-70 lg:block"><div className="studio-orbit"><span className="material-symbols-outlined text-5xl text-primary/60">auto_awesome</span></div></div>
              <span className="studio-eyebrow">From your archive</span>
              <div className="relative max-w-2xl pt-8"><h2 className="font-display-lg text-display-lg">{featured.name}</h2>
                <p className="mt-4 max-w-xl font-body-lg text-xl leading-relaxed text-on-surface-variant">{featured.description || 'An unwritten horizon. Your world begins here.'}</p>
                <p className="mt-6 text-xs text-on-surface-variant/70">{featured.manuscriptCount} manuscripts · {featured.entityCount} bound entities</p>
                <button onClick={() => handleSelectWorld(featured.id)} className="studio-primary mt-7">Open World Studio<span className="material-symbols-outlined text-base">arrow_forward</span></button>
              </div>
            </section>}
            <section>
              <div className="mb-5 flex items-center justify-between"><h2 className="font-headline-md text-2xl">Authored universes</h2><span className="text-xs text-on-surface-variant/60">{worlds.length} {worlds.length === 1 ? 'world' : 'worlds'}</span></div>
              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                {worlds.map(world => <article key={world.id} className="studio-card group flex min-h-56 flex-col p-6 transition-colors hover:border-primary/30">
                  <div className="mb-5 flex items-center justify-between"><span className="material-symbols-outlined text-primary/70">public</span><button onClick={event => handleDeleteWorld(event, world.id)} title="Delete World" aria-label={`Delete ${world.name}`} className="p-1 text-on-surface-variant/60 hover:text-error"><span className="material-symbols-outlined text-base">delete</span></button></div>
                  <button className="text-left" onClick={() => handleSelectWorld(world.id)}><h3 className="font-headline-md text-2xl group-hover:text-primary">{world.name}</h3><p className="mt-2 line-clamp-3 text-sm leading-relaxed text-on-surface-variant/70">{world.description || 'A new chronicle, waiting for its first inscription.'}</p></button>
                  <div className="mt-auto flex items-center justify-between pt-6 text-xs text-on-surface-variant/60"><span>{world.manuscriptCount} manuscripts · {world.entityCount} entities</span><button onClick={() => handleSelectWorld(world.id)} className="text-primary">Open <span aria-hidden="true">↗</span></button></div>
                </article>)}
                <button onClick={handleCreateNewWorld} className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-outline-variant/50 p-6 text-on-surface-variant hover:border-primary hover:text-primary"><span className="material-symbols-outlined text-3xl">add</span><span className="font-headline-md text-xl">Forge New World</span><span className="text-xs">Every world begins as a fragment.</span></button>
              </div>
            </section>
          </>}
          <footer className="flex flex-wrap items-center justify-between gap-4 border-t border-white/5 py-5 text-xs text-on-surface-variant/60"><span>{user?.email}</span><button onClick={handleLogout} className="flex items-center gap-2 hover:text-primary"><span className="material-symbols-outlined text-base">lock_open</span>Lock Archive (Logout)</button></footer>
        </div>
      </main>
    </AppShell>
  );
};
