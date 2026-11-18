// What erplora.com sent about a hub, as a spec changes it and puts it back: the plan in its photo, and its
// registration put on the Hub's `/internal` door, signed the way erplora.com signs it.
import { createHmac } from 'node:crypto';

import { expect } from '@playwright/test';

import { psql } from './psql';
import { STACK } from './stack';

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
