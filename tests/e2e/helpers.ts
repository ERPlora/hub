// Shared steps of the browser PoC (plan §8): the real login per host (Hub → SaaS → /auth/callback),
// the demo's API for setup, the list's readiness, the measurements file and the control of the dev
// server (runserver + Vite).
import { execSync, spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { readMailCode } from './mail';
import { isConnectionRefused, withRetry } from './retry';
import { STACK } from './stack';

export const A = STACK.hub('a');
export const B = STACK.hub('b');

const HERE = dirname(fileURLToPath(import.meta.url));
export const HUB_DIR = join(HERE, '..', '..');
export const REPO_DIR = join(HUB_DIR, '..');
export const ARTIFACTS = join(HERE, '.artifacts');
const METRICS = join(ARTIFACTS, 'metrics');
const RUNSERVER_LOG = `/tmp/erplora-hub-runserver-${STACK.hubPort}.log`;

export interface Item {
  id: string;
  name: string;
  status: 'open' | 'done';
  note: string;
}

/** Every `ion-icon` on screen: its name and whether its shadow root painted an `<svg>`. */
export async function iconStates(page: Page): Promise<{ name: string; painted: boolean }[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('ion-icon')]
      .filter((el) => el.getBoundingClientRect().width > 0)
      .map((el) => ({
        name: el.getAttribute('name') ?? '(icon prop)',
        painted: !!el.shadowRoot?.querySelector('svg'),
      })),
  );
}

/** Path of a screenshot under `.artifacts/` (created on demand). */
export function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

/** Writes the measurements of a check to `.artifacts/metrics/<key>.json` for the report. */
export function record(key: string, data: unknown): void {
  mkdirSync(METRICS, { recursive: true });
  writeFileSync(join(METRICS, `${key}.json`), `${JSON.stringify(data, null, 2)}\n`);
}

export const uniqueName = (prefix: string): string => `${prefix} ${Date.now().toString(36)}`;

/** The SaaS (`erplora.com` in production): the only login page a hub has. */
export const SAAS = STACK.saas;
/**
 * Whether `page` is on the SaaS (its login): what its console says there is the SaaS's, judged by the SaaS's own
 * suite. Its headless API answers 401 while nobody is signed in (allauth's protocol), and Chrome logs each one.
 */
export const onSaas = (page: Page): boolean => new URL(page.url()).origin === SAAS;
/** A SaaS account: what its sign-in page asks for. */
export interface Credentials {
  email: string;
  password: string;
}
/** The PoC's customer account in the SaaS (`saas-next … demo_seed`): owner of hubs `a` and `b`. */
export const OWNER: Credentials = { email: 'owner@example.com', password: 'owner' };
/** The PoC's employee in the SaaS (`demo_seed`): `hub_employee` of `a` and `b`, views Demo only. */
export const EMPLOYEE: Credentials = { email: 'employee@example.com', password: 'employee' };
/** Where the local SaaS writes its mails (Django's file backend); `E2E_MAIL_DIR` overrides it. */
export const MAIL_DIR = process.env.E2E_MAIL_DIR ?? join(REPO_DIR, 'saas-next', '.mail');
/** Slack between our clock and the mail file's modification time, in ms. */
const MAIL_CLOCK_SLACK = 50;

/**
 * The real login of a hub: `origin + next` → the SPA's gate sends to the SaaS (`/hub-login/?hub=…`)
 * → the SaaS asks for the account at `/launch` (or, signed in there already, skips it) → every
 * password sign-in then waits at `/verify-email` for the code the SaaS mails to the account
 * (`ACCOUNT_LOGIN_BY_CODE_REQUIRED`), read from the local SaaS's mail folder (`MAIL_DIR`) → it
 * follows its `next` (`/hub-login/…`), which POSTs a one-time code to `origin/auth/callback` → the Hub
 * opens its session and lands on `next`. The account is `credentials` (the owner unless told otherwise).
 *
 * runserver or the SaaS restarting (another session saved a `.py` file) refuses the connection for
 * a moment: the trip through the SaaS then starts again once, a second later (`withRetry`). From
 * `origin + next` again, because a POST that died leaves Chrome's error page, with no form to
 * submit; if the SaaS did sign in, the second trip skips its form, and if it did not, signing in
 * again mails a new code, the one read then. Any other failure fails at once, saying at which step.
 */
