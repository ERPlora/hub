// @vitest-environment happy-dom
// The «Plan» tab of a paid module told almost everybody they had no plan — hub#1652.
//
// Every premium module we publish ships a tier at 0 €, and ADR-0032 makes that tier installable
// WITHOUT a purchase (`_has_free_tier()` / `is_module_entitled()` in
// `saas/apps/public/modules/entitlement.py`): the free plan is how the majority come in. With no
// purchase row there is no `ModulePurchase`, so `/module-subscription/` answers `status: "none"`
// and the panel painted «No plan · You don't have a plan for this module yet» in grey — on the one
// screen that exists to explain the plan the customer is on. It also painted every tier card the
// same, so with four prices in front of you nothing said which one was yours.
//
// ERPlora/saas#1921 closed the missing half of the contract: the endpoint now also answers `tier`,
// the SLUG of the `ModuleTier` this hub is entitled to right now — the bought tier while its
// subscription is current, else an in-window no-card trial, else the module's free tier. It is a
// different question from `status` (which describes the *subscription*), and it is additive: an
// older SaaS leaves the key out.
//
// The assertions read i18n KEYS, not sentences: the panel is mounted with an empty catalogue, so
// `t()` echoes the key back and the guard cannot go green on a reworded string (ADR-0055). The two
// tests at the bottom are the exception on purpose — they mount the real `en`/`es` catalogues,
// because "the plan name reaches the sentence, in both languages" is the actual requirement there.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Plugin } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/module-loader', () => ({ loadModuleLocale: vi.fn(async () => undefined) }));
vi.mock('../lib/device', () => ({ getDeviceContext: vi.fn(async () => ({ distribution: 'web' })) }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/saas-door', () => ({ saasDoor: vi.fn(async (p: string) => `https://erplora.com${p}`) }));
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1234', cloudApiUrl: 'https://erplora.com' } }));

const { cloudModuleSubscription } = vi.hoisted(() => ({
  cloudModuleSubscription: vi.fn(),
}));
vi.mock('../lib/cloud', () => ({ cloudModuleSubscription }));

import ModulePlanPanel from './ModulePlanPanel.vue';
import type { ModuleBilling } from '@erplora/module-types';

// The published `whatsapp_inbox` manifest: a free tier plus three paid ones. `quota` is an OBJECT
// in every real manifest and in `module.schema.json`, while `BillingTierDef` types it
// `number | string` — that contradiction is hub#1609, hence the cast (same as the sibling suites).
const WITH_FREE = {
  tiers: [
    { slug: 'free', name: 'WhatsApp Free', price: 0, interval: 'month' },
    { slug: 'starter', name: 'WhatsApp Starter', price: 14.99, interval: 'month' },
    { slug: 'business', name: 'WhatsApp Business', price: 59.99, interval: 'month' },
    { slug: 'flex', name: 'WhatsApp Flex', price: 19.99, interval: 'month', metered: true, overage_price: 0.08 },
  ],
} as unknown as ModuleBilling;

// A module sold the other way round: no tier at 0 €, so the way in is the 15-day trial. One of the
// two, never both — the rule Ioan set on 2026-09-07, guarded at publish time by
// ERPlora/module-toolkit#228. Nothing below may invent a free plan for this one.
const NO_FREE = {
  tiers: [
    { slug: 'starter', name: 'Starter', price: 14.99, interval: 'month' },
    { slug: 'pro', name: 'Pro', price: 29.99, interval: 'month' },
  ],
} as unknown as ModuleBilling;

type Sub = { status: string; trialEnd?: string | null; periodEnd?: string | null; tier?: string | null };

/** An empty catalogue, so `t()` echoes the key back and the assertions read codes, not prose. */
function emptyI18n() {
  return createI18n({ legacy: false, locale: 'es', missingWarn: false, fallbackWarn: false, messages: { es: {} } });
}

// The empty catalogue and the real one type differently (`createI18n` infers its locales from the
// messages it is given), and the panel only ever needs either as a plugin — hence the widening.
async function mountWith(sub: Sub, billing: ModuleBilling = WITH_FREE, i18n: object = emptyI18n()) {
  cloudModuleSubscription.mockResolvedValue({ trialEnd: null, periodEnd: null, tier: null, ...sub });
  const w = mount(ModulePlanPanel, {
    props: { moduleId: 'whatsapp_inbox', billing },
    global: { plugins: [i18n as Plugin] },
  });
  await flushPromises();
  return w;
}

/** The card marked as «yours», by tier name. `null` when the panel marks none. */
function featuredName(w: VueWrapper): string | null {
  const marked = w.findAll('ok-pricing-card').filter((c) => c.attributes('featured') !== undefined);
  expect(marked.length).toBeLessThanOrEqual(1);
  return marked.length ? (marked[0].attributes('name') ?? null) : null;
}

const pillLabel = (w: VueWrapper): string | undefined => w.find('ok-status-pill').attributes('label');
const pillTone = (w: VueWrapper): string | undefined => w.find('ok-status-pill').attributes('tone');
/** The sentence under the pill, read exactly — `expiredOnFree` starts with `expired`, so
 *  `toContain` could not tell the two apart and would go green on the wrong one. */
const hint = (w: VueWrapper): string => w.find('[data-testid="module-plan-hint"]').text();

beforeEach(() => {
  cloudModuleSubscription.mockReset();
});

describe('ModulePlanPanel — the free plan is a plan (hub#1652)', () => {
  it('says you are ACTIVE on the free tier when the Cloud reports no subscription', async () => {
    const w = await mountWith({ status: 'none', tier: 'free' });

    expect(pillTone(w)).toBe('success');
    expect(pillLabel(w)).toBe('modulePlan.status.active');
    expect(hint(w)).toBe('modulePlan.hint.free');
    // The sentence it replaces is the whole bug: it is the screen that explains your plan.
    expect(w.text()).not.toContain('modulePlan.status.none');
  });

  it('marks the free card as yours, and only that one', async () => {
    const w = await mountWith({ status: 'none', tier: 'free' });

    expect(featuredName(w)).toBe('WhatsApp Free');
    const badges = w.findAll('ok-pricing-card').map((c) => c.attributes('badge')).filter(Boolean);
    expect(badges).toEqual(['modulePlan.yourPlan']);
  });

  it('marks the tier the Cloud names when the plan is a paid one', async () => {
    const w = await mountWith({ status: 'active', tier: 'business', periodEnd: '2026-10-07T00:00:00Z' });

    expect(featuredName(w)).toBe('WhatsApp Business');
    expect(pillLabel(w)).toBe('modulePlan.status.active');
  });

  it('marks nothing when the Cloud names a tier this manifest does not have', async () => {
    // A slug the installed version does not know (module updated in the marketplace, hub still on
    // the older bundle). The manifest is what the cards come from, so marking a card by position
    // would put the badge on somebody else's plan. Better to mark none than to mark the wrong one.
    const w = await mountWith({ status: 'active', tier: 'enterprise' });

    expect(featuredName(w)).toBeNull();
  });

  it('still falls back to the free tier when the Cloud does not send `tier` at all', async () => {
    // Additive contract (ERPlora/saas#1921): a hub pointing at an older SaaS gets no key. The
    // manifest already says which tier costs nothing, so the floor is known without asking.
    const w = await mountWith({ status: 'none' });

    expect(featuredName(w)).toBe('WhatsApp Free');
    expect(pillLabel(w)).toBe('modulePlan.status.active');
  });

  it('keeps «no plan» for a module that ships no free tier', async () => {
    // The positive control for the guard above: without a tier at 0 € there is nothing to fall back
    // to, and inventing a free plan here would promise a module the customer cannot run.
    const w = await mountWith({ status: 'none', tier: null }, NO_FREE);

    expect(pillTone(w)).toBe('neutral');
    expect(pillLabel(w)).toBe('modulePlan.status.none');
    expect(hint(w)).toBe('modulePlan.hint.none');
    expect(featuredName(w)).toBeNull();
  });
});

describe('ModulePlanPanel — «trialing» only where there is a trial (hub#1652)', () => {
  it('never says «trialing» when the tier you are on is the free one', async () => {
    // ADR-0032: the no-card trial is the way in for modules WITHOUT a free tier. A module that has
    // one does not have a trial, so a trial state on its free tier is not a state of this product.
    const w = await mountWith({ status: 'trialing', tier: 'free', trialEnd: '2026-09-23T00:00:00Z' });

    expect(w.text()).not.toContain('modulePlan.status.trialing');
    expect(w.text()).not.toContain('modulePlan.trialEnds');
    expect(pillLabel(w)).toBe('modulePlan.status.active');
    expect(featuredName(w)).toBe('WhatsApp Free');
  });

  it('still says «trialing» for the module that is actually sold with a trial', async () => {
    const w = await mountWith({ status: 'trialing', tier: 'starter', trialEnd: '2026-09-23T00:00:00Z' }, NO_FREE);

    expect(pillLabel(w)).toBe('modulePlan.status.trialing');
    expect(pillTone(w)).toBe('success');
    expect(featuredName(w)).toBe('Starter');
  });
});

describe('ModulePlanPanel — expiring drops you to the free plan, not out (hub#1652)', () => {
  it('says you are still on the free tier and marks it', async () => {
    const w = await mountWith({ status: 'expired', tier: 'free' });

    // The status itself is not softened — the paid plan really did lapse, and hiding that is how a
    // customer misses a failed renewal. What changes is where it leaves you.
    expect(pillLabel(w)).toBe('modulePlan.status.expired');
    expect(pillTone(w)).toBe('danger');
    expect(hint(w)).toBe('modulePlan.hint.expiredOnFree');
    expect(featuredName(w)).toBe('WhatsApp Free');
  });

  it('keeps the plain «expired» sentence for a module with no free tier to fall to', async () => {
    const w = await mountWith({ status: 'expired', tier: null }, NO_FREE);

    expect(hint(w)).toBe('modulePlan.hint.expired');
    expect(featuredName(w)).toBeNull();
  });
});

describe('ModulePlanPanel — the free-plan sentence is translated, and names the plan', () => {
  for (const [lang, catalogue, sentence] of [
    ['en', en, 'You are on WhatsApp Free'],
    ['es', es, 'Estás en WhatsApp Free'],
  ] as const) {
    it(`names the tier in ${lang}`, async () => {
      const i18n = createI18n({ legacy: false, locale: lang, fallbackLocale: 'en', messages: { es, en } as never });
      const w = await mountWith({ status: 'none', tier: 'free' }, WITH_FREE, i18n);

      expect(w.text()).toContain(sentence);
      expect(w.find('ok-pricing-card').attributes('badge')).toBe(catalogue.modulePlan.yourPlan);
    });
  }
});
