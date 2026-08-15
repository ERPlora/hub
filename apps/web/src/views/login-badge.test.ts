// @vitest-environment happy-dom
// hub#658 — **entrar pasando la placa**, en la pantalla de login.
//
// Lo que fija esta suite es lo que la decisión de mercado dice y lo que la pantalla podría
// traicionar sin que ningún test del runtime se enterase:
//
//   1. **No hace falta enfocar nada, ni elegir a nadie.** La ráfaga la caza el listener global del
//      shell y la tarjeta resuelve la identidad entera — sustituye al par (nombre, PIN), no al PIN.
//   2. **La placa se ofrece exactamente donde se ofrece el pinpad.** Es la misma decisión de
//      negocio (modo del dispositivo + confianza + dial): aceptar tarjetas en un portátil marcado
//      `personal` sería abrir por la placa una puerta que el dueño cerró.
//   3. **Un rechazo no deja a nadie fuera.** La pantalla se queda donde estaba, con su pinpad: la
//      placa es comodidad, y el PIN es la vía de vuelta cuando la tarjeta se pierde.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return {
    pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]),
    hubContextReady: ref(false),
    machineRegistered: ref(true),
    machineRegistrationRequired: ref(false),
  };
});

vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  const actual = await vi.importActual<typeof import('../lib/device-mode')>('../lib/device-mode');
  const deviceMode = ref<'shared' | 'personal'>('shared');
  const deviceTrusted = ref(false);
  return {
    deviceMode,
    deviceTrusted,
    deviceModeReady: ref(true),
    loadDeviceMode: vi.fn(async () => deviceMode.value),
    setDeviceMode: vi.fn(),
    offersPinLogin: actual.offersPinLogin,
  };
});

const setUser = vi.fn();
const setHubSession = vi.fn();
vi.mock('../lib/session', () => ({
  setUser: (...a: unknown[]) => setUser(...a),
  setHubSession: (...a: unknown[]) => setHubSession(...a),
  getHubSession: vi.fn(() => 'sess-1'),
}));

const runtimeBadgeLogin = vi.fn();
vi.mock('../lib/cloud', () => ({
  cloudLogin: vi.fn(),
  cloudLogin2fa: vi.fn(),
  TwoFactorRequiredError: class TwoFactorRequiredError extends Error {
    ticket = '';
  },
  setTokens: vi.fn(),
  runtimeCloudSession: vi.fn(),
  runtimePinLogin: vi.fn(),
  runtimeBadgeLogin: (...a: unknown[]) => runtimeBadgeLogin(...a),
  runtimeSetPin: vi.fn(),
  googleLoginUrl: vi.fn(() => 'https://example.invalid/oauth'),
  exchangeGoogleCode: vi.fn(),
}));
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1', demo: false } }));
vi.mock('../lib/theme', () => ({ isDark: ref(false), toggleTheme: vi.fn() }));
vi.mock('../lib/branding', () => ({ hubLogo: ref('/logo.svg'), DEFAULT_HUB_LOGO: '/logo.svg' }));
const replace = vi.fn();
vi.mock('vue-router', () => ({
  useRouter: () => ({ currentRoute: { value: { query: {} } }, replace: (...a: unknown[]) => replace(...a) }),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import LoginPage from './LoginPage.vue';
import { hubContextReady, machineRegistrationRequired, pinUsers } from '../lib/runtime';
import { deviceMode, deviceTrusted } from '../lib/device-mode';
import { installBadgeScanner } from '../lib/badge-scanner';
import en from '../i18n/locales/en';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
});

const ANA_BADGE = '0009171456';

/** El lector: caracteres rápidos y un Enter, sin que nada tenga el foco. */
function swipe(badge: string): void {
  for (const ch of badge) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
  }
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
}

/** El mostrador tal y como lo ve el hub: gente con PIN y un login online ya hecho aquí. */
function seedCounterTill(): void {
  pinUsers.value = [{ id: 'u1', name: 'Marta Ruiz', role: 'employee' }];
  hubContextReady.value = true;
  machineRegistrationRequired.value = false;
  deviceTrusted.value = true;
  deviceMode.value = 'shared';
}

async function mountLogin() {
  const wrapper = mount(LoginPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
      stubs: { IonPopover: true },
    },
  });
  await flushPromises();
  return wrapper;
}

let uninstall: () => void;

beforeEach(() => {
  localStorage.clear();
  runtimeBadgeLogin.mockReset();
  setUser.mockClear();
  setHubSession.mockClear();
  replace.mockClear();
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
  deviceTrusted.value = false;
  deviceMode.value = 'shared';
  uninstall = installBadgeScanner();
});

afterEach(() => uninstall());

describe('signing in with a badge', () => {
  it('opens the session from the swipe alone — no field focused, no name tapped', async () => {
    seedCounterTill();
    runtimeBadgeLogin.mockResolvedValue({
      token: 'sess-badge',
      user: { id: 'u1', name: 'Marta Ruiz', role: 'employee' },
      permissions: ['till.add_sale'],
    });
    const wrapper = await mountLogin();
    // La rejilla de caras sigue en pantalla: nadie ha elegido a nadie, y no hace falta.
    expect(wrapper.find('ok-pinpad').exists() || wrapper.text().includes('Marta')).toBe(true);

    swipe(ANA_BADGE);
    await flushPromises();

    expect(runtimeBadgeLogin).toHaveBeenCalledWith(ANA_BADGE);
    expect(setHubSession).toHaveBeenCalledWith('sess-badge');
    expect(setUser).toHaveBeenCalledWith(expect.objectContaining({ id: 'u1', name: 'Marta Ruiz' }));
    expect(replace).toHaveBeenCalled();
  });

  it('says so in words, so nobody has to discover that the card works here', async () => {
    seedCounterTill();
    const wrapper = await mountLogin();
    expect(wrapper.text()).toContain(en.login.orSwipeBadge);
  });

  it('is refused where the pinpad is refused — a personal device does not accept cards either', async () => {
    // Misma decisión de negocio: el equipo propio del dueño entra con su cuenta. Aceptar una
    // tarjeta aquí sería abrir por la placa la puerta que el administrador cerró.
    seedCounterTill();
    deviceMode.value = 'personal';
    await mountLogin();

    swipe(ANA_BADGE);
    await flushPromises();

    expect(runtimeBadgeLogin).not.toHaveBeenCalled();
  });

  it('leaves the person exactly where they were when the card is refused', async () => {
    // La placa es comodidad: quedarse sin ella nunca puede dejar a nadie fuera, y el pinpad sigue
    // ahí para entrar con el PIN de siempre.
    seedCounterTill();
    runtimeBadgeLogin.mockRejectedValue(Object.assign(new Error('nope'), { code: 'badge_rejected' }));
    const wrapper = await mountLogin();

    swipe(ANA_BADGE);
    await flushPromises();

    expect(setHubSession).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain(en.login.badgeRejected);
  });
});
