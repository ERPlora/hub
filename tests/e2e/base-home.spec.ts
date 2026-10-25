// The Home of the Hub (APP-BASE-1; the old hub's dashboard, docs/reference/old-hub/dashboard-*.png,
// dashboard-activity-*.png and apps-launcher-*.png) in the three viewports, as the owner of hub `a`: the
// heading, «My apps», «Finish setting up your business» (the platform's steps and the demo's example, which a
// development server shows), the board with the demo's panel — followed live: an item created elsewhere moves
// it without a reload —, «Customize panel», the bell, «Upgrade plan» in the side menu and «Activity» at
// `/#actividad`. Each flow leaves its capture `APP-BASE-1-<flow>-<width>` once nothing scrolls sideways.
// flow: BASE-F02 BASE-F01 BASE-F03 BASE-F05 BASE-F06 BASE-F07 BASE-F08 BASE-F09 BASE-F10 BASE-F11
import { expect, type Page, test } from '@playwright/test';

import { A, api, bellBadge, clearItems, hostPage, login, openBell, psql, shot, shown, uniqueName, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The side menu is pinned from 992 px; below it is a drawer behind the bar's menu button. */
const PINNED_MIN = 992;

/**
 * Counts the Ionic overlays sliding in or out: their animations run in shadow roots, out of
 * `document.getAnimations()` (as demo-flows.spec.ts). A present counts from `ionMount`, not from «will
 * present»: an inline overlay paints its content on mount and waits a frame before its animation starts.
 */
function countMovingOverlays(): void {
  const w = window as unknown as { __overlaysMoving: number };
  w.__overlaysMoving = 0;
  const done = () => (w.__overlaysMoving = Math.max(0, w.__overlaysMoving - 1));
  document.addEventListener('ionMount', () => (w.__overlaysMoving += 1));
  for (const kind of ['Modal', 'Popover']) {
    document.addEventListener(`ion${kind}DidPresent`, done);
    document.addEventListener(`ion${kind}WillDismiss`, () => (w.__overlaysMoving += 1));
    document.addEventListener(`ion${kind}DidDismiss`, done);
  }
}

/**
 * The capture of a flow, once the screen settled: no overlay sliding, no animation running in the page nor in a
 * shadow root (the checklist's `ion-progress-bar` slides its bar there) — a shimmer that never ends aside — and
 * nothing of the Home still loading (its skeletons, «Loading widgets…»).
 */
async function snap(page: Page, flow: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible, [data-testid="widgets-loading"]:visible')).toHaveCount(0);
  await page.waitForFunction(() => ((window as unknown as { __overlaysMoving?: number }).__overlaysMoving ?? 0) === 0);
  await untilStill(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${flow} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-1-${flow}-${width}`) });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F01 BASE-F02 BASE-F03 BASE-F05 BASE-F06 BASE-F07 BASE-F08 BASE-F09 BASE-F10 BASE-F11 — the Home at ${width}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    await context.addInitScript(countMovingOverlays);
    await clearItems(context, A);

    // BASE-F02 — the Home at `/`, headed by the business (or a greeting) and today's date.
    await page.goto(`${A}/`);
    await expect(shown(page).locator('h1')).toBeVisible();
    await expect(testid(page, 'home-date')).toBeVisible();
    // BASE-F05 — «My apps»: the demo among the apps this person can open.
    const myApps = testid(page, 'home-my-apps');
    await expect(myApps.locator('[data-testid="home-my-app"]').first()).toBeVisible();
    await expect(myApps.locator('[data-testid="home-my-app"][href="/demo/items"]')).toHaveCount(1);
    await snap(page, 'BASE-F02', width);
    await snap(page, 'BASE-F05', width);

    // BASE-F01 — the list from base.setup.status: the demo's example step, pending with no items. Recommended, it
    // folds behind «View all» while an important step of another app is pending (VeriFactu's, until its way to the
    // AEAT is ready): the whole list, always offered here («Your apps» is done), shows it.
    const card = testid(page, 'setup-card');
    await expect(card).toHaveAttribute('aria-busy', 'false');
    await card.locator('[data-testid="setup-toggle"]').click();
    const demoStep = card.locator('[data-testid="setup-row"][data-key="demo.first_item"]');
    await expect(demoStep.locator('[data-testid="setup-pill"]')).toHaveText('Recommended');
    await card.scrollIntoViewIfNeeded();
    await snap(page, 'BASE-F01', width);

    // BASE-F06 / BASE-F08 — the demo's panel «Open items», and a new open item moves it without a reload.
    const panel = testid(page, 'widget-board').locator('[data-testid="widget"][data-key="demo.open_items"]');
    const value = panel.locator('[data-testid="widget-value"]');
    await expect(value).toHaveText('0');
    await api(context, A, 'POST', '/demo/items', { name: uniqueName('Home') });
    await expect(value).toHaveText('1');
    // The step «Create your first item» is done now: the list re-ran on the server too.
    await expect(demoStep.locator('[data-testid="setup-pill"]')).toHaveText('Done');
    await panel.scrollIntoViewIfNeeded();
    await snap(page, 'BASE-F06', width);
    await snap(page, 'BASE-F08', width);

    // BASE-F03 — «Set up» of a row leads to its screen (the demo's step, while it was pending).
    await clearItems(context, A);
    const configure = card.locator('[data-testid="setup-configure-demo.first_item"]');
    await expect(configure).toBeVisible();
    await snap(page, 'BASE-F03', width);
    await configure.click();
    await expect(page).toHaveURL(`${A}/demo/items/new`);
    await page.goto(`${A}/`);

    // BASE-F07 — «Customize panel»: the demo's panel among the active ones; removing them all (Sales' two of today
    // are on by default too) empties the board.
    await testid(page, 'widgets-customize').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    await expect(picker.locator('[data-testid="widgets-active-item"][data-key="demo.open_items"]')).toBeVisible();
    await snap(page, 'BASE-F07', width);
    const active = picker.locator('[data-testid="widgets-active-item"]');
    const keys = await active.evaluateAll((items) => items.map((item) => item.getAttribute('data-key') ?? ''));
    for (const [index, key] of keys.entries()) {
      await picker.locator(`[data-testid="widgets-remove-${key}"]`).click();
      await expect(active).toHaveCount(keys.length - index - 1);
    }
    await picker.locator('[data-testid="widgets-close"]').click();
    await expect(picker).toBeHidden();
    await expect(testid(page, 'widgets-empty')).toBeVisible();
    await page.reload();
    await expect(testid(page, 'widgets-empty')).toBeVisible();
    await page.evaluate(() => localStorage.removeItem('dashboard-hub'));
    await page.reload();
    await expect(testid(page, 'widget-board').locator('[data-testid="widget"][data-key="demo.open_items"]')).toBeVisible();

    // BASE-F10 — the bell (base.bell.counters): the demo's «Open demo items» counter once there is one open.
    await api(context, A, 'POST', '/demo/items', { name: uniqueName('Bell') });
    await expect(bellBadge(page)).toHaveText('1');
    await openBell(page);
    const rows = page.locator('ion-popover [data-testid="hub-bell-row"]');
    await expect(rows).toHaveCount(1);
    await snap(page, 'BASE-F10', width);
    await rows.first().click();
    await expect(page).toHaveURL(`${A}/demo/items`);
    await page.goto(`${A}/`);

    // BASE-F11 — «Upgrade plan» at the foot of the side menu, to this hub's plan on the SaaS.
    if (width < PINNED_MIN) await shown(page).locator('ion-menu-button').click();
    const upgrade = page.locator('ion-menu [data-testid="upgrade-plan"]');
    await expect(upgrade).toBeVisible();
    await expect(upgrade).toHaveAttribute('href', /\/store\/plans\?business=[0-9a-f-]{36}$/);
    await expect(upgrade).toHaveAttribute('target', '_blank');
    await snap(page, 'BASE-F11', width);
    // A fresh page, without the drawer (closing it while it still slides in is ignored by Ionic).
    if (width < PINNED_MIN) await page.reload();
    await expect(testid(page, 'home-my-apps')).toBeVisible();

    // BASE-F09 — «Activity» at `/#actividad`: the table of the last sales.
    await page.goto(`${A}/#actividad`);
    await expect(shown(page).locator('[data-testid="tab-activity"]')).toHaveClass(/segment-button-checked/);
    await expect(shown(page).locator('[data-testid="home-activity-search"]')).toBeVisible();
    // «Summary» takes the hash away again (Back leaves the Home instead of walking its tabs).
    await shown(page).locator('[data-testid="tab-summary"]').click();
    await expect(page).toHaveURL(`${A}/`);
    await expect(testid(page, 'home-my-apps')).toBeVisible();
    await page.goto(`${A}/#actividad`);
    await expect(shown(page).locator('[data-testid="home-activity-search"]')).toBeVisible();
    await snap(page, 'BASE-F09', width);

    await clearItems(context, A);
    await context.close();
  });
}

// FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH: the board learnt its panels from its first live stream and
// reopened it for their data on every load of the Home (`net::ERR_ABORTED`, and every query run twice). The shell
// now carries the person's panels (`widget-list`): one stream carries the board and its panels' data.
for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  test(`BASE-F06 BASE-F08 — the Home opens one live stream, with its panels' data in it, at ${label}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    const isLive = (url: string) => new URL(url).pathname === '/api/live';
    const opened: string[] = [];
    const cut: string[] = [];
    page.on('request', (request) => {
      if (isLive(request.url())) opened.push(request.url());
    });
    page.on('requestfailed', (request) => {
      if (isLive(request.url())) cut.push(request.failure()?.errorText ?? 'failed');
    });
    await page.reload();
    // The panel's figure only comes through a stream that carries the panel: by then any reopening has happened.
    const panel = testid(page, 'widget-board').locator('[data-testid="widget"][data-key="demo.open_items"]');
    await expect(panel.locator('[data-testid="widget-value"]')).toHaveText(/\d/);
    expect(cut).toEqual([]);
    expect(opened).toHaveLength(1);
    await context.close();
  });
}

// BASE-F06 — a panel's row without its value (FIX-HUB-BASE-HOME-PANEL-NULL-SHOWS-ZERO): with «Exigir recuento al cierre»
// off in Cash register, a session closed without a count has no difference, and «Descuadres recientes» painted it as
// «0,00 €», a discrepancy that never was. The owner of `a`, in Spanish, adds the panel from «Personalizar panel»: the
// uncounted session says «—» with no bar, the one counted to the cent «0,00 €» on its track. Cash register's settings
// row is parked for the block and put back after it; the sessions it opens are deleted, with their movements and counts.
test.describe('BASE-F06 — a panel row without its value', () => {
  test.describe.configure({ mode: 'serial' });

  const KEY = 'FIX-HUB-BASE-HOME-PANEL-NULL-SHOWS-ZERO';
  const RECENT = 'cash_register.recent_sessions';
  const PARKED = 'e2e_fix_base_home_null_parked';
  const NOTE = `E2E ${KEY} ${Date.now()}`;
  /** The sessions this block opened: the only ones its cleanup deletes. */
  const mine: string[] = [];
  const numbers = { uncounted: '', counted: '' };
  let zero = '';

  interface Session {
    id: string;
    number: string;
    expected_balance: number | null;
    difference: number | null;
  }

  test.beforeAll(async ({ browser }) => {
    psql([`drop table if exists ${PARKED}`, `create table ${PARKED} as select * from cash_register_settings`].join('; '));
    const context = await browser.newContext({ baseURL: A });
    try {
      const page = await context.newPage();
      await login(page, A, '/cash_register/sessions');
      const settings = await api(context, A, 'POST', '/cash_register/settings', {
        enable_cash_register: true,
        require_closing_balance: false,
        require_blind_count: false,
      });
      expect(settings.status, '«Exigir recuento al cierre» off').toBe(200);
      // One drawer open per business: a shift an earlier run left open is closed first, as Cash register's specs do.
      const left = (await api<{ session: Session | null }>(context, A, 'GET', '/cash_register/sessions/current')).data.session;
      if (left) {
        const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
          session_id: left.id,
          closing_balance: Math.max(left.expected_balance ?? 0, 0),
          closing_notes: 'e2e: left open by an earlier run',
        });
        expect(closed.status).toBe(200);
      }
      for (const kind of ['uncounted', 'counted'] as const) {
        const opened = await api<Session>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 10000, opening_notes: NOTE });
        expect(opened.status).toBe(201);
        mine.push(opened.data.id);
        numbers[kind] = opened.data.number;
        const count = kind === 'counted' ? { closing_balance: opened.data.expected_balance } : {};
        const closed = await api<Session>(context, A, 'POST', '/cash_register/sessions/close', { session_id: opened.data.id, ...count });
        expect(closed.status, `${kind} session closed`).toBe(200);
        expect(closed.data.difference, `${kind}: its difference as the server keeps it`).toBe(kind === 'counted' ? 0 : null);
      }
      const currency = await api<{ currency: string; decimals: number }>(context, A, 'GET', '/cash_register/currency');
      expect(currency.status).toBe(200);
      const { currency: code, decimals } = currency.data;
      zero = new Intl.NumberFormat('es-ES', {
        style: 'currency',
        currency: code,
        currencyDisplay: 'narrowSymbol',
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(0);
    } finally {
      await context.close();
    }
  });

  test.afterAll(() => {
    const ids = mine.map((id) => `'${id}'`).join(',');
    if (ids) {
      psql(`delete from cash_register_count where session_id in (${ids})`);
      psql(`delete from cash_register_movement where session_id in (${ids})`);
      psql(`delete from cash_register_session where id in (${ids})`);
    }
    psql(['delete from cash_register_settings', `insert into cash_register_settings select * from ${PARKED}`, `drop table ${PARKED}`].join('; '));
  });

  for (const [label, viewport] of Object.entries(VIEWPORTS)) {
    test(`BASE-F06 — «Descuadres recientes» says «—» for a session closed without a count, never «0,00 €», at ${label}`, async ({ browser }) => {
      const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
      try {
        const page = await context.newPage();
        await login(page, A, '/');
        await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
        await page.goto(`${A}/`);
        await expect(page.locator('html')).toHaveAttribute('lang', /^es/);

        await testid(page, 'widgets-customize').click();
        const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
        await picker.locator(`[data-testid="widgets-add-${RECENT}"]`).click();
        await picker.locator('[data-testid="widgets-close"]').click();
        await expect(picker).toHaveCount(0);

        const panel = testid(page, 'widget-board').locator(`[data-testid="widget"][data-key="${RECENT}"]`);
        await expect(panel.locator('[data-testid="widget-title"]')).toHaveText('Descuadres recientes');
        await expect(panel).toHaveAttribute('aria-busy', 'false');
        const bar = (number: string) =>
          panel.locator('[data-testid="widget-bar"]').filter({ has: page.locator('.widget-bar-label').getByText(number, { exact: true }) });
        await expect(bar(numbers.uncounted).locator('.widget-bar-text')).toHaveText('—');
        await expect(bar(numbers.uncounted).locator('.widget-bar-track')).toHaveCount(0);
        await expect(bar(numbers.counted).locator('.widget-bar-text')).toHaveText(zero);
        await expect(bar(numbers.counted).locator('.widget-bar-track')).toHaveCount(1);
        await expect(panel).not.toContainText('null');

        await panel.evaluate((element) => element.scrollIntoView({ block: 'center' }));
        await untilStill(page);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: shot(`${KEY}-${label}`) });
      } finally {
        await context.close();
      }
    });
  }
});
