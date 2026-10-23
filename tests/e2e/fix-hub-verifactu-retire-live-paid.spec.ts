// flow: VERIFACTU-F08
// FIX-HUB-VERIFACTU-RETIRE-LIVE-PAID (PLAN §30, round 2026-10-22b: VeriFactu on Free): «Pasar a producción» asks for no
// plan option any more. In VeriFactu → Ajustes, in Spanish, against the real Hub: with ERPlora filing and the
// authorisation approved by the SaaS's photo, what is missing is that this server has not opened real filing
// (`production_closed`: the e2e server keeps it closed), never «la opción en vivo…», with the photo of today's SaaS
// (no `live_paid`) and with one of the SaaS before it (`live_paid: false`, sent until it stops: expand/contract).
// The photo is sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`, signed); what the run changes in
// VeriFactu's configuration and in `a`'s photo is put back after it (or removed, if the run made it).
import { createHmac } from 'node:crypto';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, login, psql, shot, shown, topbarApps } from './helpers';
import { FLOW_VIEWPORTS } from './invoice-helpers';
import { STACK } from './stack';

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The copies the run keeps of what it changes. */
const BACKUP = { config: 'e2e_fix_live_paid_config_before', photo: 'e2e_fix_live_paid_photo_before' };
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
const CLOSED = 'ERPlora todavía no ha abierto la presentación real a la AEAT en este servidor';

/** The id of `a` in the registry (`base_hub`), read before the test. */
let hubId = '';
/** Whether VeriFactu's configuration row existed before the run (if not, the run's photo makes it). */
let hadConfig = true;
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);

/** The SaaS's photo of hub `a`, with the VeriFactu block given. */
async function pushPhoto(verifactu: Record<string, unknown>): Promise<void> {
  version += 1;
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

function approved(): Record<string, unknown> {
  return { status: 'approved', updated_at: new Date().toISOString(), reason: '' };
}

/** The owner on `a`, in Spanish, on VeriFactu → Ajustes. */
async function spanishSettings(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/verifactu/settings');
  // The Hub's language cookie, the one the sign-in sets from the account.
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/verifactu/settings`);
  await topbarApps(page).waitFor({ state: 'visible' });
  return { context, page };
}

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(hubId)) {
    throw new Error(`The registry of DB_NAME=${STACK.database} has no hub a (got ${JSON.stringify(hubId)}): run node tests/e2e/database.ts.`);
  }
  hadConfig = psql('select count(*) from verifactu_config') !== '0';
  // Past the version the hub already applied, or the run's photos would change nothing.
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

test('VERIFACTU-F08: with the authorisation approved, only the closed server keeps it from going live, never a plan option', async ({ browser }) => {
  // Today's SaaS: the VeriFactu block carries the authorisation alone.
  await pushPhoto({ representation: approved() });
  psql("update verifactu_config set route = 'erplora'");
  const { context, page } = await spanishSettings(browser);
  const view = shown(page);
  const blockers = view.locator('[data-testid=verifactu-settings-live-blockers]');
  await expect(blockers).toContainText('Todavía no puede pasar a producción:');
  await expect(blockers).toContainText(CLOSED);
  await expect(blockers).not.toContainText('opción en vivo');
  await expect(blockers).not.toContainText('falta que ERPlora apruebe tu autorización firmada');
  await expect(view.locator('[data-testid=verifactu-settings-go-live]')).toHaveAttribute('aria-disabled', 'true');
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(shown(page).locator('[data-testid=verifactu-settings-live-blockers]')).toBeVisible();
    await page.screenshot({ path: shot(`FIX-HUB-VERIFACTU-RETIRE-LIVE-PAID-${viewport.label}`) });
  }

  // The SaaS before this change still says `live_paid: false` until it stops: the photo is applied, nobody reads it.
  await pushPhoto({ representation: approved(), live_paid: false });
  expect(psql('select synced_version from verifactu_config')).toBe(String(version));
  await page.reload();
  await topbarApps(page).waitFor({ state: 'visible' });
  const after = shown(page).locator('[data-testid=verifactu-settings-live-blockers]');
  await expect(after).toContainText(CLOSED);
  await expect(after).not.toContainText('opción en vivo');
  await expect(after).not.toContainText('falta que ERPlora apruebe tu autorización firmada');
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});
