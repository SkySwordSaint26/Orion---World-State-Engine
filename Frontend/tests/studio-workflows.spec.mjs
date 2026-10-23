import { test, expect } from './fixtures/world.mjs';

const openArin = async page => {
  await page.goto('/worlds/w1/world');
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
};

test('traits persist after reload, can be removed, and unconfirmed writes keep the input', async ({ page, world }) => {
  await openArin(page);
  await page.getByRole('button', { name: 'Add trait', exact: true }).click();
  await page.getByLabel('New trait').fill('Patient');
  world.ignoreEntityUpdate = true;
  await page.getByRole('button', { name: 'Save trait' }).click();
  await expect(page.getByRole('alert')).toContainText('backend did not confirm');
  await expect(page.getByLabel('New trait')).toHaveValue('Patient');
  world.ignoreEntityUpdate = false;
  await page.getByRole('button', { name: 'Save trait' }).click();
  await expect(page.getByLabel('New trait')).toHaveCount(0);
  expect(world.writes.at(-1).json.attributes.traits).toEqual(['Patient']);
  await page.reload();
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Remove trait Patient' })).toBeVisible();
  await page.getByRole('button', { name: 'Remove trait Patient' }).click();
  await expect(page.getByRole('button', { name: 'Remove trait Patient' })).toHaveCount(0);
  expect(world.entities[0].facts.find(fact => fact.property_name === 'traits').current_version.value).toEqual([]);
});

test('failed fact mutations remain visible and retries use the persisted fact id', async ({ page, world }) => {
  await openArin(page);
  await page.getByRole('button', { name: /Add Fact/ }).click();
  await page.getByLabel('Fact property').fill('title');
  await page.getByLabel('Fact value').fill('Archivist');
  world.failNextFact = true;
  await page.getByRole('button', { name: 'Submit Fact' }).click();
  await expect(page.getByText('Fact was not saved', { exact: true })).toBeVisible();
  expect(world.entities[0].facts).toHaveLength(0);
  await expect(page.getByLabel('Fact value')).toHaveValue('Archivist');
  await page.getByRole('button', { name: 'Submit Fact' }).click();
  await expect(page.getByLabel('Entity inspector', { exact: true }).getByText('title: Archivist', { exact: true })).toBeVisible();
  world.failNextFactDelete = true;
  await page.getByRole('button', { name: 'Delete fact' }).click();
  await expect(page.getByRole('alert')).toHaveText('Fact was not deleted');
  await expect(page.getByLabel('Entity inspector', { exact: true }).getByText('title: Archivist', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Delete fact' }).click();
  await expect(page.getByText('title: Archivist', { exact: true })).toHaveCount(0);
  expect(world.writes.at(-1).path).toMatch(/facts\/fact-record-id$/);
});

test('chapter save failure keeps the draft and retry confirms the backend before leaving edit mode', async ({ page, world }) => {
  await page.goto('/worlds/w1/manuscripts/ms1');
  await page.getByRole('button', { name: 'Edit Text', exact: true }).click();
  await page.getByLabel('Chapter text').fill('Arin wrote a persistent chapter.');
  world.failNextChapter = true;
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await expect(page.getByRole('alert')).toContainText('Chapter was not saved');
  await expect(page.getByLabel('Chapter text')).toHaveValue('Arin wrote a persistent chapter.');
  expect(world.chapter.content).not.toContain('persistent chapter');
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await expect(page.getByLabel('Chapter text')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /Review changes/ })).toBeVisible();
  await page.getByRole('button', { name: 'Discard all' }).click();
  await page.reload();
  await expect(page.locator('.prose')).toContainText('Arin wrote a persistent chapter.');
});

test('authors can keep saving text while an extraction runs in the background', async ({ page, world }) => {
  world.completeChapterJobs = false;
  await page.goto('/worlds/w1/manuscripts/ms1');
  await page.getByRole('button', { name: /Re-run Extraction/ }).click();
  await expect(page.getByRole('button', { name: 'Cancel extraction' })).toBeVisible();
  await page.getByRole('button', { name: 'Edit Text', exact: true }).click();
  await page.getByLabel('Chapter text').fill('The author keeps writing while the world is read.');
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await expect(page.getByLabel('Chapter text')).toHaveCount(0);
  expect(world.chapter.content).toBe('The author keeps writing while the world is read.');
  expect(world.job.status).toBe('processing');
});

