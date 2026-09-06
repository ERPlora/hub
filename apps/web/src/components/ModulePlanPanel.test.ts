// @vitest-environment happy-dom
// The module «Plan» tab reuses the shared components instead of hand-rolling cards (hub#1605).
//
// The panel painted its own `ion-card` + `ion-card-header` grid and its own tier list. Two costs,
// both measured on the real hub before this test existed:
//
//   - `ion-card-header` and `ion-badge` are Shadow DOM, and their padding lives on `:host`. The
//     document-level `padding: 0` of Tailwind's preflight beats `:host`, so every title and the
//     status badge sat flush against the card border while the body text was indented. Pages that
//     look right (Profile) pay for it with their own hand-written padding; this panel did not.
//   - The panel is injected for EVERY module that declares `billing`, so a defect here is not one
//     screen: it is one per paid module.
//
// OutfitKit already ships both pieces — `ok-pricing-card` (name/price/period/features) and
// `ok-status-pill` — and they carry their padding inside their own shadow root, so the preflight
// cannot flatten them. Reuse before create is the rule; this test is what keeps it.
import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const { cloudModuleSubscription } = vi.hoisted(() => ({
  cloudModuleSubscription: vi.fn(async () => ({ status: 'none' })),
}));
vi.mock('../lib/cloud', () => ({ cloudModuleSubscription }));

import ModulePlanPanel from './ModulePlanPanel.vue';
import type { ModuleBilling } from '@erplora/module-types';

// El fixture copia un manifest publicado (`whatsapp_inbox`), y con él una contradicción del
// contrato: `module.schema.json` declara `quota` como OBJETO `{ metrica: limite }` —y así lo
// escriben los manifests y así lo lee `quotaLabel`— mientras que `BillingTierDef` lo tipa
// `number | string`. Manda el esquema, así que el fixture es el real y el `as` señala el desfase
// en vez de disfrazarlo: hub#1609.
const BILLING = {
  tiers: [
    { slug: 'free', name: 'WhatsApp Free', price: 0, interval: 'month' },
    { slug: 'starter', name: 'WhatsApp Starter', price: 14.99, interval: 'month', trial_days: 14 },
    {
      slug: 'flex',
      name: 'WhatsApp Flex',
      price: 19.99,
      interval: 'month',
      metered: true,
      overage_price: 0.08,
      quota: { conversations_per_month: 270 },
    },
  ],
} as unknown as ModuleBilling;

const TIERS = BILLING.tiers ?? [];

function mountPanel() {
  const i18n = createI18n({
    legacy: false,
    locale: 'es',
    missingWarn: false,
    fallbackWarn: false,
    messages: { es: {} },
  });
  return mount(ModulePlanPanel, {
    props: { moduleId: 'whatsapp_inbox', billing: BILLING },
    global: { plugins: [i18n] },
  });
}

describe('ModulePlanPanel', () => {
  it('paints every tier with the shared pricing card', async () => {
    const w = mountPanel();
    await flushPromises();

    const cards = w.findAll('ok-pricing-card');
    expect(cards).toHaveLength(TIERS.length);
    expect(cards[0].attributes('name')).toBe('WhatsApp Free');
    // Prices are whole currency units in the manifest (`14.99`), not minor units: the panel hands
    // the formatted amount to the card and the period separately, so the card can style them apart.
    expect(cards[1].attributes('price')).toMatch(/14[.,]99/);
  });

  it('states the subscription with the shared status pill', async () => {
    const w = mountPanel();
    await flushPromises();

    const pill = w.find('ok-status-pill');
    expect(pill.exists()).toBe(true);
    // `none` is not a failure, so it must not borrow an alarming tone.
    expect(pill.attributes('tone')).toBe('neutral');
  });

  it('hand-rolls no card of its own: the flattened Ionic padding never reaches it', async () => {
    const w = mountPanel();
    await flushPromises();

    expect(w.find('ion-card').exists()).toBe(false);
    expect(w.find('ion-card-header').exists()).toBe(false);
    expect(w.find('ion-badge').exists()).toBe(false);
  });
});
