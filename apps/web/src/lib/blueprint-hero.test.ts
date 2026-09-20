// @vitest-environment node
// The rules behind the hero card of an empty hub (hub#368, PLAN step 10).
//
// The card paints; everything it DECIDES lives here, so it can be argued with in a test instead of
// in a browser: when a hub counts as empty, which templates get offered, what one click actually
// asks the engine for, and what the owner is told happened afterwards.
import { describe, expect, it } from 'vitest';

import {
  MAX_OFFERS,
  heroOffers,
  heroPart,
  heroSelection,
  heroVisible,
  hubIsEmpty,
  importOutcome,
  mayAdminister,
  type HeroInput,
} from './blueprint-hero';
import { ADMINISTER_PERMISSION } from './management-link';
import { ALL_PERMISSIONS } from './session';
import type { BlueprintManifest, CatalogBlueprint, ImportReport } from './runtime';
import type { SetupItem, SetupStatus } from './setup-status';

function item(over: Partial<SetupItem> = {}): SetupItem {
  return {
    key: 'apps',
    source: 'core',
    moduleId: null,
    state: 'pending',
    required: true,
    level: 'functional',
    title: 'Your apps',
    description: '',
    icon: 'grid-outline',
    route: '/apps',
    order: 10,
    actions: ['template', 'catalog'],
    actionable: true,
    origin: 'user',
    missingCapabilities: [],
    ...over,
  };
}

function status(items: SetupItem[]): SetupStatus {
  const pending = items.filter((i) => i.state === 'pending').length;
  const unavailable = items.filter((i) => i.state === 'unavailable').length;
  return {
    items,
    total: items.length,
    pending,
    unavailable,
    blockingPending: 0,
    done: items.length - pending - unavailable,
  };
}

function offer(over: Partial<CatalogBlueprint> = {}): CatalogBlueprint {
  return {
    slug: 'restaurant_es',
    name: 'Restaurante',
    description: '',
    locale: 'es',
    country: 'ES',
    latest_version: '1.0.0',
    latest_sha256: 'abc',
    size_bytes: 1024,
    downloads: 3,
    ...over,
  };
}

function input(over: Partial<HeroInput> = {}): HeroInput {
  return {
    canAdminister: true,
    status: status([item()]),
    offers: [offer()],
    run: null,
    dismissed: false,
    shown: false,
    ...over,
  };
}

function manifest(over: Partial<BlueprintManifest> = {}): BlueprintManifest {
  return {
    schema_version: 1,
    name: 'Restaurante',
    locale: 'es',
    hub: {},
    created_at: '2026-08-08T00:00:00Z',
    modules: [
      { id: 'pos', version: '1.0.0', with_data: true },
      { id: 'catalog', version: '2.0.0', with_data: true },
    ],
    sections: ['hub_settings', 'media'],
    sha256: {},
    ...over,
  };
}

describe('what «an empty hub» means', () => {
  it('is what the ONE query says, not a count of our own', () => {
    // `hub.setup.status` already owns «does this hub have apps» (ADR-0222): re-deriving it from the
    // navigation or from a module list would be the second source hub#369 closed.
    expect(hubIsEmpty(status([item({ state: 'pending' })]))).toBe(true);
    expect(hubIsEmpty(status([item({ state: 'done' })]))).toBe(false);
  });

  it('counts an `unavailable` apps item as empty: the templates are a DIFFERENT door', () => {
    // `unavailable` says the module catalogue offers this hub nothing (hub#371). The blueprint
    // catalogue is another endpoint entirely, so closing the door that is still open because the
    // other one is shut would leave an empty hub with no way in at all.
    expect(hubIsEmpty(status([item({ state: 'unavailable' })]))).toBe(true);
  });

  it('says NO when there is no answer yet: an absence is not evidence of emptiness', () => {
    expect(hubIsEmpty(null)).toBe(false);
  });

  it('says NO when the answer carries no apps item at all', () => {
    // The runtime drops items this session cannot configure (hub#435) and omits checks it could not
    // make. Reading a gap as «empty» would offer a sector template on top of a working business.
    expect(hubIsEmpty(status([item({ key: 'business_identity', state: 'pending' })]))).toBe(false);
    expect(hubIsEmpty(status([]))).toBe(false);
  });
});

