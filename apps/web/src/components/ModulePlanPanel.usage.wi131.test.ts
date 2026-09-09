// @vitest-environment happy-dom
// The «Plan» tab has to say how much of the plan is already SPENT — ERPlora/whatsapp_inbox#131.
//
// The panel painted the four tiers and what each one includes, and nowhere what this hub had used.
// On a metered channel that is the number that matters: a salon on 30 conversations a month found
// out it had run out because WhatsApp stopped answering. ADR-0470 moved the counter out of the
// module's settings screen and named this tab as its home — «contadores (pestaña Plan del shell)» —
// and this is the guard that it actually arrives.
//
// The reading itself is pinned in `lib/module-usage.test.ts`. What is guarded HERE is the wiring:
// that the declared query is the one called, that the number reaches the screen in the hub's
// language, that a module which declares no `billing.usage` is not queried at all, and that a
// refusal or an outage takes the block away instead of painting a wrong number.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const { cloudModuleSubscription } = vi.hoisted(() => ({
  cloudModuleSubscription: vi.fn(async () => ({ status: 'none', tier: 'free' })),
}));
vi.mock('../lib/cloud', () => ({ cloudModuleSubscription }));

const { loadModuleLocale } = vi.hoisted(() => ({
  loadModuleLocale: vi.fn(async (_base: string, _lang: string): Promise<unknown> => undefined),
}));
vi.mock('../lib/module-loader', () => ({ loadModuleLocale }));

const { query } = vi.hoisted(() => ({ query: vi.fn(async (_name: string): Promise<unknown> => []) }));
vi.mock('../lib/runtime', () => ({ getClient: () => ({ query }) }));

import ModulePlanPanel from './ModulePlanPanel.vue';
import type { ModuleBilling } from '@erplora/module-types';

/** The published `whatsapp_inbox` manifest after wi#139 + the `usage` block wi#131 adds. */
const BILLING = {
  tiers: [
    { slug: 'free', name: 'Free', price: 0, interval: 'month', quota: { conversations_per_month: 30 } },
    { slug: 'basic', name: 'Basic', price: 0, interval: 'month', quota: { conversations_per_month: 150 } },
  ],
  usage: {
    query: 'whatsapp_inbox.usage.get',
    metric: 'conversations_per_month',
    used: 'inbound_this_month',
    limit: 'monthly_limit',
  },
} as unknown as ModuleBilling;

/** The same manifest with the block taken out — every module published before wi#131. */
const BILLING_WITHOUT_USAGE = { tiers: BILLING.tiers } as unknown as ModuleBilling;

/** Markup plus the string lists the panel hands to child components as DOM properties. */
function visibleText(w: VueWrapper): string {
  const fromProps = w
    .findAll('*')
    .map((el) => (el.element as unknown as { features?: unknown }).features)
    .filter((v): v is unknown[] => Array.isArray(v))
    .flat()
    .join(' ');
  return `${w.text()} ${fromProps}`;
}

async function mountPanel(locale: 'es' | 'en', billing: ModuleBilling = BILLING) {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { es, en } as never });
  const w = mount(ModulePlanPanel, {
    props: { moduleId: 'whatsapp_inbox', billing },
    global: { plugins: [i18n] },
  });
  await flushPromises();
  await flushPromises();
  return w;
}

beforeEach(() => {
  loadModuleLocale.mockReset();
  loadModuleLocale.mockResolvedValue(undefined);
  cloudModuleSubscription.mockReset();
  cloudModuleSubscription.mockResolvedValue({ status: 'none', tier: 'free' } as never);
  query.mockReset();
  query.mockResolvedValue([{ inbound_this_month: 24, monthly_limit: 30 }]);
});

