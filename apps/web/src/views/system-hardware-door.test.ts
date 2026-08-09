// @vitest-environment happy-dom
// **Which door does the System screen knock on when it asks "is there a printer here?"**
// (hub#524, and with it hub#500 and hub#507 — the same card telling the same three lies.)
//
// There are two doors to the same question, and this screen used the one ADR-0196 walled up:
//
//   | who asks            | how                                              | inside the app |
//   |---------------------|--------------------------------------------------|----------------|
//   | the modules         | `erplora.peripherals.detect()` → `invoke`        | **online**     |
//   | the System screen   | `detectBridge()` → `GET localhost:12321/status`  | offline        |
//
// The second row is a daemon that no longer exists: hub#339 removed its only client and hub#340
// deleted the binary. So `detectBridge()` answered `{online:false}` **everywhere, always** — and
// the card built on it told an owner standing inside `com.erplora.app`, with a printer answering
// two feet away, to go and install the app they were already using. No error, no log, no way to
// notice: **a calm sentence that is false**. It is the hub#338 pattern again — showing the
// sentence of another state sends someone to fix what was never broken.
//
// So these tests mount the real screen and assert what the owner READS, on both surfaces:
//
//   1. **The installed app asks the module door** and, when the hardware answers, is never offered
//      the installation steps.
//   2. **A plain browser still tells the truth** — no hardware there, and that is not a bug.
//   3. **What it offers has the right name and the right address**: the app is called ERPlora
//      (ADR-0254 keeps platform jargon out of the hub's screens) and the button hands out
//      `/app/download/`, not the `/bridge/download/` that still serves `erplora-bridge.exe`.
//
// The copy is asserted against the REAL catalogues, English and Spanish: the wording *is* the
// feature here, and checking it against strings invented in this file would test nothing.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { tauriMode, invokeSpy } = vi.hoisted(() => ({
  /** Are we inside `com.erplora.app`? Flipped per test — it is the whole point of the suite. */
  tauriMode: { value: false },
  invokeSpy: vi.fn<(cmd: string, args?: Record<string, unknown>) => Promise<unknown>>(
    async () => ({ version: '1.4.0' }),
  ),
}));

// Partial mocks: the surface is a double, everything else stays real. A wholesale mock of these
// modules would have to re-declare every export the import graph reaches for, and the first one
// forgotten fails as "no export defined" instead of as the behaviour under test.
vi.mock('../lib/device', async () => {
  const actual = await vi.importActual<typeof import('../lib/device')>('../lib/device');
  return { ...actual, isTauri: () => tauriMode.value, invokeTauri: invokeSpy };
});

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return {
    ...actual,
    // The card only exists when this hub prints (hub#375), so printing is installed and running.
    listInstalledModules: vi.fn(async () => [{ id: 'printing', status: 'active' }]),
  };
});

vi.mock('../lib/system', () => ({ fetchSystemInfo: vi.fn(async () => null) }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/toast', () => ({
  toast: vi.fn(),
  toastInfo: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

// The chrome around the card is not what is being tested, and AppPage drags the topbar, the
// sidebar and the setup strip behind it.
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
import { openExternal } from '../lib/open-external';
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

/** Fetch, replaced by a mock that refuses everything: no test of ours may leave this machine. */
let fetchSpy: ReturnType<typeof vi.fn>;

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

/** Every address this render tried to reach. */
function fetchedUrls(): string[] {
  return fetchSpy.mock.calls.map((call) => String(call[0]));
}

beforeEach(() => {
  invokeSpy.mockClear();
  vi.mocked(openExternal).mockClear();
  fetchSpy = vi.fn(async () => {
    throw new Error('the network is not part of this test');
  });
  vi.stubGlobal('fetch', fetchSpy);
});

describe('inside the installed app, where the hardware actually lives', () => {
  beforeEach(() => {
    tauriMode.value = true;
  });

  it('asks the door the modules use, and never the port of the retired daemon', async () => {
    await mountSystem();

    // `erplora.peripherals` in one line: the same `invoke` the printing module goes through.
    expect(invokeSpy).toHaveBeenCalledWith('erplora_bridge_status', {});
    expect(fetchedUrls().filter((url) => url.includes('12321'))).toEqual([]);
  });

  it('does not ask an owner whose printer answers to go and install one', async () => {
    const wrapper = await mountSystem();

    // The sentence, and then the absence of everything that contradicts it: no numbered steps,
    // no installer buttons. This is the whole bug — the card said «install the app» to the app.
    expect(wrapper.text()).toContain(en.system.health.printerReady);
    expect(wrapper.find('.bridge-steps').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Windows');
  });
});

describe('in a plain browser, where there is no hardware and that is the truth', () => {
  beforeEach(() => {
    tauriMode.value = false;
  });

  it('says the printer is not connected, and says how to get one', async () => {
    const wrapper = await mountSystem();

    expect(wrapper.text()).toContain(en.system.health.printerOffline);
    expect(wrapper.find('.bridge-steps').exists()).toBe(true);
  });

  it('names the ONE app it is offering, never the product ADR-0196 deleted', async () => {
    // hub#500. «Download ERPlora Bridge» and then «install ERPlora» are two names for one thing,
    // and «Bridge» is platform jargon that ADR-0254 keeps out of the hub's screens entirely.
    const wrapper = await mountSystem();

    expect(wrapper.text().toLowerCase()).not.toContain('bridge');
    expect(wrapper.text()).toContain(en.system.downloadApp);
  });

  it('hands out the installer of the APP, not the binary of the retired Bridge', async () => {
    // hub#507. `/bridge/download/windows/` serves `erplora-bridge.exe` — a product that no longer
    // exists. It does not fail and it does not warn: it downloads the wrong thing.
    const wrapper = await mountSystem();

    const windows = wrapper.findAll('ion-button').find((b) => b.text().includes('Windows'));
    expect(windows, 'the Windows installer button').toBeDefined();
    await windows!.trigger('click');
    await flushPromises();

    expect(openExternal).toHaveBeenCalledWith('https://erplora.com/app/download/windows/');
  });
});

describe('the copy, in both languages', () => {
  it('is translated, and neither language mentions the retired Bridge', () => {
    // English is the source and Spanish is what the owner reads: a string that never got its `es`
    // is the classic bug of this zone, and it does not crash — it just shows English to somebody
    // who does not read English.
    for (const catalogue of [en, es] as const) {
      for (const key of ['downloadApp', 'downloadAppHint', 'toastDownloadingApp'] as const) {
        const value = catalogue.system[key];
        expect(typeof value, key).toBe('string');
        expect(value.toLowerCase(), key).not.toContain('bridge');
      }
    }
    expect(es.system.downloadApp).not.toBe(en.system.downloadApp);
    expect(es.system.downloadAppHint).not.toBe(en.system.downloadAppHint);
  });
});