test('chapter history previews stored text and restores a new version through extraction review', async ({ page, world }) => {
  await page.goto('/worlds/w1/manuscripts/ms1');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  const history = page.getByRole('dialog', { name: 'Chapter History' });
  await history.getByRole('button', { name: /^Version 1/ }).click();
  await expect(history.getByText('Arin waited at Silver Haven. The original version.', { exact: true })).toBeVisible();
  await history.getByRole('button', { name: 'Restore Version 1' }).click();
  await expect(history).toHaveCount(0);
  await expect(page.locator('.prose')).toContainText('The original version.');
  await expect(page.getByRole('heading', { name: /Review changes/ })).toBeVisible();
  expect(world.versions).toHaveLength(3);
  expect(world.versions[0]).toMatchObject({ version_number: 3, is_current: true });
  expect(world.writes.some(write => write.path.endsWith('/versions/v1/restore'))).toBe(true);
});

test('cancel import waits for the backend and cancelled jobs stay cancelled on reload', async ({ page, world }) => {
  await page.goto('/worlds/w1/processing?jobId=job1');
  world.failNextCancel = true;
  await page.getByRole('button', { name: 'Cancel Import', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Cancellation could not be confirmed');
  expect(world.job.status).toBe('processing');
  await page.getByRole('button', { name: 'Cancel Import', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Import cancelled');
  await expect(page).toHaveURL(/processing\?jobId=job1/);
  await page.reload();
  await expect(page.getByRole('status')).toHaveText('Import cancelled');
  await expect(page.getByRole('button', { name: 'Cancel Import', exact: true })).toHaveCount(0);
});

test('leaving processing keeps extraction visible in the world shell', async ({ page }) => {
  await page.goto('/worlds/w1/processing?jobId=job1');
  await expect(page.getByRole('status')).toContainText('0 of 2 chapters completed');
  await page.getByRole('link', { name: 'Leave reading in background' }).click();
  await expect(page).toHaveURL(/\/worlds\/w1$/);
  await expect(page.getByText(/Extracting manuscript… 0 of 2 chapters completed/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'View progress' })).toHaveAttribute('href', '/worlds/w1/processing?jobId=job1');
});

test('archive upload opens live extraction progress instead of claiming completion', async ({ page }) => {
  await page.goto('/worlds/w1/manuscripts');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Browse manuscript files' }).click();
  await (await chooser).setFiles({ name: 'new-story.txt', mimeType: 'text/plain', buffer: Buffer.from('Chapter one.') });
  await expect(page).toHaveURL(/\/worlds\/w1\/processing\?jobId=job1/);
  await expect(page.getByRole('status')).toContainText('0 of 2 chapters completed');
});

test('EPUB is rejected before creating a world or uploading bytes', async ({ page, world }) => {
  await page.goto('/worlds/new');
  const file = page.getByLabel('Choose manuscript');
  await expect(file).toHaveAttribute('accept', '.txt,.md,.pdf,.docx');
  await file.setInputFiles({ name: 'novel.epub', mimeType: 'application/epub+zip', buffer: Buffer.from('PK archive') });
  await expect(page.getByRole('alert')).toContainText('EPUB is not supported');
  expect(world.writes).toHaveLength(0);
});

test('ledger selection keeps survivor choice, merge and bulk delete accessible', async ({ page, world }) => {
  await page.goto('/worlds/w1/world');
  await page.getByRole('button', { name: /Select \/ Merge/ }).click();
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('heading', { name: 'Mira', exact: true }).click();
  await page.getByRole('button', { name: /Merge Entities \(2\)/ }).click();
  await expect(page.getByRole('heading', { name: 'Merge Entities', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm & Execute Merge' }).click();
  await expect(page.getByRole('heading', { name: 'Mira', exact: true })).toHaveCount(0);
  expect(world.writes.find(write => write.path.endsWith('/merge')).json).toEqual({ source_id: 'mira', target_id: 'arin' });
  await page.getByRole('button', { name: /Select \/ Merge/ }).click();
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('button', { name: /Bulk Delete \(1\)/ }).click();
  await page.getByRole('button', { name: 'Delete Selected', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Arin', exact: true })).toHaveCount(0);
});

test('contradiction decisions report failures and preserve reject and restore', async ({ page, world }) => {
  world.contradictions.push({ id: 'c1', contradiction_type: 'FACT_FACT', explanation: '[AGE_MONOTONIC] Age decreased.', confidence: 0.9, status: 'DETECTED', sources: [], old_fact_version_id: 'old', new_fact_version_id: 'new' });
  await page.goto('/worlds/w1/contradictions');
  await page.getByRole('button', { name: 'Resolve Conflict' }).click();
  world.failNextDecision = true;
  await page.getByRole('button', { name: /Keep New Version/ }).click();
  await expect(page.getByRole('alert')).toHaveText('Decision was not saved');
  expect(world.contradictions[0].status).toBe('DETECTED');
  await page.getByRole('button', { name: /Keep New Version/ }).click();
  await page.getByRole('button', { name: /resolved \(1\)/i }).click();
  await expect(page.getByRole('heading', { name: 'Age monotonic' })).toBeVisible();
  expect(world.writes.filter(write => write.path.endsWith('/resolve')).at(-1).json.preferred_fact_version_id).toBe('new');
  world.contradictions[0].status = 'DETECTED';
  await page.reload();
  await page.getByRole('button', { name: 'Reject', exact: true }).click();
  await page.getByRole('button', { name: /rejected \(1\)/i }).click();
  await page.getByRole('button', { name: 'Restore', exact: true }).click();
  expect(world.contradictions[0].status).toBe('DETECTED');
});

test('settings retain profile, password, world edits and preference controls', async ({ page, world }) => {
  await page.goto('/worlds/w1');
  await page.getByRole('button', { name: 'Archive Settings', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Archive Settings' });
  await settings.getByLabel('World name', { exact: true }).fill('New Chronicle');
  await settings.getByRole('button', { name: 'Save world' }).click();
  await expect(settings.getByText('World saved.')).toBeVisible();
  await settings.getByRole('button', { name: 'long', exact: true }).click();
  await expect.poll(() => world.profile.preferences.chat_reply_length).toBe('long');
  await page.keyboard.press('Escape');
  await expect(settings).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'New Chronicle', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Creator Profile', exact: true }).click();
  const profile = page.getByRole('dialog', { name: 'Creator Profile' });
  await profile.getByLabel('Pen name').fill('A. Scribe');
  await profile.getByRole('button', { name: 'Save', exact: true }).click();
  await expect.poll(() => world.profile.display_name).toBe('A. Scribe');
  await profile.getByPlaceholder('Current password').fill('old-password');
  await profile.getByPlaceholder('New password (8+ characters)').fill('new-password');
  await profile.getByRole('button', { name: 'Change password' }).click();
  await expect(profile.getByText('Password changed.')).toBeVisible();
});

test('timeline keeps creation errors, participant roles, ordering, editing and deletion', async ({ page, world }) => {
  await page.goto('/worlds/w1/timeline');
  await page.getByRole('button', { name: 'Add Event', exact: false }).click();
  const form = page.getByRole('dialog', { name: 'Add Chronicle Event' });
  await form.getByLabel('Event description').fill('Arin reaches the archive.');
  await form.getByLabel('Event type', { exact: true }).fill('ARRIVAL');
  await form.getByLabel('Event chapter').selectOption('ch1');
  await form.getByLabel('Event participant').selectOption('arin');
  await form.getByLabel('Participant role').fill('WITNESS');
  await form.getByRole('button', { name: 'Add', exact: true }).click();
  world.failNextEvent = true;
  await form.getByRole('button', { name: 'Create Event' }).click();
  await expect(form.getByRole('alert')).toHaveText('Event could not be saved');
  await expect(form.getByLabel('Event description')).toHaveValue('Arin reaches the archive.');
  await form.getByRole('button', { name: 'Create Event' }).click();
  await expect(form).toHaveCount(0);
  expect(world.events.at(-1).participants).toMatchObject([{ entity_id: 'arin', role: 'WITNESS' }]);
  await page.getByRole('button', { name: 'Move later in chapter', exact: true }).first().click();
  await expect.poll(() => world.writes.filter(write => write.path.endsWith('/events/reorder')).length).toBe(1);
  expect(world.writes.find(write => write.path.endsWith('/events/reorder')).json.event_ids).toEqual(['ev2', 'ev1', 'event-2']);
  await page.locator('article').filter({ hasText: 'Arin reaches the archive.' }).click();
  await page.getByRole('button', { name: /Edit Event/ }).click();
  const edit = page.getByRole('dialog', { name: 'Edit Chronicle Event' });
  await edit.getByLabel('Event description').fill('Arin left the archive.');
  await edit.getByRole('button', { name: 'Save Changes' }).click();
  await expect(edit).toHaveCount(0);
  await page.reload();
  await page.getByLabel('Search timeline').fill('Arin left');
  await expect(page.locator('article')).toHaveCount(1);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete event', exact: true }).click();
  await expect(page.locator('article')).toHaveCount(0);
  expect(world.events).toHaveLength(2);
});

test('review preserves changed values by default and applies dependent items only after approval', async ({ page, world }) => {
  world.proposals = [
    { id: 'p1', kind: 'entity', change: 'new', summary: 'New character: Orla', proposed: { canonical_name: 'Orla', entity_type: 'character' } },
    { id: 'p2', kind: 'fact', change: 'new', summary: 'Orla title: Scout', entity: { entity_ref: 'p1' }, proposed: { property_name: 'title', value: 'Scout' } },
    { id: 'p3', kind: 'fact', change: 'changed', summary: 'Arin rank: Captain', entity: { entity_id: 'arin' }, current: { fact_version_id: 'old', value: 'Scribe' }, proposed: { property_name: 'rank', value: 'Captain' } },
  ];
  world.profile.preferences.review_preselect_new = false;
  await page.goto('/worlds/w1/manuscripts/ms1');
  await page.getByRole('button', { name: /Re-run Extraction/ }).click();
  const review = page.getByRole('dialog', { name: /Review changes/ });
  await expect(review).toBeVisible();
  const entity = review.getByRole('checkbox', { name: /New character: Orla/ });
  const fact = review.getByRole('checkbox', { name: /Orla title/ });
  const changed = review.getByRole('checkbox', { name: /Arin rank/ });
  await expect(entity).not.toBeChecked();
  await expect(fact).toBeDisabled();
  await expect(changed).not.toBeChecked();
  await entity.check();
  await fact.check();
  await review.getByRole('button', { name: 'Apply 2 selected' }).click();
  await expect(review.getByText('Applied 2 changes.', { exact: true })).toBeVisible();
  expect(world.entities.find(entity => entity.canonical_name === 'Orla').facts[0].current_version.value).toBe('Scout');
  expect(world.entities[0].facts).toHaveLength(0);
  await review.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(review).toHaveCount(0);
});

test('sign-in keeps registration validation and the existing placeholder buttons', async ({ page }) => {
  const writes = [];
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === 'POST') writes.push(path);
    const body = path.endsWith('/login') ? { access_token: 'test-token', token_type: 'bearer' }
      : path.endsWith('/worlds') ? [] : { id: 'author', email: 'test@example.com' };
    await route.fulfill({ status: path.endsWith('/register') ? 201 : 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/signin');
  await expect(page.getByRole('button', { name: 'Forgot Password?' })).toBeVisible();
  await expect(page.getByTitle('Fingerprint Login')).toBeVisible();
  await expect(page.getByTitle('Public Key Auth')).toBeVisible();
  await page.getByRole('button', { name: 'Forge an entry', exact: true }).click();
  await page.getByLabel('Email Address').fill('test@example.com');
  await page.getByLabel('Password', { exact: true }).fill('short');
  await page.getByRole('button', { name: /Register/ }).click();
  await expect(page.getByText('Password must be at least 8 characters long.')).toBeVisible();
  expect(writes).toHaveLength(0);
  await page.getByLabel('Password', { exact: true }).fill('long-password');
  await page.getByRole('button', { name: /Register/ }).click();
  await expect(page).toHaveURL(/\/worlds$/);
  expect(writes).toEqual(['/api/v1/auth/register', '/api/v1/auth/login']);
});