describe('who may press it', () => {
  it('is the permission the core ALREADY owns, not a new one', () => {
    // ADR-0248: `hub.administer` is granted by `identity::session_permissions` to exactly the roles
    // the server's admin gate accepts, and no `module.json` can mint it (the `hub.` namespace is
    // reserved). Inventing a second name for the same thing is how two gates start disagreeing.
    expect(ADMINISTER_PERMISSION).toBe('hub.administer');
    expect(mayAdminister([ADMINISTER_PERMISSION])).toBe(true);
    expect(mayAdminister(['pos.sale.create'])).toBe(false);
  });

  it('honours the wildcard the shell hands an owner', () => {
    expect(mayAdminister([ALL_PERMISSIONS])).toBe(true);
  });

  it('says no when the session brought no permissions at all', () => {
    expect(mayAdminister(undefined)).toBe(false);
    expect(mayAdminister([])).toBe(false);
  });
});

describe('when the card is on screen', () => {
  it('is up for an administrator, on an empty hub, with something to offer', () => {
    expect(heroVisible(input())).toBe(true);
  });

  it('is gone for a session that cannot administer the business (hub#435)', () => {
    // Importing a template is a TASK, not a wall: nothing here stops a cashier from selling, so the
    // rule of ADR-0248 applies in full — the task that is not yours goes away.
    expect(heroVisible(input({ canAdminister: false }))).toBe(false);
  });

  it('is gone even mid-run for a session that cannot administer', () => {
    expect(
      heroVisible(input({ canAdminister: false, run: { phase: 'working', name: 'Restaurante' } })),
    ).toBe(false);
  });

  it('is gone when there is no template to offer', () => {
    // A hero card with no options is a promise we cannot keep. Settings › Data still has the
    // catalogue and its honest empty-state.
    expect(heroVisible(input({ offers: [] }))).toBe(false);
  });

  it('is gone once the business has an app', () => {
    expect(heroVisible(input({ status: status([item({ state: 'done' })]) }))).toBe(false);
  });

  it('is gone while we do not know whether the business has apps', () => {
    expect(heroVisible(input({ status: null }))).toBe(false);
  });

  it('stays up while the click is in flight, even though the hub stops being empty', () => {
    // The import installs apps, which ticks the first item: the card that started the job would
    // vanish mid-way and take its own progress with it.
    expect(
      heroVisible(
        input({
          status: status([item({ state: 'done' })]),
          offers: [],
          run: { phase: 'working', name: 'Restaurante' },
        }),
      ),
    ).toBe(true);
  });

  it('stays up on the outcome, so what happened can be read', () => {
    expect(
      heroVisible(
        input({
          status: status([item({ state: 'done' })]),
          offers: [],
          run: { phase: 'finished', outcome: { kind: 'ready' } },
        }),
      ),
    ).toBe(true);
  });

  // 🔴 hub#1120 — the door must not close under the pointer.
  //
  // The panel re-reads `hub.setup.status` while the owner is reading the card, and `hubIsEmpty`
  // stops saying «empty» for three things that are not the owner acting: a failed re-read (the
  // document arrives `null` — hub#1120 turned out to be the 429 of saas#1640), the `apps` item
  // dropping out for this session (hub#435), and the import this card itself started. The card
  // would then be pulled out of the DOM mid-reading, and a press aimed at «Use this» lands on empty
  // space: no spinner, no error, no request. That is the shape the owner reported, and it is
  // indistinguishable from a dead button.
  //
  // So once the card has been shown to THIS session it stays until the owner acts on it or closes
  // it — the same contract as the onboarding guides of Shopify, Odoo or Square. The protection is
  // untouched: `shown` only latches AFTER the business legitimately counted as empty, so a hub
  // that already had apps still never sees the offer.
  //
  // (This used to say a FREE hub arrives with `customers` preinstalled. It does not — hub#1179.)
  it('does not close on its own once it is up, even when `apps` ticks done', () => {
    expect(heroVisible(input({ shown: true, status: status([item({ state: 'done' })]) }))).toBe(true);
  });

  it('a business that already had apps still never gets it', () => {
    expect(heroVisible(input({ shown: false, status: status([item({ state: 'done' })]) }))).toBe(false);
  });

  it('does not survive on an empty offer: the card that has nothing to offer goes anyway', () => {
    // The latch keeps a card that CAN still be pressed. With no template left to press it is a
    // promise we cannot keep — the same rule as the first render.
    expect(heroVisible(input({ shown: true, offers: [] }))).toBe(false);
  });

  it('goes when the outcome has been read and closed', () => {
    expect(
      heroVisible(
        input({ dismissed: true, run: { phase: 'finished', outcome: { kind: 'ready' } } }),
      ),
    ).toBe(false);
  });
});

