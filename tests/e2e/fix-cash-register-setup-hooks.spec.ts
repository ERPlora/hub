// flow: CASH_REGISTER-F01 CASH_REGISTER-F12
// Cash register's hooks of the Home (FIX-CASH_REGISTER-SETUP-HOOKS; the old module's `setup` and `widgets`, the old
// hub's dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads them in Spanish: «Tu caja»
// pending and «Recomendado» in «Termina de configurar tu negocio» while the drawer runs on its factory values, done
// without a reload once the settings are saved (also as they came, from the «Configurar» it leads to);
// «Caja (sesión actual)» on the board by default with the open session's expected cash as the server gives it, which
// moves with a cash movement; «Descuadres recientes» to add, with a bar per closed session; and an employee, who counts
// blind, never gets the expected cash panel. Captures `FIX-CASH_REGISTER-SETUP-HOOKS-CASH_REGISTER-F01-<width>` (the
// step) and `…-CASH_REGISTER-F12-<width>` (the two panels).
// The hub's settings row is parked for the run and put back after it; the sessions this file opens (`E2E …` notes)
// are deleted after it, with their movements and counts. A shift an earlier run left open is closed first (one drawer
// open per business), as cash-register-shift.spec.ts does.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, horizontalOverflow, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';
import { stamp } from './sale-helpers';

const KEY = 'FIX-CASH_REGISTER-SETUP-HOOKS';
const STEP = 'cash_register.drawer';
const EXPECTED = 'cash_register.current_session';
const RECENT = 'cash_register.recent_sessions';
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';
/** The hub's own settings row, parked while the run needs a drawer on its factory values. */
const PARKED = 'e2e_fix_cr_hooks_parked';
const RUN = stamp();
/** The sessions this file opened: the only ones its cleanup deletes. */
const mine = new Set<string>();

interface SessionRow {
  id: string;
  number: string;
  expected_balance: number | null;
  difference: number | null;
}
interface Current {
  session: SessionRow | null;
}
interface Currency {
  currency: string;
  decimals: number;
}

test.describe.configure({ mode: 'serial' });

/** The settings back to none at all: the drawer on its factory values, «Tu caja» pending. */
function factoryValues(): void {
  psql('delete from cash_register_settings');
}

test.beforeAll(async ({ browser }) => {
  psql([`drop table if exists ${PARKED}`, `create table ${PARKED} as select * from cash_register_settings`].join('; '));
  factoryValues();
  // Two closed sessions (40 cents short, 5.50 € over) and one open with 100.00 €, all of this run.
  const context = await browser.newContext({ baseURL: A });
  try {
    const page = await context.newPage();
    await login(page, A, '/cash_register/sessions');
    const left = (await api<Current>(context, A, 'GET', '/cash_register/sessions/current')).data.session;
    if (left) {
      const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
        session_id: left.id,
        closing_balance: Math.max(left.expected_balance ?? 0, 0),
        closing_notes: 'e2e: left open by an earlier run',
      });
      expect(closed.status).toBe(200);
    }
    for (const counted of [9960, 10550, null]) {
      const opened = await api<SessionRow>(context, A, 'POST', '/cash_register/sessions/open', {
        opening_balance: 10000,
        opening_notes: `E2E ${RUN}`,
      });
      expect(opened.status).toBe(201);
      mine.add(opened.data.id);
      if (counted === null) break;
      const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
        session_id: opened.data.id,
        closing_balance: counted,
      });
      expect(closed.status).toBe(200);
    }
  } finally {
    await context.close();
  }
});

test.afterAll(() => {
  const ids = [...mine].map((id) => `'${id}'`).join(',');
  if (ids) {
    psql(`delete from cash_register_count where session_id in (${ids})`);
    psql(`delete from cash_register_movement where session_id in (${ids})`);
    psql(`delete from cash_register_session where id in (${ids})`);
  }
  psql(
    [
      'delete from cash_register_settings',
      `insert into cash_register_settings select * from ${PARKED}`,
      `drop table ${PARKED}`,
    ].join('; '),
  );
});

/** A person of `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function spanish(
  browser: Browser,
  viewport: { width: number; height: number },
  options: { board?: string[]; who?: Credentials } = {},
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const { board } = options;
  if (board) await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify(board)]);
  const page = await context.newPage();
  await login(page, A, '/', options.who ?? OWNER);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="widget-board"]')).toBeVisible();
  // The owner's Spanish session with both panels for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
  if (board && !options.who && process.env.E2E_SAVE_STORAGE_STATE) {
    await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  }
  return { context, page };
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const row = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);
const panel = (page: Page, key: string): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);

/** «Ver todo»: a «Recomendado» step is folded while «Importante» or «Necesario para facturar» ones are pending. */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(row(page)).toBeVisible();
}

