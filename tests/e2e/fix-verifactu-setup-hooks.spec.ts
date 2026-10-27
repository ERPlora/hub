// flow: HUB_HOME verifactu hooks
// VeriFactu's hooks of the Home (FIX-VERIFACTU-SETUP-HOOKS; the old module's `setup` and `widgets`, the old hub's
// dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads them in Spanish: «Configura
// VeriFactu» pending and «Importante» in «Termina de configurar tu negocio» while ERPlora still has no approved
// authorisation (its «Configurar» leads to VeriFactu's Configuration), done without a reload once the account's photo
// approves it; «Pendientes VeriFactu» on the board by default with the server's figure, and the other three panels
// («Cola de contingencia», «Registros por estado», «Eventos AEAT recientes», whose types speak Spanish, never their
// codes) on the board in each size, leaving the capture `FIX-VERIFACTU-SETUP-HOOKS-<width>`.
// The photo is sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`, signed); what the run changes in
// VeriFactu's configuration and in `a`'s photo is put back after it (or removed, if the run made it).
import { createHmac } from 'node:crypto';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown, untilStill } from './helpers';
import { STACK } from './stack';

const KEY = 'FIX-VERIFACTU-SETUP-HOOKS';
const STEP = 'verifactu.sending_route';
const PANELS = ['verifactu.pending', 'verifactu.contingency', 'verifactu.by_status', 'verifactu.events'];
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';
/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The copies the run keeps of what it changes. */
const BACKUP = { config: 'e2e_fix_vf_hooks_config_before', photo: 'e2e_fix_vf_hooks_photo_before' };
/** The configuration's columns the run moves (the photo's and the route). */
const CONFIG_COLUMNS = [
  'route',
  'representation_status',
  'representation_updated_at',
  'representation_reason',
  'synced_version',
  'synced_at',
  'hub_status',
  'hub_id',
];

let hubId = '';
let hadConfig = true;
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);

/** The SaaS's photo of hub `a`, with the signed authorisation in `status`. */
async function pushPhoto(status: string): Promise<void> {
  version += 1;
  const verifactu = { representation: { status, updated_at: new Date().toISOString(), reason: '' } };
  const body = JSON.stringify({ hub_id: hubId, slug: 'a', version, status: 'active', verifactu });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${hubId}/state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** ERPlora files, and its authorisation is `status`: what the step reads. */
async function erploraWith(status: string): Promise<void> {
  await pushPhoto(status);
  psql("update verifactu_config set route = 'erplora'");
}

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(hubId)) {
    throw new Error(`The registry of DB_NAME=${STACK.database} has no hub a (got ${JSON.stringify(hubId)}): run node tests/e2e/database.ts.`);
  }
  hadConfig = psql('select count(*) from verifactu_config') !== '0';
  version = Math.max(
    version,
    Number(psql('select coalesce(max(synced_version), 0) from verifactu_config')),
    Number(psql(`select state_version from base_hub where id = '${hubId}'`)),
  );
  psql(
    [
      `drop table if exists ${BACKUP.config}`,
      `drop table if exists ${BACKUP.photo}`,
      `create table ${BACKUP.config} as select * from verifactu_config`,
      `create table ${BACKUP.photo} as select id, state, state_version from base_hub where id = '${hubId}'`,
    ].join('; '),
  );
});

