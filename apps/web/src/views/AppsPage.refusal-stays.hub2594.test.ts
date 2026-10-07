// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2594 — in «My apps», when the hub refused to switch off, uninstall
// or update an app (VeriFactu still owes records to the AEAT, the business would be left with no
// fiscal app, other apps need it, the new version needs paid apps…), the reason came up in a red
// notice that went away on its own after 2.5 s. Those are long sentences that say what to do next:
// nobody could finish reading them, and the only way to see them again was to repeat the attempt.
//
// What this pins, on the wiring of AppsPage itself: every refusal of those three actions stays on
// screen in red until the person closes it (duration 0, «Close» with the cancel role) — the pattern
// the same screen already uses for a failed install (hub#2244). Successes still go away on their own.
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
// Every confirmation dialog of the page (switch off, uninstall) is answered «confirm».
vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  onIonViewWillEnter: () => {},
  onIonViewWillLeave: () => {},
  alertController: {
    create: async () => ({ present: async () => {}, onDidDismiss: async () => ({ role: 'confirm' }) }),
  },
}));

const { runtimeMocks, ModuleActionError, InstallBlockedError } = vi.hoisted(() => ({
  runtimeMocks: {
    deactivateModule: vi.fn(),
    activateModule: vi.fn(),
    uninstallModule: vi.fn(),
    updateModule: vi.fn(),
  },
  ModuleActionError: class ModuleActionError extends Error {
    code?: string;
    dependents?: readonly string[];
    constructor(message: string, code?: string, dependents?: readonly string[]) {
      super(message);
      this.code = code;
      this.dependents = dependents;
    }
  },
  InstallBlockedError: class InstallBlockedError extends Error {
    blockedOn: string[];
    constructor(message: string, blockedOn: string[]) {
      super(message);
      this.blockedOn = blockedOn;
    }
  },
}));

const INSTALLED = [{ id: 'verifactu', name: 'VeriFactu', version: '1.0.0', status: 'active' }];

vi.mock('../lib/cloud', () => ({ cloudMarketplaceModules: async () => [] }));
vi.mock('../lib/system', () => ({ fetchSystemInfo: async () => ({ hubVersion: 'v1.4.0' }) }));
vi.mock('../lib/module-loader', () => ({ reloadForModuleUpdate: vi.fn() }));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: vi.fn(),
  listInstalledModules: async () => INSTALLED,
  activateModule: (id: string) => runtimeMocks.activateModule(id),
  deactivateModule: (id: string) => runtimeMocks.deactivateModule(id),
  uninstallModule: (id: string, opts?: unknown) => runtimeMocks.uninstallModule(id, opts),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError,
  ModuleActionError,
  updateModule: (id: string, version?: string) => runtimeMocks.updateModule(id, version),
  listModuleUpdates: async () => [],
  // One version ahead: no «Choose a version» dialog.
  listModuleVersions: async () => ({ versions: ['2.0.0'] }),
  modulePublicationStatus: async () => null,
}));
vi.mock('../lib/nav', () => ({ moduleNav: { value: [] }, refreshModuleNav: vi.fn() }));
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
  const wrapper = mount(AppsPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
  mounted.push(wrapper);
  return wrapper;
}
type Wrapper = ReturnType<typeof mountApps>;

async function settle(): Promise<void> {
  for (let i = 0; i < 3; i += 1) {
    await flushPromises();
    await nextTick();
  }
}

/** The page's single `<ion-toast>` (stubbed by `shallow`, but it keeps the props it was bound). */
function toast(w: Wrapper) {
  const stub = w.findComponent({ name: 'IonToast' });
  return {
    message: stub.props('message') as string,
    color: stub.props('color') as string,
    duration: stub.props('duration') as number,
    buttons: (stub.props('buttons') ?? []) as ToastButton[],
  };
}

/** Presses `actionId` on the VeriFactu row of «My apps» (the first table of the page). */
async function press(w: Wrapper, actionId: 'toggle' | 'uninstall' | 'update'): Promise<void> {
  const mine = w.findAll('ok-data-table')[0].element;
  mine.dispatchEvent(new CustomEvent('rowAction', { detail: { actionId, row: { ...INSTALLED[0] } } }));
  await settle();
}

/** The refusal stays until closed: red, sticky, and its only button is «Close». */
function expectStickyRefusal(w: Wrapper, message: string): void {
  const n = toast(w);
  expect(n.message).toBe(message);
  expect(n.color).toBe('danger');
  // 0 = until the person closes it. It was 2500: gone before anyone could read it.
  expect(n.duration).toBe(0);
  expect(n.buttons.map((b) => b.text)).toEqual([enCatalogue.apps.noticeClose]);
  expect(n.buttons[0].role).toBe('cancel');
}

const unsentRecords = () =>
  new ModuleActionError(
    '3 VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module',
    'verifactu.unsent_records',
  );
