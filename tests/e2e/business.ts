// The business a spec runs on, set up for it and put back after: the apps it needs, what a template brings, the plan
// in its photo and its registration as erplora.com sent them, and who is signed in on it; and «Upgrade plan» landing
// inside erplora.com's plans.
import { createHmac } from 'node:crypto';

import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { turnOffRecorded, turnOnRecording } from './apps-turned-on';
import { A, api, psql } from './helpers';
import { SAAS } from './saas-login';
import { STACK } from './stack';

/** «Upgrade plan» pressed in a browser with no session of erplora.com (BASE-F11): a tab of its own lands inside `a`'s
 *  plans by a pass, never on the sign-in form, and cannot reach back into the hub. */
export async function upgradeLandsInside(page: Page, link: Locator): Promise<void> {
  const context = page.context();
  // Only the SaaS's cookies (host `localhost`): the hub's session, on `a.localhost`, stays.
  await context.clearCookies({ domain: new URL(SAAS).hostname });
  const inside = `${SAAS}/dashboard/store/plans?business=${psql("SELECT id FROM base_hub WHERE slug = 'a'")}`;
  const passes: string[] = [];
  const seen = (request: { url(): string }) => {
    if (request.url().startsWith(`${SAAS}/hub-pass/?pass=`)) passes.push(request.url());
  };
  context.on('request', seen);
  const before = context.pages().length;
  const [tab] = await Promise.all([page.waitForEvent('popup'), link.click()]);
  await tab.waitForURL((url) => url.href.startsWith(inside));
  await expect(tab.getByTestId('store-plans')).toBeVisible();
  await expect(tab.getByTestId('login-form')).toHaveCount(0);
  expect(await tab.evaluate(() => window.opener), 'the new tab cannot reach back into the hub').toBeNull();
  expect(context.pages(), 'one tab, not two: the click did not also follow the link').toHaveLength(before + 1);
  expect(passes, 'through the door with one pass').toHaveLength(1);
  context.off('request', seen);
  await tab.close();
}

/** What a template brings, last first (tables before their zones, products before their categories), each with
 * the operation's route that lists it and the one that takes a row away: the server's own (`base.blueprint`). */
const TEMPLATE_DATA = [
  ['/table/tables', '/table/tables/delete'],
  ['/table/zones', '/table/zones/delete'],
  ['/service/services', '/service/services/archive'],
  ['/service/categories', '/service/categories/delete'],
  ['/inventory/products', '/inventory/products/delete'],
  ['/inventory/categories', '/inventory/categories/delete'],
] as const;

/**
 * Takes away every row a template brings from the business at `origin`, through the apps' operations (their apps
 * on), until the server says the business is empty.
 */
export async function emptyOfTemplateData(context: BrowserContext, origin: string): Promise<void> {
  for (let pass = 0; pass < 5; pass += 1) {
    for (const [list, remove] of TEMPLATE_DATA) {
      const rows = await api<{ rows: { id: string }[] }>(context, origin, 'GET', `${list}?limit=100&offset=0`);
      expect(rows.status, list).toBe(200);
      for (const row of rows.data.rows) {
        const res = await api(context, origin, 'POST', remove, { id: row.id });
        expect(res.status, `${remove} ${row.id}`).toBeLessThan(300);
      }
    }
    const catalogue = await api<{ empty: boolean }>(context, origin, 'GET', '/settings/data/blueprints');
    if (catalogue.data.empty) return;
  }
  throw new Error('the business could not be emptied of what a template brings');
}

/** How long the run's worker may take to make an app's tables in a business's own database: its tick, the
 *  migrations of the app and what it needs, and its settle. */
export const APP_SET_UP_MS = 60_000;

/**
 * Turns on `apps` in the business at `origin`, as the person of `context` who runs it, through Apps' own command
 * (`POST /api/apps/enable`, `base.app.enable`): a business is born with every app off.
 * One already on changes nothing. In a business whose own database lacks an app's tables (a demo, a new business)
 * the answer is 202 «creating» and the run's worker makes them: it waits until `base.app.list` says it is on.
 */
export async function turnOn(context: BrowserContext, origin: string, ...apps: string[]): Promise<void> {
  for (const app of apps) {
    const answer = await api<{ state: string }>(context, origin, 'POST', '/apps/enable', { app });
    const said = `turn on ${app}: ${answer.status} ${JSON.stringify(answer.data)}`;
    expect([200, 202], said).toContain(answer.status);
    if (answer.status === 202) {
      expect(answer.data.state, said).toBe('creating');
      await expect
        .poll(
          async () => {
            const listed = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
            return listed.data.apps.find((row) => row.id === app)?.state;
          },
          { message: `${app} set up by the worker`, timeout: APP_SET_UP_MS },
        )
        .toBe('on');
    }
  }
}

