// @vitest-environment happy-dom
// The band that says the network is gone, and keeps saying it (hub#1743).
//
// The module screen now tells «no connection» apart from «this module is broken», but only when
// something FAILS. That leaves the commonest shape of the complaint uncovered: the network drops
// while somebody is looking at a screen that already loaded, and nothing on it changes — the till
// looks perfectly healthy right up to the moment a sale will not go through.
//
// Every product that runs in a shop settles this the same way (Square's dashboard, Toast, Shopify
// POS, and Gmail and Google Docs outside our sector): ONE persistent band, up for as long as there
// is no network, gone by itself the moment there is. So that is what this is, and it lives in
// `AppPage` next to `SetupBlockingStrip` — the shell's single layout — for the reason that strip
// already writes down: a warning that scrolls away is not a warning, and putting it in each view
// means the next view forgets it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';
import { readFileSync } from 'node:fs';

import OfflineStrip from './OfflineStrip.vue';
import { startHubWatch } from '../lib/offline';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

function goOffline(): void {
  window.dispatchEvent(new Event('offline'));
}

function goOnline(): void {
  window.dispatchEvent(new Event('online'));
}

const mounted: Array<{ unmount: () => void }> = [];

function mountStrip(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(OfflineStrip, { global: { plugins: [i18n] } });
  mounted.push(wrapper);
  return wrapper;
}

beforeEach(() => goOnline());
afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
  goOnline();
});

describe('the shell says out loud that there is no network (hub#1743)', () => {
  it('🔴 is not there at all while there IS a network', async () => {
    // This sits over EVERY screen of the product, the till included, so «harmless when idle» is
    // not good enough: silence is the default and the band has to earn its way out of it.
    const wrapper = mountStrip();
    await nextTick();

    expect(wrapper.find('[data-testid="offline-strip"]').exists()).toBe(false);
    expect(wrapper.text()).toBe('');
  });

  it('hub1743_rises_while_the_network_is_gone_and_names_the_connection', async () => {
    const wrapper = mountStrip();
    goOffline();
    await nextTick();

    const strip = wrapper.find('[data-testid="offline-strip"]');
    expect(strip.exists(), 'the network went away and nothing said so').toBe(true);
    expect(strip.attributes('heading')).toBe(enCatalogue.offline.title);
    expect(wrapper.text()).toContain(enCatalogue.offline.body);
    // A tone that says «transient», not «broken»: nothing here is damaged and it heals itself.
    expect(strip.attributes('tone')).toBe('warning');
  });

  it('goes down by itself the moment the network is back', async () => {
    const wrapper = mountStrip();
    goOffline();
    await nextTick();
    expect(wrapper.find('[data-testid="offline-strip"]').exists()).toBe(true);

    goOnline();
    await nextTick();
    expect(
      wrapper.find('[data-testid="offline-strip"]').exists(),
      'the band outlived the outage',
    ).toBe(false);
  });

  it('says it in Spanish too', async () => {
    const wrapper = mountStrip('es');
    goOffline();
    await nextTick();

    expect(wrapper.find('[data-testid="offline-strip"]').attributes('heading')).toBe(
      esCatalogue.offline.title,
    );
    expect(wrapper.text()).toContain(esCatalogue.offline.body);
  });

  it('🔴 offers nothing that would throw the app away', async () => {
    // Deliberate, and the one place this band departs from the brief («banner … con Reintentar»).
    // The only thing a retry on a shell-wide band can do is reload the document, and that is
    // strictly worse than waiting, twice over: it throws away whatever the cashier had half-typed,
    // and `public/sw.js` passes `/modules/**` straight to the network on purpose, so the shell
    // would come back from its cache with every module screen still unable to load its bundle.
    // The browser clears `navigator.onLine` on its own, so a retry HERE has nothing to do that
    // waiting does not do better — the retry belongs on the screen that actually failed, and
    // `ModuleView` has it.
    const wrapper = mountStrip();
    goOffline();
    await nextTick();

    expect(wrapper.find('ion-button').exists(), 'the band grew a button that can only hurt').toBe(
      false,
    );
    expect(wrapper.html()).not.toContain('location.reload');
  });
});

