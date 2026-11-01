// The QA battery of the Hub's assistant with the REAL model and the REAL documentation index
// (docs/plans/2026-10-31-qa-asistente.md of erplora-next: block B, 21 to 34, and C35 to C37), one test per item.
// Skipped unless QA_REAL_PROVIDER=1: it spends real tokens (about 20 turns) and never runs in CI. Needs the keys in
// the environment (QA_QWEN_API_KEY, QA_OPENAI_API_KEY; never in the repo, the report or a screenshot) and the stack's
// SaaS checkout (E2E_SAAS_DIR) running with ASSISTANT_SERVICE_PROVIDER=openai (README «La QA del asistente con el modelo
// real»). Once per run it registers the Hub's apps in the SaaS (`register_apps`), sets the real providers through the
// SaaS's operations (assistant-battery.ts, `SEED_PY`), indexes the documentation (`index_docs`) and empties this
// month's messages of `a`. Each item asks in a new conversation, records what went over the wire
// (`/api/assistant/turn`), decides the card as a person would, checks the record through the Hub's API and writes
// `.artifacts/qa/<run>/assistant-battery-B.md` (the report) and `.artifacts/qa/<run>/<item>-<slug>.png`. The test fails when the
// automatic verdict does; the wording is for a person to read in the report.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { ITEMS, type Meta, observe, type Outcome, redact, renderReport, verdictOf } from '../assistant-battery';
import {
  answerOf,
  converse,
  emptyMonth,
  foot,
  noticesOf,
  openPanel,
  panel,
  saasSql,
  SECRETS,
  seedRealProviders,
  TURN_MS,
} from '../assistant-real';
import { A, api, ARTIFACTS, capture, login } from '../helpers';

test.skip(process.env.QA_REAL_PROVIDER !== '1', 'QA with the real model: QA_REAL_PROVIDER=1 (tests/e2e/README.md)');

/** The run the report belongs to: Playwright's, or `QA_BATTERY_RUN` to ask some items again into an earlier report. */
const RUN = (process.env.QA_BATTERY_RUN || process.env.PW_RUN_ID || 'run').replace(/[^A-Za-z0-9._-]/g, '-');
/** Each run keeps its own report and screenshots: a later run never overwrites an earlier one's evidence. */
const QA_DIR = join(ARTIFACTS, 'qa', RUN);
const STATE = join(QA_DIR, 'assistant-battery-B.json');
const REPORT = join(QA_DIR, 'assistant-battery-B.md');
/** The apps the battery's do-it items write in; Reservations stays as the business has it (B26 asks about it). */
const APPS = ['tax', 'customer', 'inventory', 'sale', 'cash_register', 'staff', 'printing'];

interface State {
  run: string;
  meta: Meta;
  prepared: boolean;
  outcomes: Record<string, Outcome>;
}

function readState(): State | null {
  if (!existsSync(STATE)) return null;
  const state = JSON.parse(readFileSync(STATE, 'utf8')) as State;
  return state.run === RUN ? state : null;
}

function writeState(state: State): void {
  writeFileSync(STATE, redact(JSON.stringify(state, null, 2), SECRETS));
  const ordered = ITEMS.map((item) => state.outcomes[item.id]).filter((outcome): outcome is Outcome => Boolean(outcome));
  writeFileSync(REPORT, redact(renderReport(ordered, state.meta), SECRETS));
}

/** Once per run: the apps' docs in the SaaS, the real providers, the index, and `a`'s month of messages emptied. */
function prepare(): State {
  mkdirSync(QA_DIR, { recursive: true });
  const kept = readState();
  if (kept) return kept;
  const seeded = seedRealProviders();
  emptyMonth();
  const state: State = { run: RUN, meta: { run: RUN, ...seeded }, prepared: false, outcomes: {} };
  writeState(state);
  return state;
}

async function footText(page: Page): Promise<string> {
  return (await foot(page).isVisible()) ? (await foot(page).innerText()).trim() : '';
}

/** The month's messages of the business and its plan's allowance, as the Hub's panel reads them. */
async function messages(context: BrowserContext): Promise<{ used: number; limit: number }> {
  const usage = await api<{ used: number; limit: number }>(context, A, 'GET', '/assistant/usage');
  expect(usage.status, JSON.stringify(usage.data)).toBe(200);
  return usage.data;
}

