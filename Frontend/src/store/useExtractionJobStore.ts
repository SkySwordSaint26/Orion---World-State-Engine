import { create } from 'zustand';
import type { JobStatus } from '../api/jobs';

const STORAGE_KEY = 'orion_extraction_job';

interface StoredJob {
  worldId: string;
  jobId: string;
}

interface ExtractionJobState {
  worldId: string | null;
  jobId: string | null;
  job: JobStatus | null;
  register: (worldId: string, jobId: string, job?: JobStatus) => void;
  update: (job: JobStatus) => void;
  clear: () => void;
}

const readStoredJob = (): StoredJob | null => {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value ? JSON.parse(value) as StoredJob : null;
  } catch {
    return null;
  }
};

const storedJob = readStoredJob();

export const useExtractionJobStore = create<ExtractionJobState>((set) => ({
  worldId: storedJob?.worldId || null,
  jobId: storedJob?.jobId || null,
  job: null,
  register: (worldId, jobId, job) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ worldId, jobId }));
    set({ worldId, jobId, job: job || null });
  },
  update: (job) => set({ job }),
  clear: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ worldId: null, jobId: null, job: null });
  },
}));
