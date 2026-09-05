// @vitest-environment happy-dom
// hub#1430 — «Mi perfil» no dejaba cambiar el PIN: el único camino era Personal → mi fila →
// Editar, la pantalla de gestión de PERSONAL (donde uno entra a administrar a OTROS, no a sí
// mismo). Esto prueba la puerta self-service nueva: pide el PIN actual solo cuando ya hay uno
// (`has_pin`), lo manda a `runtimeSetPin` (la misma puerta que la alta de PIN tras login cloud,
// `/api/auth/set-pin`), y traduce el rechazo del runtime cuando el PIN actual no coincide.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonInput } from '@ionic/vue';

import es from '../i18n/locales/es';

vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn() }));

import ProfilePage from './ProfilePage.vue';
import { setHubSession } from '../lib/session';
import { resetUserProfile } from '../lib/user-profile';

const SESSION = 'sess-1';

function profileResponse(hasPin: boolean): Record<string, unknown> {
  return {
    id: 'u-1',
    name: 'Nora Vega',
    first_name: 'Nora',
    last_name: 'Vega',
    email: 'nora@example.com',
    role: 'employee',
    permissions: [],
    cloud_user_id: null,
    avatar_url: null,
    has_pin: hasPin,
    preferences: { language: null, theme_mode: null, theme_palette: null },
  };
}

function stubRuntime(hasPin: boolean, setPinResult: () => Promise<Response>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/api/profile') && (!init || init.method === undefined)) {
        return new Response(JSON.stringify(profileResponse(hasPin)), { status: 200 });
      }
      if (path.endsWith('/api/auth/set-pin')) {
        return setPinResult();
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
}

function pinInput(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAllComponents(IonInput).find((i) => i.props('label') === label);
}

async function mountProfile() {
  const i18n = createI18n({ legacy: false, locale: 'es', fallbackLocale: 'es', messages: { es } });
  const wrapper = mount(ProfilePage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  }) as unknown as ReturnType<typeof mount> & {
    vm: {
      currentPin: string;
      newPin: string;
      confirmPin: string;
      savePin: () => Promise<void>;
    };
  };
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  setHubSession(SESSION);
  resetUserProfile();
});

afterEach(() => {
  setHubSession(null);
  resetUserProfile();
});

describe('«Mi perfil» → cambiar mi PIN (hub#1430)', () => {
  it('sin PIN todavía: no pide el PIN actual y llama a set-pin sin `current_pin`', async () => {
    let sentBody: unknown;
    stubRuntime(false, async () => {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    const wrapper = await mountProfile();

    expect(pinInput(wrapper, es.profile.currentPin)).toBeUndefined();
    expect(wrapper.text()).toContain(es.profile.setPin);

    // Sustituye el stub para capturar el body exacto de esta llamada.
    vi.mocked(fetch).mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/api/auth/set-pin')) {
        sentBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      return new Response(JSON.stringify(profileResponse(false)), { status: 200 });
    });

    wrapper.vm.newPin = '8246';
    wrapper.vm.confirmPin = '8246';
    await wrapper.vm.savePin();
    await flushPromises();

    expect(sentBody).toEqual({ pin: '8246' });
  });

  it('con PIN existente: pide el PIN actual y lo manda como `current_pin`', async () => {
    let sentBody: unknown;
    stubRuntime(true, async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const wrapper = await mountProfile();

    expect(pinInput(wrapper, es.profile.currentPin)).toBeDefined();
    expect(wrapper.text()).toContain(es.profile.changePin);

    vi.mocked(fetch).mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/api/auth/set-pin')) {
        sentBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      return new Response(JSON.stringify(profileResponse(true)), { status: 200 });
    });

    wrapper.vm.currentPin = '1379';
    wrapper.vm.newPin = '8246';
    wrapper.vm.confirmPin = '8246';
    await wrapper.vm.savePin();
    await flushPromises();

    expect(sentBody).toEqual({ pin: '8246', current_pin: '1379' });
  });

  it('no llama al runtime si el PIN nuevo y su repetición no coinciden', async () => {
    stubRuntime(true, async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const wrapper = await mountProfile();
    const calls = vi.mocked(fetch).mock.calls.length;

    wrapper.vm.currentPin = '1379';
    wrapper.vm.newPin = '8246';
    wrapper.vm.confirmPin = '0000';
    await wrapper.vm.savePin();
    await flushPromises();

    expect(vi.mocked(fetch).mock.calls.length).toBe(calls);
    // El error se pinta bajo el propio input (hub#1190), no como banner suelto — `wrapper.text()`
    // no ve dentro del shadow DOM de `ion-input`, así que se comprueba por el prop que lo pinta.
    expect(pinInput(wrapper, es.profile.newPin)?.props('errorText')).toBe(es.profile.pinMismatch);
  });

  it('traduce el rechazo del runtime cuando el PIN actual no coincide (hub.users.pin_current_mismatch)', async () => {
    stubRuntime(true, async () =>
      new Response(
        JSON.stringify({
          ok: false,
          error: { code: 'hub.users.pin_current_mismatch', message: 'the current PIN does not match' },
        }),
        { status: 409 },
      ),
    );
    const wrapper = await mountProfile();

    wrapper.vm.currentPin = '0000';
    wrapper.vm.newPin = '8246';
    wrapper.vm.confirmPin = '8246';
    await wrapper.vm.savePin();
    await flushPromises();

    const errorText = pinInput(wrapper, es.profile.newPin)?.props('errorText');
    expect(errorText).not.toContain('the current PIN does not match');
    expect(errorText).toBe(es.employeeForm.errors.pin_current_mismatch);
  });
});