/** Sets this month's messages of `a` on erplora.com (the row its first question made), as base-assistant.spec.ts does. */
function setMonth(used: number): void {
  saasSql(
    `update assistant_assistantusage set messages = ${Math.trunc(used)} where hub_id = (select id from hubs_hub where slug = 'a') ` +
      "and month = date_trunc('month', now() at time zone 'UTC')::date",
  );
}

async function rowsNamed(context: BrowserContext, path: string, search: string, named: (row: Record<string, unknown>) => boolean): Promise<number> {
  const listed = await api<{ rows: Record<string, unknown>[] }>(context, A, 'GET', `${path}?search=${encodeURIComponent(search)}&limit=50&offset=0`);
  expect(listed.status, `${path}: ${JSON.stringify(listed.data)}`).toBe(200);
  return listed.data.rows.filter(named).length;
}

const customers = (context: BrowserContext, name: string) => rowsNamed(context, '/customer/customers', name, (row) => row.name === name);
const products = (context: BrowserContext, name: string) => rowsNamed(context, '/inventory/products', name, (row) => row.name === name);
const members = (context: BrowserContext, name: string) =>
  rowsNamed(context, '/staff/members', name, (row) => String(row.full_name ?? '').toLowerCase().includes(name.toLowerCase()));

/** 1 when the app `id` is on in the business, 0 otherwise. */
async function appOn(context: BrowserContext, id: string): Promise<number> {
  const apps = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
  expect(apps.status, JSON.stringify(apps.data)).toBe(200);
  return apps.data.apps.find((app) => app.id === id)?.state === 'on' ? 1 : 0;
}

/** The roles of the team members named `name`, as the Team screen lists them. */
async function rolesOf(context: BrowserContext, name: string): Promise<string> {
  const listed = await api<{ rows: { full_name?: string; role_name?: string | null }[] }>(
    context,
    A,
    'GET',
    `/staff/members?search=${encodeURIComponent(name)}&limit=50&offset=0`,
  );
  const roles = listed.data.rows.filter((row) => (row.full_name ?? '').toLowerCase().includes(name.toLowerCase()));
  return roles.map((row) => row.role_name || '(no role)').join(', ') || 'none';
}

/** How each item checks its record through the Hub's API: counted before the question, judged after it (`detail`: what
 *  else the report says of it). */
const RECORDS: Record<
  string,
  {
    count: (context: BrowserContext) => Promise<number>;
    ok: (before: number, after: number) => boolean;
    says: string;
    detail?: (context: BrowserContext) => Promise<string>;
  }
> = {
  B28b: { count: (c) => appOn(c, 'reservation'), ok: (b, a) => b === 1 && a === 0, says: 'Reservations on (1) or off (0)' },
  B28c: { count: (c) => appOn(c, 'reservation'), ok: (b, a) => b === 0 && a === 1, says: 'Reservations on (1) or off (0)' },
  B29: { count: (c) => customers(c, 'Ana QA'), ok: (b, a) => a === b + 1, says: 'customers named «Ana QA»' },
  B30: {
    count: (c) => members(c, 'Luis QA'),
    ok: (b, a) => a === b + 1,
    says: 'team members named «Luis QA»',
    detail: async (c) => `roles: ${await rolesOf(c, 'Luis QA')}`,
  },
  B31: { count: (c) => products(c, 'Café QA'), ok: (b, a) => a === b + 1, says: 'products named «Café QA»' },
  B33: { count: (c) => customers(c, 'Ana QA'), ok: (b, a) => a === b - 1, says: 'customers named «Ana QA»' },
  C36: { count: (c) => customers(c, 'Cancelado QA'), ok: (b, a) => a === b, says: 'customers named «Cancelado QA»' },
};

