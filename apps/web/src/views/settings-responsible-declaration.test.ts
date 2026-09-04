// @vitest-environment happy-dom
// **The responsible declaration is visible INSIDE the product, in every version** (hub#528).
//
// Art. 13.2 RRSIF (RD 1007/2023): the producer's responsible declaration must appear «por escrito
// y de modo visible en el propio sistema informático **en cada una de sus versiones**». Until
// hub#528 the Hub showed it nowhere: the public half existed (the erplora.com archive) and none
// inside the till, which is where an inspection asks for it.
//
// What these tests pin is not that the card exists but where its data comes from. A screen that
// painted `ERPlora Hub / EC / 1.0.0` out of constants looks THE SAME as this one — until the day
// the control plane corrects the manufacturer's block and the till certifies one identity while
// every invoice declares another. So the real SettingsPage is mounted over the real lib, with only
// `fetch` intercepted, and what is painted is checked against what the runtime answered.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

// The icon registry drags ~70 virtual `~icons/…?raw` ids this environment denies; it has its own
// test (`lib/icons.test.ts`). Same seam as the neighbouring Settings tests.
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
// The representation grant (hub#817) has its own panel and its own test; here its fetches only get in the way.
vi.mock('../components/RepresentationGrantPanel.vue', () => ({
  default: { name: 'RepresentationGrantPanel', template: '<div />' },
}));
// The runtime lib is mocked for the OTHER reads of this page (certificate, modules); the two
// constants the real declaration lib imports from it must keep working.
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

/** A stub that DOES render what it wraps (a bare stub swallows its slot). */
const PASSTHROUGH = { template: '<div><slot /></div>' };

const HUB_ID = '6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10';

/** The runtime's answer exactly as `GET /api/system/declaration` serves it. */
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

/** Answers `/api/system/declaration` with `payload`; any other URL of this page, a silent 404. */
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

describe('Settings › Business · responsible declaration (hub#528)', () => {
  it('shows the responsible declaration of the installed version (hub#528)', async () => {
    stubDeclarationFetch(declarationPayload());
    const wrapper = await mountTaxTab();

    const card = wrapper.find('.responsible-declaration');
    expect(card.exists(), 'the responsible declaration card is rendered').toBe(true);
    const text = card.text();

    // The version of the BINARY this hub runs, not the `package.json` one nor a constant.
    expect(text).toContain('2.4.1');
    // `NumeroInstalacion` = the `hub_id`: what identifies this installation before the AEAT.
    expect(text).toContain(HUB_ID);
    // The identifying data of art. 13.4, with the literal name of the record element.
    expect(text).toContain('ERPLORA CLOUD SL');
    expect(text).toContain('B27593136');
    expect(text).toContain('IdSistemaInformatico');
    expect(text).toContain('EC');
    // The signed text is read on THIS hub's control plane (here, PRE).
    expect(card.find('a.responsible-declaration-link').attributes('href')).toBe(
      'https://pre.erplora.com/legal/declaracion-responsable/',
    );
  });

  // hub#1510 (item 4 of hub#1449's DoD). Art. 13.3 RRSIF lets several declarations coexist — one
  // per range of versions — so the link on its own does not say WHICH text it points at. Naming it
  // next to the link is what lets an inspector check that the text they are reading covers this
  // release, without following the URL and comparing folder names.
  it('names WHICH declaration text covers this release, next to the link (hub#1510)', async () => {
    stubDeclarationFetch(
      declarationPayload({
        declarationUrl: 'https://erplora.com/legal/declaracion-responsable/v2/',
        declarationVersion: 'v2',
      }),
    );
    const wrapper = await mountTaxTab();

    const card = wrapper.find('.responsible-declaration');
    const version = card.find('.responsible-declaration-version');
    expect(version.exists(), 'the declaration version is rendered').toBe(true);
    expect(version.text()).toContain('v2');
    // Next to the LINK, not buried among the nine elements of the record's block: they are the
    // pair an inspector reads together.
    const link = card.find('a.responsible-declaration-link');
    expect(link.exists()).toBe(true);
    expect(version.element.parentElement).toBe(link.element.parentElement);
    // The label is translated, never hardcoded (ADR-0055/0199).
    expect(version.text()).toContain(en.settings.declarationTextVersion);
    // The BINARY's version keeps its own row: `v2` is the text, `2.4.1` is the release.
    expect(card.text()).toContain('2.4.1');
  });

  it('without a named declaration nothing is painted next to the link (hub#1510)', async () => {
    // No `declarationVersion`: an older control plane, or a hub that has never reached it. The
    // link falls back to the archive root, which has no version to name.
    stubDeclarationFetch(declarationPayload());
    const wrapper = await mountTaxTab();

    const card = wrapper.find('.responsible-declaration');
    expect(card.find('a.responsible-declaration-link').exists()).toBe(true);
    expect(
      card.find('.responsible-declaration-version').exists(),
      'an empty version label reads as «this declaration has no version», a different claim',
    ).toBe(false);
    expect(card.text()).not.toContain(en.settings.declarationTextVersion);
  });

  it('does not invent the manufacturer identity while the hub has not received it (hub#528)', async () => {
    stubDeclarationFetch(declarationPayload({ sistemaInformatico: null }));
    const wrapper = await mountTaxTab();

    const card = wrapper.find('.responsible-declaration');
    expect(card.exists()).toBe(true);
    expect(card.find('.responsible-declaration-pending').exists()).toBe(true);
    expect(card.text()).not.toContain('ERPLORA CLOUD SL');
    // What this hub DOES know about itself is still shown.
    expect(card.text()).toContain('2.4.1');
    expect(card.text()).toContain(HUB_ID);
  });

  it('a failed read is stated, never painted as an empty green card (hub#528)', async () => {
    stubDeclarationFetch({ ok: false }, 500);
    const wrapper = await mountTaxTab();

    expect(wrapper.find('.responsible-declaration-error').exists()).toBe(true);
    expect(wrapper.find('.responsible-declaration-field').exists()).toBe(false);
  });
});
