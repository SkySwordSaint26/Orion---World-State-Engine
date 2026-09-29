import React, { useEffect, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { useWorldStore } from '../store/useWorldStore';

export const ProcessingWorld: React.FC = () => {
  const navigate = useNavigate();
  const { worldId } = useParams<{ worldId: string }>();
  const location = useLocation();
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('Initializing extraction pipeline...');

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const jobId = params.get('jobId');

    if (!jobId) {
      // Fallback to mock progress if no job ID (e.g. from scratch creation)
      const progressInterval = setInterval(() => {
        setProgress((prev) => (prev >= 100 ? 100 : prev + 2));
      }, 50);
      return () => clearInterval(progressInterval);
    }

    // Poll the backend job status endpoint
    const pollInterval = setInterval(async () => {
      try {
        const data = await apiFetch<any>(`/jobs/${jobId}/status`);
        if (data.progress_total > 0) {
          const currentProgress = Math.min(100, Math.floor((data.progress_current / data.progress_total) * 100));
          setProgress(currentProgress);
        }
        
        if (data.status === 'processing') {
          setStatusText(`Extracting entities & lore (${data.progress_current} / ${data.progress_total})...`);
        } else if (data.status === 'done') {
          setProgress(100);
          setStatusText('Extraction complete! Finalizing world ledger...');
          clearInterval(pollInterval);
        } else if (data.status === 'failed') {
          clearInterval(pollInterval);
          console.error("Job failed:", data.error_message);
          setStatusText(`Extraction failed: ${data.error_message || 'Unknown error'}`);
        }
      } catch (e: any) {
        console.error("Polling error", e);
      }
    }, 1500);

    return () => clearInterval(pollInterval);
  }, [location.search]);

  const { fetchManuscriptsForWorld, fetchEntitiesForWorld } = useWorldStore();

  useEffect(() => {
    if (progress === 100) {
      if (worldId) {
        fetchManuscriptsForWorld(worldId);
        fetchEntitiesForWorld(worldId);
      }
      const timeout = setTimeout(() => {
        navigate(`/worlds/${worldId || ''}`);
      }, 1200);
      return () => clearTimeout(timeout);
    }
  }, [progress, navigate, worldId, fetchManuscriptsForWorld, fetchEntitiesForWorld]);

  return (
    <div className="bg-void-black text-on-surface h-screen w-screen overflow-hidden flex flex-col items-center justify-center relative selection:bg-primary/30 selection:text-primary-fixed select-none">
      
      {/* Ambient background glow */}
      <div className="absolute inset-0 ambient-glow animate-pulse-slow pointer-events-none z-0"></div>

      {/* Cancel button in top right */}
      <div className="absolute top-0 right-0 p-gutter z-50">
        <button 
          onClick={() => navigate('/worlds')}
          className="flex items-center gap-2 px-4 py-2 rounded-full border border-outline-variant text-on-surface-variant font-label-sm text-xs hover:text-primary hover:border-primary transition-all duration-300 backdrop-blur-md bg-surface-dim/50"
        >
          <span className="material-symbols-outlined text-[16px] font-light">close</span>
          Cancel Import
        </button>
      </div>

      {/* Content canvas */}
      <main className="relative z-10 w-full max-w-2xl px-gutter flex flex-col items-center mx-auto">
        
        {/* Left column: progress */}
        <section className="flex flex-col gap-6 w-full animate-fade-in-up">
          <div className="flex flex-col gap-2 text-center">
            <h1 className="font-display-lg text-display-lg text-on-surface tracking-tight leading-tight">
              Building a first draft of your world.
            </h1>
            <p className="font-body-lg text-body-lg text-on-surface-variant/80 mt-2 leading-relaxed">
              Analyzing manuscript syntax and mapping entity relationships. You remain the final authority on all lore.
            </p>
          </div>

          {/* Progress indicators */}
          <div className="flex flex-col gap-stack-md mt-6">
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-end">
                <span className="font-label-sm text-label-sm text-primary uppercase tracking-widest text-[10px]">
                  {statusText}
                </span>
                <span className="font-label-sm text-label-sm text-copper-glow font-semibold">{progress}%</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-high rounded-full overflow-hidden relative">
                <div 
                  className="absolute inset-y-0 left-0 bg-copper-glow shadow-[0_0_12px_rgba(230,162,126,0.6)] transition-all duration-300 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Sub-tasks lists */}
            <div className="flex flex-col gap-3 mt-4 text-sm">
              <div className="flex items-center gap-3 text-on-surface-variant">
                <span className="material-symbols-outlined text-primary text-[20px] fill font-light">check_circle</span>
                <span className="font-body-md text-on-surface-variant/80">Structural analysis complete</span>
              </div>
              
              <div className="flex items-center gap-3 text-primary">
                {progress < 85 ? (
                  <span className="material-symbols-outlined animate-spin text-[20px] font-light">sync</span>
                ) : (
                  <span className="material-symbols-outlined text-primary text-[20px] fill font-light">check_circle</span>
                )}
                <span className={`font-body-md ${progress < 85 ? 'text-copper-glow' : 'text-on-surface-variant/80'}`}>
                  {progress < 85 ? 'Detecting characters and locations...' : 'Character and location extraction complete'}
                </span>
              </div>
              
              <div className={`flex items-center gap-3 ${progress < 85 ? 'text-on-surface-variant/40' : 'text-primary'}`}>
                {progress < 85 ? (
                  <span className="material-symbols-outlined text-[20px] font-light">hourglass_empty</span>
                ) : progress < 100 ? (
                  <span className="material-symbols-outlined animate-spin text-[20px] font-light">sync</span>
                ) : (
                  <span className="material-symbols-outlined text-primary text-[20px] fill font-light">check_circle</span>
                )}
                <span className="font-body-md">
                  {progress < 85 ? 'Generating timeline anchors' : progress < 100 ? 'Generating timeline anchors...' : 'Timeline anchors generated'}
                </span>
              </div>
            </div>
          </div>
        </section>
      </main>

    </div>
  );
};
