// flow: BASE-F01 («Termina de configurar tu negocio») with VeriFactu's step (VERIFACTU-F01, VERIFACTU-F08); hub#682
// VeriFactu is Spanish law, so «Configura VeriFactu» is only for a business in Spain. With `a` filing in production and
// ERPlora's authorisation revoked (the step a ⛔ wall: the case that shows most), erplora.com registers `a`'s business
// in Poland: the owner's Home has no «Configura VeriFactu» in «Termina de configurar tu negocio», not even under «Ver
// todo», counts one step fewer, and the strip «Todavía no puedes facturar» does not name it. Registered in Spain, or
// with no country (a demo, ERPlora's own hub: ERPlora's market, Spain), the step is there with «Necesario para
// facturar» and the strip names it. In 375, 768 and 1440, with the captures `<KEY>-<PL|ES|none>-<width>` of the Home.
// The registration and the photo are sent the way the SaaS sends them (`PUT /internal/hubs/{id}` and `…/state`,
// signed); production is the configuration's environment, set in the database for the run (nothing is sent). What the
// run changes in `a`'s registration, its photo and VeriFactu's configuration is put back after it.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import {
  A,
  horizontalOverflow,
  internalPut,
  login,
  psql,
  registerBusinessIn,
  type Registration,
  registrationOf,
  shot,
  shown,
  untilStill,
} from './helpers';

const KEY = 'FIX-HUB-HOME-VERIFACTU-STEP-ONLY-IN-SPAIN';
const STEP = 'verifactu.sending_route';
const TITLE = 'Configura VeriFactu';
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '768', width: 768, height: 1024 },
  { label: '1440', width: 1440, height: 900 },
];
/** The countries of the run: Poland, Spain and none (ERPlora's market), each with whether the step is for it. */
const COUNTRIES = [
  { label: 'PL', country: 'PL', told: false },
  { label: 'ES', country: 'ES', told: true },
  { label: 'none', country: '', told: true },
];
/** The copies the run keeps of what it changes. */
const BACKUP = { config: 'e2e_fix_vf_spain_config_before', photo: 'e2e_fix_vf_spain_photo_before' };
/** The configuration's columns the run moves (the photo's, the route and the environment). */
const CONFIG_COLUMNS = [
  'route',
  'environment',
  'production_since',
  'representation_status',
  'representation_updated_at',
  'representation_reason',
  'synced_version',
  'synced_at',
  'hub_status',
  'hub_id',
];

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let hadConfig = true;
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);

/** The SaaS's photo of hub `a`, with the signed authorisation in `status`. */
async function pushPhoto(status: string): Promise<void> {
  version += 1;
  const verifactu = { representation: { status, updated_at: new Date().toISOString(), reason: '' } };
  const body = JSON.stringify({ hub_id: original.id, slug: 'a', version, status: 'active', verifactu });
  const response = await internalPut(`/internal/hubs/${original.id}/state`, body);
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** `a` files in production through ERPlora, its authorisation revoked: the step is a ⛔ wall where it applies. */
async function walledInProduction(): Promise<void> {
  await pushPhoto('approved');
  await pushPhoto('revoked');
  psql("update verifactu_config set route = 'erplora', environment = 'production', production_since = now()");
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  original = registrationOf('a');
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(original.id)) {
    throw new Error(`The registry has no hub a (got ${JSON.stringify(original.id)}): run node tests/e2e/database.ts.`);
  }
  hadConfig = psql('select count(*) from verifactu_config') !== '0';
  version = Math.max(
    version,
    Number(psql('select coalesce(max(synced_version), 0) from verifactu_config')),
    Number(psql(`select state_version from base_hub where id = '${original.id}'`)),
  );
  psql(
    [
      `drop table if exists ${BACKUP.photo}`,
      `create table ${BACKUP.photo} as select id, state, state_version from base_hub where id = '${original.id}'`,
    ].join('; '),
  );
  psql([`drop table if exists ${BACKUP.config}`, `create table ${BACKUP.config} as select * from verifactu_config`].join('; '));
  await walledInProduction();
});

test.afterAll(async () => {
  if (!original) return;
  await registerBusinessIn(original, original.country);
  const sets = CONFIG_COLUMNS.map((column) => `${column} = b.${column}`).join(', ');
  psql(
    [
      hadConfig
        ? `update verifactu_config c set ${sets} from ${BACKUP.config} b where b.id = c.id`
        : 'delete from verifactu_config where not exists (select 1 from verifactu_record)',
      `drop table ${BACKUP.config}`,
    ].join('; '),
  );
  psql(
    [
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP.photo} b where b.id = h.id`,
      `drop table ${BACKUP.photo}`,
    ].join('; '),
  );
});

/** The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function ownerOnHome(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const row = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);
const strip = (page: Page): Locator => shown(page).locator('[data-testid="blocking-strip"]');
const named = (page: Page): Locator => strip(page).locator('[data-testid="blocking-item"]').filter({ hasText: TITLE });

/** How many steps «Termina de configurar tu negocio» counts («{done} de {total} hechos»). */
async function counted(page: Page): Promise<number> {
  const text = (await card(page).locator('[data-testid="setup-progress"]').textContent()) ?? '';
  const total = /de (\d+) hechos/.exec(text);
  expect(total, `the progress says how many steps there are: ${JSON.stringify(text)}`).not.toBeNull();
  return Number(total![1]);
}

/** Every step of the card in sight: «Ver todo» pressed when the fold leaves some out. */
async function unfolded(page: Page): Promise<void> {
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') {
    await toggle.click();
    await expect(toggle).toHaveText('Ver menos');
  }
}

for (const size of SIZES) {
  test(`BASE-F01 VERIFACTU-F01 hub#682 at ${size.label}: «Configura VeriFactu» and its wall only for a business in Spain or without a country`, async ({ browser }) => {
    const totals: Record<string, number> = {};
    for (const { label, country, told } of COUNTRIES) {
      await registerBusinessIn(original, country);
      const { context, page } = await ownerOnHome(browser, { width: size.width, height: size.height });
      try {
        // Folded, the ⛔ go first: the capture shows the wall where it applies, and its absence in Poland.
        if (told) await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Necesario para facturar');
        await card(page).scrollIntoViewIfNeeded();
        await untilStill(page);
        expect(await horizontalOverflow(page), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: shot(`${KEY}-${label}-${size.label}`) });

        await unfolded(page);
        totals[label] = await counted(page);
        if (told) {
          await expect(row(page).locator('.setup-row-title')).toHaveText(TITLE);
        } else {
          await expect(card(page).locator('[data-testid="setup-row"]').first()).toBeVisible();
          await expect(row(page)).toHaveCount(0);
          await expect(card(page).getByText(TITLE)).toHaveCount(0);
        }

        // Over the other screens the strip names the wall only where the step is for the business.
        await page.goto(`${A}/#actividad`);
        await expect(shown(page).locator('[data-testid="home-activity-loading"]')).toHaveCount(0);
        await expect(named(page)).toHaveCount(told ? 1 : 0);
      } finally {
        await context.close();
      }
    }
    // The same Home, one step fewer for the business in Poland: the step is gone, nothing else.
    expect([totals.PL + 1, totals.none]).toEqual([totals.ES, totals.ES]);
  });
}
