// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1174 —
// `a_denied_permission_says_what_breaks_not_only_what_it_allows_hub1174`.
//
// **Settings → Permissions paints every permission as label + description + toggle, and NOTHING
// says what stops working while the switch is off.** Default-deny is right; an invisible
// consequence is not. With `certificate` off the hub issues invoices that are never registered
// with the tax authority; with `printer` off every ticket piles up in the queue and the owner only
// finds out through the "nobody is printing" alarm, minutes later.
//
// The consequence sentence must come from ONE place — the capability catalogue keyed by capability
// id (`lib/module-capabilities.ts`) — never typed into this screen, and it must be an i18n key so
// the owner reads it in their own language (ADR-0055/0199).
//
// The action that fixes it sits in the same row: the toggle itself (hub#800 §3 — "a warning with
// no action next to it is a reproach").
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import type { ModuleCapability } from '../lib/runtime';

vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  // Deep-link straight into the tab under test: the permissions list only loads on `#permissions`.
  useRoute: () => ({ hash: '#permissions', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]) }));

vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref<Record<string, unknown>>({}),
  hubTimezone: () => 'Europe/Madrid',
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings: vi.fn().mockResolvedValue({}),
}));

const listInstalledModules = vi.fn();
const getModuleCapabilities = vi.fn();
// Only these are swapped: `SettingsPage` pulls a dozen things from `lib/runtime`, and a hand-written
// mock of the whole module turns any future import into a timeout instead of a failed assertion.
vi.mock('../lib/runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  listInstalledModules,
  getModuleCapabilities,
  putModuleCapabilities: vi.fn().mockResolvedValue({}),
  getBusinessCertificate: vi.fn().mockResolvedValue(null),
  refreshHubTimezone: vi.fn().mockResolvedValue('Europe/Madrid'),
  getClient: () => ({}),
}));

const isAdmin = ref(true);
vi.mock('../lib/session', () => ({ isAdmin }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn().mockResolvedValue({}) }));

// The REAL sentences of the screen. With `messages: {}` every `t()` returns its own key, so a card
// that printed the raw key would pass just the same — and that is the failure being guarded.
const CERT_BREAKS = 'Sin esto, tus facturas no se registran en Hacienda.';
const PRINTER_BREAKS = 'Sin esto, los tiques se quedan en la cola y no sale ninguno.';
const UNKNOWN_BREAKS = 'Sin esto, la parte de la app que necesita este permiso no funcionará.';

const i18n = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    es: {
      settings: {
        permissionsTitle: 'Permisos de las apps',
        permissionsDesc: 'Concede o revoca los permisos que cada app pide.',
        capabilityBreaks: {
          certificate: CERT_BREAKS,
          printer: PRINTER_BREAKS,
          unknown: UNKNOWN_BREAKS,
        },
      },
    },
  },
});

const PASSTHROUGH = { template: '<div><slot /></div>' };

function cap(id: string, granted: boolean): ModuleCapability {
  return {
    id,
    label: `Etiqueta de ${id}`,
    // What it ALLOWS — the only thing the card said before this fix.
    description: `Permite al módulo usar ${id}.`,
    requested: true,
    granted,
  };
}

async function mountPermissions(caps: ModuleCapability[]) {
  listInstalledModules.mockResolvedValue([{ id: 'verifactu', name: 'VeriFactu' }]);
  getModuleCapabilities.mockResolvedValue({ module_id: 'verifactu', capabilities: caps });
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  const wrapper = mount(SettingsPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: { AppPage: PASSTHROUGH, IonCard: PASSTHROUGH, IonCardContent: PASSTHROUGH },
      // The Ionic stubs do not paint their `<slot>`, and the row lives inside `ion-list` >
      // `ion-item` > `ion-label`. Without this the test would say "there is no warning" whatever
      // the screen did — green before writing it and green after deleting it.
      renderStubDefaultSlot: true,
    },
  });
  await flushPromises();
  return wrapper;
}

// Compiling this SFC is the slowest thing in the file; doing it inside the first `it` makes that
// test look like a timeout instead of an assertion. Same warm-up as `settings-timezone.test.ts`.
beforeAll(async () => {
  await import('./SettingsPage.vue');
}, 60_000);

describe('Settings → Permissions · what breaks while the switch is off (hub#1174)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isAdmin.value = true;
  });

  it('a denied permission says what BREAKS, not only what it allows — a_denied_permission_says_what_breaks_not_only_what_it_allows_hub1174', async () => {
    const wrapper = await mountPermissions([cap('certificate', false)]);

    const warn = wrapper.find('[data-testid="cap-breaks-certificate"]');
    expect(warn.exists(), 'the denied permission card shows no consequence at all').toBe(true);
    expect(warn.text()).toContain(CERT_BREAKS);
    // The sentence is the CONSEQUENCE, not a second copy of what the permission allows.
    expect(warn.text()).not.toContain('Permite al módulo usar certificate.');
    // ...and it is translated, never a raw i18n key leaking onto the screen.
    expect(warn.text()).not.toMatch(/capabilityBreaks/);
  });

  it('a GRANTED permission shows no warning: the card stays as it is today (hub#1174)', async () => {
    const wrapper = await mountPermissions([cap('certificate', true)]);
    expect(wrapper.find('[data-testid="cap-breaks-certificate"]').exists()).toBe(false);
  });

  it('each denied capability gets ITS OWN consequence, not one generic line (hub#1174)', async () => {
    const wrapper = await mountPermissions([cap('certificate', false), cap('printer', false)]);
    expect(wrapper.find('[data-testid="cap-breaks-certificate"]').text()).toContain(CERT_BREAKS);
    expect(wrapper.find('[data-testid="cap-breaks-printer"]').text()).toContain(PRINTER_BREAKS);
  });

  it('a capability the shell does not know still says something, never an empty box (hub#1174)', async () => {
    // A new core capability that this mirror has not learnt yet must not paint a blank warning:
    // that is how a screen ends up shouting at the owner without telling them anything.
    const wrapper = await mountPermissions([cap('some_future_capability', false)]);
    const warn = wrapper.find('[data-testid="cap-breaks-some_future_capability"]');
    expect(warn.exists()).toBe(true);
    expect(warn.text()).toContain(UNKNOWN_BREAKS);
  });

  it('a non-admin sees the consequence too: knowing WHY it is broken is not an admin privilege (hub#1174)', async () => {
    isAdmin.value = false;
    const wrapper = await mountPermissions([cap('certificate', false)]);
    expect(wrapper.find('[data-testid="cap-breaks-certificate"]').text()).toContain(CERT_BREAKS);
  });

  // Ionic's `--ion-color-warning` (#ffc409) renders at ~1.6:1 contrast on white — and its
  // `-shade` (#e0ac08), the fallback already used by ExportPanel/ImportPanel, only reaches
  // ~2.1:1. Both fail WCAG AA's 4.5:1 floor for normal text. This sentence is not decorative:
  // the owner has to READ it to know their invoices stop reaching Hacienda. The market pattern
  // (iOS/Android permission screens, Shopify, Square) keeps the warning accent on the ICON and
  // reads the sentence in the theme's normal/muted text colour.
  it('the consequence sentence is legible: never rendered in the raw warning yellow (hub#1174)', async () => {
    const wrapper = await mountPermissions([cap('certificate', false)]);
    const warn = wrapper.find('[data-testid="cap-breaks-certificate"]');
    expect(warn.attributes('color'), 'warning-yellow text is ~1.6:1 on white, under WCAG AA 4.5:1').not.toBe('warning');
  });
});
