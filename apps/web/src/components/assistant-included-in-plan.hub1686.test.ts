// @vitest-environment happy-dom
// The assistant level comes with the hub plan — hub#1686 (ADR-0474, ERPlora/saas#1952).
//
// When the SaaS says `source: "plan"`, the assistant is not sold separately any more: the drawer
// says the level is «Included in your Standard plan» and the way to more messages is a bigger HUB
// plan, on the account page (the same door as the side menu), never the assistant checkout.
// Without `source` (older SaaS) the drawer keeps today's checkout — that is the control case.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonTextarea } from '@ionic/vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return {
    assistantOpen: ref(false),
    assistantIntent: ref(null),
    closeAssistant: vi.fn(),
  };
});

// Real `ref`: a plain stand-in would not unwrap in the template and `v-if="isAdmin"` would be
// truthy forever — the guard would look wired while gating nothing.
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});

vi.mock('../lib/assistant-plan', () => ({
  assistantPlan: vi.fn(),
  startAssistantCheckout: vi.fn(),
}));

vi.mock('../lib/assistant', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  streamAssistant: vi.fn(() => () => {}),
}));

vi.mock('../lib/runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getClient: () => ({ query: vi.fn(async () => []), command: vi.fn(async () => ({})) }),
}));

vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
// The one door out of the till (hub#475). Mocked so the tests see WHERE the checkout was sent.
vi.mock('../lib/open-external', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  openExternal: vi.fn(async () => {}),
}));
// Who handed out this copy (hub#1910). `null` is the browser — no store governs it.
vi.mock('../lib/device', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getDeviceContext: vi.fn(async () => null),
  isTauri: vi.fn(() => false),
}));
vi.mock('../lib/saas-door', () => ({ saasDoor: vi.fn(async (p: string) => `https://erplora.com${p}`) }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
// `lib/nav` → `lib/module-loader` → `~icons/…?raw`, which the test environment denies (same
// reason SetupChecklistCard.test.ts stubs HubIcon). The drawer only reads the module paths.
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]) };
});
vi.mock('vue-router', () => ({ useRouter: () => ({ getRoutes: () => [], push: vi.fn() }) }));

import AssistantDrawer from './AssistantDrawer.vue';
import { assistantOpen } from '../lib/shell';
import { isAdmin } from '../lib/session';
import { assistantPlan, startAssistantCheckout } from '../lib/assistant-plan';
import { streamAssistant, type StreamCallbacks } from '../lib/assistant';
import { assistantMessages } from '../lib/assistant-history';
import { toastError } from '../lib/toast';
import { getDeviceContext, isTauri } from '../lib/device';
import { openExternal, OpenExternalError } from '../lib/open-external';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

// A drawer left mounted keeps its window listeners and would answer another test's `focus` (hub#1914).
enableAutoUnmount(afterEach);

function mountDrawer() {
  return mount(AssistantDrawer, { global: { plugins: [i18n] } });
}

/** Abre el drawer y deja que lea su plan. */
async function openWith(plan: unknown) {
  vi.mocked(assistantPlan).mockResolvedValue(plan as never);
  const wrapper = mountDrawer();
  (assistantOpen as unknown as { value: boolean }).value = true;
  await flushPromises();
  return wrapper;
}

/** Manda un turno cuyo stream muere por cuota agotada, y devuelve el drawer ya con el CTA. */
async function sendATurnThatRunsOutOfQuota(wrapper: ReturnType<typeof mountDrawer>) {
  vi.mocked(streamAssistant).mockImplementation(((_msgs: unknown, cb: StreamCallbacks) => {
    cb.onError?.({
      message: 'Monthly message quota exhausted',
      quota: {
        limit: 30,
        used: 30,
        tier: 'free',
        kind: 'messages',
        upgradeRequired: true,
        resetsAt: '2026-09-01T00:00:00+00:00',
      },
    });
    return () => {};
  }) as never);
  wrapper.findComponent(IonTextarea).vm.$emit('update:modelValue', '¿cuánto he vendido?');
  await flushPromises();
  await wrapper.find(`ion-button[aria-label="${en.assistant.send}"]`).trigger('click');
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  (isAdmin as unknown as { value: boolean }).value = true;
  (assistantOpen as unknown as { value: boolean }).value = false;
  assistantMessages.value = [];
  vi.mocked(streamAssistant).mockImplementation((() => () => {}) as never);
  vi.mocked(startAssistantCheckout).mockResolvedValue('https://checkout.stripe.com/c/pay/cs_x');
  vi.mocked(getDeviceContext).mockResolvedValue(null);
  vi.mocked(isTauri).mockReturnValue(false);
});