let state: State;

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  state = prepare();
  if (state.prepared) return;
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const listed = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
  expect(listed.status, JSON.stringify(listed.data)).toBe(200);
  const on = new Set(listed.data.apps.filter((app) => app.state === 'on').map((app) => app.id));
  for (const app of APPS.filter((id) => !on.has(id))) {
    const answer = await api(context, A, 'POST', '/apps/enable', { app });
    expect(answer.status, `turn on ${app}: ${JSON.stringify(answer.data)}`).toBe(200);
  }
  const reservation = listed.data.apps.find((app) => app.id === 'reservation')?.state ?? 'missing';
  state.meta = { ...state.meta, run: `${RUN} (Reservations ${reservation} at the start)` };
  state.prepared = true;
  writeState(state);
  await context.close();
});

for (const item of ITEMS) {
  test(`${item.id} ${item.slug} — ${item.question}`, async ({ page, context }) => {
    test.setTimeout(TURN_MS + 120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page, A, '/');
    await context.addCookies([{ name: 'django_language', value: item.language, domain: new URL(A).hostname, path: '/' }]);
    const record = RECORDS[item.id];
    let precondition = '';
    if (item.id === 'B33' && (await customers(context, 'Ana QA')) === 0) {
      const made = await api(context, A, 'POST', '/customer/customers', { name: 'Ana QA', phone: '600000000' });
      expect(made.status, JSON.stringify(made.data)).toBe(201);
      precondition = ' (B29 left none: «Ana QA» created through the API first)';
    }
    const countBefore = record ? await record.count(context) : 0;
    await openPanel(page);
    const usedBefore = item.check === 'quota' ? (await messages(context)).used : 0;

    const { bodies, decided } = await converse(page, item.question, item.decide, item.id);

    const observed = observe(bodies);
    const outcome: Outcome = {
      item,
      answer: await answerOf(page),
      receipts: (await panel(page).locator('[data-testid="assistant-receipt"]').allInnerTexts()).map((text) => text.trim()),
      notices: await noticesOf(page),
      observed,
      decided,
      screenshot: join(QA_DIR, `${item.id}-${item.slug}.png`),
    };
    if (record) {
      const after = await record.count(context);
      const detail = record.detail ? `; ${await record.detail(context)}` : '';
      outcome.record = { checked: `${record.says}: ${countBefore} → ${after}${detail}${precondition}`, ok: record.ok(countBefore, after) };
    }
    if (item.check === 'activate') {
      const apps = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
      const customer = apps.data.apps.find((app) => app.id === 'customer')?.state ?? 'missing';
      outcome.record = { checked: `Customers is ${customer}`, ok: customer === 'on' };
    }
    if (item.check === 'quota') {
      await expect.poll(async () => (await messages(context)).used, { timeout: 15_000 }).toBeGreaterThan(usedBefore);
      const { used, limit } = await messages(context);
      // The foot only shows from 80 % of the month (BASE-G122): the month set to 5 left, the same question once more,
      // and the month put back to what was really spent.
      setMonth(limit - 5);
      let asked = false;
      try {
        await openPanel(page);
        await expect(foot(page)).toBeVisible().catch(() => undefined);
        const footBefore = await footText(page);
        asked = true;
        const again = await converse(page, item.question, item.decide, item.id);
        outcome.observed = observe([...bodies, ...again.bodies]);
        await expect.poll(() => footText(page), { timeout: 15_000 }).not.toBe(footBefore).catch(() => undefined);
        outcome.usage = { before: usedBefore, after: used, footBefore, footAfter: await footText(page) };
      } finally {
        setMonth(used + (asked ? 1 : 0));
      }
    }
    try {
      await capture(page, `qa/${RUN}/${item.id}-${item.slug}`);
    } catch (error) {
      outcome.screenshot = `(not captured: ${(error as Error).message.slice(0, 200)})`;
    }
    const kept = readState() ?? state;
    kept.outcomes[item.id] = outcome;
    writeState(kept);

    // Reservations ends as the business had it, whatever B28b and B28c did (B26 asks about it in the next run).
    if (item.id === 'B28c' && (await appOn(context, 'reservation')) === 0) {
      const back = await api(context, A, 'POST', '/apps/enable', { app: 'reservation' });
      expect(back.status, `turn Reservations back on: ${JSON.stringify(back.data)}`).toBe(200);
    }
    const verdict = verdictOf(outcome);
    expect(verdict.verdict, `${item.id}: ${verdict.reasons.join('; ')}`).toBe('PASS');
  });
}
