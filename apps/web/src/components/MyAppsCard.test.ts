// @vitest-environment happy-dom
// The «My apps» card (hub#367, PLAN step 10) — the launcher of the panel.
//
// ERPlora is an ERP: what the owner has in front is THEIR apps. The rest of the panel is a report,
// and a report needs history the hub does not have on day one. This card is the only widget that
// works with zero data, and that is the whole reason it goes first.
//
// What these tests protect:
//   - the grid lists the installed apps, most used first, and each tile opens its app;
//   - the ＋ Add apps tile is ALWAYS there, last, and it leads to the catalogue (`/apps`);
//   - a hub with no apps still says something useful — never a mute empty grid, and never
//     «install your first module» (the phrase the plan forbids: it asks a bar owner to understand
//     our architecture before serving a coffee);
//   - opening an app is what counts it, so «most used first» is the user's history and not ours.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// HubIcon bakes its SVGs through `~icons/…?raw`, which the test environment denies (same
// workaround as SetupChecklistCard.test.ts / ImportPanel.test.ts).
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import MyAppsCard from './MyAppsCard.vue';
import { APP_USAGE_KEY, readAppUsage } from '../lib/app-usage';
// REAL catalogues: English is the source language and Spanish is NOT optional (binding rule of
// 2026-08-04). A card with half its strings untranslated ships as half-Spanish.
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: enCatalogue },
});

// A second instance instead of switching the locale of the first one: what is checked with it is
// that the card reads the SPANISH catalogue, and a half-switched instance would hide exactly that.
const i18nEs = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  messages: { es: esCatalogue },
});

const pos = { path: '/m/pos', label: 'Till', icon: 'cart-outline' };
const stock = { path: '/m/inventory', label: 'Stock', icon: 'cube-outline' };
const agenda = { path: '/m/appointments', label: 'Appointments', icon: 'calendar-outline' };

function mountCard(
  apps: { path: string; label: string; icon: string }[] = [],
  messages: typeof i18n | typeof i18nEs = i18n,
  // What the card is told about the list it was handed. `ready` by default: a caller that passes a
  // list and says nothing else IS saying «this is the list».
  state: 'loading' | 'ready' | 'error' = 'ready',
) {
  return mount(MyAppsCard, {
    props: { apps, state },
    global: { plugins: [messages], renderStubDefaultSlot: true },
    shallow: true,
  });
}

const tilePaths = (w: ReturnType<typeof mountCard>): string[] =>
  w.findAll('[data-testid="apps-tile"]').map((t) => t.attributes('data-path') ?? '');

beforeEach(() => {
  localStorage.clear();
});

describe('the grid is the installed apps', () => {
  it('paints one tile per installed app, with its name', () => {
    const w = mountCard([pos, stock]);

    expect(tilePaths(w)).toEqual(['/m/pos', '/m/inventory']);
    expect(w.text()).toContain('Till');
    expect(w.text()).toContain('Stock');
  });

  it('each tile opens ITS app in the shell (no full reload)', () => {
    const tile = mountCard([pos]).find('[data-testid="apps-tile"]');

    // The route is the app's own, not the catalogue's: a launcher whose tiles all land on the shop
    // is the launcher this card came to replace. (The `ion-button` stub lowercases the prop.)
    const route = tile.attributes('routerlink') ?? tile.attributes('router-link');
    expect(route).toBe('/m/pos');
  });

  it('the most used one goes first', () => {
    localStorage.setItem(APP_USAGE_KEY, JSON.stringify({ '/m/appointments': 5, '/m/inventory': 2 }));

    expect(tilePaths(mountCard([pos, stock, agenda]))).toEqual([
      '/m/appointments',
      '/m/inventory',
      '/m/pos',
    ]);
  });

  it('with nothing opened yet it keeps the order the runtime answered', () => {
    expect(tilePaths(mountCard([pos, stock, agenda]))).toEqual([
      '/m/pos',
      '/m/inventory',
      '/m/appointments',
    ]);
  });
});

describe('the ＋ Add apps tile', () => {
  it('is always there and leads to the catalogue', async () => {
    const add = mountCard([pos, stock]).find('[data-testid="apps-add"]');

    expect(add.exists()).toBe(true);
    expect(add.html()).toContain('/apps');
  });

  it('is the LAST tile: it offers more, it does not compete with what is installed', () => {
    const w = mountCard([pos, stock]);
    const tiles = w.findAll('[data-testid="apps-tile"], [data-testid="apps-add"]');

    expect(tiles).toHaveLength(3);
    expect(tiles[tiles.length - 1].attributes('data-testid')).toBe('apps-add');
  });

  it('survives an empty hub — it IS what the empty hub has', () => {
    expect(mountCard([]).find('[data-testid="apps-add"]').exists()).toBe(true);
  });
});

describe('a hub with no apps', () => {
  it('says something useful instead of showing a mute empty grid', () => {
    const w = mountCard([]);

    expect(w.findAll('[data-testid="apps-tile"]')).toHaveLength(0);
    const empty = w.find('[data-testid="apps-empty"]');
    expect(empty.exists()).toBe(true);
    expect(empty.text().trim().length).toBeGreaterThan(0);
  });

  it('does not ask for a «module»: nobody bought an architecture, they bought a till', () => {
    const w = mountCard([]);

    expect(w.text().toLowerCase()).not.toContain('module');
  });

  it('and the message goes AWAY once there is an app: it was guidance, not decoration', () => {
    expect(mountCard([pos]).find('[data-testid="apps-empty"]').exists()).toBe(false);
  });
});

