// @vitest-environment happy-dom
// The «Plan» tab named the plans in English inside a Spanish hub — hub#1748.
//
// Half the screen was already translated: hub#1604 made what a plan INCLUDES come from the module's
// own `locales/<lang>.json` («Incluye 30 mensajes al mes»). The titles of the four cards and the
// sentence above them («Estás en Free») kept coming straight from `billing.tiers[].name` of the
// manifest, which is written in the source language (ADR-0055) — so the owner read a Spanish
// sentence with an English plan inside it, on the screen that exists to explain what they pay.
//
// The module already publishes the translation (`billing.tiers`, keyed by slug); this guard is that
// the shell READS it, in both places, and that it keeps falling back to the manifest for a module
// that ships none.
//
// Card titles are read as ATTRIBUTES, not with `w.text()`: `ok-pricing-card` takes `name` that way,
// so a `text()` assertion would go green whether or not the string ever reached the card.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Plugin } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/device', () => ({ getDeviceContext: vi.fn(async () => ({ distribution: 'web' })) }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/saas-door', () => ({ saasDoor: vi.fn(async (p: string) => `https://erplora.com${p}`) }));
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1234', cloudApiUrl: 'https://erplora.com' } }));

const { cloudModuleSubscription } = vi.hoisted(() => ({
  cloudModuleSubscription: vi.fn(async () => ({ status: 'none' })),
}));
vi.mock('../lib/cloud', () => ({ cloudModuleSubscription }));

// Mocked whole, not spread over the real module: `module-loader` pulls the icon set in and the test
// environment refuses those virtual `~icons/*` ids. The panel only asks it for this one thing.
const { loadModuleLocale } = vi.hoisted(() => ({
  loadModuleLocale: vi.fn(async (_base: string, _lang: string): Promise<unknown> => undefined),
}));
vi.mock('../lib/module-loader', () => ({ loadModuleLocale }));

import ModulePlanPanel from './ModulePlanPanel.vue';
import type { ModuleBilling } from '@erplora/module-types';

// The published `whatsapp_inbox` manifest, names included. `quota` is an OBJECT in every real
// manifest and in `module.schema.json` while `BillingTierDef` types it `number | string` — that
// contradiction is hub#1609, hence the cast (same as the sibling suites).
const BILLING = {
  tiers: [
    { slug: 'free', name: 'WhatsApp Free', price: 0, interval: 'month', quota: { billable_messages_per_month: 30 } },
    { slug: 'basic', name: 'WhatsApp Basic', price: 14.99, interval: 'month' },
    { slug: 'pro', name: 'WhatsApp Pro', price: 29.99, interval: 'month' },
    { slug: 'enterprise', name: 'WhatsApp Enterprise', price: 59.99, interval: 'month' },
  ],
} as unknown as ModuleBilling;

// What that module really ships in `locales/es.json` (verified against its `origin/main`).
const ES_LOCALE = {
  billing: {
    quota: { billable_messages_per_month: 'mensajes al mes' },
    tiers: { free: 'Gratis', basic: 'Básico', pro: 'Profesional', enterprise: 'Empresa' },
  },
};

function mountPanel(locale: 'es' | 'en', billing: ModuleBilling = BILLING) {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { es, en } as never });
  const w = mount(ModulePlanPanel, {
    props: { moduleId: 'whatsapp_inbox', billing },
    global: { plugins: [i18n as unknown as Plugin] },
  });
  return { w, i18n };
}

/** What titles the four cards carry, in order. */
const cardNames = (w: VueWrapper): string[] =>
  w.findAll('ok-pricing-card').map((c) => c.attributes('name') ?? '');

/** The sentence under the status pill, read whole. */
const hint = (w: VueWrapper): string => w.find('[data-testid="module-plan-hint"]').text();

beforeEach(() => {
  loadModuleLocale.mockReset();
  loadModuleLocale.mockResolvedValue(undefined);
  cloudModuleSubscription.mockReset();
  cloudModuleSubscription.mockResolvedValue({ status: 'none' } as never);
});

describe('ModulePlanPanel — the plans are named in the language of the hub (hub#1748)', () => {
  it('titles every card with the name the module publishes for that tier', async () => {
    loadModuleLocale.mockResolvedValue(ES_LOCALE as never);

    const { w } = mountPanel('es');
    await flushPromises();

    expect(cardNames(w)).toEqual(['Gratis', 'Básico', 'Profesional', 'Empresa']);
    // The control that fails before the fix: the English of the manifest must be gone from the tab.
    expect(w.html()).not.toContain('WhatsApp Free');
  });

  it('says which plan you are on with that same name', async () => {
    loadModuleLocale.mockResolvedValue(ES_LOCALE as never);

    const { w } = mountPanel('es');
    await flushPromises();

    // No purchase → the free tier is the one you are on (hub#1652), and the sentence names it.
    expect(hint(w)).toBe('Estás en Gratis, el plan con el que entra todo el mundo.');
  });

  it('names the plan you fall back to when a subscription expires', async () => {
    // `expiredOnFree` interpolates the same plan, and it is the sentence the customer reads on the
    // worst day: it must not switch back to English there.
    cloudModuleSubscription.mockResolvedValue({ status: 'expired' } as never);
    loadModuleLocale.mockResolvedValue(ES_LOCALE as never);

    const { w } = mountPanel('es');
    await flushPromises();

    expect(hint(w)).toBe('Tu suscripción ha caducado. Sigues en Gratis.');
  });

  it('keeps the manifest names for a module that ships no translation', async () => {
    // Nothing is invented: English is the source language, so a module with no `locales/es.json`
    // shows exactly what its manifest says — the behaviour before this issue, kept on purpose.
    const { w } = mountPanel('es');
    await flushPromises();

    expect(cardNames(w)).toEqual([
      'WhatsApp Free',
      'WhatsApp Basic',
      'WhatsApp Pro',
      'WhatsApp Enterprise',
    ]);
    expect(hint(w)).toBe('Estás en WhatsApp Free, el plan con el que entra todo el mundo.');
  });

  it('keeps the manifest name of a tier the translation forgot, and translates the rest', async () => {
    loadModuleLocale.mockResolvedValue({ billing: { tiers: { free: 'Gratis' } } } as never);

    const { w } = mountPanel('es');
    await flushPromises();

    expect(cardNames(w)).toEqual([
      'Gratis',
      'WhatsApp Basic',
      'WhatsApp Pro',
      'WhatsApp Enterprise',
    ]);
  });

  it('re-asks the module when the language on screen changes, like the quota already does', async () => {
    loadModuleLocale.mockImplementation(async (_base: string, lang: string) => ({
      billing: { tiers: { free: lang === 'es' ? 'Gratis' : 'Free plan' } },
    }));

    const { w, i18n } = mountPanel('es');
    await flushPromises();
    expect(cardNames(w)[0]).toBe('Gratis');

    // Switching the hub's language must repaint the card, not leave the previous language frozen
    // on it: the panel watches `locale` and asks the module again for that file.
    i18n.global.locale.value = 'en';
    await flushPromises();

    expect(cardNames(w)[0]).toBe('Free plan');
  });
});
