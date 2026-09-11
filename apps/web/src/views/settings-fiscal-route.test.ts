// @vitest-environment happy-dom
// **Ajustes › Negocio pregunta UNA cosa: por qué vía llegan tus facturas a la AEAT** (hub#1314).
//
// Antes apilaba dos tarjetas —«Certificado fiscal» y «Otorgamiento de representación»— como si
// hicieran falta las dos. No es así: son dos vías EXCLUYENTES (ADR-0320 §1, «La clave delegada deja
// la flota…»). O firma y remite el propio obligado con su `.p12`, o lo hace ERPlora en su nombre
// con el Sello, y solo esa segunda necesita el Anexo I. El SaaS ya enruta así
// (`select_transmission_route`); la pantalla pedía las dos y decía «no puedes pasar a producción
// hasta que lo firmes» a quien ya tenía su certificado subido.
//
// 🔴 Lo que estos tests fijan NO es que exista un segmento, es que enseña UNA vía cada vez. Una
// pantalla que pintara el selector y dejara las dos tarjetas debajo pasaría un test de «hay
// segmento» y seguiría siendo el bug.
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '#tax', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]) }));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({}),
  hubTimezone: () => 'Europe/Madrid',
  // `format-datetime` la lee para fechar la subida del `.p12`; sin ella el mock hace saltar al
  // mocker por un export que no existe y el fallo aparenta ser de la pantalla.
  publishedHubTimezone: () => 'Europe/Madrid',
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings: vi.fn().mockResolvedValue({}),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn().mockResolvedValue({}) }));
vi.mock('../lib/autostart', () => ({
  autostartState: vi.fn().mockResolvedValue({ available: false, enabled: false }),
  setAutostart: vi.fn(),
}));

/** Lo que contesta `GET /api/business/certificate`, que es quien nombra la vía (hub#1314). */
const getBusinessCertificate = vi.fn();
// Solo se cambian los exports que este caso conduce: un mock a mano del módulo entero convierte
// cualquier import futuro de `SettingsPage` en un timeout en vez de en una aserción fallida.
vi.mock('../lib/runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getBusinessCertificate,
  putBusinessCertificate: vi.fn().mockResolvedValue(undefined),
  deleteBusinessCertificate: vi.fn().mockResolvedValue(undefined),
  listInstalledModules: vi.fn().mockResolvedValue([]),
  getClient: () => ({}),
}));

const i18n = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  // Los catálogos REALES: con mensajes de mentira, una clave que no existiese se pintaría como su
  // propio nombre y el test seguiría verde con la pantalla sin traducir.
  messages: { en, es },
});

const PASSTHROUGH = { template: '<div><slot /></div>' };

async function mountBusinessTab() {
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  const wrapper = mount(SettingsPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: { AppPage: PASSTHROUGH, IonCard: PASSTHROUGH, IonCardContent: PASSTHROUGH },
      // Sin esto los stubs de Ionic no pintan su `<slot>` y todo lo que vive dentro de un
      // `ion-card-content` «no existe»: verde antes de escribir la pantalla y verde tras borrarla.
      renderStubDefaultSlot: true,
    },
  });
  await flushPromises();
  return wrapper;
}

/** Cambia de vía como lo hace Ionic de verdad: `ionChange` con su `CustomEvent`. */
async function pickRoute(wrapper: VueWrapper, value: string) {
  (wrapper.getComponent('[data-testid="settings-fiscal-route-segment"]') as VueWrapper).vm.$emit(
    'ionChange',
    new CustomEvent('ionChange', { detail: { value } }),
  );
  await flushPromises();
}

// Compilar `SettingsPage.vue` y su árbol de imports tarda más que el timeout por defecto.
beforeAll(async () => {
  await import('./SettingsPage.vue');
}, 60_000);

beforeEach(() => {
  getBusinessCertificate.mockReset();
});

describe('Ajustes › Negocio · la vía hacia la AEAT es UNA de dos (hub#1314)', () => {
  it('sin certificado propio arranca en «lo hace ERPlora» y enseña SOLO el otorgamiento', async () => {
    getBusinessCertificate.mockResolvedValue({ present: false, transmission_route: 'delegated' });

    const wrapper = await mountBusinessTab();

    const segment = wrapper.find('[data-testid="settings-fiscal-route-segment"]');
    expect(segment.exists(), 'la pregunta se hace con un segmento de dos opciones').toBe(true);
    expect(segment.attributes('value')).toBe('delegated');
    expect(wrapper.find('[data-testid="settings-fiscal-route-delegated"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="settings-fiscal-route-own"]').exists()).toBe(true);
    // La vía delegada enseña el otorgamiento y NADA del `.p12`: pedir las dos cosas es el bug.
    expect(wrapper.find('.fiscal-grant').exists()).toBe(true);
    expect(wrapper.find('.fiscal-certificate').exists()).toBe(false);
  });

  it('con certificado propio arranca en «mi certificado» y el otorgamiento NO se pide', async () => {
    getBusinessCertificate.mockResolvedValue({
      present: true,
      transmission_route: 'own',
      uploaded_at: '2026-08-08T09:00:00Z',
      subject: 'CN=BAR PEPE SL',
    });

    const wrapper = await mountBusinessTab();

    expect(wrapper.find('[data-testid="settings-fiscal-route-segment"]').attributes('value')).toBe('own');
    expect(wrapper.find('.fiscal-certificate').exists()).toBe(true);
    // 🔴 Y con él NO aparece «no puedes pasar a producción hasta que lo firmes»: ese texto vive en
    // el panel del otorgamiento, que en esta vía no se pinta. Es el síntoma exacto de la issue.
    expect(wrapper.find('.fiscal-grant').exists()).toBe(false);
    expect(wrapper.text()).not.toContain(es.grant.stateAbsent);
  });

  it('cambiar de vía solo cambia lo que se enseña, en las dos direcciones', async () => {
    getBusinessCertificate.mockResolvedValue({ present: false, transmission_route: 'delegated' });
    const wrapper = await mountBusinessTab();

    await pickRoute(wrapper, 'own');
    expect(wrapper.find('.fiscal-certificate').exists()).toBe(true);
    expect(wrapper.find('.fiscal-grant').exists()).toBe(false);

    await pickRoute(wrapper, 'delegated');
    expect(wrapper.find('.fiscal-grant').exists()).toBe(true);
    expect(wrapper.find('.fiscal-certificate').exists()).toBe(false);
  });

  it('la pregunta y las dos vías están escritas en inglés Y en español (ADR-0055/0199)', () => {
    const keys = [
      'fiscalRouteTitle',
      'fiscalRouteLead',
      'fiscalRouteDelegated',
      'fiscalRouteOwn',
      'fiscalRouteOwnHint',
    ] as const;
    for (const key of keys) {
      expect(en.settings[key], `falta la cadena fuente en.settings.${key}`).toBeTruthy();
      expect(es.settings[key], `falta la traducción es.settings.${key}`).toBeTruthy();
      expect(es.settings[key], `es.settings.${key} está sin traducir`).not.toBe(en.settings[key]);
    }
  });
});
