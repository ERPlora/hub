// @vitest-environment happy-dom
// The Resources tab stops guessing from one instant sample (saas#1511): CPU, memory and DB
// connections become `ok-resource-usage` panels fed with the SERIES the SaaS records for this
// hub, proxied by the runtime (`GET /api/system/usage-series?range=`). What these tests pin:
//
//   1. **The range selector stops at 3 days.** The contract offers 3h/24h/3d and nothing else —
//      a longer range would only pretend the SaaS keeps history it does not serve.
//   2. **A dead series endpoint is not a dead screen.** The panels say «we could not read this»
//      (known:false — the component paints that state itself, ADR-0237) while the instant values
//      from `/api/system` are still handed over as `current`: measured is measured.
//   3. **The thresholds are the SaaS's 70/80.** The old local [70/90/100] gauge zones retire —
//      two sources of truth about when a hub is «hot» is how panels contradict alert emails.
//   4. **The plan pressure is the hub's to say, and the Play copy does not say it** (hub#1922). The
//      SaaS attaches an upgrade link and a sentence per metric, but both are PROSE of a machine
//      call — English whatever the person reads — and the link is a relative `/pricing/` that the
//      panel paints as an `<a href>`: it took the hub's own window to «this page does not exist».
//      The hub reads only the codes (`status`, `current`, `upgrade.show`), words them itself, and
//      walks to the plan through the one door that asks who distributed this copy (hub#756).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import type { DeviceContext } from '../lib/device';
import type { UsageSeries } from '../lib/system-usage';

const contractSeries: UsageSeries = {
  range: '24h',
  step_seconds: 900,
  generated_at: '2026-08-15T10:00:00Z',
  thresholds: { warning: 70, critical: 80 },
  metrics: {
    cpu: {
      known: true,
      unit: '%',
      current: 42.5,
      status: 'ok',
      points: [
        [1755100800, 38.2],
        [1755101700, 42.5],
      ],
      message: null,
    },
    ram: {
      known: true,
      unit: '%',
      current: 61,
      status: 'warning',
      points: [[1755100800, 58]],
      message: null,
    },
    db_connections: {
      known: true,
      unit: 'connections',
      current: 3,
      status: 'ok',
      points: [[1755100800, 2]],
      message: null,
    },
  },
  upgrade: { show: false, reason: null, message: null, url: null },
};

const { fetchUsageSeriesMock } = vi.hoisted(() => ({
  fetchUsageSeriesMock: vi.fn<() => Promise<UsageSeries | null>>(async () => contractSeries),
}));

// SystemPage reads the modules with a bell counter (hub#2306) through `module-loader`, whose icon
// chain (`~icons/…?raw`) the vitest transform denies — stubbed like DataPanel/dashboard-widgets.
vi.mock('../lib/module-loader', () => ({ loadInstalledManifests: vi.fn(async () => []) }));
vi.mock('../lib/system-usage', async () => {
  const actual = await vi.importActual<typeof import('../lib/system-usage')>('../lib/system-usage');
  return { ...actual, fetchUsageSeries: fetchUsageSeriesMock };
});

// The instant reading of `/api/system` stays the fallback `current`: CPU 42 %, memory 50 %,
// three DB connections.
vi.mock('../lib/system', () => ({
  fetchSystemInfo: vi.fn(async () => ({
    backend: 'cloud',
    shell: 'web',
    cpu: { usedLabel: '0,4 cores', fraction: 0.42 },
    memory: { usedLabel: '256 MB', fraction: 0.5 },
    database: { engine: 'postgres', connections: 3, connectionsLimit: 20 },
    logs: [],
  })),
}));

// Which copy of the app is asking (hub#756): a browser by default — no shell, no `distribution`.
const { getDeviceContextMock, isTauriMock, saasDoorMock } = vi.hoisted(() => ({
  getDeviceContextMock: vi.fn<() => Promise<DeviceContext | null>>(async () => null),
  isTauriMock: vi.fn(() => false),
  saasDoorMock: vi.fn(async (_path: string, url: string, _reason: string) => `${url}&pass=one-shot`),
}));

vi.mock('../lib/device', async () => {
  const actual = await vi.importActual<typeof import('../lib/device')>('../lib/device');
  return {
    ...actual,
    isTauri: isTauriMock,
    invokeTauri: vi.fn(async () => ({})),
    getDeviceContext: getDeviceContextMock,
  };
});
vi.mock('../lib/saas-door', () => ({ saasDoor: saasDoorMock }));

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return { ...actual, listInstalledModules: vi.fn(async () => []) };
});

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
vi.mock('../components/HubIcon.vue', () => ({
  default: { name: 'HubIcon', template: '<span />' },
}));
vi.mock('vue-router', () => ({
  useRoute: () => ({ hash: '' }),
  useRouter: () => ({ replace: vi.fn() }),
}));

