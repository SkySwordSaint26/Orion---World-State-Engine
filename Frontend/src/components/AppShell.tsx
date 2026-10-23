import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { useAuthStore } from '../store/useAuthStore';
import { apiFetch } from '../api/client';
import { EntityPanel } from './EntityPanel';
import { ErrorBoundary } from './ErrorBoundary';
import { CreatorProfileModal } from './CreatorProfileModal';
import { SettingsModal } from './SettingsModal';
import { getJobStatus, cancelJob } from '../api/jobs';
import { useExtractionJobStore } from '../store/useExtractionJobStore';

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { worldId, manuscriptId } = useParams<{ worldId: string; manuscriptId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { activeEntityId, isEntityPanelOpen, setEntityPanelOpen, setActiveWorld, activeWorldId,
    contradictions, worlds, manuscripts, activeChapterId, setWorlds } = useWorldStore();
  const user = useAuthStore(state => state.user);
  const [openPanel, setOpenPanel] = useState<'profile' | 'settings' | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  const { worldId: extractionWorldId, jobId: extractionJobId, job: extractionJob, update: updateExtractionJob, clear: clearExtractionJob } = useExtractionJobStore();
  const [cancellingExtraction, setCancellingExtraction] = useState(false);

  useEffect(() => {
    if (!extractionJobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const status = await getJobStatus(extractionJobId, controller.signal);
        if (controller.signal.aborted) return;
        updateExtractionJob(status);
        if (!['done', 'failed', 'cancelled'].includes(status.status)) timer = setTimeout(poll, 1500);
      } catch {
        if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
      }
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [extractionJobId, updateExtractionJob]);

  const cancelExtraction = async () => {
    if (!extractionJobId || cancellingExtraction) return;
    setCancellingExtraction(true);
    try { updateExtractionJob(await cancelJob(extractionJobId)); }
    catch (error) { setWriteError(error instanceof Error ? error.message : 'Cancellation was not confirmed.'); }
    finally { setCancellingExtraction(false); }
  };

  useEffect(() => {
    if (worldId && worldId !== activeWorldId) setActiveWorld(worldId);
  }, [worldId, activeWorldId, setActiveWorld]);
  useEffect(() => {
    if (!worldId || worlds.some(world => world.id === worldId)) return;
    let cancelled = false;
    apiFetch<any>(`/worlds/${worldId}`).then(world => {
      if (!cancelled) setWorlds([...useWorldStore.getState().worlds.filter(item => item.id !== world.id), {
        id: world.id, name: world.name, description: world.description || '',
        entityCount: world.stats?.entities_count || 0, manuscriptCount: world.stats?.manuscripts_count || 0,
        characterCount: world.stats?.characters_count || 0, locationCount: world.stats?.locations_count || 0,
        objectCount: world.stats?.objects_count || 0, eventCount: world.stats?.events_count || 0,
      }]);
    }).catch(error => { if (!cancelled) setWriteError(error.message); });
    return () => { cancelled = true; };
  }, [worldId, worlds, setWorlds]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMobileNav(false); setEntityPanelOpen(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); };
  }, [setEntityPanelOpen]);

  const unresolved = contradictions.filter(item => !item.resolved && item.status !== 'DISMISSED').length;
  const navItems = worldId ? [
    { path: `/worlds/${worldId}`, icon: 'home', label: 'Home' },
    { path: `/worlds/${worldId}/manuscripts`, icon: 'history_edu', label: 'Manuscripts' },
    { path: `/worlds/${worldId}/world`, icon: 'public', label: 'World Ledger' },
    { path: `/worlds/${worldId}/graph`, icon: 'hub', label: 'Network Graph' },
    { path: `/worlds/${worldId}/timeline`, icon: 'hourglass_empty', label: 'Timeline' },
    { path: `/worlds/${worldId}/contradictions`, icon: 'balance', label: 'Contradictions', badge: unresolved },
    { path: `/worlds/${worldId}/assistant`, icon: 'forum', label: 'AI Assistant' },
  ] : [
    { path: '/worlds', icon: 'public', label: 'Worlds' },
    { path: '/worlds/new', icon: 'add', label: 'New World' },
  ];
  const activeItem = navItems.find(item => location.pathname === item.path ||
    (item.label === 'Manuscripts' && location.pathname.startsWith(`${item.path}/`)));
  const manuscript = manuscripts.find(item => item.id === manuscriptId);
  const chapter = manuscript?.chapters.find(item => item.id === activeChapterId) || manuscript?.chapters[0];
  const pageTitle = manuscriptId ? 'Chapter Editor' : location.pathname.endsWith('/processing') ? 'Processing World' : activeItem?.label || 'Worlds';
  const worldName = worlds.find(item => item.id === worldId)?.name || 'Your world';
  useEffect(() => { document.title = `${pageTitle}${worldId ? ` · ${worldName}` : ''} · Orion`; }, [pageTitle, worldId, worldName]);

  return (
    <div className="studio-shell">
      {mobileNav && <button className="fixed inset-0 z-40 bg-black/70 md:hidden" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}
      <nav id="studio-navigation" aria-label="World navigation" className={`studio-rail ${mobileNav ? 'is-open' : ''}`}>
        <Link to="/worlds" aria-label="Return to Archive" className="studio-mark" onClick={() => { setActiveWorld(null); setMobileNav(false); }}><span className="material-symbols-outlined">auto_awesome</span><span className="rail-label">Orion</span></Link>
        <div className="flex flex-1 flex-col gap-2 pt-8">
          {navItems.map(item => {
            const active = activeItem?.path === item.path;
            return <Link key={item.path} to={item.path} title={item.label} aria-label={item.label} aria-current={active ? 'page' : undefined}
              className={`studio-nav-link ${active ? 'is-active' : ''}`} onClick={() => setMobileNav(false)}>
              <span className="material-symbols-outlined">{item.icon}</span><span className="rail-label">{item.label}</span>
              {'badge' in item && !!item.badge && <span className="nav-badge">{item.badge}</span>}
            </Link>;
          })}
        </div>
        <button title="Profile" aria-label="Creator Profile" className="studio-nav-link" onClick={() => { setOpenPanel('profile'); setMobileNav(false); }}><span className="material-symbols-outlined">person</span><span className="rail-label">Creator Profile</span></button>
        <button title="Archive Settings" aria-label="Archive Settings" className="studio-nav-link" onClick={() => { setOpenPanel('settings'); setMobileNav(false); }}><span className="material-symbols-outlined">settings</span><span className="rail-label">Settings</span></button>
      </nav>
      <div className="studio-stage">
        <header className="studio-topbar">
          <button aria-label="Open navigation" aria-controls="studio-navigation" aria-expanded={mobileNav} onClick={() => setMobileNav(true)} className="p-1 md:hidden"><span className="material-symbols-outlined">menu</span></button>
          <button aria-label="Go back" title="Go back" className="p-1 text-on-surface-variant hover:text-primary" onClick={() => window.history.state?.idx > 0 ? navigate(-1) : navigate('/worlds')}><span className="material-symbols-outlined text-lg">arrow_back</span></button>
          <nav aria-label="Breadcrumb" className="min-w-0 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <Link to="/worlds" className="text-on-surface-variant">Worlds</Link>
            {worldId && <><span aria-hidden="true">/</span><Link to={`/worlds/${worldId}`} className="max-w-48 truncate font-headline-md text-base text-on-surface">{worldName}</Link></>}
            {manuscriptId && <><span aria-hidden="true">/</span><Link to={`/worlds/${worldId}/manuscripts`}>Manuscripts</Link></>}
            {pageTitle !== 'Worlds' && <><span aria-hidden="true">/</span><span aria-current="page" className="text-primary">{pageTitle}</span></>}
            {chapter && <span className="hidden text-on-surface-variant lg:inline">· Chapter {chapter.number}: {chapter.title}</span>}
          </nav>
          <div className="ml-auto shrink-0">
            <button title="Creator Profile" aria-label="Open creator profile" onClick={() => setOpenPanel('profile')} className="studio-avatar">{user?.email?.slice(0, 1).toUpperCase() || 'O'}</button>
          </div>
        </header>
        {writeError && <div role="alert" className="flex shrink-0 items-center justify-between gap-4 border-b border-error/30 bg-error/10 px-5 py-3 text-sm text-error"><span>{writeError}</span><button aria-label="Dismiss error" onClick={() => setWriteError(null)}><span className="material-symbols-outlined text-lg">close</span></button></div>}
        {extractionJobId && extractionJob && <div aria-live="polite" className="flex shrink-0 items-center gap-4 border-b border-primary/20 bg-primary/5 px-5 py-3 text-sm text-on-surface">
          <span className="material-symbols-outlined text-primary">{extractionJob.status === 'done' ? 'check_circle' : extractionJob.status === 'failed' ? 'error' : extractionJob.status === 'cancelled' ? 'pause_circle' : 'progress_activity'}</span>
          <span className="min-w-0 flex-1">
            {extractionJob.status === 'done' ? 'Manuscript extraction is complete.' : extractionJob.status === 'failed' ? `Manuscript extraction failed: ${extractionJob.error_message || 'Unknown error.'}` : extractionJob.status === 'cancelled' ? 'Manuscript extraction was cancelled.' : `Extracting manuscript… ${extractionJob.current_chapter ? `Chapter ${extractionJob.current_chapter} · ` : ''}${extractionJob.current_stage || `${extractionJob.progress_current} of ${extractionJob.progress_total} chapters completed`} (${extractionJob.progress_percent ?? (extractionJob.progress_total ? Math.floor(100 * extractionJob.progress_current / extractionJob.progress_total) : 0)}%).`}
          </span>
          <Link className="shrink-0 text-primary underline" to={`/worlds/${extractionWorldId}/processing?jobId=${extractionJobId}`}>View progress</Link>
          {!['done', 'failed', 'cancelled'].includes(extractionJob.status) && <button className="shrink-0 text-primary" disabled={cancellingExtraction} onClick={cancelExtraction}>{cancellingExtraction ? 'Cancelling…' : 'Cancel'}</button>}
          {['done', 'failed', 'cancelled'].includes(extractionJob.status) && <button aria-label="Dismiss extraction status" className="shrink-0" onClick={clearExtractionJob}><span className="material-symbols-outlined text-lg">close</span></button>}
        </div>}
        <div className="studio-content">{children}</div>
      </div>
      {openPanel === 'profile' && <CreatorProfileModal onClose={() => setOpenPanel(null)} />}
      {openPanel === 'settings' && <SettingsModal worldId={worldId || null} onClose={() => setOpenPanel(null)} />}
      {isEntityPanelOpen && activeEntityId && <>
        <button className="fixed inset-0 z-40 bg-black/30 md:left-16" aria-label="Close entity inspector" onClick={() => setEntityPanelOpen(false)} />
        <aside aria-label="Entity inspector" className="studio-entity-inspector"><ErrorBoundary fallbackTitle="Could not display entity" onReset={() => setEntityPanelOpen(false)}><EntityPanel key={activeEntityId} entityId={activeEntityId} onClose={() => setEntityPanelOpen(false)} /></ErrorBoundary></aside>
      </>}
    </div>
  );
};
