import { apiFetch } from './client';

export interface ChapterVersion {
  id: string;
  chapter_id: string;
  version_number: number;
  is_current: boolean;
  created_at: string;
}

export interface ChapterVersionContent extends ChapterVersion { content: string }

export const getChapterVersions = (worldId: string, chapterId: string) =>
  apiFetch<ChapterVersion[]>(`/worlds/${worldId}/chapters/${chapterId}/versions`);
export const getChapterVersion = (worldId: string, chapterId: string, versionId: string) =>
  apiFetch<ChapterVersionContent>(`/worlds/${worldId}/chapters/${chapterId}/versions/${versionId}`);