export async function login(
  page: Page,
  origin: string,
  next = '/demo/items',
  credentials: Credentials = OWNER,
): Promise<void> {
  const target = `${origin}${next}`;
  const inHub = () => page.locator('ion-menu').waitFor({ state: 'attached', timeout: 30_000 });
  await withRetry(
    async () => {
      await page.goto(target);
      const where = await Promise.race([
        page.waitForURL((url) => url.origin === SAAS, { timeout: 30_000 }).then(() => 'saas' as const, () => null),
        inHub().then(() => 'hub' as const, () => null),
      ]);
      if (where === null) throw new Error(`login on ${origin}: neither the SaaS nor the hub's shell showed up`);
      if (where === 'saas') {
        const form = page.getByTestId('login-form');
        const step = await Promise.race([
          form.waitFor({ state: 'visible', timeout: 30_000 }).then(() => 'form' as const, () => null),
          page.waitForURL((url) => url.origin === origin, { timeout: 30_000 }).then(() => 'back' as const, () => null),
        ]);
        if (step === null) throw new Error(`login on ${origin}: the SaaS showed neither its sign-in form nor the hub`);
        if (step === 'form') await signInWithCode(page, origin, target, credentials);
      }
      await page.waitForURL(target, { timeout: 30_000 });
    },
    {
      onRetry: (error) =>
        console.warn(`login on ${origin}: ${String(error).split('\n')[0]}; trying once more in 1 s`),
    },
  );
  await inHub();
}

/**
 * The SaaS's sign-in form (`/launch`) and then, when the SaaS asks for it, the code it mailed
 * (`/verify-email`); done once the browser is on its way back to the hub. A step that does not come
 * fails with the step's name and what the page said; a refused connection keeps its own error, so
 * that `login` tries again.
 */
async function signInWithCode(page: Page, origin: string, target: string, credentials: Credentials): Promise<void> {
  const form = page.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  // Taken before the submit: the mail is written while the SaaS answers it.
  const since = Date.now() - MAIL_CLOCK_SLACK;
  await form.getByTestId('login-submit').click();

  const codeForm = page.getByTestId('verify-email-form');
  const backHome = (url: URL) => url.origin === origin || url.pathname.startsWith('/hub-login');
  const step = await Promise.race([
    codeForm.waitFor({ state: 'visible', timeout: 30_000 }).then(() => 'code' as const, () => null),
    page.waitForURL(backHome, { timeout: 30_000 }).then(() => 'back' as const, () => null),
  ]);
  if (step === null) {
    throw new Error(`login on ${origin}: sign-in form sent, but neither /verify-email nor the hub came${await saidBy(page)}`);
  }
  if (step === 'back') return;

  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since }).catch((error: unknown) => {
    throw new Error(`login on ${origin}: mail not found: ${error instanceof Error ? error.message : String(error)}`);
  });
  // `CodeField` is one input today; six one-digit inputs would take a digit each.
  const inputs = codeForm.locator('input:not([type=hidden])');
  const count = await inputs.count();
  if (count >= code.length) {
    for (const [i, digit] of [...code].entries()) await inputs.nth(i).fill(digit);
  } else {
    await inputs.first().fill(code);
  }
  await codeForm.getByTestId('verify-email-submit').click();
  try {
    await page.waitForURL(target, { timeout: 30_000 });
  } catch (error) {
    if (isConnectionRefused(error)) throw error;
    const where = new URL(page.url()).pathname === '/verify-email' ? 'code rejected' : 'next not reached';
    throw new Error(`login on ${origin}: ${where} (code ${code} for ${credentials.email}, at ${page.url()})${await saidBy(page)}`);
  }
}

/** The alert the page shows, if any, as `: «…»` for an error message. */
async function saidBy(page: Page): Promise<string> {
  // Only decorates an error already being thrown: a page that is gone or navigating adds nothing.
  const alerts = await page
    .locator('[role=alert]:visible')
    .allInnerTexts()
    .catch(() => []);
  const text = alerts.map((alert) => alert.trim()).filter(Boolean).join(' / ');
  return text ? `: «${text}»` : '';
}

/** A new browser context logged in on `origin` (as the owner unless `credentials`), first page on `next`. */
export async function hostPage(
  browser: Browser,
  origin: string,
  options: { next?: string; viewport?: { width: number; height: number }; credentials?: Credentials } = {},
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: origin, viewport: options.viewport });
  const page = await context.newPage();
  await login(page, origin, options.next, options.credentials);
  return { context, page };
}