describe('opening an app is what counts it', () => {
  it('counts the open so the next visit ranks it higher', async () => {
    const w = mountCard([pos, stock]);

    await w.findAll('[data-testid="apps-tile"]')[1].trigger('click');

    expect(readAppUsage()).toEqual({ '/m/inventory': 1 });
  });

  it('the catalogue tile is not an app: it never enters the ranking', async () => {
    const w = mountCard([pos]);

    await w.find('[data-testid="apps-add"]').trigger('click');

    expect(readAppUsage()).toEqual({});
  });
});

describe('the strings ship in both languages', () => {
  it('English is the source and Spanish is not optional', () => {
    const en = enCatalogue as unknown as { dashboard: Record<string, string> };
    const es = esCatalogue as unknown as { dashboard: Record<string, string> };

    for (const key of ['appsAdd', 'appsEmpty'] as const) {
      expect(en.dashboard[key], `en.dashboard.${key}`).toBeTruthy();
      expect(es.dashboard[key], `es.dashboard.${key}`).toBeTruthy();
      expect(es.dashboard[key], `es.dashboard.${key} is still the English one`).not.toBe(
        en.dashboard[key],
      );
    }
  });

  it('the card paints the Spanish catalogue when the app is in Spanish', () => {
    const w = mountCard([], i18nEs);

    expect(w.find('[data-testid="apps-empty"]').text()).toBe(
      (esCatalogue as unknown as { dashboard: Record<string, string> }).dashboard.appsEmpty,
    );
  });
});

// hub#770 — «Your apps will show up here» is a statement about the HUB, and the card was making it
// while it simply did not know yet.
//
// On a cold load the panel painted the empty line for the ~3 seconds before `/api/navigation`
// answered: a restaurant with twelve apps installed told its owner it had none, on the screen whose
// only offer is «add your first ones». And a failed request came out identical, because `catch`
// left the list empty — a session displaced by a second device (Free plan) read as «somebody
// uninstalled everything» while the till in the next tab was still selling.
describe('loading and failing are not «you have no apps»', () => {
  it('says nothing about an empty hub while it is still asking', () => {
    const w = mountCard([], i18n, 'loading');

    expect(w.find('[data-testid="apps-empty"]').exists()).toBe(false);
    // And the ＋ tile stays: it is the one thing that is true in every state.
    expect(w.find('[data-testid="apps-add"]').exists()).toBe(true);
  });

  it('says nothing about an empty hub when the request FAILED', () => {
    const w = mountCard([], i18n, 'error');

    expect(w.find('[data-testid="apps-empty"]').exists()).toBe(false);
  });

  it('keeps painting the apps it already had when a reload fails', () => {
    // The last known-good list beats every message we could put in its place.
    const w = mountCard([pos, stock], i18n, 'error');

    expect(tilePaths(w)).toEqual(['/m/pos', '/m/inventory']);
    expect(w.find('[data-testid="apps-empty"]').exists()).toBe(false);
  });

  it('says it, and only then, when an answer came back empty', () => {
    expect(mountCard([], i18n, 'ready').find('[data-testid="apps-empty"]').exists()).toBe(true);
  });
});

// hub#894 — silence was not enough.
//
// hub#770 stopped the card from LYING: on a failure it no longer says «you have no apps». What it
// says instead is nothing at all, and next to a grid whose only tile is «＋ Add apps», nothing still
// reads as «this hub is empty». A real hub with twelve modules registered went two surfaces deep
// like that, and its owner's only available move was to go install what they already had.
//
// A failure the user cannot see is a failure nobody reports either — the runtime log for that hub
// held the 401 the whole time and it took a code read to find it. So an empty launcher that FAILED
// has to say so, out loud, in the card.
describe('a launcher that failed says so', () => {
  it('paints a visible failure when it has nothing to show and the request failed', () => {
    const w = mountCard([], i18n, 'error');

    const error = w.find('[data-testid="apps-error"]');
    expect(error.exists()).toBe(true);
    expect(error.text().length).toBeGreaterThan(0);
    // And it is NOT the «you have no apps» sentence wearing another hat.
    expect(w.find('[data-testid="apps-empty"]').exists()).toBe(false);
  });

  it('stays quiet about failing while it still has apps on screen', () => {
    // Data wins (hub#770): rows beat every message, including this one.
    const w = mountCard([pos, stock], i18n, 'error');

    expect(tilePaths(w)).toEqual(['/m/pos', '/m/inventory']);
    expect(w.find('[data-testid="apps-error"]').exists()).toBe(false);
  });

  it('does not cry failure while it is merely still asking', () => {
    const w = mountCard([], i18n, 'loading');

    expect(w.find('[data-testid="apps-error"]').exists()).toBe(false);
  });

  it('does not cry failure on a hub that genuinely has nothing', () => {
    const w = mountCard([], i18n, 'ready');

    expect(w.find('[data-testid="apps-error"]').exists()).toBe(false);
    expect(w.find('[data-testid="apps-empty"]').exists()).toBe(true);
  });

  it('ships the failure line in both languages', () => {
    const en = enCatalogue as unknown as { dashboard: Record<string, string> };
    const es = esCatalogue as unknown as { dashboard: Record<string, string> };

    expect(en.dashboard.appsLoadError, 'en.dashboard.appsLoadError').toBeTruthy();
    expect(es.dashboard.appsLoadError, 'es.dashboard.appsLoadError').toBeTruthy();
    expect(es.dashboard.appsLoadError).not.toBe(en.dashboard.appsLoadError);
    expect(mountCard([], i18nEs, 'error').find('[data-testid="apps-error"]').text()).toBe(
      es.dashboard.appsLoadError,
    );
  });
});