describe('which templates get offered', () => {
  const es = offer({ slug: 'restaurant_es', country: 'ES', locale: 'es' });
  const esTwo = offer({ slug: 'barber_es', country: 'ES', locale: 'es' });
  const mx = offer({ slug: 'pizza_mx', country: 'MX', locale: 'es' });
  const fr = offer({ slug: 'salon_fr', country: 'FR', locale: 'fr' });

  it('never turns into a list: four at most', () => {
    const many = Array.from({ length: 9 }, (_, n) => offer({ slug: `t${n}`, country: '', locale: '' }));
    expect(MAX_OFFERS).toBe(4);
    expect(heroOffers(many, {})).toHaveLength(MAX_OFFERS);
  });

  it('puts this country first, then this language, then the rest', () => {
    const picked = heroOffers([fr, mx, es], { country: 'ES', language: 'es' });
    expect(picked.map((b) => b.slug)).toEqual(['restaurant_es', 'pizza_mx', 'salon_fr']);
  });

  it('orders, it never hides: everything published stays reachable', () => {
    // Filtering by country would silently drop the only template a border business wants. The card
    // shows four and points at the full catalogue for the rest.
    expect(heroOffers([fr], { country: 'ES', language: 'es' }).map((b) => b.slug)).toEqual(['salon_fr']);
  });

  it('keeps the catalogue order inside each tier', () => {
    const picked = heroOffers([esTwo, es], { country: 'ES', language: 'es' });
    expect(picked.map((b) => b.slug)).toEqual(['barber_es', 'restaurant_es']);
  });

  it('prefers nothing when the business has not said where it is', () => {
    const picked = heroOffers([fr, mx, es], {});
    expect(picked.map((b) => b.slug)).toEqual(['salon_fr', 'pizza_mx', 'restaurant_es']);
  });

  it('does not care about case: a country code is a country code', () => {
    const picked = heroOffers([fr, es], { country: 'es', language: 'ES' });
    expect(picked[0].slug).toBe('restaurant_es');
  });

  it('does not care about the blank space a stored setting may carry either', () => {
    expect(heroOffers([fr, es], { country: ' es ' })[0].slug).toBe('restaurant_es');
  });
});

describe('what one click asks the engine for', () => {
  it('asks for every app of the template and for the data that fills the catalogue', () => {
    expect(heroSelection(manifest()).modules).toEqual(['pos', 'catalog']);
  });

  it('NEVER asks for the people of the other business (ADR-0195 §5)', () => {
    // One click is a click with no review screen. The step that let a human eye veto somebody
    // else's identities is exactly the step this card removes, so it must not ask for them.
    const selection = heroSelection(manifest({ sections: ['hub_users', 'hub_settings'] }));
    expect(selection.users).toBe(false);
  });

  it('NEVER asks for the fiscal identity of the other business', () => {
    const selection = heroSelection(manifest({ sections: ['fiscal', 'hub_settings'] }));
    expect(selection.fiscal).toBe(false);
  });

  it('asks for the settings and the images only when the bundle carries them', () => {
    const full = heroSelection(manifest({ sections: ['hub_settings', 'media'] }));
    expect(full.settings).toBe(true);
    expect(full.media).toBe(true);

    const bare = heroSelection(manifest({ sections: [] }));
    expect(bare.settings).toBe(false);
    expect(bare.media).toBe(false);
  });

  it('understands the short alias of the settings section', () => {
    expect(heroSelection(manifest({ sections: ['settings'] })).settings).toBe(true);
  });

  it('survives a manifest with no module list', () => {
    expect(heroSelection(manifest({ modules: undefined as never })).modules).toEqual([]);
  });
});