const fill = (s: string, params: Record<string, string>) =>
  Object.entries(params).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v), s);

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  Object.values(runtimeMocks).forEach((m) => m.mockReset());
});

describe('a refusal to switch off, uninstall or update an app stays until closed (hub#2594)', () => {
  it('🔴 switching off refused by VeriFactu', async () => {
    runtimeMocks.deactivateModule.mockRejectedValue(unsentRecords());
    const w = mountApps();
    await settle();
    await press(w, 'toggle');
    expect(runtimeMocks.deactivateModule).toHaveBeenCalledWith('verifactu');
    expectStickyRefusal(w, enCatalogue.runtimeErrors.verifactu.unsent_records);
  });

  it('🔴 switching off that fails without a sentence of the hub', async () => {
    runtimeMocks.deactivateModule.mockRejectedValue(new Error('deactivate verifactu → 500'));
    const w = mountApps();
    await settle();
    await press(w, 'toggle');
    expectStickyRefusal(w, fill(enCatalogue.apps.toggleError, { name: 'VeriFactu' }));
  });

  it('🔴 uninstalling refused by VeriFactu', async () => {
    runtimeMocks.uninstallModule.mockRejectedValue(unsentRecords());
    const w = mountApps();
    await settle();
    await press(w, 'uninstall');
    expect(runtimeMocks.uninstallModule).toHaveBeenCalled();
    expectStickyRefusal(w, enCatalogue.runtimeErrors.verifactu.unsent_records);
  });

  it('🔴 uninstalling refused because other apps need it', async () => {
    runtimeMocks.uninstallModule.mockRejectedValue(
      new ModuleActionError('verifactu is required by invoice', 'has_dependents', ['invoice']),
    );
    const w = mountApps();
    await settle();
    await press(w, 'uninstall');
    expectStickyRefusal(w, fill(enCatalogue.apps.uninstallBlocked, { name: 'VeriFactu', apps: 'invoice' }));
  });

  it('🔴 updating that fails, with the sentence of the hub', async () => {
    runtimeMocks.updateModule.mockRejectedValue(
      Object.assign(new Error('update → 502'), { detail: 'The marketplace did not answer' }),
    );
    const w = mountApps();
    await settle();
    await press(w, 'update');
    expect(runtimeMocks.updateModule).toHaveBeenCalledWith('verifactu', '2.0.0');
    expectStickyRefusal(w, 'The marketplace did not answer');
  });

  it('🔴 updating blocked by paid apps not subscribed to can be closed too', async () => {
    runtimeMocks.updateModule.mockRejectedValue(new InstallBlockedError('blocked', ['Payroll']));
    const w = mountApps();
    await settle();
    await press(w, 'update');
    expectStickyRefusal(w, fill(enCatalogue.apps.updateBlocked, { name: 'VeriFactu', missing: 'Payroll' }));
  });

  it('says it, and «Cerrar», in Spanish', async () => {
    runtimeMocks.deactivateModule.mockRejectedValue(unsentRecords());
    const w = mountApps('es');
    await settle();
    await press(w, 'toggle');
    const n = toast(w);
    expect(n.message).toBe(esCatalogue.runtimeErrors.verifactu.unsent_records);
    expect(n.duration).toBe(0);
    expect(n.buttons.map((b) => b.text)).toEqual([esCatalogue.apps.noticeClose]);
    expect(esCatalogue.apps.noticeClose).toBe('Cerrar');
  });

  it('closing it does close it', async () => {
    runtimeMocks.deactivateModule.mockRejectedValue(unsentRecords());
    const w = mountApps();
    await settle();
    await press(w, 'toggle');
    const stub = w.findComponent({ name: 'IonToast' });
    expect(stub.props('isOpen')).toBe(true);
    stub.vm.$emit('didDismiss');
    await settle();
    expect(stub.props('isOpen')).toBe(false);
  });

  it('a switch-off that goes through still goes away on its own (no buttons, not sticky)', async () => {
    runtimeMocks.deactivateModule.mockResolvedValue(undefined);
    const w = mountApps();
    await settle();
    await press(w, 'toggle');
    const n = toast(w);
    expect(n.message).toBe(fill(enCatalogue.apps.deactivated, { name: 'VeriFactu' }));
    expect(n.duration).toBeGreaterThan(0);
    expect(n.buttons).toEqual([]);
  });

  it('an uninstall that goes through still goes away on its own', async () => {
    runtimeMocks.uninstallModule.mockResolvedValue(undefined);
    const w = mountApps();
    await settle();
    await press(w, 'uninstall');
    const n = toast(w);
    expect(n.message).toBe(fill(enCatalogue.apps.uninstalled, { name: 'VeriFactu' }));
    expect(n.duration).toBeGreaterThan(0);
    expect(n.buttons).toEqual([]);
  });
});
