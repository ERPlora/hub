// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1130 — installing a module SILENTLY dragged in its dependencies
// (ADR-0060's install-plan closure): the owner asked for ONE app and three more icons showed up
// with no explanation. The reverse door already names what it removes (hub#1101, `409
// has_dependents` + `error.dependents`); this pins the forward door naming what it added, in the
// SAME confirmation the owner is already reading (market: Odoo/Shopify — no separate modal).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
// `lib/icons` bakes its SVGs through `~icons/…?raw`, which this environment denies (same cut as
// apps-refresh-keeps-the-screen.test.ts / AppsPage.retired-badge.hub1134.test.ts).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

function catalogueEntry(id: string, name: string) {
  return {
    id,
    name,
    description: 'what it does',
    priceLabel: '',
    priceAmount: null,
    priceInterval: null,
    isFree: true,
    moduleType: 'free',
    category: 'Operations',
    installed: false,
    available: true,
    version: '1.0.0',
    capabilities: [],
  };
}

let CATALOG: Array<Record<string, unknown>> = [];
const cloudMarketplaceModules = vi.fn(async () => CATALOG);
const listInstalledModules = vi.fn(async () => [] as Array<Record<string, unknown>>);
const requestInstallMock = vi.fn();

vi.mock('../lib/cloud', () => ({
  cloudMarketplaceModules: () => cloudMarketplaceModules(),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: (moduleId: string, version: string) => requestInstallMock(moduleId, version),
  listInstalledModules: () => listInstalledModules(),
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  // Rejects → `installModule` falls back to `fromRuntime = null`, and with an empty catalogue
  // `capabilities` array `capabilitiesToConsent` returns `[]`: no consent modal in the way of the
  // install this test drives straight through.
  getModuleCapabilities: vi.fn().mockRejectedValue(new Error('unknown module')),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError: class InstallBlockedError extends Error {},
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: vi.fn(),
  listModuleUpdates: async () => [],
  // Empty version list → `chooseVersion` never opens the picker alert and resolves straight to
  // `latest` (`shouldPickVersion([]) === false`).
  listModuleVersions: async () => ({ versions: [] }),
  modulePublicationStatus: async () => null,
}));
const { moduleNav } = vi.hoisted(() => ({ moduleNav: { value: [] as Array<{ path: string }> } }));
vi.mock('../lib/nav', () => ({ moduleNav, refreshModuleNav: vi.fn() }));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/entitlement', () => ({
  isModuleEntitled: () => true,
  entitlementStatus: () => 'active',
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/setup-status', () => ({ setupStatus: ref(null), refreshSetupStatus: vi.fn() }));

import '@erplora/outfitkit/ok-data-table';
import AppsPage from './AppsPage.vue';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

type Row = Record<string, unknown>;
type TableEl = HTMLElement & { rows?: Row[] };

const mounted: Array<{ unmount: () => void }> = [];

function mountApps(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(AppsPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
  mounted.push(wrapper);
  return wrapper;
}

type Wrapper = ReturnType<typeof mountApps>;

/** Template order: «Mis apps» first, the catalogue second (both `v-show`, both always mounted). */
const catalogTable = (w: Wrapper): TableEl =>
  w.findAll('ok-data-table').map((t) => t.element as TableEl)[1];

/** Ionic components resolve through Vue (only `ok-`/`erp-` are native custom elements — see
 *  `vite.config.ts`'s `isCustomElement`), so `shallow: true` stubs `<ion-toast>` into
 *  `<ion-toast-stub>`, carrying every bound prop as a lowercased attribute. */
const toastMessage = (w: Wrapper): string | undefined =>
  w.find('ion-toast-stub').attributes('message');

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
  await nextTick();
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  CATALOG = [];
  moduleNav.value = [];
  cloudMarketplaceModules.mockClear();
  listInstalledModules.mockClear();
  requestInstallMock.mockReset();
});

describe('installing a module that drags in dependencies (hub#1130)', () => {
  it('names what got dragged in, BY NAME, in the same confirmation (en)', async () => {
    CATALOG = [
      catalogueEntry('verifactu', 'Verifactu'),
      catalogueEntry('invoice', 'Invoice'),
      catalogueEntry('sales', 'Sales'),
    ];
    requestInstallMock.mockResolvedValue({
      ok: true,
      module_id: 'verifactu',
      version: '1.0.0',
      status: 'installed',
      also_installed: ['invoice', 'sales'],
    });
    const wrapper = mountApps('en');
    await settle();

    const row = (catalogTable(wrapper).rows ?? []).find((r) => r.id === 'verifactu');
    expect(row, 'the catalogue must list the module under test').toBeTruthy();

    catalogTable(wrapper).dispatchEvent(
      new CustomEvent('rowAction', { detail: { actionId: 'install', row } }),
    );
    await settle();

    expect(requestInstallMock).toHaveBeenCalledWith('verifactu', 'latest');
    const message = toastMessage(wrapper);
    expect(message).toContain('Verifactu');
    expect(message).toContain('Invoice');
    expect(message).toContain('Sales');
  });

  it('names what got dragged in, in Spanish, in the reader’s language (es)', async () => {
    CATALOG = [
      catalogueEntry('verifactu', 'Verifactu'),
      catalogueEntry('invoice', 'Facturas'),
      catalogueEntry('sales', 'Ventas'),
    ];
    requestInstallMock.mockResolvedValue({
      ok: true,
      module_id: 'verifactu',
      version: '1.0.0',
      status: 'installed',
      also_installed: ['invoice', 'sales'],
    });
    const wrapper = mountApps('es');
    await settle();

    const row = (catalogTable(wrapper).rows ?? []).find((r) => r.id === 'verifactu');
    catalogTable(wrapper).dispatchEvent(
      new CustomEvent('rowAction', { detail: { actionId: 'install', row } }),
    );
    await settle();

    const message = toastMessage(wrapper);
    expect(message).toContain('Facturas');
    expect(message).toContain('Ventas');
    expect(message?.toLowerCase()).toContain('también se instaló');
    // The binding rule of 2026-08-04: English is the source and Spanish is NOT optional, and the
    // two must not be the same string by accident.
    expect(esCatalogue.apps.installSuccessWithDependencies).not.toBe(
      enCatalogue.apps.installSuccessWithDependencies,
    );
  });

  it('a module with NOTHING dragged in gets the plain success message — no "also installed" noise', async () => {
    CATALOG = [catalogueEntry('customers', 'Customers')];
    requestInstallMock.mockResolvedValue({
      ok: true,
      module_id: 'customers',
      version: '1.0.0',
      status: 'installed',
      also_installed: [],
    });
    const wrapper = mountApps('en');
    await settle();

    const row = (catalogTable(wrapper).rows ?? []).find((r) => r.id === 'customers');
    catalogTable(wrapper).dispatchEvent(
      new CustomEvent('rowAction', { detail: { actionId: 'install', row } }),
    );
    await settle();

    const message = toastMessage(wrapper);
    expect(message).toBe(enCatalogue.apps.installSuccess.replace('{name}', 'Customers'));
  });
});
