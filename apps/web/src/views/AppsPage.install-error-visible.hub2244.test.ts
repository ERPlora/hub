// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2244 — on a desktop, a failed install left no readable trace: the
// dialog closed, the row went back to «Available», and the only sign of the failure was a red toast
// that lasted 2.5 s, bounced at the very bottom edge of the window and sat ON TOP of the Apps tab
// bar. Whoever pressed «Install and grant» could not tell whether the click had registered, what
// went wrong, or whether to try again.
//
// What this pins, on the wiring of AppsPage itself (not on a helper it might stop calling):
//   · an install failure stays on screen until the person closes it (duration 0), in red;
//   · it offers «Retry», which asks the runtime to install the SAME app and version again, and
//     «Close»;
//   · every notice of the page is anchored to the Apps footer, so it sits ABOVE the tab bar instead
//     of under the window edge / over the tabs (the geometry itself is measured in the real
//     browser by tests/e2e/InstallErrorVisible.spec.ts);
//   · the sticky «blocked» notice (ADR-0060) can be closed too.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, ref } from 'vue';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '' }),
}));
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
// The Ionic page lifecycle, captured so a test can walk away from Apps and back (hub#2249 review).
const { lifecycle } = vi.hoisted(() => ({
  lifecycle: { willEnter: [] as Array<() => void>, willLeave: [] as Array<() => void> },
}));
// The global notices the page hands over to once it is unmounted (hub#2252). A spy: happy-dom
// cannot animate a real overlay (the browser side is tests/e2e/InstallResultAfterLeaving.spec.ts).
const { globalToasts } = vi.hoisted(() => ({
  globalToasts: [] as Array<{ opts: Record<string, unknown>; dismissed: boolean }>,
}));
vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  onIonViewWillEnter: (fn: () => void) => lifecycle.willEnter.push(fn),
  onIonViewWillLeave: (fn: () => void) => lifecycle.willLeave.push(fn),
  toastController: {
    create: async (opts: Record<string, unknown>) => {
      const entry = { opts, dismissed: false };
      globalToasts.push(entry);
      return {
        present: async () => {},
        dismiss: async () => {
          entry.dismissed = true;
        },
      };
    },
  },
}));

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
const requestInstallMock = vi.fn();

const { InstallBlockedError } = vi.hoisted(() => ({
  InstallBlockedError: class InstallBlockedError extends Error {
    blockedOn: string[];
    constructor(message: string, blockedOn: string[]) {
      super(message);
      this.blockedOn = blockedOn;
    }
  },
}));

vi.mock('../lib/cloud', () => ({
  cloudMarketplaceModules: async () => CATALOG,
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: (moduleId: string, version: string) => requestInstallMock(moduleId, version),
  listInstalledModules: async () => [],
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  // No capabilities anywhere → no consent modal: the install runs straight through.
  getModuleCapabilities: vi.fn().mockRejectedValue(new Error('unknown module')),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError,
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: vi.fn(),
  listModuleUpdates: async () => [],
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
type ToastButton = { text: string; role?: string; handler?: () => unknown };

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

const catalogTable = (w: Wrapper): TableEl => w.findAll('ok-data-table').map((t) => t.element as TableEl)[1];

/** The page's single `<ion-toast>` (stubbed by `shallow`, but it keeps the props it was bound). */
function toast(w: Wrapper) {
  const stub = w.findComponent({ name: 'IonToast' });
  return {
    message: stub.props('message') as string,
    color: stub.props('color') as string,
    duration: stub.props('duration') as number,
    positionAnchor: stub.props('positionAnchor') as string | undefined,
    buttons: (stub.props('buttons') ?? []) as ToastButton[],
  };
}

/** A request-install failure as `requestInstall` throws it: the runtime's sentence rides in `detail`. */
const runtimeFailure = (sentence: string): Error =>
  Object.assign(new Error('request-install flows → 502'), { detail: sentence });

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
  await nextTick();
}

async function pressInstall(w: Wrapper, id: string): Promise<void> {
  const row = (catalogTable(w).rows ?? []).find((r) => r.id === id);
  expect(row, `the catalogue must list ${id}`).toBeTruthy();
  catalogTable(w).dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'install', row } }));
  await settle();
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  CATALOG = [catalogueEntry('flows', 'Automations')];
  moduleNav.value = [];
  requestInstallMock.mockReset();
  lifecycle.willEnter.length = 0;
  lifecycle.willLeave.length = 0;
  globalToasts.length = 0;
});