describe('what the owner is told happened', () => {
  function report(over: Partial<ImportReport> = {}): ImportReport {
    return { sections: [], installed_modules: [], ...over };
  }

  it('everything in ⇒ ready', () => {
    expect(
      importOutcome(
        report({
          sections: [{ section: 'hub_settings', status: 'Applied' }],
          installed_modules: [{ id: 'pos', version: '1.0.0', status: 'installed' }],
        }),
      ),
    ).toEqual({ kind: 'ready' });
  });

  it('an app that needs subscribing first is NOT a failure (ADR-0060, hub#409)', () => {
    const outcome = importOutcome(
      report({
        installed_modules: [
          { id: 'pos', version: '1.0.0', status: 'installed' },
          { id: 'invoice', version: '1.0.0', status: 'blocked', blocked_on: ['invoice'] },
        ],
      }),
    );
    expect(outcome).toEqual({ kind: 'partial', blockedApps: ['invoice'], failedApps: [], failedSections: [] });
  });

  it('an app that could not be installed at all IS one', () => {
    const outcome = importOutcome(
      report({ installed_modules: [{ id: 'pos', version: '1.0.0', status: 'failed', error: 'boom' }] }),
    );
    expect(outcome).toEqual({ kind: 'partial', blockedApps: [], failedApps: ['pos'], failedSections: [] });
  });

  it('an app already installed is not news', () => {
    expect(
      importOutcome(
        report({ installed_modules: [{ id: 'pos', version: '1.0.0', status: 'already_installed' }] }),
      ),
    ).toEqual({ kind: 'ready' });
  });

  it('a section the engine DISCARDED on purpose is not a failure (ADR-0195)', () => {
    // A template is supposed to arrive without the other business's identities. Reporting that as
    // «something did not make it» would alarm on every single import that worked perfectly.
    expect(
      importOutcome(report({ sections: [{ section: 'hub_users', status: { Ignored: 'identity_not_portable' } }] })),
    ).toEqual({ kind: 'ready' });
  });

  it('a section applied in PART is not a failure either (hub#405)', () => {
    expect(
      importOutcome(
        report({ sections: [{ section: 'hub_settings', status: { PartiallyApplied: 'settings_not_portable' } }] }),
      ),
    ).toEqual({ kind: 'ready' });
  });

  // hub#1947 — the `peluqueria` template was published against `appointments` 1.1.53 and carried a
  // row for a table the module retired in 1.1.79. That one row failed the whole section, so the
  // salon's first screen was the red «Casi: algo no ha entrado» and an agenda with none of the 28
  // appointments the card promises. With the rows left out and SAID, the card is `ready` again:
  // a table the app no longer keeps is the product moving on, not something the owner must fix.
  it('rows for a table the app RETIRED are not a failure (hub#1947)', () => {
    expect(
      importOutcome(
        report({
          sections: [
            {
              section: 'modules/appointments',
              status: { PartiallyApplied: 'table_gone_in_installed_version' },
              discarded_rows: 7,
            },
          ],
        }),
      ),
    ).toEqual({ kind: 'ready' });
  });

  // hub#899 — the count used to be all the card got, and the reason written here was that the
  // engine's names are ours, not words the owner ever chose. True about the raw key, and it left
  // her reading «something else did not go in» on the one screen where she is checking whether her
  // business is inside. The KEY travels; putting it into her words is the card's job.
  it('a section that failed is NAMED, not just counted', () => {
    const outcome = importOutcome(
      report({ sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }] }),
    );
    expect(outcome).toEqual({
      kind: 'partial',
      blockedApps: [],
      failedApps: [],
      failedSections: ['hub_settings'],
    });
  });

  it('names EVERY part that did not go in, in the engine\'s order', () => {
    const outcome = importOutcome(
      report({
        sections: [
          { section: 'hub_settings', status: { Failed: 'db down' } },
          { section: 'roles', status: 'Applied' },
          { section: 'modules/hairdressing', status: { Failed: 'sql error' } },
        ],
      }),
    );
    expect(outcome).toEqual({
      kind: 'partial',
      blockedApps: [],
      failedApps: [],
      failedSections: ['hub_settings', 'modules/hairdressing'],
    });
  });

  it('images that ALL failed are one part that did not go in, named as such', () => {
    expect(
      importOutcome(report({ media: { selected: true, copied: 0, failed: 4 } })),
    ).toEqual({ kind: 'partial', blockedApps: [], failedApps: [], failedSections: ['media'] });
  });

  it('a partial media copy is never ready — including the observed 98/182 split', () => {
    // Product rows already point at every media path. Calling this ready would leave 182 broken
    // catalogue tiles while hiding the persisted report that can retry them.
    expect(importOutcome(report({ media: { selected: true, copied: 98, failed: 182 } }))).toEqual({
      kind: 'partial',
      blockedApps: [],
      failedApps: [],
      failedSections: ['media'],
    });
  });

  it('a bundle that simply had no images is not trouble', () => {
    // Selected, nothing to copy, nothing failed: the full report calls that «skipped», and so does
    // the silence here. Reading «copied nothing» as a failure would alarm on every template
    // published without photos.
    expect(importOutcome(report({ media: { selected: true, copied: 0, failed: 0 } }))).toEqual({
      kind: 'ready',
    });
  });

  it('lets the SERVER have the last word on the images, not the engine row', () => {
    // Media is materialised by the server, so `report.media` is the authority and the engine's own
    // row is stale by construction — the same rule the full report follows. Reading the row anyway
    // would report a breakage over a copy that went perfectly.
    expect(
      importOutcome(
        report({
          sections: [{ section: 'media', status: { Failed: 'engine does not copy media' } }],
          media: { selected: true, copied: 9, failed: 0 },
        }),
      ),
    ).toEqual({ kind: 'ready' });
  });

  it('counts the images ONCE, even though they are reported in two places', () => {
    // The engine leaves a `Skipped` row for media and the server puts the real result in
    // `report.media` (the same rule the full report follows). Counting both would say two parts
    // did not go in when only one did.
    expect(
      importOutcome(
        report({
          sections: [{ section: 'media', status: 'Skipped' }],
          media: { selected: true, copied: 0, failed: 3 },
        }),
      ),
    ).toEqual({ kind: 'partial', blockedApps: [], failedApps: [], failedSections: ['media'] });
  });

  it('reads a report with no keys at all as ready rather than inventing trouble', () => {
    expect(importOutcome({ sections: [] })).toEqual({ kind: 'ready' });
  });

  it('says everything that went wrong at once', () => {
    const outcome = importOutcome(
      report({
        sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
        installed_modules: [
          { id: 'invoice', version: '1.0.0', status: 'blocked', blocked_on: ['invoice'] },
          { id: 'pos', version: '1.0.0', status: 'failed', error: 'boom' },
        ],
      }),
    );
    expect(outcome).toEqual({
      kind: 'partial',
      blockedApps: ['invoice'],
      failedApps: ['pos'],
      failedSections: ['hub_settings'],
    });
  });
});

