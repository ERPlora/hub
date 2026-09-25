// @vitest-environment happy-dom
// hub#2072: the card of a paid app in Apps → Paid read «€/mes» with no amount. WhatsApp comes only
// with the hub plan (ADR-0474), so the catalog has no amount for it: the row must say so in words,
// in both languages, and never print the unit alone.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
// `lib/icons` bakes its SVGs through `~icons/…?raw`, which this environment denies (same cut as
// apps-refresh-keeps-the-screen.test.ts).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

let CATALOG: Array<Record<string, unknown>> = [];
let INSTALLED: Array<Record<string, unknown>> = [];
/** What the Cloud answers for one module's detail, per id. */
let PUBLICATION: Record<string, 'listed' | 'unlisted' | 'retired'> = {};
/** Ids the screen actually asked the Cloud about — the cost this design must not pay twice. */
const asked: string[] = [];
let publicationFails = false;

const cloudMarketplaceModules = vi.fn(async () => CATALOG);
const listInstalledModules = vi.fn(async () => INSTALLED);
const modulePublicationStatus = vi.fn(async (id: string) => {
  asked.push(id);
  if (publicationFails) throw new Error('cloud down');
  return PUBLICATION[id] ?? null;
});

vi.mock('../lib/cloud', () => ({
  cloudMarketplaceModules: () => cloudMarketplaceModules(),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: vi.fn(),
  listInstalledModules: () => listInstalledModules(),
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError: class InstallBlockedError extends Error {},
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: vi.fn(),
  listModuleUpdates: async () => [],
  listModuleVersions: async () => [],
  modulePublicationStatus: (id: string) => modulePublicationStatus(id),
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

function mountApps(locale: 'en' | 'es') {
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

function paidEntry(id: string, overrides: Record<string, unknown>) {
  return {
    id,
    name: id,
    description: 'what it does',
    priceLabel: '',
    priceAmount: null,
    priceInterval: 'month',
    isFree: false,
    includedInPlan: false,
    moduleType: 'subscription',
    category: 'Operations',
    installed: false,
    available: true,
    version: '1.0.0',
    capabilities: [],
    minErploraVersion: null,
    ...overrides,
  };
}

async function priceOf(locale: 'en' | 'es', id: string): Promise<string> {
  const wrapper = mountApps(locale);
  await flushPromises();
  await nextTick();
  await flushPromises();
  const rows = wrapper
    .findAll('ok-data-table')
    .flatMap((t) => (t.element as TableEl).rows ?? []);
  const row = rows.find((r) => r.id === id);
  expect(row, `the catalog must list ${id}`).toBeDefined();
  return String(row!.price);
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  INSTALLED = [];
  CATALOG = [
    paidEntry('whatsapp_inbox', { includedInPlan: true }),
    paidEntry('third_party', {}),
    paidEntry('priced', { priceAmount: '14.99' }),
  ];
});

describe('the price of a paid app in the catalog (hub#2072)', () => {
  it('an app that comes with the hub plan says so, in Spanish and in English', async () => {
    expect(await priceOf('es', 'whatsapp_inbox')).toBe('Incluida en tu plan');
    expect(await priceOf('en', 'whatsapp_inbox')).toBe('Included in your plan');
  });

  it('a paid app with no amount never shows the unit alone', async () => {
    expect(await priceOf('es', 'third_party')).toBe('Consultar');
  });

  it('a paid app with an amount keeps amount and unit', async () => {
    expect(await priceOf('es', 'priced')).toBe('14.99 €/mes');
  });
});