describe('ModulePlanPanel — what you have already spent (whatsapp_inbox#131)', () => {
  it('calls the query the manifest declares, and nothing else', async () => {
    await mountPanel('es');
    expect(query).toHaveBeenCalledWith('whatsapp_inbox.usage.get');
  });

  it('puts both numbers on the screen, with the metric named in the language of the hub', async () => {
    loadModuleLocale.mockResolvedValue({
      billing: { quota: { conversations_per_month: 'conversaciones al mes' } },
    });
    const w = await mountPanel('es');
    const text = visibleText(w);
    expect(text).toContain('24');
    expect(text).toContain('30');
    expect(text).toContain('conversaciones al mes');
    // The counter, not the allowance line of a tier: it says WHICH of the two numbers is spent.
    expect(text).toContain('Este mes');
  });

  it('falls back to the English of the metric when the module ships no translation', async () => {
    const w = await mountPanel('en');
    expect(visibleText(w)).toContain('conversations per month');
  });

  it('warns when the allowance is nearly gone', async () => {
    // 25 of 30 = 83 %: the amber band is 80–90 %, and 90 % is already the red one.
    query.mockResolvedValue([{ inbound_this_month: 25, monthly_limit: 30 }]);
    const w = await mountPanel('es');
    expect(w.find('[data-testid="module-usage"]').attributes('data-tone')).toBe('warning');
    expect(visibleText(w)).toContain(es.modulePlan.usageNearLimit);
  });

  it('says it out loud once the allowance is gone — this is when the channel goes quiet', async () => {
    query.mockResolvedValue([{ inbound_this_month: 30, monthly_limit: 30 }]);
    const w = await mountPanel('es');
    expect(w.find('[data-testid="module-usage"]').attributes('data-tone')).toBe('danger');
    expect(visibleText(w)).toContain(es.modulePlan.usageOverLimit);
  });

  it('stays calm well below the allowance', async () => {
    // 12 of 30 = 40 %. The 24 of the other cases is exactly 80 %, which is already amber.
    query.mockResolvedValue([{ inbound_this_month: 12, monthly_limit: 30 }]);
    const w = await mountPanel('es');
    expect(w.find('[data-testid="module-usage"]').attributes('data-tone')).toBe('success');
    expect(visibleText(w)).not.toContain(es.modulePlan.usageNearLimit);
    expect(visibleText(w)).not.toContain(es.modulePlan.usageOverLimit);
  });

  it('does not query, and paints no counter, for a module that declares no usage', async () => {
    const w = await mountPanel('es', BILLING_WITHOUT_USAGE);
    expect(query).not.toHaveBeenCalled();
    expect(w.find('[data-testid="module-usage"]').exists()).toBe(false);
  });

  it('paints no counter when the person is not allowed to read it', async () => {
    // `usage.get` is gated by the module's own permission; a cashier gets a refusal, and a refusal
    // is not a failure to announce — it is a block that is not theirs.
    query.mockRejectedValue(Object.assign(new Error('nope'), { code: 'permission_denied' }));
    const w = await mountPanel('es');
    expect(w.find('[data-testid="module-usage"]').exists()).toBe(false);
    expect(visibleText(w)).not.toContain(es.modulePlan.usageUnavailable);
  });

  it('says the counter could not be read when the runtime fails — never a made-up number', async () => {
    query.mockRejectedValue(new Error('boom'));
    const w = await mountPanel('es');
    expect(visibleText(w)).toContain(es.modulePlan.usageUnavailable);
    expect(w.find('[data-testid="module-usage-bar"]').exists()).toBe(false);
  });

  it('paints no counter when the query answers a row it cannot read', async () => {
    query.mockResolvedValue([{ monthly_limit: 30 }]);
    const w = await mountPanel('es');
    expect(w.find('[data-testid="module-usage"]').exists()).toBe(false);
  });

  it('falls back to the allowance of your tier when the module names no limit column', async () => {
    // A module that only exposes a counter still gets a bar: the only allowance anybody knows is
    // the one the tier promises. `currentTier` is `free` here (the Cloud answered that slug), so
    // the ceiling is its 30 — not the 150 of `basic`.
    const noLimitColumn = {
      tiers: BILLING.tiers,
      usage: { query: 'whatsapp_inbox.usage.get', metric: 'conversations_per_month', used: 'inbound_this_month' },
    } as unknown as ModuleBilling;
    query.mockResolvedValue([{ inbound_this_month: 24, monthly_limit: 999 }]);
    const w = await mountPanel('en', noLimitColumn);
    expect(w.find('[data-testid="module-usage-bar"]').exists()).toBe(true);
    const text = visibleText(w);
    expect(text).toContain('24 of 30');
    expect(text).not.toContain('999');
  });

  it('shows the count with no bar when the plan has no cap', async () => {
    query.mockResolvedValue([{ inbound_this_month: 24, monthly_limit: 0 }]);
    const w = await mountPanel('es');
    expect(visibleText(w)).toContain('24');
    expect(w.find('[data-testid="module-usage-bar"]').exists()).toBe(false);
  });

  it('ships every new string in English AND in Spanish (ADR-0055/0199)', () => {
    const keys = ['usageTitle', 'usageOfLimit', 'usageNoLimit', 'usageNearLimit', 'usageOverLimit', 'usageUnavailable'] as const;
    for (const key of keys) {
      expect(en.modulePlan[key], `en.modulePlan.${key}`).toBeTruthy();
      expect(es.modulePlan[key], `es.modulePlan.${key}`).toBeTruthy();
    }
    // Only the ones that carry WORDS have to differ. `usageOfLimit`/`usageNoLimit` are pure
    // placeholders («{used} de {limit} {metric}»), and demanding a different Spanish for a string
    // with no prose in it is asking for a translation of nothing.
    for (const key of ['usageTitle', 'usageNearLimit', 'usageOverLimit', 'usageUnavailable'] as const) {
      expect(es.modulePlan[key], `es.modulePlan.${key} is still English`).not.toBe(en.modulePlan[key]);
    }
  });
});
