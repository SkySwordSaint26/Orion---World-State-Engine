import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { cancelJob, getJobStatus, type JobStatus } from '../api/jobs';
import { useWorldStore } from '../store/useWorldStore';

export const ProcessingWorld = () => {
  const { worldId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const jobId = new URLSearchParams(location.search).get('jobId');
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [retry, setRetry] = useState(0);
  const { fetchManuscriptsForWorld, fetchEntitiesForWorld } = useWorldStore();
  const terminal = job && ['done', 'failed', 'cancelled'].includes(job.status);
  const progress = job?.status === 'done' ? 100 : job?.progress_total ? Math.min(99, Math.floor(100 * job.progress_current / job.progress_total)) : 0;

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const status = await getJobStatus(jobId, controller.signal);
        if (controller.signal.aborted) return;
        setJob(current => current?.status === 'cancelled' ? current : status);
        setError(null);
        if (!['done', 'failed', 'cancelled'].includes(status.status)) timer = setTimeout(poll, 1500);
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Could not read extraction status.');
      }
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [jobId, retry]);

  useEffect(() => {
    if (job?.status !== 'done' || !worldId) return;
    fetchManuscriptsForWorld(worldId);
    fetchEntitiesForWorld(worldId);
    const timer = setTimeout(() => navigate(`/worlds/${worldId}`), 1200);
    return () => clearTimeout(timer);
  }, [job?.status, worldId, navigate, fetchManuscriptsForWorld, fetchEntitiesForWorld]);

  const cancel = async () => {
    if (!jobId || cancelling) return;
    setCancelling(true);
    try { setJob(await cancelJob(jobId)); setError(null); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Cancellation was not confirmed.'); }
    finally { setCancelling(false); }
  };
  return <AppShell><main className="studio-page"><div className="mx-auto flex max-w-2xl flex-col items-center py-10 text-center md:py-16">
    <span className="studio-eyebrow">Sanctuary ingestion · Your manuscript</span><h1 className="studio-title">Reading the world<br /><em>between your lines.</em></h1>
    <p className="studio-intro">Characters, places, and the threads that bind them. You remain the final authority on the lore.</p>
    <div className="studio-orbit my-16"><span className={`material-symbols-outlined text-5xl text-primary ${terminal ? '' : 'animate-pulse'}`}>{job?.status === 'cancelled' ? 'pause' : job?.status === 'done' ? 'check' : 'auto_awesome'}</span></div>
    <section className="studio-card w-full p-7 text-left" aria-label="Extraction progress">
      <div className="mb-5 flex items-center justify-between gap-3"><span className="studio-eyebrow mb-0">Manuscript inscription</span><span className="text-xs text-primary">{progress}%</span></div>
      <progress max={100} value={progress} className="h-1 w-full accent-primary-container" aria-label="Completed chapters" />
      <h2 role="status" className="mt-6 font-headline-md text-2xl">{!jobId ? 'No extraction job was supplied.' : job?.status === 'cancelled' ? 'Import cancelled' : job?.status === 'failed' ? 'The reading was interrupted' : job?.status === 'done' ? 'Your world is ready' : job?.status === 'processing' ? 'Tracing characters and their connections…' : 'Waiting to begin…'}</h2>
      <p className="mt-3 text-sm leading-relaxed text-on-surface-variant/70">{job?.progress_current || 0} of {job?.progress_total || 0} chapters completed.{job?.status === 'cancelled' ? ' Completed chapters have been kept. Remaining extraction has been cancelled.' : job?.status === 'failed' ? ` ${job.error_message || 'Extraction failed.'}` : ''}</p>
      {error && <div role="alert" className="mt-4 text-sm text-error">{error}<button className="ml-3 underline" onClick={() => setRetry(value => value + 1)}>Retry status</button></div>}
    </section>
    <div className="mt-7 flex flex-wrap justify-center gap-4">{jobId && !terminal && <button className="studio-secondary" disabled={cancelling} onClick={cancel}>{cancelling ? 'Cancelling…' : 'Cancel Import'}</button>}<Link className="studio-secondary" to={`/worlds/${worldId || ''}`}>{terminal ? 'Return to world' : 'Leave reading in background'}</Link></div>
  </div></main></AppShell>;
};