// hub#899 — «Casi: algo no ha entrado. Hay algo MÁS que no ha entrado»: two «somethings» and not
// one clue, at the minute the owner is checking whether her business is inside. The section keys
// are the engine's (`hub_settings`, `modules/hairdressing`) and painting them raw would be no
// better, so each one is resolved to what it IS — a part of the hub with words of its own, or the
// data of an app, which the card then names the way she knows the app.
describe('putting a part of the template into the owner\'s words', () => {
  it('a part of the hub carries the key of its own sentence', () => {
    expect(heroPart('hub_settings')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partSettings' });
    expect(heroPart('media')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partMedia' });
    expect(heroPart('roles')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partRoles' });
    expect(heroPart('fiscal')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partFiscal' });
    expect(heroPart('hub_users')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partTeam' });
  });

  it('reads the short spelling of a section too', () => {
    // The engine writes `hub_settings`/`hub_users`; a bundle may carry the short name in its
    // manifest, and the report at Settings › Data already reads both as the same thing.
    expect(heroPart('settings')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partSettings' });
    expect(heroPart('users')).toEqual({ kind: 'named', i18nKey: 'setup.hero.partTeam' });
  });

  it('a `modules/<id>` part is the DATA of that app, and travels with its id', () => {
    // Not «the app did not go in» — that is `failedApps`, and the app may well be installed and
    // running with an empty catalogue. Telling them apart is the difference between «reinstall it»
    // and «your services are missing».
    expect(heroPart('modules/hairdressing')).toEqual({ kind: 'app_data', moduleId: 'hairdressing' });
  });

  it('a section this shell does not know is handed back whole, never swallowed', () => {
    // A runtime newer than the shell. Painting its key is what the full report at Settings › Data
    // already does with an unknown section; dropping it silently would be the one thing worse than
    // an ugly name — a part that failed and nobody ever mentioned.
    expect(heroPart('something_new')).toEqual({ kind: 'unknown', section: 'something_new' });
  });
});
