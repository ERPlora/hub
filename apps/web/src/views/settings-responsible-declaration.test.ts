// @vitest-environment happy-dom
// **La declaración responsable se ve DENTRO del producto, en cada versión** (hub#528).
//
// Art. 13.2 RRSIF (RD 1007/2023): la declaración responsable del productor tiene que constar «por
// escrito y de modo visible en el propio sistema informático **en cada una de sus versiones**».
// Hasta hub#528 el Hub no la enseñaba en ningún sitio: existía la mitad pública (el archivo de
// erplora.com) y ninguna dentro del TPV, que es donde la pide una inspección.
//
// Lo que estos tests clavan no es que la tarjeta exista, sino de dónde salen sus datos. Una
// pantalla que pintara `ERPlora Hub / EC / 1.0.0` desde constantes se ve IGUAL que esta — hasta el
// día en que el plano de control corrige el bloque del fabricante y el TPV certifica una identidad
// mientras cada factura declara otra. Así que se monta la SettingsPage real sobre la lib real, con
// solo `fetch` interceptado, y se comprueba que lo pintado es lo que respondió el runtime.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

// El registro de iconos arrastra ~70 ids virtuales `~icons/…?raw` que este entorno deniega; tiene
// su propio test (`lib/icons.test.ts`). Mismo seam que los tests vecinos de Ajustes.
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const push = vi.fn();
vi.mock('vue-router', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useRoute: () => ({ hash: '#tax', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]) }));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({}),
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings: vi.fn(),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));
vi.mock('../lib/autostart', () => ({
  autostartState: vi.fn().mockResolvedValue({ available: false, enabled: false }),
  setAutostart: vi.fn(),
}));
// La representación (hub#817) tiene su propio panel y su propio test; aquí estorba con sus fetch.
vi.mock('../components/RepresentationGrantPanel.vue', () => ({
  default: { name: 'RepresentationGrantPanel', template: '<div />' },
}));
// La lib de runtime se mockea para las OTRAS lecturas de esta página (certificado, módulos); las
// dos constantes que la lib real de la declaración importa de ella tienen que seguir funcionando.
vi.mock('../lib/runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
  listInstalledModules: vi.fn().mockResolvedValue([]),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  getBusinessCertificate: vi.fn().mockResolvedValue({ present: false }),
  publishFiscalIdentity: vi.fn(),
  putBusinessCertificate: vi.fn(),
  deleteBusinessCertificate: vi.fn(),
}));

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
});

/** Un stub que SÍ pinta lo que envuelve (un stub pelado se come su slot). */
const PASSTHROUGH = { template: '<div><slot /></div>' };

const HUB_ID = '6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10';

/** La respuesta del runtime tal cual la sirve `GET /api/system/declaration`. */
function declarationPayload(overrides: Record<string, unknown> = {}) {
  return {
    version: '2.4.1',
    numeroInstalacion: HUB_ID,
    declarationUrl: 'https://pre.erplora.com/legal/declaracion-responsable/',
    sistemaInformatico: {
      NombreRazon: 'ERPLORA CLOUD SL',
      NIF: 'B27593136',
      NombreSistemaInformatico: 'ERPlora Hub',
      IdSistemaInformatico: 'EC',
      Version: '2.4.1',
      NumeroInstalacion: HUB_ID,
      TipoUsoPosibleSoloVerifactu: 'S',
      TipoUsoPosibleMultiOT: 'S',
      IndicadorMultiplesOT: 'N',
    },
    ...overrides,
  };
}

/** Responde `/api/system/declaration` con `payload`; cualquier otra URL de esta página, 404 mudo. */
function stubDeclarationFetch(payload: unknown, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: unknown) => {
      if (String(url).includes('/api/system/declaration')) {
        return new Response(JSON.stringify(payload), { status });
      }
      return new Response('{}', { status: 404 });
    }),
  );
}

async function mountTaxTab() {
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  const wrapper = mount(SettingsPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: {
        AppPage: PASSTHROUGH,
        IonCard: PASSTHROUGH,
        IonCardContent: PASSTHROUGH,
        IonList: PASSTHROUGH,
        IonItem: PASSTHROUGH,
        IonLabel: PASSTHROUGH,
        IonNote: PASSTHROUGH,
        IonButton: PASSTHROUGH,
      },
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  push.mockClear();
});

describe('Ajustes › Negocio · declaración responsable (hub#528)', () => {
  it('muestra la DR de la versión instalada (hub#528)', async () => {
    stubDeclarationFetch(declarationPayload());
    const wrapper = await mountTaxTab();

    const card = wrapper.find('.responsible-declaration');
    expect(card.exists(), 'la tarjeta de la declaración responsable se pinta').toBe(true);
    const text = card.text();

    // La versión del BINARIO que corre este hub, no la del `package.json` ni una constante.
    expect(text).toContain('2.4.1');
    // `NumeroInstalacion` = el `hub_id`: es lo que identifica esta instalación ante la AEAT.
    expect(text).toContain(HUB_ID);
    // Los datos identificativos del art. 13.4, con el nombre literal del elemento del registro.
    expect(text).toContain('ERPLORA CLOUD SL');
    expect(text).toContain('B27593136');
    expect(text).toContain('IdSistemaInformatico');
    expect(text).toContain('EC');
    // El texto firmado se lee en el plano de control de ESTE hub (aquí, PRE).
    expect(card.find('a.responsible-declaration-link').attributes('href')).toBe(
      'https://pre.erplora.com/legal/declaracion-responsable/',
    );
  });

  it('no inventa la identidad del fabricante cuando el hub todavía no la ha recibido', async () => {
    stubDeclarationFetch(declarationPayload({ sistemaInformatico: null }));
    const wrapper = await mountTaxTab();

    const card = wrapper.find('.responsible-declaration');
    expect(card.exists()).toBe(true);
    expect(card.find('.responsible-declaration-pending').exists()).toBe(true);
    expect(card.text()).not.toContain('ERPLORA CLOUD SL');
    // Lo que este hub SÍ sabe de sí mismo se sigue enseñando.
    expect(card.text()).toContain('2.4.1');
    expect(card.text()).toContain(HUB_ID);
  });

  it('una lectura fallida se dice, nunca se pinta una tarjeta vacía en verde', async () => {
    stubDeclarationFetch({ ok: false }, 500);
    const wrapper = await mountTaxTab();

    expect(wrapper.find('.responsible-declaration-error').exists()).toBe(true);
    expect(wrapper.find('.responsible-declaration-field').exists()).toBe(false);
  });
});
