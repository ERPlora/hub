// @vitest-environment happy-dom
// hub#2064 — after reconnecting WhatsApp (or setting up the printer) the home panel kept saying it
// was broken until the page was reloaded.
//
// The home panel lives inside `ion-router-outlet`, which keeps the page cached while the owner goes
// to the module settings to fix it. Coming back does not mount it again, so a health read tied to
// `onMounted` alone never runs a second time. The panel has to re-read the strip every time it
// comes back on screen — without reading twice on the very first entry, when Ionic fires
// `ionViewWillEnter` right after the mount that already read it.
//
// The Ionic lifecycle is captured here instead of faked end to end: the view registers its hooks
// with `@ionic/vue`, and the test fires them in the order the router outlet does.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { ref } from 'vue';

const lifecycle: Record<'willEnter' | 'didLeave', Array<() => void>> = { willEnter: [], didLeave: [] };

vi.mock('@ionic/vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@ionic/vue')>();
  return {
    ...actual,
    onIonViewWillEnter: (fn: () => void) => lifecycle.willEnter.push(fn),
    onIonViewDidLeave: (fn: () => void) => lifecycle.didLeave.push(fn),
  };
});

const fetchPrintHosts = vi.fn();
const fetchWhatsAppNumbers = vi.fn();

vi.mock('../lib/print-coverage', () => ({ fetchPrintHosts: () => fetchPrintHosts() }));
vi.mock('../lib/whatsapp-connect', () => ({ fetchWhatsAppNumbers: () => fetchWhatsAppNumbers() }));
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
vi.mock('../lib/runtime', () => ({
  getClient: () => ({ queryPage: async () => ({ rows: [], total: 0, limit: 100, offset: 0 }) }),
  getHubSector: () => 'belleza',
  listInstalledModules: async () => [{ id: 'whatsapp_inbox', status: 'active' }],
}));
vi.mock('../lib/dashboard-widgets', () => ({ collectDashboardWidgets: async () => ({ widgets: [], presets: [] }) }));
vi.mock('../lib/dashboard-blueprint-widget', () => ({ buildBlueprintWidget: vi.fn() }));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]), moduleNavState: ref('ready') }));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn(), setupStatus: ref(null) }));
vi.mock('../lib/shell', () => ({ openAssistantForSetup: vi.fn() }));
vi.mock('../lib/bridge-transport', () => ({ detectPeripherals: async () => null }));
vi.mock('../lib/dashboard-heading', () => ({
  GREETING_KEY: { morning: 'dashboard.morning' },
  panelHeading: () => ({ kind: 'business', name: 'Salón Elena' }),
}));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({ business_legal_name: 'Salón Elena', country_code: 'ES', language: 'es' }),
  publishedHubTimezone: () => null,
}));
vi.mock('../lib/money', () => ({ formatAmount: (n: number) => String(n) }));
vi.mock('../lib/data-table-labels', () => ({ dataTableLabels: () => ({}) }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));

import DashboardPage from './DashboardPage.vue';

const DOWN = [{ phone_number_id: 'p1', display_phone: '+34 600 000 000', is_active: true, needs_reconnect: true }];
const BACK = [{ phone_number_id: 'p1', display_phone: '+34 600 000 000', is_active: true, needs_reconnect: false }];

function mountDashboard() {
  const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } });
  return mount(DashboardPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
}

const fire = (hook: 'willEnter' | 'didLeave') => lifecycle[hook].forEach((fn) => fn());
const pillKeys = (wrapper: ReturnType<typeof mountDashboard>) =>
  wrapper.findAll('ok-status-pill').map((p) => p.attributes('label'));

beforeEach(() => {
  lifecycle.willEnter.length = 0;
  lifecycle.didLeave.length = 0;
  fetchPrintHosts.mockReset().mockResolvedValue({ coverage: [] });
  fetchWhatsAppNumbers.mockReset().mockResolvedValue(DOWN);
});

describe('the home panel re-reads its health strip when it comes back on screen (hub#2064)', () => {
  it('drops the WhatsApp warning after the owner reconnects it in another screen and comes back', async () => {
    const wrapper = mountDashboard();
    await flushPromises();
    fire('willEnter'); // first entry, right after the mount
    await flushPromises();
    expect(pillKeys(wrapper)).toContain('system.health.whatsappDown');

    fire('didLeave'); // off to the module settings to reconnect
    fetchWhatsAppNumbers.mockResolvedValue(BACK);
    fire('willEnter'); // back on the home panel, same cached instance
    await flushPromises();

    expect(pillKeys(wrapper)).not.toContain('system.health.whatsappDown');
  });

  it('asks the printer coverage again on the way back, not only WhatsApp', async () => {
    mountDashboard();
    await flushPromises();
    fire('willEnter');
    await flushPromises();
    const before = fetchPrintHosts.mock.calls.length;

    fire('didLeave');
    fire('willEnter');
    await flushPromises();

    expect(fetchPrintHosts.mock.calls.length).toBe(before + 1);
  });

  it('does not read twice on the first entry, when the mount has just read it', async () => {
    mountDashboard();
    await flushPromises();
    fire('willEnter');
    await flushPromises();

    expect(fetchPrintHosts).toHaveBeenCalledTimes(1);
    expect(fetchWhatsAppNumbers).toHaveBeenCalledTimes(1);
  });
});
