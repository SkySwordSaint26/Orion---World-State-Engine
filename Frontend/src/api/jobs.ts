import { apiFetch } from './client';

export interface JobStatus {
  id: string;
  status: 'queued' | 'processing' | 'done' | 'failed' | 'cancelled';
  progress_current: number;
  progress_total: number;
  progress_percent?: number;
  current_stage?: string | null;
  current_chapter?: number | null;
  error_message: string | null;
}

export const getJobStatus = (id: string, signal?: AbortSignal) => apiFetch<JobStatus>(`/jobs/${id}/status`, { signal });
export const cancelJob = (id: string) => apiFetch<JobStatus>(`/jobs/${id}/cancel`, { method: 'POST' });
