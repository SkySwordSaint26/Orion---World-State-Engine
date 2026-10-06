export interface Entity {
  id: string;
  name: string;
  type: 'character' | 'location' | 'object' | 'event';
  subtype?: string;
  alias?: string;
  description: string;
  image?: string;
  traits?: string[];
  facts: {
    id: string;
    text: string;
    source: string;
    type: 'extracted' | 'manual';
  }[];
  relationships: {
    targetId: string;
    targetName: string;
    targetType: 'character' | 'location' | 'object' | 'event';
    relation: string;
    isNegative?: boolean;
  }[];
  appearances: string[]; // chapterIds
}

export interface TimelineEvent {
  id: string;
  year: number;
  period: string;
  title: string;
  description: string;
  stateChanges: {
    entityId: string;
    entityName: string;
    entityType: 'character' | 'location' | 'object';
    field: string;
    before: string;
    after: string;
    isError?: boolean;
  }[];
  chapters: { id: string; name: string }[];
}

export interface Contradiction {
  id: string;
  title: string;
  category: string;
  targetEntityId: string;
  severity: 'high' | 'medium' | 'low';
  summary: string;
  sources: {
    sourceName: string;
    text: string;
    highlightedWord: string;
  }[];
  resolved: boolean;
}

export interface Chapter {
  id: string;
  number: number;
  title: string;
  content: string;
  wordCount: number;
}

export interface Manuscript {
  id: string;
  title: string;
  chapters: Chapter[];
}

export interface World {
  id: string;
  name: string;
  description: string;
  coverImage?: string;
  status: 'active' | 'archived' | 'drafting';
  entryCount: number;
  entityCount: number;
  manuscriptCount: number;
  characterCount: number;
  locationCount: number;
  objectCount: number;
  eventCount: number;
}
