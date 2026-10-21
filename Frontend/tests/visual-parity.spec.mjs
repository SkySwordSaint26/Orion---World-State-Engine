import { test, expect } from './fixtures/world.mjs';

test.use({ reducedMotion: 'reduce' });

for (const viewport of [{ width: 1440, height: 1000 }, { width: 900, height: 1000 }, { width: 390, height: 844 }]) {
  test(`all redesigned routes remain usable at ${viewport.width}px`, async ({ page, world }, testInfo) => {
    await page.setViewportSize(viewport);
    world.entities[0].facts.push({ id: 'description', property_name: 'description', current_version: { value: 'An archivist following the forgotten treaties of Silver Haven.', status: 'ACTIVE' } });
    world.relationships.push({ id: 'r1', source_entity_id: 'arin', target_entity_id: 'mira', relationship_type: 'ALLY_OF', chapter_id: 'ch1' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const [name, path] of [
      ['worlds', '/worlds'], ['new-world', '/worlds/new'], ['overview', '/worlds/w1'],
      ['manuscripts', '/worlds/w1/manuscripts'], ['writing', '/worlds/w1/manuscripts/ms1'],
      ['ledger', '/worlds/w1/world'], ['graph', '/worlds/w1/graph'], ['timeline', '/worlds/w1/timeline'],
      ['contradictions', '/worlds/w1/contradictions'], ['assistant', '/worlds/w1/assistant'],
      ['processing', '/worlds/w1/processing?jobId=job1'],
    ]) {
      await page.goto(path);
      await expect(page.getByRole('main')).toBeVisible();
      await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(resolve => setTimeout(resolve, 1200))]));
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`${name}-${viewport.width}.png`), fullPage: true, animations: 'disabled' });
    }
    expect(errors).toEqual([]);
    if (viewport.width < 768) {
      await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
      await expect(page.getByRole('link', { name: 'World Ledger', exact: true })).toBeVisible();
      await page.getByRole('link', { name: 'World Ledger', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'The World’s Register' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Close navigation', exact: true })).toHaveCount(0);
    }
  });
}
