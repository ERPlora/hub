// The WhatsApp e2e's harness against the run's REAL erplora.com (whatsapp-helpers.ts, «The run's real erplora.com»):
// `seedErplora` has erplora.com push its photo of `a`, which brings erplora.com's plan (Free: one device), and
// `restorePhoto` puts back the photo `a` had before the spec's first seed, its version too, so that no spec seeding
// erplora.com leaves `a` on the Free plan to the specs run after it on the same database (a spec signed in on two
// devices loses one session to the device cap, BASE-G57: website-flows.spec.ts, WEBSITE-F11, 401;
// FIX-HUB-E2E-WHATSAPP-INBOX-CONNECT-LEAVES-FREE-PLAN). whatsapp-photo.test.ts makes every spec that seeds call it
// last in its `afterAll`.
import { expect, test } from '@playwright/test';

import { psql } from './helpers';
import { metaGraph, restorePhoto, seedErplora } from './whatsapp-helpers';

/** `a`'s photo as the Hub keeps it: its version and its state. */
const photo = (): unknown =>
  JSON.parse(psql("select json_build_object('version', state_version, 'state', state) from base_hub where slug = 'a'"));

test.afterAll(() => restorePhoto());

test('the photo of a goes back, plan and version, to the one it had before the spec’s first seed', async () => {
  const before = photo();
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
  // The seed changed it (erplora.com's plan and a newer version), or what follows would prove nothing.
  expect(photo()).not.toEqual(before);
  expect(psql("select state->'plan'->>'slug' from base_hub where slug = 'a'")).not.toBe('');

  // A second seed of the same spec (whatsapp-inbox-plan-cap seeds again) keeps the photo the first one found.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  restorePhoto();
  expect(photo()).toEqual(before);

  // Nothing seeded since: putting it back again changes nothing.
  restorePhoto();
  expect(photo()).toEqual(before);
});
