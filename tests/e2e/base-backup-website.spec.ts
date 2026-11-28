// flow: BASE-F35, BASE-F36, BASE-F31 — a backup of the business takes its website, on hub `a`: in Settings › Data ›
// Export, Website shows its part «Design, texts and images» once its data is ticked, never «Its data does not travel in
// the file». The file downloaded carries the page being edited, its logo inside as a WebP; with the page gone, as in a
// business that never saved one, loading the file back from Import brings it as an unpublished draft with its logo
// uploaded again. Each screen in the three sizes, and in Spanish. The site goes back as the run found it, offline: the
// other specs on hub `a` expect `/` to jump to the login.
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { importBack, rowsIn, snap } from './backup-file';
import { A, api, ARTIFACTS, hostPage, psql, shown, signedInSpanish, testid, turnOffTurnedOn, turnOnMissing } from './helpers';
import { THREE_SIZES } from './screen';
import { photo, type Site, siteBackOffline } from './website-helpers';

test.use({ actionTimeout: 30_000 });

const PART = 'website.site';
const LABEL = { en: 'Design, texts and images', es: 'Diseño, textos e imágenes' } as const;
const TITLE = `E2E Copy Website ${Date.now().toString(36)}`;
const LOGO = 'e2e-copy-logo.jpg';

interface Ref {
  id: string;
  name: string;
}
interface SiteRead extends Site {
  content: { hero: { title: string }; topbar: { logo: Ref | null } };
  is_live: boolean;
  published_version: number;
}

const turnedOn: string[] = [];
let found: Site | undefined;
let owner: { context: BrowserContext; page: Page } | undefined;

async function site(context: BrowserContext): Promise<SiteRead> {
  const read = await api<SiteRead>(context, A, 'GET', '/website/site');
  expect(read.status).toBe(200);
  return read.data;
}

/** The page saved with a title of the spec's and a logo uploaded for it; the logo's id. */
async function ourPage(context: BrowserContext, page: Page): Promise<string> {
  const raw = await photo(page, 'Logo', 200);
  const logo = await api<Ref>(context, A, 'POST', '/website/images', { filename: LOGO, content_type: 'image/jpeg', data_base64: raw.toString('base64') });
  expect(logo.status, JSON.stringify(logo.data)).toBe(201);
  const now = await site(context);
  const content = { ...now.content, hero: { ...now.content.hero, title: TITLE }, topbar: { ...now.content.topbar, logo: { id: logo.data.id } } };
  const saved = await api(context, A, 'POST', '/website/site', { template: now.template, theme: now.theme, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  return logo.data.id;
}

/** Settings › Data › Export with Website's data ticked: its part, with its one page. */
async function websitePart(page: Page, language: 'en' | 'es'): Promise<void> {
  await page.goto(`${A}/settings?data=export#data`);
  const row = shown(page).locator('[data-testid="export-app"][data-id="website"]');
  await row.scrollIntoViewIfNeeded();
  await expect(row).not.toContainText(language === 'en' ? 'Its data does not travel in the file' : 'Sus datos no viajan en el archivo');
  await testid(page, 'export-data-website').click();
  const part = shown(page).locator(`[data-testid="export-table-${PART}"]`);
  await expect(part).toContainText(`${LABEL[language]} ·`);
  await part.scrollIntoViewIfNeeded();
}

test.beforeAll(async ({ browser }) => {
  owner = await hostPage(browser, A, { next: '/settings#data', viewport: { width: 1440, height: 900 } });
  await turnOnMissing(owner.context, A, ['website'], turnedOn);
  found = await site(owner.context);
});

test.afterAll(async () => {
  try {
    if (owner && found) await siteBackOffline(owner.context, found);
    if (owner) await turnOffTurnedOn(owner.context, A, turnedOn);
  } finally {
    await owner?.context.close();
  }
});

for (const size of THREE_SIZES) {
  const label = `${size.width}x${size.height}`;

  test(`a backup takes the website and brings it back as an unpublished draft at ${label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await hostPage(browser, A, { viewport: size, next: '/settings#data' });
    const logo = await ourPage(context, page);
    await websitePart(page, 'en');
    await snap(page, `BASE-F36-backup-website-${label}`);

    const [download] = await Promise.all([page.waitForEvent('download'), testid(page, 'export-submit').click()]);
    const saved = join(ARTIFACTS, `backup-website-${label}-${download.suggestedFilename()}`);
    await download.saveAs(saved);
    const [row] = rowsIn(saved, PART) as { content: { hero: { title: string }; topbar: { logo: { file: string; name: string } } } }[];
    expect([row.content.hero.title, row.content.topbar.logo.name]).toEqual([TITLE, LOGO]);
    const inside = execFileSync('unzip', ['-Z1', saved], { encoding: 'utf8' }).split('\n');
    expect(inside).toContain(`media/${row.content.topbar.logo.file}`);

    // A business that never saved its page: what the file brings takes its place.
    psql('delete from website_site');
    await importBack(page, saved);
    const loaded = shown(page).locator('[data-testid="report-app"][data-id="website"]');
    await expect(loaded.locator('[data-testid="report-app-status"]')).toContainText('Applied');
    await loaded.scrollIntoViewIfNeeded();
    await snap(page, `BASE-F31-backup-website-back-${label}`);

    const back = await site(context);
    expect([back.content.hero.title, back.content.topbar.logo?.name, back.is_live, back.published_version]).toEqual([TITLE, LOGO, false, 0]);
    expect(back.content.topbar.logo?.id).not.toBe(logo);
    await context.close();
  });

  test(`in Spanish, Website's part says «Diseño, textos e imágenes» at ${label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, size, '/settings#data');
    await websitePart(page, 'es');
    await snap(page, `BASE-F36-backup-website-es-${label}`);
    await context.close();
  });
}
