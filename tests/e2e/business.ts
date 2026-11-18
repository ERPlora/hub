// The business a spec runs on, emptied for it and put back after: what a template brings, the plan in its photo,
// and who is signed in on it.
import { type BrowserContext, expect } from '@playwright/test';

import { A, api, psql } from './helpers';

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
