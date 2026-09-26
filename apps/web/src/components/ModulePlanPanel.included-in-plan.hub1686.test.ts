// @vitest-environment happy-dom
// «Included in your plan» — hub#1686, ADR-0474 (revised 09/09).
//
// For ERPlora's own modules the hub plan gives the level (Standard → Basic, Pro → Pro …) and that
// level is not sold separately. When the Cloud says so (`source: "plan"`, ERPlora/saas#1952), the
// tab must stop reading like a price list: it says the level comes with the plan, it paints no
// prices, and the one action it offers is to upgrade the HUB plan, landing on the account page.
//
// Without `source` (a SaaS older than saas#1952) or with any other source (third-party modules,
// bought tiers) the tab stays exactly as it was: that is the positive control of every case below.
//
// Assertions read i18n KEYS (empty catalogue, `t()` echoes the key; ADR-0055) except the two that
// mount the real `en`/`es` catalogues, where "the plan name reaches the sentence in both languages"
// is the requirement itself.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Plugin } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/module-loader', () => ({ loadModuleLocale: vi.fn(async () => undefined) }));
const { getDeviceContext, openExternal, saasDoor, cloudModuleSubscription } = vi.hoisted(() => ({
  getDeviceContext: vi.fn(),
  openExternal: vi.fn(async () => {}),
  saasDoor: vi.fn(async (p: string) => `https://erplora.com${p}`),
  cloudModuleSubscription: vi.fn(),
}));
vi.mock('../lib/device', () => ({ getDeviceContext }));
vi.mock('../lib/open-external', () => ({ openExternal }));
vi.mock('../lib/saas-door', () => ({ saasDoor }));
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1234', cloudApiUrl: 'https://erplora.com' } }));
vi.mock('../lib/cloud', () => ({ cloudModuleSubscription }));

import ModulePlanPanel from './ModulePlanPanel.vue';
import type { ModuleBilling } from '@erplora/module-types';

// The levels of an ERPlora module under ADR-0474: the same slugs as the plan → level map.
const OWN_MODULE = {
  tiers: [
    { slug: 'free', name: 'Free', price: 0, interval: 'month' },
    { slug: 'basic', name: 'Basic', price: 14.99, interval: 'month' },
    { slug: 'pro', name: 'Pro', price: 29.99, interval: 'month' },
    { slug: 'enterprise', name: 'Enterprise', price: 59.99, interval: 'month' },
  ],
} as unknown as ModuleBilling;

type Sub = {
  status: string;
  tier?: string | null;
  source?: string | null;
  planName?: string | null;
};

function emptyI18n() {
  return createI18n({ legacy: false, locale: 'es', missingWarn: false, fallbackWarn: false, messages: { es: {} } });
}

async function mountWith(sub: Sub, i18n: object = emptyI18n()) {
  cloudModuleSubscription.mockResolvedValue({
    trialEnd: null,
    periodEnd: null,
    tier: null,
    source: null,
    planName: null,
    ...sub,
  });
  const w = mount(ModulePlanPanel, {
    props: { moduleId: 'whatsapp_inbox', billing: OWN_MODULE },
    global: { plugins: [i18n as Plugin] },
  });
  await flushPromises();
  return w;
}

const hint = (w: VueWrapper): string => w.find('[data-testid="module-plan-hint"]').text();
const prices = (w: VueWrapper): (string | undefined)[] =>
  w.findAll('ok-pricing-card').map((c) => c.attributes('price'));
const upgrade = (w: VueWrapper) => w.find('[data-testid="module-upgrade-hub-plan"]');
const manage = (w: VueWrapper) => w.find('[data-testid="module-manage-plan"]');

beforeEach(() => {
  cloudModuleSubscription.mockReset();
  getDeviceContext.mockResolvedValue({ distribution: 'web' });
  openExternal.mockClear();
  saasDoor.mockClear();
});

describe('ModulePlanPanel — the level comes with the hub plan (hub#1686)', () => {
  it('says the level is included in the named hub plan', async () => {
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' });

    expect(hint(w)).toBe('modulePlan.hint.includedInPlan');
  });

  it('paints the plan level as active, not «No plan», even on a level the manifest prices', async () => {
    // Standard → Basic: no purchase, so `status` is `none`, and Basic is not the 0 € tier — the
    // free-tier rescue of hub#1652 does not reach it. The plan is still in force.
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' });

    const pill = w.find('ok-status-pill');
    expect(pill.attributes('label')).toBe('modulePlan.status.active');
    expect(pill.attributes('tone')).toBe('success');
    const cards = w.findAll('ok-pricing-card').filter((c) => c.attributes('featured') !== undefined);
    expect(cards.map((c) => c.attributes('name'))).toEqual(['Basic']);
  });

  it('still says «included in your plan» when the plan name does not arrive', async () => {
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan' });

    expect(hint(w)).toBe('modulePlan.hint.includedInHubPlan');
  });

  it('paints no price on any level: they are not sold separately', async () => {
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' });

    expect(prices(w)).toHaveLength(4);
    for (const p of prices(w)) expect(p ?? '').toBe('');
  });

  it('offers upgrading the HUB plan instead of managing a module plan', async () => {
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' });

    expect(manage(w).exists()).toBe(false);
    expect(upgrade(w).exists()).toBe(true);
    await upgrade(w).trigger('click');
    await flushPromises();
    expect(saasDoor).toHaveBeenCalledWith(
      '/dashboard/hubs/hub-1234/change-plan/?utm_source=hub',
      'https://erplora.com/dashboard/hubs/hub-1234/change-plan/?utm_source=hub',
      'upgrade-plan',
    );
    expect(openExternal).toHaveBeenCalledWith('https://erplora.com/dashboard/hubs/hub-1234/change-plan/?utm_source=hub');
  });

  it('offers no upgrade when the hub is already on the highest level', async () => {
    const w = await mountWith({ status: 'none', tier: 'enterprise', source: 'plan', planName: 'Max' });

    expect(upgrade(w).exists()).toBe(false);
    expect(manage(w).exists()).toBe(false);
  });

  it('hides the upgrade where Play would read it as steering (hub#756)', async () => {
    getDeviceContext.mockResolvedValue({ distribution: 'play' });
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' });

    expect(upgrade(w).exists()).toBe(false);
  });

  it.each([null, 'purchase', 'trial', 'free'])(
    'keeps today\'s tab when the source is %s (older SaaS, third-party or bought level)',
    async (source) => {
      const w = await mountWith({ status: 'none', tier: 'free', source });

      expect(hint(w)).toBe('modulePlan.hint.free');
      expect(manage(w).exists()).toBe(true);
      expect(upgrade(w).exists()).toBe(false);
      expect(prices(w).filter((p) => p && p !== 'modulePlan.free').length).toBe(3);
    },
  );
});

describe('ModulePlanPanel — the sentence in both languages (hub#1686)', () => {
  const real = (locale: 'en' | 'es') =>
    createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, es } as never });

  it('reads «Incluido en tu plan Standard» in Spanish', async () => {
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' }, real('es'));

    expect(hint(w)).toContain('Incluido en tu plan Standard');
  });

  it('reads «Included in your Standard plan» in English', async () => {
    const w = await mountWith({ status: 'none', tier: 'basic', source: 'plan', planName: 'Standard' }, real('en'));

    expect(hint(w)).toContain('Included in your Standard plan');
  });
});
