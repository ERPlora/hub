// @vitest-environment happy-dom
// The «Plan» tab must not print the module's internal quota key at the customer — hub#1604.
//
// `billing.tiers[].quota` of a manifest is a dict of `{ metric: limit }` and the metric is a
// snake_case identifier the module author writes: `conversations_per_month`. The panel used to
// paint it by swapping the underscores for spaces, so a Spanish hub read «Incluye 30 conversations
// per month» — half the sentence translated, half of it not, on the screen where the owner decides
// how much to spend every month.
//
// The fix reuses what hub#1094 already settled for the generated settings screen: the string comes
// from the module's own `locales/<lang>.json`, and canonical English is the fallback (ADR-0055).
//
// The assertions look at `visibleText()` and not at `w.text()` on purpose: the panel hands its
// tier lines to a child component, and hub#1605/#1606 is moving them from markup to a DOM property
// (`ok-pricing-card` takes `features` that way). Reading both is what keeps this guard from turning
// green just because the string stopped being markup.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const { cloudModuleSubscription } = vi.hoisted(() => ({
  cloudModuleSubscription: vi.fn(async () => ({ status: 'none' })),
}));
vi.mock('../lib/cloud', () => ({ cloudModuleSubscription }));

// Mocked whole, not spread over the real module: `module-loader` pulls the icon set in, and the
// test environment refuses those virtual `~icons/*` ids. The panel only asks it for this one thing.
const { loadModuleLocale } = vi.hoisted(() => ({
  loadModuleLocale: vi.fn(async (_base: string, _lang: string): Promise<unknown> => undefined),
}));
vi.mock('../lib/module-loader', () => ({ loadModuleLocale }));

import ModulePlanPanel from './ModulePlanPanel.vue';
import type { ModuleBilling } from '@erplora/module-types';

// Copied from the published `whatsapp_inbox` manifest. `quota` is an OBJECT, which is what
// `module.schema.json` declares and what every published manifest writes; `BillingTierDef` types it
// `number | string`, and that contradiction is hub#1609, not this issue — hence the cast.
const BILLING = {
  tiers: [
    { slug: 'free', name: 'WhatsApp Free', price: 0, interval: 'month', quota: { conversations_per_month: 30 } },
  ],
} as unknown as ModuleBilling;

/**
 * Everything this panel puts in front of the person: its markup plus the string lists it hands to
 * child components as DOM properties.
 */
function visibleText(w: VueWrapper): string {
  const fromProps = w
    .findAll('*')
    .map((el) => (el.element as unknown as { features?: unknown }).features)
    .filter((v): v is unknown[] => Array.isArray(v))
    .flat()
    .join(' ');
  return `${w.text()} ${fromProps}`;
}

function mountPanelWith(locale: 'es' | 'en', billing: ModuleBilling = BILLING) {
  const i18n = createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { es, en } as never,
  });
  const w = mount(ModulePlanPanel, {
    props: { moduleId: 'whatsapp_inbox', billing },
    global: { plugins: [i18n] },
  });
  return { w, i18n };
}

function mountPanel(locale: 'es' | 'en') {
  return mountPanelWith(locale).w;
}

beforeEach(() => {
  loadModuleLocale.mockReset();
  loadModuleLocale.mockResolvedValue(undefined);
});

describe('ModulePlanPanel — what a plan includes (hub#1604)', () => {
  it('says what the plan includes in the language of the hub when the module translates it', async () => {
    loadModuleLocale.mockResolvedValue({
      billing: { quota: { conversations_per_month: 'conversaciones al mes' } },
    } as never);

    const w = mountPanel('es');
    await flushPromises();

    expect(visibleText(w)).toContain('Incluye 30 conversaciones al mes');
    expect(visibleText(w)).not.toContain('conversations per month');
  });

  it('falls back to the canonical English of the manifest, never to the raw key', async () => {
    const w = mountPanel('es');
    await flushPromises();

    // No translation shipped: English is the source language (ADR-0055), so the metric shows in
    // English — the same fallback the generated settings screen already takes (hub#1094). What must
    // never reach the screen is the identifier itself, underscores and all.
    expect(visibleText(w)).toContain('Incluye 30 conversations per month');
    expect(visibleText(w)).not.toContain('conversations_per_month');
  });

  it('keeps the English of a metric the module locale does not name: older locale, newer metric', async () => {
    // The locale shipped with an earlier release only knows `conversations_per_month`; the manifest
    // now declares a second metric. That one comes out as English prose — never the raw identifier,
    // never a bare number with nothing after it — while the known one stays translated.
    loadModuleLocale.mockResolvedValue({
      billing: { quota: { conversations_per_month: 'conversaciones al mes' } },
    });
    const billing = {
      tiers: [
        {
          slug: 'free', name: 'WhatsApp Free', price: 0, interval: 'month',
          quota: { conversations_per_month: 30, messages_per_month: 100 },
        },
      ],
    } as unknown as ModuleBilling;

    const { w } = mountPanelWith('es', billing);
    await flushPromises();

    expect(visibleText(w)).toContain('Incluye 30 conversaciones al mes · 100 messages per month');
    expect(visibleText(w)).not.toContain('messages_per_month');
  });

  it('re-asks the module when the language on screen changes, like the settings screen does', async () => {
    loadModuleLocale.mockImplementation(async (_base, lang) => ({
      billing: {
        quota: {
          conversations_per_month: lang === 'es' ? 'conversaciones al mes' : 'chats per month',
        },
      },
    }));
    const { w, i18n } = mountPanelWith('es');
    await flushPromises();
    expect(visibleText(w)).toContain('Incluye 30 conversaciones al mes');

    // Same screen, still open: the person switches the hub to English from the profile.
    i18n.global.locale.value = 'en';
    await flushPromises();

    expect(loadModuleLocale).toHaveBeenLastCalledWith(expect.stringContaining('whatsapp_inbox'), 'en');
    expect(visibleText(w)).toContain('Includes 30 chats per month');
    expect(visibleText(w)).not.toContain('conversaciones al mes');
  });

  it('asks the module for the translations of the language actually on screen', async () => {
    const w = mountPanel('es');
    await flushPromises();

    expect(loadModuleLocale).toHaveBeenCalledWith(expect.stringContaining('whatsapp_inbox'), 'es');
    expect(w.exists()).toBe(true);
  });
});
