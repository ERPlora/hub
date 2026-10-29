// Shared steps of the customer e2e (customer-*.spec.ts): the app's API for setup and server-side
// evidence (never the check itself), readiness of its lists, and the cleanup every spec runs in its
// `afterAll`: what a run creates is named `e2e.…` and its ids are recorded, so it is deleted from the
// hub's database (phase 1: hubs `a` and `b` share it) even after an erasure renamed the card.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, psql, shown } from './helpers';

/** Every name a customer spec gives starts like this. */
export const PREFIX = 'e2e.';

/** `e2e.<label> <base36 time>`: unique per run. */
export const e2eName = (label: string): string => `${PREFIX}${label} ${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

/** A valid Spanish mobile number, without prefix (9 digits starting with 6), unique enough per run. */
export const spanishMobile = (): string => `6${String(Math.floor(Math.random() * 1e8)).padStart(8, '0')}`;

/** Ids of the cards a spec created (to clean up even what an erasure renamed). */
export const createdIds = new Set<string>();

export interface Card {
  id: string;
  name: string;
  phone: string;
  email: string;
  tax_id: string;
  group_ids: string[];
  tag_ids: string[];
}

export async function createCard(context: BrowserContext, body: Record<string, unknown>): Promise<Card> {
  const res = await api<Card>(context, A, 'POST', '/customer/customers', body);
  expect(res.status, `create ${String(body.name)}`).toBe(201);
  createdIds.add(res.data.id);
  return res.data;
}

export async function cardOf(context: BrowserContext, id: string): Promise<{ status: number; data: Card }> {
  return api<Card>(context, A, 'GET', `/customer/customers/detail?id=${id}`);
}

/** The id of the card a URL `/customer/customers/<id>` shows. */
export function idFromUrl(page: Page): string {
  const id = new URL(page.url()).pathname.split('/').pop() ?? '';
  createdIds.add(id);
  return id;
}

/** Waits until the customer list painted its first result (rows, cards or the empty state). */
export async function customersReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=customer-list-empty], [data-testid=customer-list-row]').first().waitFor({ state: 'visible' });
}

/** Types in the list's search box. */
export async function searchList(page: Page, prefix: string, text: string): Promise<void> {
  await shown(page).locator(`[data-testid=${prefix}-search] input`).fill(text);
}

/** The row (or card) of the list named `name`. */
export const rowNamed = (page: Page, prefix: string, name: string): Locator =>
  shown(page).locator(`[data-testid=${prefix}-row]`, { hasText: name });

/** The text an `ion-input` holds. */
export const inputOf = (scope: Page | Locator, testid: string): Locator => scope.locator(`[data-testid=${testid}] input`);

const quoted = (ids: Iterable<string>): string => [...ids].map((id) => `'${id.replace(/'/g, '')}'`).join(',');

/** Deletes what the specs created: the recorded cards, any `e2e.` card, group, tag and field. */
export function cleanUp(): void {
  const named = psql(`select string_agg(id::text, ',') from customer_customer where name like '${PREFIX}%'`);
  const ids = new Set([...createdIds, ...named.split(',').filter(Boolean)]);
  if (ids.size) {
    const list = quoted(ids);
    // The duplicates merged into them too (their `merged_into` points here).
    psql(`update customer_customer set merged_into_id = null where merged_into_id in (${list})`);
    for (const table of ['customer_activity', 'customer_consent', 'customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue', 'customer_healthrecord', 'customer_orderlink', 'customer_purchase']) {
      psql(`delete from ${table} where customer_id in (${list})`);
    }
    psql(`delete from customer_customer where id in (${list})`);
  }
  psql(`delete from customer_customer_groups where customergroup_id in (select id from customer_customergroup where name like '${PREFIX}%')`);
  psql(`delete from customer_customergroup where name like '${PREFIX}%'`);
  psql(`delete from customer_customer_tags where customertag_id in (select id from customer_customertag where name like '${PREFIX}%')`);
  psql(`delete from customer_customertag where name like '${PREFIX}%'`);
  psql(`delete from customer_customfieldvalue where field_id in (select id from customer_customfield where name like '${PREFIX}%')`);
  psql(`delete from customer_customfield where name like '${PREFIX}%'`);
  createdIds.clear();
}

/** The three sizes every flow of the app is seen at (brief APP-CUSTOMER): a phone, a tablet and a desk. */
export const FLOW_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

export { horizontalOverflow } from './helpers';
