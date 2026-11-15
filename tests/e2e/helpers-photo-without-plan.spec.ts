// flow: none — the e2e harness (hub#808)
// `dropPlanFromPhoto` and `restorePhotoFrom` (helpers.ts): a spec that signs in from more than one browser runs with no
// plan in `a`'s photo, whatever the seed left there (erplora.com's Free covers one device, and each entry from another
// browser would end the others' sessions with a 401), and puts the
// photo back as it found it at the end. No browser: only the registry's row of `a`.
import { expect, test } from '@playwright/test';

import { dropPlanFromPhoto, psql, restorePhotoFrom } from './helpers';

/** Where `a`'s photo as the run finds it waits while this spec gives it a plan of its own. */
const FOUND = 'e2e_backup_photo_without_plan_found';
/** The table the helpers are tried with. */
const KEPT = 'e2e_backup_photo_without_plan';

interface Photo {
  version: number;
  state: Record<string, unknown>;
}

/** `a`'s photo as the Hub keeps it: its version and its state. */
const photo = (): Photo =>
  JSON.parse(psql("select json_build_object('version', state_version, 'state', state) from base_hub where slug = 'a'")) as Photo;

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  // Whatever plan the run found goes aside, and `a` gets erplora.com's Free: one device.
  dropPlanFromPhoto(FOUND);
  psql(
    "update base_hub set state = state || jsonb_build_object('plan', jsonb_build_object('slug', 'free', 'max_devices', 1)) " +
      "where slug = 'a'",
  );
});

test.afterAll(() => {
  restorePhotoFrom(KEPT);
  restorePhotoFrom(FOUND);
});

test('the plan leaves a’s photo while a spec runs, and the photo comes back whole, as it was found', () => {
  const found = photo();
  expect(found.state.plan).toEqual({ slug: 'free', max_devices: 1 });
  const rest = { ...found.state };
  delete rest.plan;

  dropPlanFromPhoto(KEPT);
  // Only the plan goes: the rest of the photo and its version stay, so a newer photo of erplora.com still applies.
  expect(photo()).toEqual({ version: found.version, state: rest });

  restorePhotoFrom(KEPT);
  expect(photo()).toEqual(found);
  expect(psql(`select to_regclass('${KEPT}') is null`)).toBe('t');

  // Nothing kept since (a spec whose `beforeAll` stopped before keeping it): putting it back changes nothing.
  restorePhotoFrom(KEPT);
  expect(photo()).toEqual(found);
});