describe('a failed install stays readable and can be retried (hub#2244)', () => {
  it('stays on screen in red until closed, with the runtime sentence', async () => {
    requestInstallMock.mockRejectedValue(runtimeFailure('The marketplace did not answer'));
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');

    const n = toast(w);
    expect(n.message).toBe('The marketplace did not answer');
    expect(n.color).toBe('danger');
    // 0 = sticky. It was 2500: the error was gone before anyone could read it.
    expect(n.duration).toBe(0);
  });

  it('offers «Retry» — the same app and version again — and «Close»', async () => {
    requestInstallMock.mockRejectedValue(runtimeFailure('The marketplace did not answer'));
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');

    const { buttons } = toast(w);
    expect(buttons.map((b) => b.text)).toEqual([enCatalogue.apps.installRetry, enCatalogue.apps.noticeClose]);
    const close = buttons[1];
    expect(close.role).toBe('cancel');
    expect(requestInstallMock).toHaveBeenCalledTimes(1);

    requestInstallMock.mockResolvedValue({
      ok: true,
      module_id: 'flows',
      version: '1.0.0',
      status: 'installed',
      also_installed: [],
    });
    await buttons[0].handler?.();
    await settle();

    expect(requestInstallMock).toHaveBeenCalledTimes(2);
    expect(requestInstallMock).toHaveBeenLastCalledWith('flows', 'latest');
    expect(toast(w).message).toBe(enCatalogue.apps.installSuccess.replace('{name}', 'Automations'));
  });

  it('says «Reintentar» and «Cerrar» in Spanish', async () => {
    requestInstallMock.mockRejectedValue(runtimeFailure('El marketplace no respondió'));
    const w = mountApps('es');
    await settle();
    await pressInstall(w, 'flows');

    expect(toast(w).buttons.map((b) => b.text)).toEqual(['Reintentar', 'Cerrar']);
    expect(esCatalogue.apps.installRetry).toBe('Reintentar');
    expect(esCatalogue.apps.noticeClose).toBe('Cerrar');
  });

  it('the «Installing…» notice closing late does not take the error down with it', async () => {
    // In the browser the chain is: «Installing…» is presented, the failure arrives, the page closes
    // it and opens the error — and only THEN does Ionic finish dismissing «Installing…» and fire its
    // `didDismiss`. That late event used to set `isOpen = false` and close the error ~0.3 s after it
    // rose: the red flash at the bottom edge of hub#2244.
    let fail: (e: unknown) => void = () => {};
    requestInstallMock.mockImplementation(
      () =>
        new Promise((_, reject) => {
          fail = reject;
        }),
    );
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');
    expect(toast(w).message).toBe(enCatalogue.apps.installing.replace('{name}', 'Automations'));

    fail(runtimeFailure('The marketplace did not answer'));
    await settle();
    const stub = w.findComponent({ name: 'IonToast' });
    expect(stub.props('message')).toBe('The marketplace did not answer');

    stub.vm.$emit('didDismiss');
    await settle();
    expect(stub.props('isOpen')).toBe(true);

    // …while closing the error ITSELF (its «Close» button) does close it.
    stub.vm.$emit('didDismiss');
    await settle();
    expect(stub.props('isOpen')).toBe(false);
  });

  it('is anchored to the Apps footer, so it sits above the tab bar', async () => {
    requestInstallMock.mockRejectedValue(runtimeFailure('boom'));
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');

    expect(toast(w).positionAnchor).toBe('apps-footer');
  });

  it('a failure that lands after the person left Apps is not anchored to the hidden footer', async () => {
    // Ionic keeps a page it navigated away from in the DOM, hidden: a notice anchored to its footer
    // is placed from a zero-size box and rises ABOVE the top edge of the window (measured at
    // top -61 px on a 1080 px bench). The error of an install still running when the person left
    // has to show where they are now, at the bottom of the window.
    let fail: (e: unknown) => void = () => {};
    requestInstallMock.mockImplementation(
      () =>
        new Promise((_, reject) => {
          fail = reject;
        }),
    );
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');
    expect(toast(w).positionAnchor).toBe('apps-footer');

    lifecycle.willLeave.forEach((fn) => fn());
    fail(runtimeFailure('The marketplace did not answer'));
    await settle();
    expect(toast(w).message).toBe('The marketplace did not answer');
    // Unset (the stub reports Ionic Vue's empty-prop sentinel, not `undefined`): no anchor at all.
    expect(typeof toast(w).positionAnchor).not.toBe('string');

    // Back on Apps, its notices sit above the tab bar again.
    lifecycle.willEnter.forEach((fn) => fn());
    requestInstallMock.mockRejectedValue(runtimeFailure('boom'));
    await toast(w).buttons[0].handler?.();
    await settle();
    expect(toast(w).message).toBe('boom');
    expect(toast(w).positionAnchor).toBe('apps-footer');
  });

  it('leaving Apps for good while it installs hands the notice, and then the outcome, to a global one (hub#2252)', async () => {
    // Leaving through the side menu UNMOUNTS the page; its inline toast would stay over the next
    // screen saying «Installing…» for good, and the outcome would land in a page that is gone.
    let fail: (e: unknown) => void = () => {};
    requestInstallMock.mockImplementation(
      () =>
        new Promise((_, reject) => {
          fail = reject;
        }),
    );
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');
    const installing = enCatalogue.apps.installing.replace('{name}', 'Automations');
    expect(toast(w).message).toBe(installing);

    mounted.splice(mounted.indexOf(w), 1);
    w.unmount();
    await settle();
    expect(globalToasts.map((g) => g.opts.message)).toEqual([installing]);

    fail(runtimeFailure('The marketplace did not answer'));
    await settle();
    expect(globalToasts.map((g) => g.opts.message)).toEqual([installing, 'The marketplace did not answer']);
    expect(globalToasts[0].dismissed).toBe(true);
    const error = globalToasts[1].opts;
    expect(error.color).toBe('danger');
    expect(error.duration).toBe(0);
    expect((error.buttons as ToastButton[]).map((b) => b.text)).toEqual([
      enCatalogue.apps.installRetry,
      enCatalogue.apps.noticeClose,
    ]);
  });

  it('the sticky «blocked» notice can be closed (no Retry: nothing changes until they subscribe)', async () => {
    requestInstallMock.mockRejectedValue(new InstallBlockedError('blocked', ['Payroll']));
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');

    const n = toast(w);
    expect(n.color).toBe('danger');
    expect(n.duration).toBe(0);
    expect(n.buttons.map((b) => b.text)).toEqual([enCatalogue.apps.noticeClose]);
    expect(n.buttons[0].role).toBe('cancel');
  });

  it('a success still goes away on its own (no buttons, not sticky)', async () => {
    requestInstallMock.mockResolvedValue({
      ok: true,
      module_id: 'flows',
      version: '1.0.0',
      status: 'installed',
      also_installed: [],
    });
    const w = mountApps('en');
    await settle();
    await pressInstall(w, 'flows');

    const n = toast(w);
    expect(n.color).toBe('success');
    expect(n.duration).toBeGreaterThan(0);
    expect(n.buttons).toEqual([]);
  });
});