/** The demo's API with the context's session (setup and server-side evidence, never the check). */
export async function api<T>(
  context: BrowserContext,
  origin: string,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<{ status: number; data: T }> {
  // The context also holds the SaaS's cookies (host `localhost`), and Playwright hands them to
  // `a.localhost` too: the token is the hub host's own.
  const host = new URL(origin).hostname;
  const cookies = await context.cookies(origin);
  const csrf = cookies.find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const url = `${origin}/api${path}`;
  const headers = { 'X-CSRFToken': csrf, Accept: 'application/json' };
  const res =
    method === 'GET'
      ? await context.request.get(url, { headers })
      : await context.request.post(url, { headers, data: body ?? {} });
  const text = await res.text();
  return { status: res.status(), data: (text ? JSON.parse(text) : null) as T };
}

export async function createItem(context: BrowserContext, origin: string, name: string): Promise<Item> {
  const res = await api<Item>(context, origin, 'POST', '/demo/items', { name });
  expect(res.status, `create ${name}`).toBe(201);
  return res.data;
}

export async function itemDetail(
  context: BrowserContext,
  origin: string,
  id: string,
): Promise<Item & { lines: { text: string; client_line_id: string | null }[] }> {
  const res = await api<Item & { lines: { text: string; client_line_id: string | null }[] }>(
    context,
    origin,
    'GET',
    `/demo/items/detail?id=${id}`,
  );
  expect(res.status).toBe(200);
  return res.data;
}

/** Deletes every demo item (phase 1: `a` and `b` share them), through the API. */
export async function clearItems(context: BrowserContext, origin: string): Promise<number> {
  let deleted = 0;
  for (;;) {
    const page = await api<{ rows: { id: string }[] }>(context, origin, 'GET', '/demo/items?limit=100');
    if (page.data.rows.length === 0) return deleted;
    for (const row of page.data.rows) {
      const res = await api(context, origin, 'POST', '/demo/items/delete', { id: row.id });
      expect(res.status).toBeLessThan(300);
      deleted += 1;
    }
  }
}

/** The page shown by `IonRouterOutlet` (hidden pages stay in the DOM). */
export const shown = (page: Page): Locator => page.locator('.ion-page:not(.ion-page-hidden)').last();

/** Waits until the list painted its first result (empty state or rows). */
export async function listReady(page: Page): Promise<void> {
  await shown(page)
    .locator('[data-testid=demo-items-empty], [data-testid=demo-items-row]')
    .first()
    .waitFor({ state: 'visible' });
}

export async function rowNames(page: Page): Promise<string[]> {
  return shown(page).locator('[data-testid=demo-item-name]').allInnerTexts();
}

export const row = (page: Page, name: string): Locator =>
  shown(page).locator('[data-testid=demo-items-row]', { has: page.getByText(name, { exact: true }) });

/** The row (or card) of the item `id` on the list shown. */
export const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=demo-items-row][data-id="${id}"]`);

/** From the list: «New item» → `/demo/items/new`, types the name and arms a click-time probe on
 *  «Save» (not clicked yet). */
export async function fillNewItem(page: Page, name: string): Promise<Locator> {
  await shown(page).locator('[data-testid=demo-items-add]').click();
  await page.waitForURL(/\/demo\/items\/new$/);
  const form = shown(page).locator('[data-testid=demo-form]');
  await form.locator('[data-testid=demo-form-name] input').fill(name);
  const save = form.locator('[data-testid=demo-form-save]');
  await save.evaluate((el) => {
    el.addEventListener('click', () => ((window as unknown as Record<string, number>).__saveClickedAt = Date.now()), {
      capture: true,
      once: true,
    });
  });
  return save;
}

/** Creates an item through the «New item» page and waits until it is back on the list. */
export async function createViaPage(page: Page, name: string): Promise<void> {
  const save = await fillNewItem(page, name);
  await save.click();
  await page.waitForURL(/\/demo\/items$/, { timeout: 10_000 });
  await listReady(page);
}

/** In-page probe: the `Date.now()` at which a row named `name` shows up (read by `appearedAt`). */
export async function watchForRow(page: Page, name: string): Promise<void> {
  await page.evaluate((wanted) => {
    const w = window as unknown as { __rowSeen?: Record<string, number> };
    w.__rowSeen ??= {};
    const seen = w.__rowSeen;
    const check = (): boolean => {
      const found = [...document.querySelectorAll('[data-testid=demo-item-name]')].some(
        (el) => el.textContent?.trim() === wanted,
      );
      if (found && seen[wanted] === undefined) seen[wanted] = Date.now();
      return found;
    };
    if (check()) return;
    const observer = new MutationObserver(() => {
      if (check()) observer.disconnect();
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  }, name);
}

export async function appearedAt(page: Page, name: string): Promise<number | undefined> {
  return page.evaluate((wanted) => (window as unknown as { __rowSeen?: Record<string, number> }).__rowSeen?.[wanted], name);
}

/** Collects CSP violations (in-page listener), console errors and uncaught page errors. */
export async function collectProblems(
  page: Page,
): Promise<() => Promise<{ csp: unknown[]; console: string[]; warnings: string[]; page: string[] }>> {
  const consoleErrors: string[] = [];
  const warnings: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (msg) => {
    if (onSaas(page)) return;
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') warnings.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: unknown[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      w.__csp.push({ directive: e.violatedDirective, blocked: e.blockedURI, sample: e.sample, source: e.sourceFile });
    });
  });
  return async () => ({
    csp: await page.evaluate(() => (window as unknown as { __csp?: unknown[] }).__csp ?? []),
    console: consoleErrors,
    warnings,
    page: pageErrors,
  });
}

// ── Dev server control ──────────────────────────────────────────────────────────────────────────

/** Pids LISTENING on a TCP port (never the browser's client sockets). */
export function listeningPids(port: number): number[] {
  try {
    return execSync(`lsof -ti tcp:${port} -sTCP:LISTEN`, { encoding: 'utf8' })
      .split(/\s+/)
      .filter(Boolean)
      .map(Number);
  } catch {
    return [];
  }
}

export async function healthy(): Promise<boolean> {
  try {
    const res = await fetch(STACK.healthz, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * runserver's Vite (`pnpm run dev` in hub-next) answers. It starts after Django: `healthy()` alone
 * lets a page load HTML whose module scripts point at a Vite that is not listening yet, and that page
 * stays blank (nothing retries a failed module script).
 */
export async function viteReady(): Promise<boolean> {
  try {
    const res = await fetch(STACK.viteClient, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function waitFor(check: () => Promise<boolean> | boolean, timeoutMs: number, stepMs = 250): Promise<number> {
  const start = Date.now();
  for (;;) {
    if (await check()) return Date.now() - start;
    if (Date.now() - start > timeoutMs) throw new Error(`condition not met within ${timeoutMs} ms`);
    await new Promise((r) => setTimeout(r, stepMs));
  }
}

/**
 * Starts `manage.py runserver 127.0.0.1:<E2E_HUB_PORT>` detached (it outlives the test run), with this
 * run's environment (`VITE_DEV_PORT`, `SAAS_URL`, `DB_NAME`).
 */
export function startRunserver(): void {
  const child = spawn(
    '/bin/bash',
    ['-c', `cd '${HUB_DIR}' && nohup uv run python manage.py runserver 127.0.0.1:${STACK.hubPort} >> ${RUNSERVER_LOG} 2>&1 &`],
    { detached: true, stdio: 'ignore' },
  );
  child.unref();
}

/**
 * Rows of `pg_stat_activity` named `live-listener` (the process-level LISTEN connection) on this run's
 * database: another stack beside it (another checkout's runserver) has its own.
 */
export function listenerRows(): { pid: number; backend_start: string }[] {
  const out = execSync(
    `docker compose exec -T postgres psql -U hub -d ${STACK.database} -At -F '|' -c "select pid, backend_start from pg_stat_activity where application_name='live-listener' and datname = current_database() order by pid"`,
    { cwd: REPO_DIR, encoding: 'utf8' },
  );
  return out
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const [pid, start] = line.split('|');
      return { pid: Number(pid), backend_start: start };
    });
}

export function psql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${STACK.database} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** Decodes the `s=` of a `/api/live` URL (base64url JSON) into its subscriptions. */
export function decodeSubs(url: string): unknown[] {
  const s = new URL(url).searchParams.get('s') ?? '';
  const json = Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
  try {
    const value: unknown = JSON.parse(json);
    return Array.isArray(value) ? value : [value];
  } catch {
    return [json];
  }
}