// hub#2085 — the same band, the other cause. The router is up (so the browser flag stays `true`)
// but the hub does not answer: the wording must not claim «no internet», because the person may
// well have internet and the fault may be ours. It names what is known — ERPlora is not answering —
// and the two places the fault can be.
describe('hub#2085 — the hub stops answering while the browser still believes it is online', () => {
  let stop: (() => void) | undefined;

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    stop?.();
    stop = undefined;
    vi.useRealTimers();
  });

  async function hubGoesSilent(): Promise<ReturnType<typeof vi.fn<() => Promise<void>>>> {
    const probe = vi.fn<() => Promise<void>>().mockRejectedValue(new TypeError('Failed to fetch'));
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(5_000);
    return probe;
  }

  it('hub2085_rises_with_the_flag_still_up_and_does_not_blame_the_internet', async () => {
    const wrapper = mountStrip();
    await hubGoesSilent();
    await nextTick();

    const strip = wrapper.find('[data-testid="offline-strip"]');
    expect(strip.exists(), 'the hub went silent and the till looked healthy').toBe(true);
    expect(strip.attributes('heading')).toBe(enCatalogue.offline.hubTitle);
    expect(wrapper.text()).toContain(enCatalogue.offline.hubBody);
    // 🔴 The sentence for «no network» would be a lie here: the browser has a network.
    expect(strip.attributes('heading')).not.toBe(enCatalogue.offline.title);
    expect(strip.attributes('tone')).toBe('warning');
  });

  it('says it in Spanish too', async () => {
    const wrapper = mountStrip('es');
    await hubGoesSilent();
    await nextTick();

    expect(wrapper.find('[data-testid="offline-strip"]').attributes('heading')).toBe(
      esCatalogue.offline.hubTitle,
    );
    expect(wrapper.text()).toContain(esCatalogue.offline.hubBody);
  });

  it('goes down by itself when the hub answers again', async () => {
    const wrapper = mountStrip();
    const probe = await hubGoesSilent();
    await nextTick();
    expect(wrapper.find('[data-testid="offline-strip"]').exists()).toBe(true);

    probe.mockResolvedValue(undefined);
    await vi.advanceTimersByTimeAsync(5_000);
    await nextTick();
    expect(wrapper.find('[data-testid="offline-strip"]').exists(), 'the band outlived the outage').toBe(
      false,
    );
  });

  it('🔴 when the browser itself has no network, that is the sentence, whatever the hub did', async () => {
    const wrapper = mountStrip();
    await hubGoesSilent();
    goOffline();
    await nextTick();

    expect(wrapper.find('[data-testid="offline-strip"]').attributes('heading')).toBe(
      enCatalogue.offline.title,
    );
  });
});

// Wiring, not layout — the shape `shell-setup-strip.test.ts` already uses for the strip next door:
// mounting the whole shell would test Ionic instead of testing this.
describe('every screen of the shell carries it', () => {
  const source = (path: string): string => readFileSync(new URL(path, import.meta.url), 'utf8');
  const appPage = source('./AppPage.vue');

  it('the single layout mounts it, so no screen has to remember', () => {
    expect(appPage).toContain('OfflineStrip');
  });

  it('🔴 sits above the scroller, not inside it', () => {
    // Inside `ion-content` it scrolls away with the page, and a warning that scrolls away is not a
    // warning — the till is exactly where somebody is looking at the bottom of a long order.
    const strip = appPage.indexOf('<OfflineStrip');
    const topbarEnd = appPage.indexOf('</AppTopbar>');
    const content = appPage.indexOf('<ion-content');

    expect(strip, 'the band is not in the layout').toBeGreaterThan(-1);
    expect(strip).toBeGreaterThan(topbarEnd);
    expect(strip).toBeLessThan(content);
  });

  it('the module screens inherit it — that is where hub#1743 was seen', () => {
    for (const page of ['ModuleView.vue', 'SettingsPage.vue', 'DashboardPage.vue']) {
      expect(source(`../views/${page}`), `${page} left the shared layout`).toContain('<AppPage');
    }
  });

  it('🔴 the icon is BAKED, because this is the one surface that is definitely offline', () => {
    // `okIcon()` hands a name it does not know straight to `ion-icon`, which then tries to FETCH
    // the SVG. Everywhere else that merely risks a blank icon; here it is a certainty, because the
    // whole reason this band is up is that nothing can be fetched. The registry that answers is
    // the hub's own (`lib/icons.ts` → `addIcons` in `main.ts`), not OutfitKit's smaller `BY_NAME`.
    const registry = source('../lib/icons.ts');
    for (const icon of ['cloud-offline-outline']) {
      // Quote-agnostic on purpose (hub#2156): the key is what is pinned, not the formatter's style.
      expect(registry, `${icon} is not baked into the shell`).toMatch(new RegExp(`^\\s*(['"])${icon}\\1\\s*:`, 'm'));
    }
    expect(source('./OfflineStrip.vue')).toContain('icon="cloud-offline-outline"');
    expect(source('../views/ModuleView.vue')).toContain('icon="cloud-offline-outline"');
  });
});