/**
 * Turns on, in their order, the apps of `needed` that are off in the business at `origin` (`turnOn`), and appends each
 * to `turnedOn` once it is on: the record a spec file's `afterAll` hands to `turnOffTurnedOn`, so it turns off what
 * this file turned on and nothing else. Called from a `beforeAll`, after whatever may fall first (the check of the
 * SaaS's assistant provider): a file that fell before turning anything on leaves the business as it found it (hub#480).
 */
export async function turnOnMissing(context: BrowserContext, origin: string, needed: readonly string[], turnedOn: string[]): Promise<void> {
  const listed = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
  expect(listed.status, `list the apps: ${JSON.stringify(listed.data)}`).toBe(200);
  const on = new Set(listed.data.apps.filter((app) => app.state === 'on').map((app) => app.id));
  await turnOnRecording(needed, on, (app) => turnOn(context, origin, app), turnedOn);
}

/** Turns off, last first, what `turnOnMissing` recorded in `turnedOn`, through Apps' own command
 *  (`POST /api/apps/disable`, `base.app.disable`): nothing when nothing was turned on (hub#480). */
export async function turnOffTurnedOn(context: BrowserContext, origin: string, turnedOn: string[]): Promise<void> {
  await turnOffRecorded(turnedOn, async (app) => {
    const off = await api(context, origin, 'POST', '/apps/disable', { app });
    expect(off.status, `turn off ${app}: ${JSON.stringify(off.data)}`).toBe(200);
  });
}

/**
 * The username of whoever is signed in on `context`. Not by email: a hub database kept from a stack whose SaaS was
 * created again holds an older account with the same email (a new SaaS, new users), and the email names both.
 */
export async function usernameOf(context: BrowserContext): Promise<string> {
  const me = await api<{ user: { id: string } | null }>(context, A, 'GET', '/me');
  expect(me.status, 'GET /api/me').toBe(200);
  const id = me.data.user?.id ?? '';
  expect(id, 'the person signed in').not.toBe('');
  // `/api/me` names the person of the business's database (base.HubUser), whose username is the session's.
  return psql(`SELECT username FROM base_hubuser WHERE id = '${id}'`);
}

/** Takes the plan out of `a`'s photo while a spec runs, keeping the photo in its scratch table `backup` (next to the
 * registry) for `restorePhotoFrom`: for a spec that signs in from more than one browser. With a plan in the photo
 * (erplora.com's Free covers one device, as its seed or a run of the WhatsApp specs can leave it), every entry from
 * another browser ends the sessions of the others on `a`, and the next request of the first gets a 401. */
export function dropPlanFromPhoto(backup: string): void {
  psql(`drop table if exists ${backup}; create table ${backup} as select id, state from base_hub where slug = 'a'`);
  psql("update base_hub set state = state - 'plan' where slug = 'a'");
}

/** `a`'s photo as `dropPlanFromPhoto` found it, and its scratch table `backup` dropped; nothing when it kept none. */
export function restorePhotoFrom(backup: string): void {
  if (psql(`select to_regclass('${backup}') is not null`) !== 't') return;
  psql(`update base_hub h set state = b.state from ${backup} b where b.id = h.id; drop table ${backup}`);
}

/** The secret `/internal` is signed with; the local default of both projects. */
const INTERNAL_SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';

/** `PUT <path>` on the Hub's `/internal` door, with `body` signed the way erplora.com signs it. */
export async function internalPut(path: string, body: string): Promise<Response> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', INTERNAL_SECRET).update(`${timestamp}.${body}`).digest('hex');
  return fetch(`http://127.0.0.1:${STACK.hubPort}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
}

/** A hub's registration as erplora.com sent it (`base_hub`): read before a run moves its business, put back after. */
export interface Registration {
  id: string;
  slug: string;
  name: string;
  country: string;
  timezone: string;
  language: string;
  vertical: string | null;
}

/** The registration of the hub `slug` as the run finds it. */
export function registrationOf(slug: string): Registration {
  const [id, name, country, timezone, language, vertical] = psql(
    `select id, name, country, timezone, language, coalesce(vertical, '') from base_hub where slug = '${slug}'`,
  ).split('|');
  return { id, slug, name, country, timezone, language, vertical: vertical || null };
}

/** erplora.com registers `registration`'s business in `country`, the way the SaaS does (`PUT /internal/hubs/{id}`,
 *  signed): its currency is then its country's. */
export async function registerBusinessIn(registration: Registration, country: string): Promise<void> {
  const response = await internalPut(`/internal/hubs/${registration.id}`, JSON.stringify({ ...registration, country }));
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(psql(`select country from base_hub where slug = '${registration.slug}'`)).toBe(country);
}
