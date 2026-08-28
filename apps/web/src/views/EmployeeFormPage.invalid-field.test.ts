// @vitest-environment happy-dom
// Personal habla en el idioma del hub, y el error sale DEBAJO del campo (hub#1190, hub#1241).
//
// Antes de PR #1185 el runtime rechazaba en español; #1185 le dio a cada rechazo su `field` y su
// `reason` estables y escribió las frases en inglés (regla del idioma del código). Esta pantalla
// pintaba `error.message` tal cual, así que una encargada que dejaba el nombre vacío en un hub en
// español leía «the name is required». Es una regresión visible contra ADR-0055.
//
// Se prueba con el catálogo `es` REAL y con el cliente REAL (`lib/hub-users`) hablando con un
// `fetch` de mentira: lo que se ejercita es la cadena entera envelope → cliente → pantalla, que es
// donde se perdía el idioma.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonInput } from '@ionic/vue';

import es from '../i18n/locales/es';

const { replace, push } = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ replace, push }),
  onBeforeRouteLeave: () => {},
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../lib/badge-scanner', () => ({ onBadgeScan: () => () => {} }));
vi.mock('../lib/nfc-badge', () => ({ nfcBadgeReady: { value: false } }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import EmployeeFormPage from './EmployeeFormPage.vue';

/** La frase EXACTA que el runtime manda hoy y que un hub en español no debe enseñar. */
const ENGLISH_FROM_THE_RUNTIME = 'the name is required';

/** Respuestas del runtime: censo y catálogo vacíos, y el alta que rechaza el campo que se pida. */
function runtimeRefusing(error: Record<string, unknown> | null): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && error) {
        return { ok: false, status: 422, json: async () => ({ ok: false, error }) };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: [] }) };
    }),
  );
}

async function mountForm() {
  const i18n = createI18n({ legacy: false, locale: 'es', fallbackLocale: 'es', messages: { es } });
  const wrapper = mount(EmployeeFormPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  }) as unknown as ReturnType<typeof mount> & {
    vm: { form: Record<string, unknown>; onSave: () => Promise<void> };
  };
  await flushPromises();
  return wrapper;
}

/** El texto de error que pinta el input etiquetado `label` — donde el usuario lo lee de verdad. */
function errorTextOf(form: VueWrapper, label: string): string | undefined {
  const input = form.findAllComponents(IonInput).find((i) => i.props('label') === label);
  if (!input) throw new Error(`no hay ningún campo etiquetado «${label}»`);
  return input.props('errorText') as string | undefined;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('Personal traduce el rechazo del core (hub#1190)', () => {
  // 🔴 El bug.
  it('NO enseña la frase inglesa del runtime cuando el hub está en español', async () => {
    runtimeRefusing({
      code: 'invalid_field',
      field: 'name',
      reason: 'required',
      message: ENGLISH_FROM_THE_RUNTIME,
    });
    const form = await mountForm();
    Object.assign(form.vm.form, { name: 'Marta Ruiz', role: 'employee', local: false, email: 'marta@example.com' });
    await form.vm.onSave();
    await flushPromises();

    expect(form.text()).not.toContain(ENGLISH_FROM_THE_RUNTIME);
    expect(errorTextOf(form as unknown as VueWrapper, es.employeeForm.fullName)).toBe(
      es.invalidField.byField.name.required,
    );
  });

  it('ancla el rechazo al campo que lo causó, no a un banner suelto', async () => {
    // Lo que hacen Odoo, Shopify y Business Central: el error se pinta bajo el input que se
    // arregla. Un banner al principio del formulario obliga a adivinar qué campo era.
    runtimeRefusing({
      code: 'invalid_field',
      field: 'email',
      reason: 'format',
      message: 'invalid email',
    });
    const form = await mountForm();
    Object.assign(form.vm.form, { name: 'Marta Ruiz', role: 'employee', local: false, email: 'marta@example.com' });
    await form.vm.onSave();
    await flushPromises();

    expect(errorTextOf(form as unknown as VueWrapper, es.employeeForm.email)).toBe(
      es.invalidField.byField.email.format,
    );
    // Y NO como banner suelto: el hueco del formulario sigue vacío.
    expect(form.text()).not.toContain(es.invalidField.byField.email.format);
  });

  it('un rechazo de NEGOCIO sigue saliendo con su propia frase traducida', async () => {
    // `hub.users.*` ya se traducía por código (hub#355) y no se toca: son motivos con remedio
    // propio («reincorpora a esa persona»), no un campo mal escrito.
    runtimeRefusing({ code: 'hub.users.pin_in_use', message: 'another active user already uses that PIN' });
    const form = await mountForm();
    Object.assign(form.vm.form, { name: 'Marta Ruiz', role: 'employee', local: false, email: 'marta@example.com' });
    await form.vm.onSave();
    await flushPromises();

    expect(form.text()).toContain(es.employeeForm.errors.pin_in_use);
  });

  it('un fallo mudo no inventa una frase: se queda con lo que haya', async () => {
    runtimeRefusing({ code: 'db', message: 'the request could not be completed' });
    const form = await mountForm();
    Object.assign(form.vm.form, { name: 'Marta Ruiz', role: 'employee', local: false, email: 'marta@example.com' });
    await form.vm.onSave();
    await flushPromises();

    expect(form.text()).toContain('the request could not be completed');
  });
});
