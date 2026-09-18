// @vitest-environment happy-dom
// El plan del asistente, en la pantalla — ERPlora/hub#1183 y ERPlora/hub#1259.
//
// hub#1183: el hub sabía leer su plan (`assistantPlan()`) y no lo llamaba NUNCA desde producción,
// así que solo descubría su límite al agotarlo — el dueño se enteraba en el peor momento posible.
// Y el botón se llamaba «ver planes» sin enseñar ninguno: iba derecho al checkout de `basic`, con
// lo que un hub que necesita `pro` compraba el más barato, lo agotaba igual y volvía.
//
// hub#1259: ese mismo botón se le pintaba al CAJERO, que desde hub#1254 solo puede recibir un 403
// y un toast genérico. El peor de los tres finales: peor que no ver el botón, y peor que leer a
// quién pedírselo.
//
// Se monta el SFC de verdad (no se lee su fuente): lo que hay que probar es que el aviso APARECE
// y que el control DESAPARECE según el rol, y una aserción sobre el texto del fichero no distingue
// «pintado» de «escrito en el template pero nunca renderizado».
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { alertController, IonTextarea } from '@ionic/vue';

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
// Who handed out this copy (hub#1910). `null` is the browser — no store governs it.
vi.mock('../lib/device', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getDeviceContext: vi.fn(async () => null),
  isTauri: vi.fn(() => false),
}));
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

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

const PAID_TIERS = [
  { slug: 'basic', name: 'Basic', priceMonthly: '11.99' },
  { slug: 'pro', name: 'Pro', priceMonthly: '44.99' },
];

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

describe('hub#1183 — el hub conoce su plan ANTES de agotarlo', () => {
  it('lee el plan al abrir el drawer, en vez de esperar a quedarse sin mensajes', async () => {
    await openWith({ tier: 'free', used: 4, limit: 30, paidTiers: PAID_TIERS });

    expect(vi.mocked(assistantPlan)).toHaveBeenCalled();
  });

  it('a partir del 80 % avisa de cuántos mensajes quedan y con qué plan', async () => {
    const wrapper = await openWith({
      tier: 'free',
      used: 25,
      limit: 30,
      resetsAt: '2026-09-01T00:00:00+00:00',
      paidTiers: PAID_TIERS,
    });

    const warn = wrapper.find('[data-testid="assistant-quota-warning"]');
    expect(warn.exists(), 'sin el aviso el dueño se entera del límite cuando ya no puede preguntar').toBe(true);
    expect(warn.text()).toContain('5'); // 30 − 25 mensajes restantes
    expect(warn.text()).toContain('free');
  });

  // El control del control: por debajo del umbral NO se pinta nada. Sin esta mitad, un aviso
  // permanente pasaría los tests de arriba y sería ruido en la pantalla todo el mes.
  it('por debajo del 80 % no interrumpe con nada', async () => {
    const wrapper = await openWith({ tier: 'free', used: 4, limit: 30, paidTiers: PAID_TIERS });

    expect(wrapper.find('[data-testid="assistant-quota-warning"]').exists()).toBe(false);
  });

  it('el contador se mueve con el frame `usage` del turno, sin recargar', async () => {
    const wrapper = await openWith({ tier: 'free', used: 4, limit: 30, paidTiers: PAID_TIERS });
    expect(wrapper.find('[data-testid="assistant-quota-warning"]').exists()).toBe(false);

    vi.mocked(streamAssistant).mockImplementation(((_msgs: unknown, cb: StreamCallbacks) => {
      cb.onUsage?.({ tier: 'free', messagesUsed: 27, messagesLimit: 30 });
      cb.onDone?.();
      return () => {};
    }) as never);
    wrapper.findComponent(IonTextarea).vm.$emit('update:modelValue', 'hola');
    await flushPromises();
    await wrapper.find(`ion-button[aria-label="${en.assistant.send}"]`).trigger('click');
    await flushPromises();

    const warn = wrapper.find('[data-testid="assistant-quota-warning"]');
    expect(warn.exists(), 'el frame POST-turno es el único contador que no va un mensaje por detrás').toBe(true);
    expect(warn.text()).toContain('3');
  });
});

