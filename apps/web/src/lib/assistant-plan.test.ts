// El hub sabe SU PLAN, y el «ver planes» lleva a algún sitio (saas#1540).
//
// El asistente solo descubría su tier cuando ya lo había agotado: el hub nunca leía
// `assistant/config/`. Y sin camino al checkout, decir «ver planes» era una frase sin salida — el
// único momento de conversión del tier gratuito moría ahí.
//
// Las dos llamadas van por el RUNTIME, no desde el navegador: la credencial hub-scoped es secreto
// del runtime (ADR-0003) y el web app no tiene con qué firmarlas.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));

vi.mock('./runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  RUNTIME_URL: '',
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
}));

import { assistantPlan, startAssistantCheckout } from './assistant-plan';

describe('assistantPlan — leer el plan', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('lo pide al RUNTIME, no al SaaS: el navegador no firma nada', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ tier: 'free', usage: { messages_used: 12, messages_limit: 30 } }),
    });

    const plan = await assistantPlan();

    expect(fetchMock.mock.calls[0][0]).toContain('/api/assistant/config');
    expect(plan?.tier).toBe('free');
    expect(plan?.used).toBe(12);
    expect(plan?.limit).toBe(30);
  });

  // Si no se puede leer, se devuelve null y la UI se calla. Inventar un plan sería peor que no
  // enseñarlo: el consumo es un número que el dueño usa para decidir si paga.
  it('si no se puede leer, no se inventa', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, json: async () => ({}) });

    expect(await assistantPlan()).toBeNull();
  });
});

describe('startAssistantCheckout — que el botón lleve a algún sitio', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('devuelve la url de Stripe que abre el pago', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ checkout_url: 'https://checkout.stripe.com/c/pay/cs_test_x' }),
    });

    const url = await startAssistantCheckout('basic');

    expect(fetchMock.mock.calls[0][0]).toContain('/api/assistant/checkout');
    expect(url).toContain('checkout.stripe.com');
  });

  it('sin url no se navega a ninguna parte', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });

    expect(await startAssistantCheckout('basic')).toBeNull();
  });
});