async function money(context: BrowserContext): Promise<Intl.NumberFormat> {
  const res = await api<Currency>(context, A, 'GET', '/cash_register/currency');
  expect(res.status).toBe(200);
  const { currency, decimals } = res.data;
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency,
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

async function expectedNow(context: BrowserContext): Promise<number> {
  const res = await api<Current>(context, A, 'GET', '/cash_register/sessions/current');
  expect(res.status).toBe(200);
  expect(res.data.session?.expected_balance).not.toBeNull();
  return res.data.session?.expected_balance as number;
}

async function closedSessions(context: BrowserContext): Promise<SessionRow[]> {
  const res = await api<{ rows: SessionRow[] }>(context, A, 'GET', '/cash_register/sessions?status=closed&sort=closed_at&dir=desc&limit=8');
  expect(res.status).toBe(200);
  return res.data.rows;
}

test('CASH_REGISTER-F01: «Tu caja» pending on the factory values, done when the settings are saved, even as they came', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    await unfolded(page);
    await expect(row(page).locator('.setup-row-title')).toHaveText('Tu caja');
    await expect(row(page).locator('.setup-row-desc')).toHaveText(
      'Decide cómo se abre y se cierra la caja: el fondo inicial, el arqueo de cierre y la pantalla del TPV que queda bloqueada hasta abrirla.',
    );
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Recomendado');

    // Saved (by the API, as the assistant would): done without a reload.
    const saved = await api(context, A, 'POST', '/cash_register/settings', { require_blind_count: false });
    expect(saved.status).toBe(200);
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Hecho');
    await expect(row(page).locator(`[data-testid="setup-configure-${STEP}"]`)).toHaveCount(0);

    // Back on the factory values, «Configurar» leads to the drawer's settings, which save as they come.
    factoryValues();
    await page.reload();
    await unfolded(page);
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Recomendado');
    await row(page).locator(`[data-testid="setup-configure-${STEP}"]`).click();
    await expect(page).toHaveURL(`${A}/cash_register/settings`);
    const save = shown(page).locator('[data-testid=cash-register-settings-save]');
    await expect(save).not.toHaveAttribute('aria-disabled', 'true');
    await save.click();
    await expect(page.getByText('Ajustes guardados.')).toBeVisible();
    await expect(save).toHaveAttribute('aria-disabled', 'true');
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await unfolded(page);
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Hecho');
  } finally {
    await context.close();
    factoryValues();
  }
});

test('CASH_REGISTER-F12: «Caja (sesión actual)» by default with the server\'s expected cash, «Descuadres recientes» to add', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    const format = await money(context);
    const expected = panel(page, EXPECTED);
    await expect(expected.locator('[data-testid="widget-title"]')).toHaveText('Caja (sesión actual)');
    await expect(expected.locator('[data-testid="widget-value"]')).toHaveText(format.format((await expectedNow(context)) / 100));
    await expect(panel(page, RECENT)).toHaveCount(0);

    // 5.00 € out for a supplier: the panel follows without a reload.
    const before = await expectedNow(context);
    const out = await api(context, A, 'POST', '/cash_register/movements', { type: 'out', amount: 500, description: `E2E ${RUN}` });
    expect(out.status).toBe(201);
    expect(await expectedNow(context)).toBe(before - 500);
    await expect(expected.locator('[data-testid="widget-value"]')).toHaveText(format.format((before - 500) / 100));

    // «Personalizar panel» offers «Descuadres recientes», grouped under «Caja».
    await shown(page).locator('[data-testid="widgets-customize"]').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    await expect(picker).toContainText('Caja');
    await picker.locator(`[data-testid="widgets-add-${RECENT}"]`).click();
    await picker.locator('[data-testid="widgets-close"]').click();
    const recent = panel(page, RECENT);
    await expect(recent.locator('[data-testid="widget-title"]')).toHaveText('Descuadres recientes');
    const closed = await closedSessions(context);
    expect(closed.length).toBeGreaterThanOrEqual(2);
    const bars = recent.locator('[data-testid="widget-bar"]');
    // A session closed without a count has no difference: the server's list is the source of truth for the labels.
    await expect(bars.locator('.widget-bar-label')).toHaveText(closed.map((session) => session.number));
    const ours = closed.slice(0, 2);
    expect(ours.map((session) => session.difference)).toEqual([550, -40]);
    await expect(bars.nth(0).locator('.widget-bar-text')).toHaveText(format.format(5.5));
    await expect(bars.nth(1).locator('.widget-bar-text')).toHaveText(format.format(-0.4));
  } finally {
    await context.close();
  }
});

test('CASH_REGISTER-F12: an employee counts blind and never gets the expected cash panel, but reads the discrepancies', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 }, { board: [EXPECTED, RECENT], who: EMPLOYEE });
  try {
    await expect(panel(page, RECENT).locator('[data-testid="widget-title"]')).toHaveText('Descuadres recientes');
    await expect(panel(page, RECENT)).toHaveAttribute('aria-busy', 'false');
    await expect(panel(page, EXPECTED)).toHaveCount(0);
    await shown(page).locator('[data-testid="widgets-customize"]').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    await expect(picker).toBeVisible();
    await expect(picker.locator(`[data-testid="widgets-add-${EXPECTED}"]`)).toHaveCount(0);
  } finally {
    await context.close();
  }
});

for (const size of VIEWPORTS) {
  test(`CASH_REGISTER-F01 and CASH_REGISTER-F12 at ${size.label}: «Tu caja» pending, then the two panels with the server's figures`, async ({ browser }) => {
    const { context, page } = await spanish(browser, { width: size.width, height: size.height }, { board: [EXPECTED, RECENT] });
    try {
      const overflow = () => horizontalOverflow(page);
      await unfolded(page);
      await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Recomendado');
      await row(page).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-CASH_REGISTER-F01-${size.label}`) });

      const format = await money(context);
      for (const key of [EXPECTED, RECENT]) {
        await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
        await expect(panel(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
      }
      await expect(panel(page, EXPECTED).locator('[data-testid="widget-value"]')).toHaveText(format.format((await expectedNow(context)) / 100));
      await expect(panel(page, RECENT).locator('[data-testid="widget-bar"]')).toHaveCount((await closedSessions(context)).length);
      await panel(page, EXPECTED).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-CASH_REGISTER-F12-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
