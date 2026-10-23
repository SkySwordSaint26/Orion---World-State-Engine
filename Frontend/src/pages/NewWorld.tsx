import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { apiFetch } from '../api/client';
import { AppShell } from '../components/AppShell';
import { useExtractionJobStore } from '../store/useExtractionJobStore';

export const NewWorld: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { setActiveWorld } = useWorldStore();
  const registerExtractionJob = useExtractionJobStore(state => state.register);
  const [worldName, setWorldName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const processFileUpload = async (file: File) => {
    if (loading) return;
    if (!/\.(txt|md|pdf|docx)$/i.test(file.name)) { setError('Upload TXT, Markdown, DOCX or PDF. EPUB is not supported.'); return; }
    setLoading(true);
    setError(null);

    const filenameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
    const nameToUse = worldName.trim() || filenameWithoutExt || 'Extracted World';
    const descToUse = description.trim() || `World extracted from uploaded manuscript ${file.name}.`;

    try {
      // Step 1: Create world
      const worldData = await apiFetch<any>('/worlds', {
        method: 'POST',
        body: JSON.stringify({ name: nameToUse, description: descToUse })
      });

      setActiveWorld(worldData.id);

      // Step 2: Upload manuscript file
      const formData = new FormData();
      formData.append('file', file);

      const manuscriptRes = await apiFetch<any>(`/worlds/${worldData.id}/manuscripts`, {
        method: 'POST',
        body: formData
      });

      // Step 3: Redirect to processing view with job_id
      if (manuscriptRes.job_id) {
        registerExtractionJob(worldData.id, manuscriptRes.job_id);
        navigate(`/worlds/${worldData.id}/processing?jobId=${manuscriptRes.job_id}`);
      } else {
        navigate(`/worlds/${worldData.id}`);
      }
    } catch (e: any) {
      console.error("Failed to upload manuscript via API", e);
      setError(e.message || "Failed to upload manuscript file");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFileUpload(e.target.files[0]);
    }
  };

  const handleStartImport = async (mode: string) => {
    if (mode === 'manuscript' || mode === 'notes') {
      fileInputRef.current?.click();
      return;
    }

    setLoading(true);
    setError(null);

    const nameToUse = worldName.trim() || 'New Chronicle';
    const descToUse = description.trim() || 'A blank canvas initialized in the archives. Add characters, locations, and facts manually.';

    try {
      const data = await apiFetch<any>('/worlds', {
        method: 'POST',
        body: JSON.stringify({ name: nameToUse, description: descToUse })
      });

      setActiveWorld(data.id);
      navigate(`/worlds/${data.id}`);
    } catch (e: any) {
      console.error("Failed to create world via API", e);
      setError(e.message || "Failed to create world");
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFileUpload(e.dataTransfer.files[0]);
    }
  };

  return (
    <AppShell>
      <main className="studio-page">
        <div className="mx-auto max-w-3xl py-5 md:py-8">
          <header className="mb-10 text-center"><span className="studio-eyebrow">Genesis · Inscribe a cosmology</span><h1 className="studio-title">What world are you <em>carrying?</em></h1><p className="studio-intro mx-auto">Every universe begins as an image, a memory, or a solitary name. Inscribe its earliest seed.</p></header>
          <div className="studio-card space-y-6 p-6 md:p-9">
            <label className="block"><span className="studio-eyebrow">World name</span><input className="studio-field" maxLength={255} value={worldName} onChange={event => setWorldName(event.target.value)} placeholder="The name at the heart of your library" /></label>
            <label className="block"><span className="studio-eyebrow">A sentence to ground the horizon · Optional</span><textarea className="studio-field min-h-28" value={description} onChange={event => setDescription(event.target.value)} placeholder="A little of its history, its atmosphere, its possibilities…" /></label>
            {error && <p role="alert" className="rounded border border-error/30 bg-error/5 p-3 text-sm text-error">{error}</p>}
            <div className="flex flex-wrap items-center gap-4 border-t border-white/5 pt-6"><button disabled={loading} className="studio-primary" onClick={() => handleStartImport('scratch')}>Begin the world<span className="material-symbols-outlined text-base">auto_awesome</span></button><button disabled={loading} className="text-xs text-on-surface-variant hover:text-primary" onClick={() => navigate('/worlds')}>I’ll decide later</button><span className="text-xs text-on-surface-variant/60">You can reshape it as the narrative grows.</span></div>
          </div>
          <section className="mt-8"><span className="studio-eyebrow">Already carrying a few pages?</span><div className="grid gap-4 sm:grid-cols-2"><button disabled={loading} onClick={() => handleStartImport('manuscript')} className="studio-secondary justify-start p-5"><span className="material-symbols-outlined">menu_book</span><span className="text-left"><span className="block font-headline-md text-lg">Import a Manuscript</span><span className="block pt-1 text-xs text-on-surface-variant/60">Extract characters, places, relationships and events.</span></span></button><button disabled={loading} onClick={() => handleStartImport('notes')} className="studio-secondary justify-start p-5"><span className="material-symbols-outlined">folder_open</span><span className="text-left"><span className="block font-headline-md text-lg">Import World Material</span><span className="block pt-1 text-xs text-on-surface-variant/60">Bring existing notes and written lore into the archive.</span></span></button></div></section>
          <input aria-label="Choose manuscript" type="file" ref={fileInputRef} onChange={handleFileChange} accept=".txt,.md,.pdf,.docx" className="hidden" />
          <div role="button" tabIndex={loading ? -1 : 0} aria-disabled={loading} aria-label="Browse manuscript files" onDragOver={event => event.preventDefault()} onDrop={handleDrop} onClick={() => !loading && fileInputRef.current?.click()} onKeyDown={event => { if (!loading && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); fileInputRef.current?.click(); } }} className="mt-6 cursor-pointer rounded-lg border border-dashed border-outline-variant/60 p-8 text-center hover:border-primary/50"><span className="material-symbols-outlined mb-2 text-2xl text-primary">upload_file</span><p className="font-headline-md text-xl">{loading ? 'Uploading & initializing extraction…' : 'Lay your chapters onto the desk'}</p><p className="mt-2 text-xs text-on-surface-variant/60">Drop or browse TXT, Markdown, DOCX or PDF</p></div>
          <p className="mt-9 text-center font-body-lg text-lg italic text-on-surface-variant/50">“A universe does not arrive in order; it arrives in fragments.”</p>
        </div>
      </main>
    </AppShell>
  );
};