import SystemPage from './SystemPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { openExternal } from '../lib/open-external';
import { upgradePlanPath, upgradePlanUrl } from '../lib/upgrade-plan-link';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** The `.metric` JS prop the fixed `ok-resource-usage` contract receives. */
interface PanelMetric {
  known: boolean;
  current: number | null;
  points: [number, number][];
  status: string;
  message: string | null;
}

type PanelElement = HTMLElement & {
  metric?: PanelMetric;
  thresholds?: { warning: number; critical: number };
  upgrade?: { show: boolean; message?: string | null; url?: string | null } | null;
};

async function mountSystem() {
  const wrapper = mount(SystemPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  await flushPromises();
  return wrapper;
}

function panels(wrapper: Awaited<ReturnType<typeof mountSystem>>): PanelElement[] {
  return wrapper.findAll('ok-resource-usage').map((p) => p.element as PanelElement);
}

beforeEach(() => {
  fetchUsageSeriesMock.mockClear();
  fetchUsageSeriesMock.mockResolvedValue(contractSeries);
  getDeviceContextMock.mockReset();
  getDeviceContextMock.mockResolvedValue(null);
  isTauriMock.mockReturnValue(false);
  saasDoorMock.mockClear();
  vi.mocked(openExternal).mockClear();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('the range selector', () => {
  it('caps at 3 days: exactly 3h / 24h / 3d, nothing longer', async () => {
    const wrapper = await mountSystem();

    // The options the person can actually read: exactly three buttons, the longest being
    // 3 days. (`value` travels as a component prop and happy-dom keeps slotted text out of
    // `textContent`, so the serialized markup is the observable truth here.)
    const segment = wrapper.find('.usage-range');
    expect(segment.findAll('ion-segment-button')).toHaveLength(3);
    const html = segment.html();
    expect(html).toContain(en.system.usageRange3h);
    expect(html).toContain(en.system.usageRange24h);
    expect(html).toContain(en.system.usageRange3d);
  });
});

describe('the three usage panels', () => {
  it('replace the gauges: CPU, memory and connections are ok-resource-usage now', async () => {
    const wrapper = await mountSystem();

    expect(panels(wrapper)).toHaveLength(3);
    expect(wrapper.findAll('ok-gauge')).toHaveLength(0);
  });

  it('feed on the series, preferring the SaaS current over the local instant one', async () => {
    const wrapper = await mountSystem();

    const [cpu, ram, connections] = panels(wrapper);
    expect(cpu.metric).toMatchObject({ known: true, current: 42.5, status: 'ok' });
    expect(cpu.metric?.points).toEqual(contractSeries.metrics.cpu.points);
    expect(ram.metric).toMatchObject({ known: true, current: 61, status: 'warning' });
    expect(connections.metric).toMatchObject({ known: true, current: 3 });
  });

  it('show the unreadable state when the series endpoint fails, keeping local instant values', async () => {
    fetchUsageSeriesMock.mockResolvedValue(null);
    const wrapper = await mountSystem();

    const [cpu, ram, connections] = panels(wrapper);
    // known:false — the component paints «we could not read this» on its own (ADR-0237)…
    for (const panel of [cpu, ram, connections]) {
      expect(panel.metric?.known).toBe(false);
      expect(panel.metric?.points).toEqual([]);
    }
    // …but the instant values `/api/system` DID measure still travel as `current`.
    expect(cpu.metric?.current).toBe(42);
    expect(ram.metric?.current).toBe(50);
    expect(connections.metric?.current).toBe(3);
    // And the translated unreadable label is handed to the component, not hard-coded inside it.
    expect(cpu.getAttribute('unreadable-label')).toBe(en.system.health.notMeasured);
  });

  it('pass the 70/80 thresholds from the contract — the old 70/90/100 zones retire', async () => {
    const wrapper = await mountSystem();

    for (const panel of panels(wrapper)) {
      expect(panel.thresholds).toEqual({ warning: 70, critical: 80 });
    }
  });
});

describe('the copy, in both languages', () => {
  it('every range label exists in English and is translated in Spanish', () => {
    for (const key of ['usageRange3h', 'usageRange24h', 'usageRange3d'] as const) {
      expect(typeof en.system[key], key).toBe('string');
      expect(typeof es.system[key], key).toBe('string');
    }
    // «3 days» is the one with words in it: it must actually be translated.
    expect(es.system.usageRange3d).not.toBe(en.system.usageRange3d);
  });
});

describe('the plan pressure (hub#1922)', () => {
  // What the SaaS answered to the QA's Play tablet (v1.1.27): a free hub with memory at 77 % and
  // connections at 120 %, the sentences in English and the link relative to the SaaS.
  const underPressure: UsageSeries = {
    ...contractSeries,
    metrics: {
      ...contractSeries.metrics,
      ram: {
        ...contractSeries.metrics.ram,
        current: 77,
        status: 'warning',
        message: 'RAM usage is at 77% of your plan limit.',
      },
      db_connections: {
        known: true,
        unit: '%',
        current: 120,
        status: 'critical',
        points: [[1755100800, 120]],
        message: 'Database connections usage exceeds 120% of your plan limit — performance may degrade.',
      },
    },
    upgrade: { show: true, message: 'Upgrade from Free to Starter (CPU +100%).', url: '/pricing/' },
  };

  afterEach(() => {
    i18n.global.locale.value = 'en';
  });

  it('never hands the SaaS link to the panels: it took the hub window to a page that does not exist', async () => {
    fetchUsageSeriesMock.mockResolvedValue(underPressure);
    const wrapper = await mountSystem();

    for (const panel of panels(wrapper)) {
      expect(panel.upgrade?.show ?? false).toBe(false);
    }
  });

  it('words each notice itself, in the language of the person, from the codes of the series', async () => {
    i18n.global.locale.value = 'es';
    fetchUsageSeriesMock.mockResolvedValue(underPressure);
    const wrapper = await mountSystem();

    const [cpu, ram, connections] = panels(wrapper);
    expect(ram.metric?.message).toBe(i18n.global.t('system.usageNearLimit', { pct: 77 }));
    expect(connections.metric?.message).toBe(i18n.global.t('system.usageOverLimit', { pct: 120 }));
    // A metric with nothing to say says nothing — not an empty band.
    expect(cpu.metric?.message).toBeNull();
    // The Spanish is really Spanish, and it carries the figure.
    expect(es.system.usageNearLimit).not.toBe(en.system.usageNearLimit);
    expect(es.system.usageOverLimit).not.toBe(en.system.usageOverLimit);
    expect(ram.metric?.message).toContain('77');
  });

  it('offers the plan door once, in the person\'s words, where this copy may offer it', async () => {
    fetchUsageSeriesMock.mockResolvedValue(underPressure);
    const wrapper = await mountSystem();

    const notice = wrapper.find('[data-testid="system-plan-pressure"]');
    expect(notice.exists()).toBe(true);
    expect(notice.text()).toContain(en.system.planPressure);
    const doors = wrapper.findAll('[data-testid="system-upgrade-plan"]');
    expect(doors).toHaveLength(1);

    await doors[0].trigger('click');
    await flushPromises();

    // Out through the shared door (one-time pass, pm#196) to THIS hub's plan page — never the
    // hub's own window, never the pricing grid.
    expect(saasDoorMock).toHaveBeenCalledWith(upgradePlanPath(), upgradePlanUrl(), 'upgrade-plan');
    expect(openExternal).toHaveBeenCalledWith(`${upgradePlanUrl()}&pass=one-shot`);
  });

  it('offers nothing on the copy Google Play distributes: no link, no button, no invitation', async () => {
    getDeviceContextMock.mockResolvedValue({ distribution: 'play' } as DeviceContext);
    fetchUsageSeriesMock.mockResolvedValue(underPressure);
    const wrapper = await mountSystem();

    expect(wrapper.find('[data-testid="system-plan-pressure"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="system-upgrade-plan"]').exists()).toBe(false);
    for (const panel of panels(wrapper)) {
      expect(panel.upgrade?.show ?? false).toBe(false);
    }
  });

  it('inside the installed app, stays closed until the shell has said which copy this is', async () => {
    isTauriMock.mockReturnValue(true);
    getDeviceContextMock.mockReturnValue(new Promise(() => {}));
    fetchUsageSeriesMock.mockResolvedValue(underPressure);
    const wrapper = await mountSystem();

    expect(wrapper.find('[data-testid="system-plan-pressure"]').exists()).toBe(false);
  });

  it('says nothing about the plan while the plan is not under pressure', async () => {
    const wrapper = await mountSystem();

    expect(wrapper.find('[data-testid="system-plan-pressure"]').exists()).toBe(false);
  });
});
