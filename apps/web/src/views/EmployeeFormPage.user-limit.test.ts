// @vitest-environment happy-dom
// hub#1685 — el hub Gratis cubre tres personas y la cuarta se creaba sin decir nada.
//
// El runtime ya la rechaza (`hub.users.user_limit_reached`, 409). Lo que se prueba aquí es la otra
// mitad: que quien está delante del formulario ENTIENDE el rechazo en su idioma y tiene a mano la
// salida — su plan, en la cuenta de ERPlora.
//
// La puerta es la receta permitida (`lib/upgrade-plan-link`): etiqueta neutra y destino la página
// de plan de ESTE hub, nunca el marketplace. En una copia repartida por Play NO se ofrece
// (hub#756): la frase sigue saliendo, el botón no.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

const { replace, push } = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ replace, push }),
  onBeforeRouteLeave: () => {},
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../lib/toast', () => ({ toast: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/badge-scanner', () => ({ onBadgeScan: () => () => {} }));
vi.mock('../lib/nfc-badge', () => ({ nfcBadgeReady: { value: false } }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

// El reparto REAL que manda el shell (`lib/device`): un navegador no manda ninguno, y es el caso
// por defecto de aquí — «sin señal se ofrece», que es lo que dice `planUpgradeIsOfferable`.
const { openExternal, saasDoor, getDeviceContext } = vi.hoisted(() => ({
  openExternal: vi.fn(async (_url: string): Promise<void> => {}),
  saasDoor: vi.fn(async (_path: string, url: string) => `${url}&pass=one-shot`),
  getDeviceContext: vi.fn(
    async (): Promise<{ distribution?: 'play' | 'msstore' | 'direct' }> => ({}),
  ),
}));
vi.mock('../lib/open-external', () => ({ openExternal }));
vi.mock('../lib/saas-door', () => ({ saasDoor }));
vi.mock('../lib/device', () => ({ getDeviceContext }));

import EmployeeFormPage from './EmployeeFormPage.vue';

/** La frase EXACTA en inglés que manda el runtime y que un hub en español no debe enseñar. */
const ENGLISH_FROM_THE_RUNTIME = 'the plan does not cover another user';

/** Censo y catálogo vacíos; el alta rechaza con el tope de plazas del plan. */
function runtimeRefusingTheSeat(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return {
          ok: false,
          status: 409,
          json: async () => ({
            ok: false,
            error: { code: 'hub.users.user_limit_reached', message: ENGLISH_FROM_THE_RUNTIME },
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: [] }) };
    }),
  );
}

async function mountFormAndSave(locale: 'es' | 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'es',
    messages: { es, en },
  });
  const wrapper = mount(EmployeeFormPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  }) as unknown as ReturnType<typeof mount> & {
    vm: { form: Record<string, unknown>; onSave: () => Promise<void> };
  };
  await flushPromises();
  Object.assign(wrapper.vm.form, {
    name: 'Marta Ruiz',
    role: 'employee',
    local: false,
    email: 'marta@example.com',
  });
  await wrapper.vm.onSave();
  await flushPromises();
  return wrapper;
}

/** El botón «Actualizar plan», o `undefined` si esta copia no lo ofrece. */
function planButton(wrapper: Awaited<ReturnType<typeof mountFormAndSave>>, label: string) {
  return wrapper.findAllComponents(IonButton).find((b) => b.text().includes(label));
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  getDeviceContext.mockResolvedValue({});
});

describe('El tope de usuarios del plan se explica y ofrece su salida (hub#1685)', () => {
  // 🔴 El bug, por el lado de la pantalla: la cuarta alta se rechazaba con la línea inglesa del
  // runtime, que no dice ni qué pasó ni qué hacer.
  it('en un hub en español lo explica en español, no con la frase del runtime', async () => {
    runtimeRefusingTheSeat();
    const form = await mountFormAndSave('es');

    expect(form.text()).not.toContain(ENGLISH_FROM_THE_RUNTIME);
    expect(form.text()).toContain(es.employeeForm.errors.user_limit_reached);
  });

  // La otra mitad de la cadena `en` + `es` (ADR-0055): el inglés es el idioma FUENTE, así que
  // tiene que existir como cadena propia, no como hueco que cae al español.
  it('en un hub en inglés lo explica en inglés', async () => {
    runtimeRefusingTheSeat();
    const form = await mountFormAndSave('en');

    expect(form.text()).toContain(en.employeeForm.errors.user_limit_reached);
    expect(form.text()).not.toContain(es.employeeForm.errors.user_limit_reached);
  });

  it('ofrece la salida a gestionar el plan y cruza por la puerta de un solo uso', async () => {
    runtimeRefusingTheSeat();
    const form = await mountFormAndSave('es');

    const button = planButton(form, es.nav.upgradePlan);
    expect(button, 'falta el botón de plan junto al aviso').toBeTruthy();

    await button!.trigger('click');
    await flushPromises();

    // pm#196 — el pase de un solo uso, igual que en el menú: dentro de la app instalada el
    // navegador del sistema no comparte cookies con el webview.
    expect(saasDoor).toHaveBeenCalledOnce();
    expect(openExternal).toHaveBeenCalledOnce();
    const destination = openExternal.mock.calls[0]![0];
    expect(destination).toContain('/change-plan/');
  });

  it('en una copia repartida por Play explica igual pero NO ofrece el botón (hub#756)', async () => {
    getDeviceContext.mockResolvedValue({ distribution: 'play' });
    runtimeRefusingTheSeat();
    const form = await mountFormAndSave('es');

    expect(form.text()).toContain(es.employeeForm.errors.user_limit_reached);
    expect(planButton(form, es.nav.upgradePlan)).toBeFalsy();
  });

  it('un rechazo que NO es el tope de plazas no arrastra el botón de plan', async () => {
    // La puerta pertenece a este motivo y solo a este: un PIN repetido no se arregla pagando.
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === 'POST') {
          return {
            ok: false,
            status: 409,
            json: async () => ({
              ok: false,
              error: { code: 'hub.users.pin_in_use', message: 'another active user already uses that PIN' },
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({ ok: true, data: [] }) };
      }),
    );
    const form = await mountFormAndSave('es');

    expect(form.text()).toContain(es.employeeForm.errors.pin_in_use);
    expect(planButton(form, es.nav.upgradePlan)).toBeFalsy();
  });
});
