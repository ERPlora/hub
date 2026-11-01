// The WhatsApp e2e's harness against the run's REAL erplora.com (whatsapp-helpers.ts, «The run's real erplora.com»):
// `seedErplora` has erplora.com push its photo of `a`, which brings erplora.com's plan (Free: one device), and
// `restorePhoto` puts back the photo `a` had before the spec's first seed, its version too, so that no spec seeding
// erplora.com leaves `a` on the Free plan to the specs run after it on the same database (a spec signed in on two
// devices loses one session to the device cap, BASE-G57: website-flows.spec.ts, WEBSITE-F11, 401;
// FIX-HUB-E2E-WHATSAPP-INBOX-CONNECT-LEAVES-FREE-PLAN). What the photo applies on its way in goes back with it: the
// row of `a`'s WhatsApp channel, whose version the next photo must exceed (`whatsapp_inbox.channel.sync` ignores an
// equal or older one), so a row left by a seed would make a later run's erplora.com, on a database made afresh, push
// photos the channel never takes. whatsapp-photo.test.ts makes every spec that seeds call it last in its `afterAll`.
// A spec that never seeds but drives the inbox keeps the photo with `keepPhoto()` first (hub#528: erplora.com pushes
// it when it answers the Hub), and puts it back the same way.
import { expect, test } from '@playwright/test';

import { psql } from './helpers';
import { cleanUp, keepPhoto, metaGraph, pushChannel, restorePhoto, seedErplora } from './whatsapp-helpers';

/** `a`'s photo as the Hub keeps it: its version and its state. */
const photo = (): unknown =>
  JSON.parse(psql("select json_build_object('version', state_version, 'state', state) from base_hub where slug = 'a'"));

/** The row of `a`'s WhatsApp channel, whole, or none. */
const channel = (): unknown =>
  JSON.parse(psql("select coalesce(json_agg(c order by c.id), '[]') from whatsapp_inbox_channel c where c.host = 'a'"));

test.describe.configure({ mode: 'serial' });

test.afterAll(() => {
  cleanUp();
  restorePhoto();
});

test('the photo of a and its channel go back, plan and versions, to the ones before the spec’s first seed', async () => {
  const before = photo();
  // No row of the channel before: none pushed by another spec (cleanUp drops it) stands in front of the photo's.
  cleanUp();
  const channelBefore = channel();
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
  // The seed changed it (erplora.com's plan and a newer version), or what follows would prove nothing.
  expect(photo()).not.toEqual(before);
  expect(psql("select state->'plan'->>'slug' from base_hub where slug = 'a'")).not.toBe('');
  expect(channel()).not.toEqual(channelBefore);

  // A second seed of the same spec (whatsapp-inbox-plan-cap seeds again) keeps the photo the first one found.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  restorePhoto();
  expect(photo()).toEqual(before);
  expect(channel()).toEqual(channelBefore);

  // Nothing seeded since: putting it back again changes nothing.
  restorePhoto();
  expect(photo()).toEqual(before);
  expect(channel()).toEqual(channelBefore);
});

test('hub#528 — a spec that never seeds keeps the photo first and gets it back, whatever erplora.com pushed meanwhile', () => {
  cleanUp();
  const before = photo();
  const channelBefore = channel();
  keepPhoto();
  // What erplora.com pushes when it answers the Hub (fix-whatsapp-inbox-template-header-thumbnail: Meta refuses the
  // seed's made-up permission, the number is to reconnect): a newer photo on its Free plan, and the channel's state.
  // Written here, not seeded: the seed keeps the photo itself, and this proves that keepPhoto() alone did.
  psql(
    "update base_hub set state = state || jsonb_build_object('plan', jsonb_build_object('slug', 'free', 'max_devices', 1, " +
      "'max_apps', 20)), state_version = state_version + 1 where slug = 'a'",
  );
  pushChannel({ status: 'reconnect_needed' });
  expect(photo()).not.toEqual(before);
  expect(channel()).not.toEqual(channelBefore);

  // Kept again (another scope of the spec, or a seed after it): what was found first stays.
  keepPhoto();
  restorePhoto();
  expect(photo()).toEqual(before);
  expect(channel()).toEqual(channelBefore);
});

test('a channel row there before the seed stays as it was', () => {
  // A row the spec finds (pushed above any photo's version: the seed's channel does not replace it).
  pushChannel({ status: 'reconnect_needed', monthly_usage: 7 });
  const channelBefore = channel();
  expect(channelBefore).toHaveLength(1);
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  restorePhoto();
  expect(channel()).toEqual(channelBefore);
});
