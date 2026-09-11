// @vitest-environment happy-dom
// Lo que LEE el dueño cuando el asistente no puede atenderle — ERPlora/hub#1738.
//
// En PRE (banco-pre, 10/09) el turno muere así, en HTTP 200:
//   data: {"error":"No active credential for provider 'openai'","type":"error"}
// y la burbuja decía «No se pudo contactar con el asistente. Denunciar un problema». El servicio
// contestó: no hay nada que contactar, nada que reintentar en su router y nada que denunciar.
//
// Se monta el SFC de verdad (mismo criterio que assistant-plan-cta.test.ts): una aserción sobre
// el fichero no distingue «pintado» de «escrito en el template y nunca renderizado».
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonTextarea } from '@ionic/vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return { assistantOpen: ref(false), assistantIntent: ref(null), closeAssistant: vi.fn() };
});
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});
vi.mock('../lib/assistant-plan', () => ({
  assistantPlan: vi.fn(async () => null),
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
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]) };
});
vi.mock('vue-router', () => ({ useRouter: () => ({ getRoutes: () => [], push: vi.fn() }) }));

import AssistantDrawer from './AssistantDrawer.vue';
import { assistantOpen } from '../lib/shell';
import { streamAssistant, type AssistantFailure, type StreamCallbacks } from '../lib/assistant';
import { assistantMessages } from '../lib/assistant-history';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** Manda un turno que muere con `failure` y devuelve el drawer ya pintado. */
async function turnThatDiesWith(failure: AssistantFailure) {
  vi.mocked(streamAssistant).mockImplementation(((_msgs: unknown, cb: StreamCallbacks) => {
    cb.onError?.(failure);
    return () => {};
  }) as never);
  const wrapper = mount(AssistantDrawer, { global: { plugins: [i18n] } });
  (assistantOpen as unknown as { value: boolean }).value = true;
  await flushPromises();
  wrapper.findComponent(IonTextarea).vm.$emit('update:modelValue', '¿cuántos productos tengo?');
  await flushPromises();
  await wrapper.find(`ion-button[aria-label="${en.assistant.send}"]`).trigger('click');
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  (assistantOpen as unknown as { value: boolean }).value = false;
  assistantMessages.value = [];
});

describe('hub#1738 — el asistente que no puede atender lo dice sin mentir', () => {
  it('cuando el servicio contesta que no atiende, NO dice que no se pudo contactar', async () => {
    const wrapper = await turnThatDiesWith({
      message: "No active credential for provider 'openai'",
      reason: 'service',
    });

    expect(
      wrapper.text(),
      'erplora.com contestó: mandar al dueño a revisar su conexión le hace perder el rato en algo que no está roto',
    ).not.toContain(en.assistant.error);
    expect(wrapper.text()).toContain(en.assistant.unavailable);
  });

  // El control del control: sin esta mitad, sustituir SIEMPRE el texto de conexión pasaría el
  // test de arriba — y el día que el TPV se quede sin red diría que el servicio está caído.
  it('cuando de verdad no se alcanza a erplora.com, sigue diciendo que no se pudo contactar', async () => {
    const wrapper = await turnThatDiesWith({
      message: 'cloud_unreachable',
      reason: 'unreachable',
    });

    expect(wrapper.text()).toContain(en.assistant.error);
    expect(wrapper.text()).not.toContain(en.assistant.unavailable);
  });

  it('el aviso está traducido al español (ADR-0055/0199)', () => {
    expect(es.assistant.unavailable).toBeTruthy();
    expect(es.assistant.unavailable).not.toBe(en.assistant.unavailable);
  });
});
