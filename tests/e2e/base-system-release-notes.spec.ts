// System › Updates lists what is new under the version: the notes this hub ships, as its own API serves them. Who runs
// the business reads them, at the three sizes; a failed read says so and keeps the version.
// flow: BASE-F116
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  A,
  api,
  capture,
  horizontalOverflow,
  hostPage,
  shown,
  signedInSpanish,
  testid,
  THREE_SIZES,
  untilStill,
} from './helpers';

interface Note {
  id: string;
  title: string;
}

const NOTES_ROUTE = /\/api\/system\/release-notes\b/;

/** The notes the hub serves this person: what the list must show, in that order. */
async function served(context: BrowserContext): Promise<Note[]> {
  const answer = await api<{ items: Note[] }>(context, A, 'GET', '/system/release-notes');
  expect(answer.status).toBe(200);
  return answer.data.items;
}

async function openUpdates(browser: Browser, viewport: { width: number; height: number }) {
  return hostPage(browser, A, { viewport, next: '/system#updates' });
}

/** The list on screen is the hub's: the same notes, in the same order, each with its kind and its day. */
async function listsWhatIsServed(page: Page, context: BrowserContext): Promise<void> {
  const notes = await served(context);
  expect(notes.length).toBeGreaterThan(0);
  const rows = shown(page).locator('[data-testid="system-release-note"]');
  await expect(rows).toHaveCount(notes.length);
  await expect(rows.locator('[data-testid="system-release-note-title"]')).toHaveText(notes.map((note) => note.title));
  expect(await rows.evaluateAll((items) => items.map((item) => item.getAttribute('data-id')))).toEqual(
    notes.map((note) => note.id),
  );
  await expect(rows.first().locator('[data-testid="system-release-note-kind"]')).toHaveText(/^(New|Improved|Fixed)$/);
  await expect(rows.first().locator('[data-testid="system-release-note-day"]')).toHaveText(/^[A-Z][a-z]{2} \d{1,2}, \d{4}$/);
}

async function snap(page: Page, name: string): Promise<void> {
  await page.mouse.move(0, 0);
  await expect(shown(page).locator('[data-testid$="-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name, { fullPage: true });
}

for (const { label, ...viewport } of THREE_SIZES) {
  test(`what is new, under the version, at ${label}`, async ({ browser }) => {
    const { context, page } = await openUpdates(browser, viewport);
    try {
      await expect(testid(page, 'system-release-version')).toContainText('You are on ');
      await expect(testid(page, 'system-release-notes').locator('h3')).toHaveText("What's new");
      await listsWhatIsServed(page, context);
      await snap(page, `BASE-F116-release-notes-${label}`);
    } finally {
      await context.close();
    }
  });
}

test('in Spanish, the list and its kinds are in Spanish', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, THREE_SIZES[1], '/system#updates');
  try {
    await expect(testid(page, 'system-release-notes').locator('h3')).toHaveText('Novedades');
    const first = shown(page).locator('[data-testid="system-release-note"]').first();
    await expect(first.locator('[data-testid="system-release-note-kind"]')).toHaveText(/^(Nuevo|Mejora|Arreglo)$/);
    await expect(first.locator('[data-testid="system-release-note-day"]')).toHaveText(/^\d{1,2} [a-z]{3} \d{4}$/);
    await snap(page, 'BASE-F116-release-notes-es-834');
  } finally {
    await context.close();
  }
});

test('a failed read says so with «Retry», and the version stays in view', async ({ browser }) => {
  const { context, page } = await openUpdates(browser, THREE_SIZES[0]);
  try {
    await page.route(NOTES_ROUTE, (route) =>
      route.fulfill({ status: 500, json: { error: { code: 'internal_error', message: 'Down.' } } }),
    );
    await page.reload();
    await expect(testid(page, 'system-release-notes-error')).toContainText("Could not load what's new");
    await expect(testid(page, 'system-release-version')).toContainText('You are on ');
    await snap(page, 'BASE-F116-release-notes-error-390');
    await page.unroute(NOTES_ROUTE);
    await testid(page, 'system-release-notes-retry').click();
    await expect(testid(page, 'system-release-notes-error')).toHaveCount(0);
    await listsWhatIsServed(page, context);
  } finally {
    await context.close();
  }
});

test('with no notes, it says there is nothing new yet', async ({ browser }) => {
  const { context, page } = await openUpdates(browser, THREE_SIZES[0]);
  try {
    await page.route(NOTES_ROUTE, (route) => route.fulfill({ json: { items: [], total: 0 } }));
    await page.reload();
    await expect(testid(page, 'system-release-notes-empty')).toContainText('Nothing new yet.');
    await expect(shown(page).locator('[data-testid="system-release-note"]')).toHaveCount(0);
    await snap(page, 'BASE-F116-release-notes-empty-390');
  } finally {
    await context.close();
  }
});
