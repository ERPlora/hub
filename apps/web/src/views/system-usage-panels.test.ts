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
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

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

vi.mock('../lib/device', async () => {
  const actual = await vi.importActual<typeof import('../lib/device')>('../lib/device');
  return { ...actual, isTauri: () => false, invokeTauri: vi.fn(async () => ({})) };
});

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
  upgrade?: { show: boolean };
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
