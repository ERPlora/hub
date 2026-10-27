// flow: BASE-G52 BASE-G53 BASE-G54 BASE-G55 BASE-G56 BASE-G57 BASE-G58 BASE-G59 BASE-G60 BASE-G61 BASE-G62 BASE-G63
// BASE-G64 BASE-G65 BASE-G66 BASE-G72 BASE-G81 BASE-G125 BASE-G126 BASE-G151 (base/WORKBOOK.md, «Acceso»; APP-BASE-3)
// The way in of a business on the Free plan (one device at a time), two people and two browsers: the owner enters with
// their erplora.com account on a first device (A), names themselves (the side menu takes the name at once) and chooses
// a PIN in «My profile», names the device in Settings and sees it in use in System › «Plan and limits»; the employee enters with theirs on a till (B), which asks them to create their PIN and ends A's
// session (the plan covers one device). On B: sign out (the PIN pad), a wrong and a right PIN, a badge, «Switch user»
// over the screen in use, the idle lock, a session that ends, removing the unused device and the one in hand. Fresh
// accounts signed up on the SaaS's screens and a business created through its API, as the panel creates it
// (base-session-revoke.spec.ts).
// Never a PIN in the hubs `a`/`b` (it would change every other spec's way in); the business's dial is put back after.
import { createHmac } from 'node:crypto';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { api, collectProblems, type Credentials, login, MAIL_DIR, psql, SAAS, shot, shown, turnOn, untilStill } from './helpers';
import { readMailCode } from './mail';
import { cleanSales } from './sale-helpers';
import { STACK } from './stack';

const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const SAAS_STEP = 30_000;
const OWNER_PIN = '4826';
const EMPLOYEE_PIN = '9071';
/** A card's number, one per run: a badge opens one person's door only, and phase 1 keeps every hub's in one table. */
const BADGE = `77${String(Date.now()).slice(-8)}`;
/** Where the Sales app's till keeps the check it has on screen (`useCurrentCheck`). */
const CURRENT_CHECK_KEY = 'erplora.sale.pos.currentCheck';

interface Person {
  context: BrowserContext;
  page: Page;
  credentials: Credentials;
}

interface Business {
  id: string;
  slug: string;
}

async function signUp(browser: Browser, who: string): Promise<Person> {
  const credentials = { email: `e2e-access-${who}-${Date.now()}@example.com`, password: PASSWORD };
  const context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${SAAS}/launch?tab=signup`);
  const form = page.getByTestId('login-form');
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  const since = Date.now() - 50;
  await form.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/verify-email$/);
  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: SAAS_STEP });
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/launch$/);
  return { context, page, credentials };
}

async function saasPost(context: BrowserContext, path: string, data: unknown) {
  const host = new URL(SAAS).hostname;
  const csrf = (await context.cookies(SAAS)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken of the SaaS (sign in first)`);
  return context.request.post(`${SAAS}/api${path}`, { headers: { 'X-CSRFToken': csrf }, data });
}

async function businessOf(owner: Person): Promise<Business> {
  const created = await saasPost(owner.context, '/hubs/businesses', { name: `Access ${Date.now().toString(36)}`, country: 'ES' });
  expect(created.status(), await created.text()).toBe(201);
  const business = (await created.json()) as Business;
  await expect
    .poll(() => psql(`SELECT status FROM base_hub WHERE id = '${business.id}'`), { timeout: SAAS_STEP, message: 'registered here' })
    .toBe('ready');
  // The plan's photo (Free: one device at a time) comes with the business's ready state.
  await expect
    .poll(() => psql(`SELECT state->'plan'->>'max_devices' FROM base_hub WHERE id = '${business.id}'`), {
      timeout: SAAS_STEP,
      message: 'the plan in the photo',
    })
    .toBe('1');
  return business;
}

