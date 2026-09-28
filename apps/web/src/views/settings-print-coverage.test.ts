// @vitest-environment happy-dom
// **Settings › Receipts shows who is printing each kind of ticket — and who is NOT** (hub#800).
//
// The runtime has answered `GET /api/print/hosts` with per-role coverage since hub#748/#749, and
// no screen ever read it. A coverage failure does not look like a failure: the sale closes with a
// 200 and the kitchen ticket just never prints, in another room. These tests mount the REAL
// SettingsPage over the REAL print-coverage lib with only `fetch` stubbed (hub#770), and pin the
// four states the owner can meet: the alarm, the reassurance, "could not check", and silence.
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
  useRoute: () => ({ hash: '#tickets', query: {} }),
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
// The runtime lib is mocked for the OTHER onMounted reads of this page (certificate, modules) —
// but the two constants the REAL print-coverage lib imports from it must keep working.
vi.mock('../lib/runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
  listInstalledModules: vi.fn().mockResolvedValue([]),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  getBusinessCertificate: vi.fn().mockResolvedValue({ present: false }),
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

/** A stub that DOES render what it wraps (a plain stub drops its slot). */
const PASSTHROUGH = { template: '<div><slot /></div>' };

/** Answers /api/print/hosts with `payload`; any other URL of this page 404s quietly. */
function stubHostsFetch(payload: unknown, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: unknown) => {
      if (String(url).includes('/api/print/hosts')) {
        return new Response(JSON.stringify(payload), { status });
      }
      return new Response('{}', { status: 404 });
    }),
  );
}

async function mountTicketsTab() {
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

describe('Settings › Receipts · print coverage (hub#800)', () => {
  it('shouts when tickets are waiting and nobody is printing them', async () => {
    stubHostsFetch({
      ok: true,
      hosts: [],
      coverage: [{ role: 'kitchen', waiting: 3, liveHosts: 0 }],
    });
    const wrapper = await mountTicketsTab();

    const alarm = wrapper.find('[data-status="stalled"]');
    expect(alarm.exists(), 'the stalled role renders as an alarm row').toBe(true);
    // The sentence the issue quotes, verbatim from the shipped catalogue: the wording IS the feature.
    expect(alarm.text()).toContain('Nobody is printing these');
    expect(alarm.text()).toContain('3');
    expect(alarm.text()).toContain(en.print.roleKitchen);
  });

  it('reassures with WHO is printing when a live host covers the role', async () => {
    stubHostsFetch({
      ok: true,
      hosts: [
        {
          deviceId: 'dev-1',
          role: 'receipt',
          label: 'Counter till',
          live: true,
          registeredAt: '',
          registeredBy: '',
          lastSeenAt: '',
        },
      ],
      coverage: [{ role: 'receipt', waiting: 0, liveHosts: 1 }],
    });
    const wrapper = await mountTicketsTab();

    const row = wrapper.find('[data-status="ready"]');
    expect(row.exists()).toBe(true);
    expect(row.text()).toContain('Counter till');
  });

  it('marks lost coverage — a host that stopped reporting — without inventing waiting work', async () => {
    stubHostsFetch({
      ok: true,
      hosts: [],
      coverage: [{ role: 'bar', waiting: 0, liveHosts: 0 }],
    });
    const wrapper = await mountTicketsTab();

    expect(wrapper.find('[data-status="unattended"]').exists()).toBe(true);
    expect(wrapper.find('[data-status="stalled"]').exists()).toBe(false);
  });

  it('a refusal reads "could not check" — never an empty green screen (hub#375)', async () => {
    stubHostsFetch({ ok: false }, 401);
    const wrapper = await mountTicketsTab();

    expect(wrapper.find('.print-coverage-error').exists()).toBe(true);
    expect(wrapper.find('[data-status]').exists(), 'no per-role row is invented').toBe(false);
  });

  it('stays quiet when the business never printed anything: no rows, no warning', async () => {
    stubHostsFetch({ ok: true, hosts: [], coverage: [] });
    const wrapper = await mountTicketsTab();

    expect(wrapper.find('[data-status]').exists()).toBe(false);
    expect(wrapper.find('.print-coverage-error').exists()).toBe(false);
  });
});
