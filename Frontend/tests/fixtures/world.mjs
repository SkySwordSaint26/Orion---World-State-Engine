import { test as base, expect } from 'playwright/test';

// Requests stay in the browser fixture: these tests never touch an author's database.
export const test = base.extend({
  world: async ({ page }, provideWorld) => {
    const chapter = { id: 'ch1', chapter_number: 1, title: 'The Crossing', content: 'Arin crossed Silver Haven to meet Mira.\n\nThe treaty was signed at dawn.', word_count: 14 };
    const entities = [
      { id: 'arin', canonical_name: 'Arin', entity_type: 'character' },
      { id: 'mira', canonical_name: 'Mira', entity_type: 'character' },
      { id: 'legacy-event', canonical_name: 'Legacy event entity', entity_type: 'event' },
    ].map(item => ({ ...item, world_id: 'w1', aliases: [], facts: [] }));
    const events = [1, 2].map(number => ({ id: `ev${number}`, world_id: 'w1', chapter_id: 'ch1', chapter_number: 1, event_type: 'MEETING', description: `Real timeline event ${number}`, participants: [], sequence_index: number }));
    const profile = { id: 'author', email: 'test@example.com', display_name: 'The Archivist', created_at: '2026-01-01T00:00:00Z', stats: { worlds: 1, manuscripts: 1, chapters: 1, entities: 3 }, preferences: { chat_reply_length: 'medium', review_preselect_new: true } };
    const versions = [{ id: 'v2', chapter_id: 'ch1', version_number: 2, is_current: true, created_at: '2026-10-21T10:00:00Z', content: chapter.content }, { id: 'v1', chapter_id: 'ch1', version_number: 1, is_current: false, created_at: '2026-10-20T10:00:00Z', content: 'Arin waited at Silver Haven. The original version.' }];
    const state = { chapter, profile, versions, completeChapterJobs: true, proposals: [], contradictions: [], job: { id: 'job1', status: 'processing', progress_current: 0, progress_total: 2, error_message: null }, failNextChapter: false, failNextFact: false, failNextFactDelete: false, failNextCancel: false, failNextDecision: false, ignoreEntityUpdate: false, entities, events, relationships: [], writes: [], graphReads: 0, failNextEntity: false, failNextEntityUpdate: false, failNextRelationship: false, failNextEvent: false };
    await page.addInitScript(() => localStorage.setItem('orion_token', 'browser-test-token'));
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname.replace('/api/v1', '');
      const method = request.method();
      const json = request.headers()['content-type']?.includes('application/json') ? request.postDataJSON() : null;
      const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (method !== 'GET') state.writes.push({ path, method, json });
      if (path === '/auth/me') return reply({ id: 'author', email: 'test@example.com' });
      if (path === '/worlds' && method === 'POST') return reply({ id: 'w1', name: json.name, description: json.description, stats: {} }, 201);
      if (path === '/worlds') return reply([{ id: 'w1', name: 'Test World', description: 'A chronicle of tides, treaties and distant places.', stats: { entities_count: state.entities.length, manuscripts_count: 1 } }]);
      if (path === '/worlds/w1') return reply({ id: 'w1', name: json?.name || 'Test World', description: json?.description || 'A chronicle of tides, treaties and distant places.', stats: { entities_count: state.entities.length, manuscripts_count: 1 } });
      if (path === '/auth/profile') { if (method === 'PUT') { if (json.display_name !== undefined) profile.display_name = json.display_name; Object.assign(profile.preferences, json.preferences || {}); } return reply(profile); }
      if (path === '/auth/password') return reply({ message: 'Password changed.' });
      if (path === '/auth/logout') return reply({ message: 'Logged out.' });
      if (path === '/jobs/job1/status') return reply(state.job);
      if (path === '/jobs/job1/cancel') { if (state.failNextCancel) { state.failNextCancel = false; return reply({ detail: 'Cancellation could not be confirmed' }, 503); } state.job.status = 'cancelled'; return reply(state.job); }
      if (path === '/jobs/job1/proposals') return reply({ job_id: 'job1', world_id: 'w1', chapter_id: 'ch1', chapter_number: 1, status: 'ready', proposals: state.proposals });
      if (path === '/worlds/w1/chapters/ch1/versions') return reply(state.versions.map(({ content: _content, ...version }) => version));
      if (path.startsWith('/worlds/w1/chapters/ch1/versions/')) {
        const version = state.versions.find(item => item.id === path.split('/')[6]);
        if (!version) return reply({ detail: 'Version not found' }, 404);
        if (method === 'POST') {
          chapter.content = version.content; state.versions.forEach(item => { item.is_current = false; });
          state.versions.unshift({ ...version, id: `v${state.versions.length + 1}`, version_number: state.versions.length + 1, is_current: true });
          state.job.status = 'done'; return reply({ job_id: 'job1', chapter_id: 'ch1' }, 202);
        }
        return reply(version);
      }
      if (path.startsWith('/worlds/w1/contradictions/') && method === 'POST') {
        if (state.failNextDecision) { state.failNextDecision = false; return reply({ detail: 'Decision was not saved' }, 503); }
        const contradiction = state.contradictions.find(item => item.id === path.split('/')[4]); Object.assign(contradiction, { status: json.status }); return reply(contradiction);
      }
      if (path === '/worlds/w1/contradictions') return reply(state.contradictions);
      if (path === '/worlds/w1/manuscripts' && method === 'POST') return reply({ job_id: 'job1', manuscript_id: 'ms2', chapters_total: 2 }, 202);
      if (path === '/worlds/w1/manuscripts') return reply([{ id: 'ms1', title: 'Test Manuscript' }]);
      if (path === '/worlds/w1/manuscripts/ms1/chapters') return reply([chapter]);
      if (path === '/worlds/w1/chapters/ch1') {
        if (method === 'PUT') { if (state.failNextChapter) { state.failNextChapter = false; return reply({ detail: 'Chapter was not saved' }, 503); } chapter.content = json.content; if (state.completeChapterJobs) state.job.status = 'done'; return reply({ job_id: 'job1', chapter_id: 'ch1' }, 202); }
        return reply(chapter);
      }
      if (path === '/worlds/w1/entities/merge') { state.entities = state.entities.filter(item => item.id !== json.source_id); return reply(state.entities.find(item => item.id === json.target_id)); }
      if (path === '/worlds/w1/entities/bulk-delete') { state.entities = state.entities.filter(item => !json.entity_ids.includes(item.id)); return route.fulfill({ status: 204 }); }
      if (path.includes('/facts') && method === 'POST') {
        if (state.failNextFact) { state.failNextFact = false; return reply({ detail: 'Fact was not saved' }, 503); }
        const entity = state.entities.find(item => item.id === path.split('/')[4]);
        entity.facts.push({ id: 'fact-record-id', property_name: json.property_name, current_version: { id: 'fact-version-id', value: json.value, status: 'ACTIVE', chapter_id: null } });
        return reply({ id: 'fact-version-id', property: json.property_name, value: json.value, status: 'ACTIVE' }, 201);
      }
      if (path.includes('/facts/') && method === 'DELETE') { if (state.failNextFactDelete) { state.failNextFactDelete = false; return reply({ detail: 'Fact was not deleted' }, 503); } const entity = state.entities.find(item => item.id === path.split('/')[4]); entity.facts = entity.facts.filter(item => item.id !== path.split('/').at(-1)); return route.fulfill({ status: 204 }); }
      if (path.includes('/aliases')) { const entity = state.entities.find(item => item.id === path.split('/')[4]); if (method === 'POST') entity.aliases.push(json.alias); if (method === 'DELETE') { entity.aliases = entity.aliases.filter(alias => alias !== new URL(request.url()).searchParams.get('alias')); return route.fulfill({ status: 204 }); } return reply(entity); }

      if (path === '/worlds/w1/entities' && method === 'GET') return reply(state.entities);
      if (path === '/worlds/w1/chat' && method === 'POST') return reply({
        response: json.entity_focus ? 'I will protect Nandivan.' : 'Your world contains Arin and Mira.',
        citations: [], suggested_actions: [],
      });
      if (path === '/worlds/w1/entities' && method === 'POST') {
        if (state.failNextEntity) { state.failNextEntity = false; return reply({ detail: 'Entity could not be saved' }, 400); }
        const entity = { id: `entity-${state.entities.length}`, world_id: 'w1', ...json, aliases: json.aliases || [], facts: Object.entries(json.attributes || {}).map(([property_name, value]) => ({ id: `${property_name}-${state.entities.length}`, property_name, current_version: { value, status: 'ACTIVE', chapter_id: null } })) };
        state.entities.push(entity);
        return reply(entity, 201);
      }
      if (path.startsWith('/worlds/w1/entities/') && method === 'PUT') {
        if (state.failNextEntityUpdate) { state.failNextEntityUpdate = false; return reply({ detail: 'Description could not be saved' }, 400); }
        const entity = state.entities.find(item => item.id === path.split('/').at(-1));
        if (state.ignoreEntityUpdate) return reply(entity);
        if (json.canonical_name !== undefined) entity.canonical_name = json.canonical_name;
        if (json.entity_type !== undefined) entity.entity_type = json.entity_type;
        for (const [property, value] of Object.entries(json.attributes || {})) {
          let fact = entity.facts.find(item => item.property_name === property);
          if (!fact) { fact = { id: `${entity.id}-${property}`, property_name: property }; entity.facts.push(fact); }
          fact.current_version = { id: `version-${state.writes.length}`, value, status: 'ACTIVE', chapter_id: null };
        }
        return reply(entity);
      }
      if (path.startsWith('/worlds/w1/entities/') && method === 'GET') {
        const id = path.split('/').at(-1);
        const entity = state.entities.find(item => item.id === id);
        const relationships = state.relationships.filter(item => item.source_entity_id === id || item.target_entity_id === id).map(item => {
          const outgoing = item.source_entity_id === id;
          const other = state.entities.find(ent => ent.id === (outgoing ? item.target_entity_id : item.source_entity_id));
          return { id: item.id, targetId: other.id, targetName: other.canonical_name, targetType: other.entity_type, relation: item.relationship_type, direction: outgoing ? 'outgoing' : 'incoming', chapter_id: item.chapter_id, chapter_number: item.chapter_id ? 1 : null };
        });
        return reply({ ...entity, relationships, appearances: [] });
      }
      if (path === '/worlds/w1/events/reorder') { state.events = json.event_ids.map(id => state.events.find(event => event.id === id)); state.events.forEach((event, index) => { event.sequence_index = index; }); return reply({ events: state.events, total: state.events.length }); }
      if (path.startsWith('/worlds/w1/events/') && method === 'PUT') { const event = state.events.find(item => item.id === path.split('/').at(-1)); Object.assign(event, json); event.participants = (json.participants || []).map(participant => ({ ...participant, entity_name: state.entities.find(entity => entity.id === participant.entity_id)?.canonical_name })); return reply(event); }
      if (path.startsWith('/worlds/w1/events/') && method === 'DELETE') { state.events = state.events.filter(item => item.id !== path.split('/').at(-1)); return route.fulfill({ status: 204 }); }
      if (path === '/worlds/w1/timeline') return reply({ events: state.events, total: state.events.length });
      if (path === '/worlds/w1/events' && method === 'POST') {
        if (state.failNextEvent) { state.failNextEvent = false; return reply({ detail: 'Event could not be saved' }, 400); }
        const event = { id: `event-${state.events.length}`, world_id: 'w1', chapter_number: json.chapter_id ? 1 : null, confidence: 1, sequence_index: null, ...json, participants: (json.participants || []).map(participant => ({ ...participant, entity_name: state.entities.find(entity => entity.id === participant.entity_id)?.canonical_name })) };
        state.events.push(event);
        return reply(event, 201);
      }
      if (path === '/worlds/w1/relationships' && method === 'POST') {
        if (state.failNextRelationship) { state.failNextRelationship = false; return reply({ detail: 'Relationship could not be saved' }, 400); }
        const relationship = { id: `relation-${state.writes.length}`, ...json };
        state.relationships.push(relationship);
        return reply(relationship, 201);
      }
      if (path.startsWith('/worlds/w1/relationships/') && method === 'DELETE') {
        state.relationships = state.relationships.filter(item => item.id !== path.split('/').at(-1));
        return route.fulfill({ status: 204 });
      }
      if (path === '/worlds/w1/graph') {
        state.graphReads++;
        return reply({ nodes: state.entities.map(item => ({ id: item.id, label: item.canonical_name, type: item.entity_type, degree: state.relationships.filter(rel => rel.source_entity_id === item.id || rel.target_entity_id === item.id).length })), edges: state.relationships.map(item => ({ id: item.id, source: item.source_entity_id, target: item.target_entity_id, type: item.relationship_type })) });
      }
      return reply({ detail: `Unexpected test request: ${method} ${path}` }, 404);
    });
    await provideWorld(state);
  },
});


export { expect };