const BY_PLAN = { tier: 'basic', used: 10, limit: 300, paidTiers: [], source: 'plan', planName: 'Standard' };

describe('hub#1686 — the assistant level comes with the hub plan', () => {
  it('says the level is included in the named plan, and offers upgrading the HUB plan', async () => {
    const wrapper = await openWith(BY_PLAN);
    await sendATurnThatRunsOutOfQuota(wrapper);

    const included = wrapper.find('[data-testid="assistant-included-in-plan"]');
    expect(included.exists()).toBe(true);
    expect(included.text()).toContain(en.assistant.includedInPlan.replace('{plan}', 'Standard'));
    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(false);

    const upgrade = wrapper.find('[data-testid="assistant-upgrade-hub-plan"]');
    expect(upgrade.exists()).toBe(true);
    await upgrade.trigger('click');
    await flushPromises();

    expect(vi.mocked(startAssistantCheckout)).not.toHaveBeenCalled();
    const opened = String(vi.mocked(openExternal).mock.calls[0]?.[0]);
    expect(opened).toContain('/change-plan/');
    expect(opened).not.toContain('checkout.stripe.com');
  });

  it('says the plan page could not be opened, not the payment page, when the door fails', async () => {
    const wrapper = await openWith(BY_PLAN);
    await sendATurnThatRunsOutOfQuota(wrapper);
    vi.mocked(openExternal).mockRejectedValueOnce(new OpenExternalError('https://erplora.com/x'));

    await wrapper.find('[data-testid="assistant-upgrade-hub-plan"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(toastError)).toHaveBeenCalledWith(en.assistant.planOpenFailed);
  });

  it('keeps knowing the level comes from the plan after a turn refreshes the counters', async () => {
    // `applyUsage` rebuilds the plan from the frame that closes every turn; dropping `source` there
    // would put the assistant checkout back one message later.
    const wrapper = await openWith(BY_PLAN);
    vi.mocked(streamAssistant).mockImplementation(((_m: unknown, cb: StreamCallbacks) => {
      cb.onUsage?.({ tier: 'basic', messagesUsed: 300, messagesLimit: 300 });
      cb.onError?.({
        message: 'Monthly message quota exhausted',
        quota: { limit: 300, used: 300, tier: 'basic', kind: 'messages', upgradeRequired: true },
      });
      return () => {};
    }) as never);
    wrapper.findComponent(IonTextarea).vm.$emit('update:modelValue', 'hola');
    await flushPromises();
    await wrapper.find(`ion-button[aria-label="${en.assistant.send}"]`).trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="assistant-upgrade-hub-plan"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(false);
  });

  it('names the plan in the 80 % warning', async () => {
    const wrapper = await openWith({ ...BY_PLAN, used: 250 });

    const warn = wrapper.find('[data-testid="assistant-quota-warning"]');
    expect(warn.text()).toContain(en.assistant.includedInPlan.replace('{plan}', 'Standard'));
  });

  it('says «included in your plan» when the plan name does not arrive', async () => {
    const wrapper = await openWith({ ...BY_PLAN, planName: null });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-included-in-plan"]').text()).toContain(
      en.assistant.includedInHubPlan,
    );
  });

  it('hides the upgrade on the Play build (hub#756/#1910)', async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(getDeviceContext).mockResolvedValue({ distribution: 'play' } as never);
    const wrapper = await openWith(BY_PLAN);
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-upgrade-hub-plan"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="assistant-quota-managed-in-account"]').exists()).toBe(true);
  });

  it('shows the cashier who to ask, not the upgrade', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;
    const wrapper = await openWith(BY_PLAN);
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-upgrade-hub-plan"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="assistant-quota-ask-admin"]').exists()).toBe(true);
  });

  it('keeps today\'s assistant checkout when the SaaS does not say the plan gives the level', async () => {
    const wrapper = await openWith({ ...BY_PLAN, source: null, planName: null, paidTiers: [{ slug: 'pro', name: 'Pro' }] });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-included-in-plan"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="assistant-upgrade-hub-plan"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(true);
  });
});

describe('hub#1686 — the sentence exists in both languages', () => {
  it('has en and es', () => {
    expect(en.assistant.includedInPlan).toContain('{plan}');
    expect(es.assistant.includedInPlan).toContain('{plan}');
    expect(es.assistant.includedInHubPlan).toBeTruthy();
    expect(es.assistant.upgradeHubPlan).toBeTruthy();
    expect(es.assistant.includedInPlan).not.toBe(en.assistant.includedInPlan);
  });
});
