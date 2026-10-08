// Regression test for ERPlora/hub#2567 — on a phone, someone who does not run the hub (an employee,
// a cashier) saw the blocking strip («You cannot issue invoices yet») cut its own sentence in half:
// «Your business details» broken over three lines on the left and, on the right, «This has to be set
// up by an admin…» running off the edge of the screen. The one thing the band tells that person —
// WHO can fix it — was the part they could not read.
//
// An admin never sees it: in that slot they get the «Set up» button, which fits. So this spec needs
// a REAL session that does not administer the hub, and the runtime is the one that decides it: it
// answers `hub.setup.status` with the item not actionable for that role (hub#435), nothing here
// fakes the payload. The bench hub has no business identity, so the strip is up for everybody.
//
// What it asserts, in the three viewports of the UI contract and on two lower phones (375 and 320 px): the note is inside the strip and the
// screen, whole; and on the phone it sits UNDER the step's name (like any list on a phone), with the
// name kept on one line.
//
// 🔴 The file name is load-bearing: it sorts AFTER `ShellVisual.spec.ts`. The person it creates
// cannot be deleted —the core's removal is deactivating, and `/employees` paints inactive rows too
// (see `UsersCrudTestids.spec.ts`)— so no visual contract may run after it.
import type { Locator } from '@playwright/test';
import { test, expect, request as pwRequest } from '../bench-boot';
import { loginByPin, withSession, VIEWPORTS } from './shell-visual-helpers';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

// Spanish on purpose: its copy is the longest the row has to hold, and it is the report's.
test.use({ locale: 'es-ES' });

/** Prefix of the person this spec creates. Also its clean-up tag. */
const PREFIX = 'QA Strip Note ';
/** A PIN this bench accepts: six digits, no progression (`isGuessablePin` refuses 123456). */
const PIN = '583926';

/**
 * The UI contract's three sizes, the low phone of the report (375 px wide) and the narrowest there is
 * (320 px): there the note no longer fits on its own line either, and has to wrap instead of running
 * off the edge.
 */
const SIZES = [...VIEWPORTS, { width: 375, height: 667 }, { width: 320, height: 568 }] as const;

interface HubUser {
  id: string;
  name: string;
  is_active?: boolean;
}

async function hubApi<T>(token: string, method: 'GET' | 'POST' | 'DELETE', path: string, data?: unknown): Promise<T> {
  const api = await pwRequest.newContext();
  const res = await api.fetch(`${RUNTIME}${path}`, { method, data, headers: { 'X-Hub-Session': token } });
  const text = await res.text();
  await api.dispose();
  expect(res.ok(), `${method} ${path}: ${res.status()} ${text}`).toBeTruthy();
  return (JSON.parse(text) as { data: T }).data;
}

/**
 * The bench database outlives a run, and a PIN only opens the session of an ACTIVE person: a run
 * that died before its clean-up would leave this PIN taken and the next one red for the wrong reason.
 */
async function deactivateLeftovers(adminToken: string): Promise<void> {
  const users = await hubApi<HubUser[]>(adminToken, 'GET', '/api/hub/users');
  for (const user of users.filter((u) => u.name.startsWith(PREFIX) && u.is_active !== false)) {
    await hubApi(adminToken, 'DELETE', `/api/hub/users/${user.id}`);
  }
}

async function box(target: Locator) {
  const b = await target.boundingBox();
  if (!b) throw new Error(`${target} has no box`);
  return b;
}

/** How many lines the text of `target` takes on screen. */
async function linesOf(target: Locator): Promise<number> {
  return target.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const tops = new Set([...range.getClientRects()].map((r) => Math.round(r.top)));
    return tops.size;
  });
}

test.describe('Blocking strip, seen by someone who does not run the hub (hub#2567)', () => {
  let employee: HubUser;
  let adminToken: string;

  test.beforeAll(async () => {
    adminToken = (await loginByPin()).token;
    await deactivateLeftovers(adminToken);
    employee = await hubApi<HubUser>(adminToken, 'POST', '/api/hub/users', {
      name: `${PREFIX}${Date.now()}`,
      email: '',
      role: 'employee',
      pin: PIN,
      local: true,
    });
  });

  test.afterAll(async () => {
    if (employee) await hubApi(adminToken, 'DELETE', `/api/hub/users/${employee.id}`);
  });

  for (const viewport of SIZES) {
    test(`${viewport.width}×${viewport.height}: «who can do it» is read whole, inside the strip`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const api = await pwRequest.newContext();
      const res = await api.post(`${RUNTIME}/api/auth/pin`, {
        data: { name: employee.name, pin: PIN, device_id: 'e2e-browser-device' },
      });
      expect(res.ok(), `employee PIN login: ${res.status()} ${await res.text()}`).toBeTruthy();
      const session = await res.json();
      await api.dispose();
      await withSession(page, { token: session.token, user: session.user });

      await page.goto('/profile');
      const strip = page.getByTestId('setup-strip');
      await expect(strip).toBeVisible();

      // The hub's own identity step: the one that blocks on every fresh hub, and the report's.
      const item = page.getByTestId('setup-strip-item-business_identity');
      const noteEl = page.getByTestId('setup-strip-note-business_identity');
      const nameEl = item.locator('.setup-strip-name');
      await expect(noteEl, 'a step that is not this session’s says who can take it').toBeVisible();
      await expect(page.locator('[data-testid^="setup-strip-action-"]')).toHaveCount(0);

      const stripBox = await box(strip);
      const note = await box(noteEl);
      const name = await box(nameEl);
      const right = Math.min(stripBox.x + stripBox.width, viewport.width);
      expect(note.x + note.width, 'the note ends inside the strip and the screen').toBeLessThanOrEqual(right + 0.5);
      expect(note.x, 'the note starts inside the strip').toBeGreaterThanOrEqual(stripBox.x - 0.5);
      expect(await linesOf(nameEl), 'the step’s name is not broken over several lines').toBe(1);

      if (viewport.width <= 540) {
        expect(note.y, 'on a phone the note goes under the step’s name').toBeGreaterThanOrEqual(
          name.y + name.height - 1,
        );
        expect(Math.round(note.x), 'and lines up with the name, not with the icon').toBe(Math.round(name.x));
      }
    });
  }

  // The other side of the fix: only the note's row wraps. An admin's «Set up» is short and stays
  // beside the step's name, even on the narrowest phone — it must not drop under the icon.
  test('320×568: an admin keeps «Set up» beside the step’s name', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await withSession(page, await loginByPin());

    await page.goto('/profile');
    const item = page.getByTestId('setup-strip-item-business_identity');
    const button = page.getByTestId('setup-strip-action-business_identity');
    await expect(button).toBeVisible();

    const name = await box(item.locator('.setup-strip-name'));
    const cta = await box(button);
    expect(cta.x, 'the button sits on the name’s row, to its right').toBeGreaterThanOrEqual(name.x + name.width);
    expect(cta.x + cta.width, 'and inside the screen').toBeLessThanOrEqual(320.5);
  });
});