describe('hub#1183 — el CTA ofrece los tiers que da el SaaS, no `basic` a ciegas', () => {
  it('deja elegir entre los planes contratables y compra el ELEGIDO', async () => {
    const created = vi.spyOn(alertController, 'create').mockResolvedValue({
      present: vi.fn(async () => {}),
      onDidDismiss: vi.fn(async () => ({ role: 'confirm', data: { values: 'pro' } })),
    } as never);
    const assign = vi.fn();
    Object.defineProperty(window, 'location', { value: { assign }, writable: true });

    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    await wrapper.find('[data-testid="assistant-quota-cta"]').trigger('click');
    await flushPromises();

    const inputs = (created.mock.calls[0][0] as { inputs?: { value?: string }[] }).inputs ?? [];
    expect(inputs.map((i) => i.value)).toEqual(['basic', 'pro']);
    expect(vi.mocked(startAssistantCheckout)).toHaveBeenCalledWith('pro');
    expect(assign).toHaveBeenCalledWith('https://checkout.stripe.com/c/pay/cs_x');
  });

  it('sin planes que ofrecer no manda a ninguna parte: lo dice', async () => {
    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: [] });
    await sendATurnThatRunsOutOfQuota(wrapper);

    await wrapper.find('[data-testid="assistant-quota-cta"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(startAssistantCheckout)).not.toHaveBeenCalled();
    expect(vi.mocked(toastError)).toHaveBeenCalled();
  });

  // Dos cifras que se contradicen en la misma pantalla valen menos que ninguna: si el pie
  // siguiera diciendo «te quedan 5» debajo de «has gastado 30 de 30», el número deja de creerse.
  it('al agotarse, el pie deja de prometer mensajes que ya no hay', async () => {
    const wrapper = await openWith({
      tier: 'free',
      used: 25,
      limit: 30,
      resetsAt: '2026-09-01T00:00:00+00:00',
      paidTiers: PAID_TIERS,
    });
    expect(wrapper.find('[data-testid="assistant-quota-warning"]').exists()).toBe(true);

    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-quota-warning"]').exists()).toBe(false);
  });

  it('el texto de cuota agotada dice cuándo vuelven los mensajes', async () => {
    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    // «has gastado 30 de 30» sin horizonte no deja decidir entre esperar y pagar.
    expect(wrapper.text()).toContain('September');
  });
});

describe('hub#1259 — el CTA es de quien puede pagarlo', () => {
  it('el owner/admin ve el botón', async () => {
    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-quota-ask-admin"]').exists()).toBe(false);
  });

  it('el cajero no ve un botón que solo le puede fallar: lee a quién pedírselo', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;

    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(
      wrapper.find('[data-testid="assistant-quota-cta"]').exists(),
      'desde hub#1254 el checkout es puerta de admin: pintarlo al cajero solo produce un 403',
    ).toBe(false);
    const ask = wrapper.find('[data-testid="assistant-quota-ask-admin"]');
    expect(ask.exists()).toBe(true);
    expect(ask.text().length).toBeGreaterThan(0);
  });
});

// hub#1910 — the assistant was the one door to money that never asked who distributed the copy:
// on the Google Play build an admin who ran out of messages got «See plans», and pressing it sent
// the webview itself to a card checkout. Google does not let a Play app lead to paying outside Play,
// so there the drawer does what the plan-limits panel and a paid module's screen already do: it
// NAMES erplora.com and opens nothing (hub#479, hub#756). The cut is the distribution, not the OS —
// a sideloaded APK runs on the same Android and Google does not govern it.
describe('hub#1910 — en la copia de Google Play el asistente no lleva a pagar', () => {
  const copyFrom = (distribution: 'play' | 'direct') =>
    vi.mocked(getDeviceContext).mockResolvedValue({
      id: 'dev-1',
      clientType: 'tauri',
      platform: 'android',
      distribution,
    } as never);

  it('al admin le dice dónde se amplía el plan, sin botón al checkout', async () => {
    copyFrom('play');
    const assign = vi.fn();
    Object.defineProperty(window, 'location', { value: { assign }, writable: true });

    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(false);
    const where = wrapper.find('[data-testid="assistant-quota-managed-in-account"]');
    expect(where.exists(), 'sin la frase, en Play el límite sería un callejón sin decir dónde se amplía').toBe(true);
    expect(where.find('a').exists(), 'se NOMBRA erplora.com, no se enlaza').toBe(false);
    expect(vi.mocked(startAssistantCheckout)).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });

  it('dentro de la app, mientras el shell no ha dicho qué copia es, no ofrece el checkout', async () => {
    // Offering by default would paint the button on a Play copy and take it away a moment later —
    // the same defect, with a jump on top. The browser is known from the first frame; the app is not.
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(getDeviceContext).mockReturnValue(new Promise(() => {}));

    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(false);
  });

  it('un APK instalado de lado conserva el botón: Google no lo gobierna', async () => {
    copyFrom('direct');

    const wrapper = await openWith({ tier: 'free', used: 30, limit: 30, paidTiers: PAID_TIERS });
    await sendATurnThatRunsOutOfQuota(wrapper);

    expect(wrapper.find('[data-testid="assistant-quota-cta"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-quota-managed-in-account"]').exists()).toBe(false);
  });
});

describe('las cadenas nuevas viajan por i18n, inglés fuente + su es (ADR-0055/0199)', () => {
  it('cada clave existe en en y en es, y no son la misma frase', () => {
    for (const key of [
      'quotaRemaining',
      'quotaResets',
      'quotaAskAdmin',
      'plansTitle',
      'plansConfirm',
      'planOption',
      'plansUnavailable',
      'quotaManagedInAccount',
    ] as const) {
      expect(en.assistant[key], `${key} falta en en.ts`).toBeTruthy();
      expect(es.assistant[key], `${key} falta en es.ts`).toBeTruthy();
      expect(en.assistant[key], `${key} sin traducir`).not.toBe(es.assistant[key]);
    }
  });
});