test.afterAll(() => {
  const sets = CONFIG_COLUMNS.map((column) => `${column} = b.${column}`).join(', ');
  psql(
    [
      hadConfig
        ? `update verifactu_config c set ${sets} from ${BACKUP.config} b where b.id = c.id`
        : 'delete from verifactu_config where not exists (select 1 from verifactu_record)',
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP.photo} b where b.id = h.id`,
      `drop table ${BACKUP.config}`,
      `drop table ${BACKUP.photo}`,
    ].join('; '),
  );
});

/** The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
  board?: string[],
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  if (board) await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify(board)]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="setup-card"]')).toHaveAttribute('aria-busy', 'false');
  // The owner's Spanish session with VeriFactu's four panels for the fleet's visual sweep
  // (`ui-clip-sweep.sh --storage-state`), when asked.
  if (board && process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const row = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);

/** «Ver todo» when the fold keeps the step out of sight: on a phone it shows 2 rows, and a hub without its tax details
 *  has «Los datos de tu negocio» (⛔, before VeriFactu's) pending too (FIX-INVOICE-SETUP-HOOKS). */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await row(page).count()) === 0 && (await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
}
const panel = (page: Page, key: string): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);

test('HUB_HOME verifactu hooks: «Configura VeriFactu» pending until the authorisation is approved, and «Pendientes VeriFactu» by default', async ({ browser }) => {
  await erploraWith('submitted');
  const { context, page } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    // Pending while ERPlora's authorisation is under review: «Importante», never «Necesario para facturar».
    await expect(row(page).locator('.setup-row-title')).toHaveText('Configura VeriFactu');
    await expect(row(page).locator('.setup-row-desc')).toHaveText(
      'Firma la autorización para que ERPlora envíe tus facturas a la AEAT, o sube el certificado del negocio.',
    );
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');

    // «Pendientes VeriFactu» on the board by default, with what the server counts.
    const pending = panel(page, 'verifactu.pending');
    await expect(pending.locator('[data-testid="widget-title"]')).toHaveText('Pendientes VeriFactu');
    const summary = await api<{ pending_count: number }>(context, A, 'GET', '/verifactu/stats/compliance_summary');
    expect(summary.status).toBe(200);
    await expect(pending.locator('[data-testid="widget-value"]')).toHaveText(new Intl.NumberFormat('es-ES').format(summary.data.pending_count));
    for (const key of PANELS.slice(1)) await expect(panel(page, key)).toHaveCount(0);

    // «Configurar» leads to VeriFactu's Configuration.
    await row(page).locator(`[data-testid="setup-configure-${STEP}"]`).click();
    await expect(page).toHaveURL(`${A}/verifactu/config`);
    await page.goto(`${A}/`);
    await expect(row(page)).toBeVisible();

    // The account approves it: the step is done without a reload (it leaves the folded list; «Ver todo» says «Hecho»).
    await pushPhoto('approved');
    await expect(row(page)).toHaveCount(0);
    await card(page).locator('[data-testid="setup-toggle"]').click();
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Hecho');
    await expect(row(page).locator(`[data-testid="setup-configure-${STEP}"]`)).toHaveCount(0);
  } finally {
    await context.close();
  }
});

for (const size of SIZES) {
  test(`HUB_HOME verifactu hooks at ${size.label}: the step pending and VeriFactu's four panels on the board`, async ({ browser }) => {
    await erploraWith('none');
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height }, PANELS);
    try {
      await unfolded(page);
      await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');
      const titles = ['Pendientes VeriFactu', 'Cola de contingencia', 'Registros por estado', 'Eventos AEAT recientes'];
      for (const [index, key] of PANELS.entries()) {
        await expect(panel(page, key).locator('[data-testid="widget-title"]')).toHaveText(titles[index]);
        await expect(panel(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
        await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
      }
      // The photo just received is the newest event: its type in Spanish, never its code (gh:verifactu#139).
      const events = panel(page, 'verifactu.events');
      await expect(events.locator('[data-testid="verifactu-events-panel-type"]').first()).toHaveText('Configuración cambiada');
      await expect(events).not.toContainText('config_changed');
      await expect(events.locator('[data-testid="verifactu-events-panel-error"]')).toHaveCount(0);
      await expect(panel(page, 'verifactu.by_status').locator('[data-testid="widget-bar"]').first()).toBeVisible();

      // The checklist and the board in sight, as far as the page scrolls, with no sideways scroll.
      await row(page).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
