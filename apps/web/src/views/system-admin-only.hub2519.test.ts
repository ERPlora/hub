// @vitest-environment happy-dom
// hub#2519 — the System state is an owner's or an administrator's, and the screen knows it.
//
// The runtime answers `GET /api/system` (the event log with each event's last error, the server's
// usage, the storage) with `403` to anyone who does not administer the hub: a refused VeriFactu
// record leaves the tax agency's Fault there, with the customer's tax id and name. The screen is
// still everybody's — the printer, the device's notices and the app download are what a cashier at
// the counter comes here for — so for someone who does not administer the hub it must:
//
//   1. not ask for the state (a refusal would paint «Could not reach the system» on a page that
//      works), nor for the usage series it would only pair with it;
//   2. not paint the server's usage nor the version pill, which would only say «we could not read
//      this» about something they are not meant to read;
//   3. not offer the Logs tab — and an address with `#logs` lands on Resources, not on an empty log
//      that reads as «nothing happened».
//
// An administrator keeps all of it, also when the session resolves after the page was opened.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

const { admin, route } = await vi.hoisted(async () => {
  const vue = await import('vue');
  return { admin: vue.ref(false), route: vue.reactive({ path: '/system', hash: '' }) };
});

const { fetchSystemInfo, fetchUsageSeries } = vi.hoisted(() => ({
  fetchSystemInfo: vi.fn(),
  fetchUsageSeries: vi.fn(),
}));

vi.mock('../lib/session', async () => {
  const actual = await vi.importActual<typeof import('../lib/session')>('../lib/session');
  return { ...actual, isAdmin: admin, isAuthed: ref(true), user: ref({ id: 'someone' }) };
});
vi.mock('../lib/system', async () => {
  const actual = await vi.importActual<typeof import('../lib/system')>('../lib/system');
  return { ...actual, fetchSystemInfo };
});
vi.mock('../lib/system-usage', async () => {
  const actual = await vi.importActual<typeof import('../lib/system-usage')>('../lib/system-usage');
  return { ...actual, fetchUsageSeries };
});
vi.mock('../lib/module-loader', () => ({ loadInstalledManifests: vi.fn(async () => []) }));
vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return { ...actual, listInstalledModules: vi.fn(async () => []), listModuleUpdates: vi.fn(async () => []) };
});
vi.mock('../lib/update-history', async () => {
  const actual = await vi.importActual<typeof import('../lib/update-history')>('../lib/update-history');
  return { ...actual, fetchUpdateHistory: vi.fn(async () => []) };
});
vi.mock('../lib/bell-counters', () => ({ loadBellCounterModuleIds: vi.fn(async () => new Set()) }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/toast', () => ({
  toast: vi.fn(),
  toastInfo: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/PlanLimitsPanel.vue', () => ({
  default: { name: 'PlanLimitsPanel', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import SystemPage from './SystemPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const STATE = {
  backend: 'cloud',
  shell: 'web',
  hubVersion: 'v1.4.0',
  cpu: { usedLabel: '0,4 cores', fraction: 0.42 },
  memory: { usedLabel: '256 MB', fraction: 0.5 },
  database: { engine: 'postgres', connections: 3, connectionsLimit: 20 },
  logs: [{ when: '2026-10-06T10:00:00Z', level: 'ERROR', message: 'sale.closed', meta: 'AEAT 4102' }],
};

async function mountSystem() {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    fallbackLocale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en, es },
  });
  const wrapper = mount(SystemPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  await flushPromises();
  return wrapper;
}

// Every page mounted here watches the same `isAdmin`: one left alive would answer the next test.
enableAutoUnmount(afterEach);

type Wrapper = Awaited<ReturnType<typeof mountSystem>>;
// `value` travels as a component prop and happy-dom keeps slotted text out of `textContent`, so the
// tab bar's serialized markup is the observable truth.
const offersLogsTab = (w: Wrapper) => w.find('.ok-tabbar').html().includes(`>${en.system.tabLogs}<`);
const versionPill = (w: Wrapper) =>
  w.findAll('ok-status-pill').filter((p) => p.text().includes('1.4.0') || p.text().includes('—'));

beforeEach(() => {
  admin.value = false;
  route.path = '/system';
  route.hash = '';
  fetchSystemInfo.mockReset();
  fetchSystemInfo.mockResolvedValue(STATE);
  fetchUsageSeries.mockReset();
  fetchUsageSeries.mockResolvedValue(null);
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('someone who does not administer the hub', () => {
  it('does not ask for the system state nor the usage series, and sees no load error', async () => {
    const wrapper = await mountSystem();

    expect(fetchSystemInfo).not.toHaveBeenCalled();
    expect(fetchUsageSeries).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain(en.system.loadErrorTitle);
    expect(wrapper.find('ion-spinner').exists()).toBe(false);
  });

  it('sees no server usage and no Logs tab', async () => {
    const wrapper = await mountSystem();

    expect(wrapper.findAll('ok-resource-usage')).toHaveLength(0);
    expect(wrapper.find('.usage-range').exists()).toBe(false);
    expect(offersLogsTab(wrapper)).toBe(false);
  });

  it('is told on Resources why the server usage is not there, instead of a blank card', async () => {
    const wrapper = await mountSystem();

    const note = wrapper.find('[data-testid="system-resources-admin-only"]');
    expect(note.exists()).toBe(true);
    expect(note.text()).toBe((en.system as Record<string, unknown>).resourcesAdminOnly);
  });

  it('lands on Resources from an address with #logs, never on an empty log', async () => {
    route.hash = '#logs';
    const wrapper = await mountSystem();

    expect(wrapper.text()).not.toContain(en.system.eventLog);
    expect(wrapper.text()).not.toContain(en.system.noEvents);
  });

  it('sees the update history without a version pill it could not fill', async () => {
    route.hash = '#updates';
    const wrapper = await mountSystem();

    expect(wrapper.text()).toContain(en.system.updateHistory);
    expect(versionPill(wrapper)).toHaveLength(0);
  });
});

describe('an owner or an administrator', () => {
  it('reads the state, the usage and the Logs tab', async () => {
    admin.value = true;
    const wrapper = await mountSystem();

    expect(fetchSystemInfo).toHaveBeenCalledTimes(1);
    expect(fetchUsageSeries).toHaveBeenCalled();
    expect(wrapper.findAll('ok-resource-usage')).toHaveLength(3);
    expect(offersLogsTab(wrapper)).toBe(true);
    expect(wrapper.find('[data-testid="system-resources-admin-only"]').exists()).toBe(false);
  });

  it('reads the log on #logs', async () => {
    admin.value = true;
    route.hash = '#logs';
    const wrapper = await mountSystem();

    expect(wrapper.text()).toContain(en.system.eventLog);
    expect(wrapper.text()).not.toContain(en.system.noEvents);
  });

  it('gets the state once the session resolves as an administrator after the page opened', async () => {
    route.hash = '#updates';
    const wrapper = await mountSystem();
    expect(fetchSystemInfo).not.toHaveBeenCalled();

    admin.value = true;
    await flushPromises();

    expect(fetchSystemInfo).toHaveBeenCalledTimes(1);
    expect(fetchUsageSeries).toHaveBeenCalled();
    expect(
      versionPill(wrapper)
        .map((p) => p.text())
        .join(' '),
    ).toContain('1.4.0');
  });
});