async function joins(owner: Person, person: Person, business: Business): Promise<void> {
  const invited = await saasPost(owner.context, '/hubs/members/invite', {
    hub_id: business.id,
    email: person.credentials.email,
    role: 'hub_employee',
    message: '',
  });
  expect(invited.status(), await invited.text()).toBe(200);
  const { id } = (await invited.json()) as { id: string };
  const accepted = await saasPost(person.context, '/hubs/invitations/accept', { id });
  expect(accepted.status(), await accepted.text()).toBe(200);
}

/**
 * `ready` at each size and a capture `APP-BASE-3-<key>-<size>` once nothing moves (a page pushed over another slides
 * in for half a second: mid-way, the screen it leaves shows at its edge); back at 1440 after.
 */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await untilStill(page);
    await page.screenshot({ path: shot(`APP-BASE-3-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The screen in hand scrolled back to its top (the capture shows its head, not where the last step left it). */
async function toTop(page: Page): Promise<void> {
  await shown(page)
    .locator('ion-content')
    .first()
    .evaluate((content) => (content as unknown as { scrollToTop: (duration: number) => Promise<void> }).scrollToTop(0));
}

async function press(page: Page, digits: string): Promise<void> {
  for (const digit of digits) await shown(page).getByTestId(`pinpad-key-${digit}`).click();
}

async function fill(field: Locator, value: string): Promise<void> {
  await field.locator('input').fill(value);
}

/** The user menu of the side menu (pinned at 1440), and the entry `id` in it. */
async function userMenu(page: Page, id: string): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
  await page.locator(`ion-popover [data-testid="user-menu-${id}"]`).click();
}

/** The labels of a segment that do not fit their button (its text ends in «…»). */
async function cutLabels(segment: Locator): Promise<string[]> {
  return segment
    .locator('ion-label')
    .evaluateAll((labels) => labels.filter((label) => label.scrollWidth > label.clientWidth).map((label) => label.textContent ?? ''));
}

/** The name the session gives the person in hand (`base.session.me`). */
async function whoIsIn(page: Page, origin: string): Promise<string | null> {
  const me = await api<{ user: { label: string } | null }>(page.context(), origin, 'GET', '/me');
  return me.data.user?.label ?? null;
}

const usernameOf = (email: string): string => psql(`SELECT username FROM auth_user WHERE email = '${email}'`);

test.describe.configure({ mode: 'serial' });

let owner: Person;
let employee: Person;
let business: Business;
let origin: string;
let till: Page;
let problems: Awaited<ReturnType<typeof collectProblems>>;
/** Every answer of 400 or more the till got: its method and path. */
const refused: string[] = [];

test.beforeAll(async ({ browser }) => {
  owner = await signUp(browser, 'owner');
  employee = await signUp(browser, 'employee');
  business = await businessOf(owner);
  await joins(owner, employee, business);
  origin = STACK.hub(business.slug);
});

test.afterAll(async () => {
  // The check of «Switch user» (its title is `e2e …`), with the Sales app's own cleanup.
  cleanSales();
  // Phase 1 keeps the business's dial in a table every hub of this database shares: back to the factory's.
  psql("UPDATE base_accesssettings SET pin_policy = 'per_shift', pin_inactivity_minutes = 5, pin_length = 4");
  await owner?.context.close();
  await employee?.context.close();
});

test('BASE-G52 BASE-G125 BASE-G126: the owner enters with the account, names themselves and chooses their PIN', async () => {
  const page = owner.page;
  await login(page, origin, '/profile', owner.credentials);
  // A business is born with every app off (PLAN-HUB round 2026-10-27): Sales, for the sale of BASE-G60 on the till.
  await turnOn(owner.context, origin, 'sale');
  const profile = shown(page);
  await expect(profile.getByTestId('profile-summary')).toBeVisible();
  // BASE-F11: entered with the account, the owner's bar has «erplora.com» (with a badge, BASE-G56, it has none).
  await expect(profile.getByTestId('topbar-manage')).toBeVisible();
  await fill(profile.getByTestId('profile-first-name'), 'Ana');
  await fill(profile.getByTestId('profile-last-name'), 'López');
  await profile.getByTestId('profile-save').click();
  await expect(profile.getByTestId('profile-saved')).toHaveText('Profile saved');
  // The side menu (pinned at 1440) takes the new name at once, without a reload.
  await expect(page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name')).toHaveText('Ana López');
  await expect(profile.getByTestId('profile-pin')).toContainText('You do not have a PIN yet.');
  await fill(profile.getByTestId('profile-pin-new'), OWNER_PIN);
  await fill(profile.getByTestId('profile-pin-repeat'), OWNER_PIN);
  await profile.getByTestId('profile-pin-save').click();
  await expect(profile.getByTestId('profile-pin-saved')).toHaveText('PIN updated');
  await expect(profile.getByTestId('profile-pin')).toContainText('The PIN you enter the till with.');
  expect(psql(`SELECT count(*) FROM base_credential WHERE username = '${usernameOf(owner.credentials.email)}' AND pin_hash <> ''`)).toBe('1');
  await atEverySize(page, 'BASE-G125', async () => {
    await expect(shown(page).getByTestId('profile-summary')).toContainText('Ana López');
    // «System (auto)», «Light» and «Dark» whole at every size, never «System (au…».
    expect(await cutLabels(shown(page).getByTestId('profile-mode'))).toEqual([]);
    await toTop(page);
  });
});

/** How the head of «My profile» lays its name out: in how many lines, whether it fits its box, and whether what does not
 *  fit ends in «…» (the whole name stays in its `title`). */
async function nameLayout(name: Locator) {
  return name.evaluate((heading) => {
    const range = document.createRange();
    range.selectNodeContents(heading);
    const tops = new Set([...range.getClientRects()].filter((rect) => rect.width > 0).map((rect) => Math.round(rect.top)));
    const style = getComputedStyle(heading);
    const box = heading.getBoundingClientRect();
    return {
      lines: tops.size,
      fits: heading.scrollWidth <= heading.clientWidth + 1,
      ellipsis: style.textOverflow === 'ellipsis' && style.overflowX === 'hidden',
      inside: box.right <= document.documentElement.clientWidth + 1,
      title: heading.getAttribute('title'),
    };
  });
}

test('BASE-G125: a name that is an email address shows whole or ends in «…» at every size, never cut mid-word', async () => {
  const page = owner.page;
  const address = 'ana.lopez.fernandez@restaurante-ejemplo.es';
  await page.goto(`${origin}/profile`);
  const profile = shown(page);
  await fill(profile.getByTestId('profile-first-name'), address);
  await fill(profile.getByTestId('profile-last-name'), '');
  await profile.getByTestId('profile-save').click();
  await expect(profile.getByTestId('profile-saved')).toHaveText('Profile saved');
  for (const size of [{ name: '375', width: 375, height: 667 }, ...SIZES]) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const name = shown(page).getByTestId('profile-name');
    await expect(name).toHaveText(address);
    await untilStill(page);
    const layout = await nameLayout(name);
    // One line, inside the screen: whole where it fits, else ending in «…»; never broken across lines mid-word.
    expect({ size: size.name, ...layout }).toMatchObject({ size: size.name, lines: 1, inside: true, title: address });
    expect(layout.fits || layout.ellipsis, `${size.name}: cut without «…»`).toBe(true);
    if (size.width >= 834) expect(layout.fits, `${size.name}: whole`).toBe(true);
    await toTop(page);
    await page.screenshot({ path: shot(`APP-BASE-3-BASE-G125-email-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // The name the rest of the run expects.
  await fill(shown(page).getByTestId('profile-first-name'), 'Ana');
  await fill(shown(page).getByTestId('profile-last-name'), 'López');
  await shown(page).getByTestId('profile-save').click();
  await expect(shown(page).getByTestId('profile-name')).toHaveText('Ana López');
});

test('BASE-G72 BASE-G151 BASE-G62 BASE-G63 BASE-G64: Settings › General shows this device, the PIN pad and the devices; one is named', async () => {
  const page = owner.page;
  await page.goto(`${origin}/settings`);
  const settings = shown(page);
  await expect(settings.getByTestId('device-mode-card')).toBeVisible();
  await expect(settings.getByTestId('pin-policy-consequence')).toContainText('Staff choose their name and type their PIN');
  const mine = settings.getByTestId('device-row').filter({ hasText: 'The one you are using' });
  await expect(mine).toHaveCount(1);
  await mine.getByTestId('device-rename').click();
  await fill(mine.getByTestId('device-name'), 'Office');
  await mine.getByTestId('device-name-save').click();
  await expect(settings.getByTestId('device-row').filter({ hasText: 'The one you are using' })).toContainText('Office');
  await atEverySize(page, 'BASE-G63', async () => {
    await expect(shown(page).getByTestId('devices-card')).toContainText('Office');
    await toTop(page);
  });
});

test('BASE-G81: «Plan and limits» counts the devices in use: the one in hand, of the one the Free plan covers', async () => {
  const page = owner.page;
  await page.goto(`${origin}/system#plan`);
  const devices = shown(page).getByTestId('system-plan-devices');
  await expect(devices.getByTestId('system-plan-devices-used')).toHaveText('1');
  await expect(devices).toContainText('Up to 1');
  await expect(devices).toContainText('With a session open now.');
  await atEverySize(page, 'BASE-G81', async () => {
    await expect(shown(page).getByTestId('system-plan-devices-used')).toHaveText('1');
    await toTop(page);
  });
});

test('BASE-G54 BASE-G57: the employee enters on a till, creates their PIN there, and the first device’s session ends', async () => {
  till = await employee.context.newPage();
  problems = await collectProblems(till);
  till.on('response', (response) => {
    if (response.status() >= 400) refused.push(`${response.status()} ${response.request().method()} ${new URL(response.url()).pathname}`);
  });
  await till.goto(`${origin}/`);
  await expect(till).toHaveURL(`${origin}/pin/setup?next=%2F`, { timeout: SAAS_STEP });
  await expect(shown(till).getByTestId('pin-setup-step')).toHaveText('Choose a 4-digit PIN');
  await atEverySize(till, 'BASE-G54', async () => {
    await expect(shown(till).getByTestId('pinpad')).toBeVisible();
  });
  await press(till, EMPLOYEE_PIN);
  await expect(shown(till).getByTestId('pin-setup-step')).toHaveText('Confirm your PIN');
  await press(till, EMPLOYEE_PIN);
  await expect(till).toHaveURL(`${origin}/`);
  await expect(shown(till).locator('[data-testid="topbar-apps"]').first()).toBeAttached();

  // A's session ended (one device at a time): its next page says why, with «Upgrade plan».
  await owner.page.goto(`${origin}/`);
  await expect(owner.page).toHaveURL(/\/login\?next=%2F&notice=device_limit$/);
  const notice = shown(owner.page).getByTestId('access-notice');
  await expect(notice).toContainText('Session opened on another device');
  await expect(notice.getByTestId('access-upgrade')).toHaveAttribute('href', `${SAAS}/dashboard/store/plans`);
  // An account without a name shows by the start of its address, however long, on one line like the others; and the
  // link closes the notice's text without a line taller than the rest.
  const faces = shown(owner.page).getByTestId('pin-face');
  const height = (face: Locator) => face.locator('.pin-door__face-name').evaluate((name) => name.getBoundingClientRect().height);
  expect(await height(faces.filter({ hasText: 'e2e-access-employee' }))).toBe(await height(faces.filter({ hasText: 'Ana López' })));
  const gaps = await notice.getByTestId('access-upgrade').evaluate((link) => {
    const range = document.createRange();
    range.selectNodeContents(link.parentElement ?? link);
    // One top per line: the boxes of a line start within a few pixels of each other.
    const tops = [...range.getClientRects()]
      .map((box) => box.top)
      .sort((a, b) => a - b)
      .filter((top, i, all) => i === 0 || top - all[i - 1] > 4);
    return tops.slice(1).map((top, i) => Math.round(top - tops[i]));
  });
  expect(Math.max(...gaps) - Math.min(...gaps), `the notice's lines are ${gaps.join(', ')} px apart`).toBeLessThanOrEqual(2);
  await atEverySize(owner.page, 'BASE-G57', async () => {
    await expect(shown(owner.page).getByTestId('access-notice')).toBeVisible();
  });
});

test('BASE-G61 BASE-G55: signing out on the till leaves its PIN pad; a wrong PIN says so, the right one enters', async () => {
  await till.goto(`${origin}/profile`);
  await fill(shown(till).getByTestId('profile-first-name'), 'Bea');
  await shown(till).getByTestId('profile-save').click();
  await expect(shown(till).getByTestId('profile-saved')).toBeVisible();
  await userMenu(till, 'logout');
  await expect(till).toHaveURL(/\/login(\?|$)/);
  const door = shown(till);
  await expect(door.getByTestId('access-tabs')).toBeVisible();
  await expect(door.getByTestId('pin-face')).toHaveText(['ALAna López', 'BBea']);
  await atEverySize(till, 'BASE-G55', async () => {
    await expect(shown(till).getByTestId('pin-face').first()).toBeVisible();
  });
  await door.getByTestId('pin-face').filter({ hasText: 'Bea' }).click();
  await press(till, '0000');
  await expect(door.getByTestId('pinpad-error')).toHaveText('Wrong PIN.');
  await press(till, EMPLOYEE_PIN);
  await expect(till).toHaveURL(`${origin}/`);
  expect(await whoIsIn(till, origin)).toBe('Bea');
});

test('BASE-G56: a badge that opens nothing says so; the owner’s badge enters as them, with no face chosen', async () => {
  await userMenu(till, 'logout');
  await expect(till).toHaveURL(/\/login(\?|$)/);
  await expect(shown(till).getByTestId('pin-face').first()).toBeVisible();
  await till.keyboard.type('9999999999', { delay: 5 });
  await till.keyboard.press('Enter');
  await expect(shown(till).getByTestId('pin-door-error')).toHaveText(
    'That badge opens nothing here. Enter with your PIN or ask an administrator.',
  );
  // The badge is given in Employees (another part of base): here, the owner's card is written as the Hub keeps it.
  const key = psql('SELECT badge_key FROM base_accesssettings');
  const digest = createHmac('sha256', Buffer.from(key, 'hex')).update(BADGE).digest('hex');
  psql(`UPDATE base_credential SET badge_digest = '${digest}', badge_set_at = now() WHERE username = '${usernameOf(owner.credentials.email)}'`);
  await till.keyboard.type(BADGE, { delay: 5 });
  await till.keyboard.press('Enter');
  await expect(till).toHaveURL(/\/$/);
  expect(await whoIsIn(till, origin)).toBe('Ana López');
  // BASE-F11 (gh:hub#2506): a badge on a till is the shift's, not the owner's erplora.com account: no «erplora.com».
  await expect(shown(till).getByTestId('assistant-button')).toBeVisible();
  await expect(shown(till).getByTestId('topbar-manage')).toHaveCount(0);
});

test('BASE-G60: «Switch user» over the sale in progress: whoever takes over enters with their PIN and the sale stays', async () => {
  // The sale in progress: a check of the Sales app with a line, the one this till has on screen (it keeps its id).
  const opened = await api<{ id: string }>(till.context(), origin, 'POST', '/sale/orders', {
    label: `e2e G60 ${Date.now().toString(36)}`,
    open_lines: [{ unit_price: 250, tax_category_key: 'restaurant.drink', name: 'Coffee' }],
  });
  expect(opened.status, JSON.stringify(opened.data)).toBe(201);
  await till.evaluate(([key, id]) => localStorage.setItem(key, id), [CURRENT_CHECK_KEY, opened.data.id]);
  await till.goto(`${origin}/sale/pos`);
  const coffee = shown(till).locator('.pos-line', { hasText: 'Coffee' });
  await expect(coffee).toHaveCount(1);
  await userMenu(till, 'switch-user');
  await expect(till).toHaveURL(`${origin}/switch-user`);
  await expect(shown(till)).toContainText('The sale stays open. From now on it is in the name of whoever enters here.');
  await atEverySize(till, 'BASE-G60', async () => {
    await expect(shown(till).getByTestId('pin-face').first()).toBeVisible();
  });
  await shown(till).getByTestId('pin-face').filter({ hasText: 'Bea' }).click();
  await press(till, EMPLOYEE_PIN);
  await expect(till).toHaveURL(`${origin}/sale/pos`);
  await expect(till.locator('ion-toast')).toContainText('Now serving Bea');
  expect(await whoIsIn(till, origin)).toBe('Bea');
  // The same check, with its line, on the till of whoever took over; still open.
  await expect(shown(till).locator('.pos-line', { hasText: 'Coffee' })).toHaveCount(1);
  expect(psql(`SELECT status FROM sale_order WHERE id = '${opened.data.id}'`)).toBe('open');
  // Back is not the screens whoever left had open: the reload replaced the page.
  await till.goto(`${origin}/settings`);
  await expect(shown(till).getByTestId('devices-admin-only')).toBeVisible();
});

test('BASE-G59: a till of a business that always asks goes back to the PIN pad after its idle minutes', async () => {
  await userMenu(till, 'switch-user');
  await shown(till).getByTestId('pin-face').filter({ hasText: 'Ana López' }).click();
  await press(till, OWNER_PIN);
  await expect(till).toHaveURL(`${origin}/settings`);
  const again = shown(till).getByTestId('pin-policy-again');
  await again.locator('ion-segment-button', { hasText: /^1 min$/ }).click();
  await expect(shown(till).getByTestId('pin-policy-card')).toContainText('A till nobody touches for 1 minutes');
  expect(psql('SELECT pin_policy || pin_inactivity_minutes FROM base_accesssettings')).toBe('always1');
  await till.clock.install();
  await till.reload();
  await expect(shown(till).getByTestId('pin-policy-card')).toBeVisible();
  await till.clock.fastForward('01:05');
  await expect(till).toHaveURL(/\/login(\?|$)/, { timeout: SAAS_STEP });
  await shown(till).getByTestId('pin-face').filter({ hasText: 'Ana López' }).click();
  await press(till, OWNER_PIN);
  await expect(till).toHaveURL(`${origin}/`);
  await till.goto(`${origin}/settings`);
  await shown(till).getByTestId('pin-policy-again').locator('ion-segment-button', { hasText: 'Until signing out' }).click();
  await expect.poll(() => psql('SELECT pin_policy FROM base_accesssettings')).toBe('per_shift');
});

test('BASE-G58: the till’s session ends while working: its next page is its PIN pad, which says so', async () => {
  // Its shift is over (or an administrator ended it): the session is past its time. The business's only live session
  // is the till's (A's ended with the employee's entry).
  const ended = psql(
    `WITH ended AS (UPDATE django_session SET expire_date = now() - interval '1 minute' WHERE expire_date > now() AND ` +
      `session_key IN (SELECT session_id FROM base_sessionowner WHERE host = '${business.slug}') RETURNING 1) ` +
      'SELECT count(*) FROM ended',
  );
  expect(ended, 'the till’s session, and only it').toBe('1');
  // A link to a tab (BASE-G52), opened as a page load (from /settings itself it would be a jump inside the shell): the
  // PIN pad keeps its fragment, and the entry goes back to that tab.
  await till.goto('about:blank');
  await till.goto(`${origin}/settings#data`);
  await expect(till).toHaveURL(/\/login\?next=%2Fsettings&notice=ended#data$/, { timeout: SAAS_STEP });
  await expect(shown(till).getByTestId('access-notice')).toContainText('Your session has ended');
  await expect(shown(till).getByTestId('access-tabs')).toBeVisible();
  await atEverySize(till, 'BASE-G58', async () => {
    await expect(shown(till).getByTestId('access-notice')).toBeVisible();
  });
  await shown(till).getByTestId('pin-face').filter({ hasText: 'Ana López' }).click();
  await press(till, OWNER_PIN);
  await expect(till).toHaveURL(`${origin}/settings#data`);
  await expect(shown(till).getByTestId('tab-data')).toHaveClass(/segment-button-checked/);
  expect(await whoIsIn(till, origin)).toBe('Ana López');
  // At most, the live stream heard the end first (a 401 the SDK reads as «the session ended», `host-closed.ts`).
  const during = refused.slice(2);
  expect(during.length <= 1 && during.every((answer) => answer === '401 GET /api/live'), refused.join('\n')).toBe(true);
});

test('BASE-G66 BASE-G65: the device nobody uses goes; removing the one in hand ends its session', async () => {
  psql(`UPDATE base_trusteddevice SET last_entry_at = now() - interval '40 days' WHERE name = 'Office'`);
  // A page load of Settings › General (BASE-G58 left the till on its Data tab).
  await till.goto(`${origin}/settings`);
  const devices = shown(till).getByTestId('devices-card');
  await expect(devices.getByTestId('devices-prune')).toHaveText(/Remove the (device|\d+ devices) unused for 30 days/);
  await devices.getByTestId('devices-prune').click();
  await devices.getByTestId('devices-prune-confirm').click();
  await expect(devices.getByTestId('device-row').filter({ hasText: 'Office' })).toHaveCount(0);

  const inHand = psql(
    'SELECT o.device_id FROM base_sessionowner o JOIN django_session s ON s.session_key = o.session_id ' +
      `WHERE o.host = '${business.slug}' AND s.expire_date > now()`,
  );
  expect(inHand, 'the till’s session names its device').toMatch(/^[0-9a-f-]{36}$/);
  const mine = devices.getByTestId('device-row').filter({ hasText: 'The one you are using' });
  await mine.getByTestId('device-remove').click();
  await expect(mine.getByTestId('device-remove-ask')).toContainText('It is the device you are using');
  // gh:hub#2577: two sign-outs, an ended session, a badge and three switches of user so far, and the till's only
  // refusals (and console errors: the browser logs every one) are the wrong PIN's, the unknown badge's and, at most,
  // the live stream's when the session ended.
  expect(refused.slice(0, 2)).toEqual(['401 POST /auth/pin', '401 POST /auth/badge']);
  const before = refused.length;
  expect((await problems()).console).toHaveLength(before);
  await mine.getByTestId('device-remove-confirm').click();
  // Its session ended and the hub no longer knows the browser: erplora.com's sign-in, whose session is alive, brings
  // the person of this browser's account back in, on a device the hub trusts anew.
  await expect(till).toHaveURL(`${origin}/`, { timeout: SAAS_STEP });
  expect(await whoIsIn(till, origin)).toBe('Bea');
  expect(psql(`SELECT count(*) FROM base_trusteddevice WHERE id = '${inHand}'`)).toBe('0');
  const seen = await problems();
  // Then, at most, the live stream hears that the session ended before the page leaves (the SDK's way to know,
  // `host-closed.ts`: a race with the navigation), and nothing else.
  const after = refused.slice(before);
  expect(after.length <= 1 && after.every((answer) => answer === '401 GET /api/live'), refused.join('\n')).toBe(true);
  expect(seen.console, seen.console.join('\n')).toHaveLength(refused.length);
  expect(seen.page, seen.page.join('\n')).toEqual([]);
  expect(seen.csp).toEqual([]);
});
