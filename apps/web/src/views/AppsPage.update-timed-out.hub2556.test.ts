// @vitest-environment happy-dom
// hub#2556 — «Update» on an app whose new version downloads too slowly. The runtime now gives up
// after its total limit, puts the version the app had back and answers 200 with
// `warning: {code: "module.update_failed_kept_previous", cause: "install_cloud_timeout"}`;
// `updateModule` turns that into an error (lib/runtime.update-outcome.hub2556.test.ts).
//
// What this pins, on the wiring of AppsPage itself: the person reads, in red and until they close
// it, that erplora.com did not answer in time and the app keeps the version it had; and «Retry»
// asks for the SAME update again without asking anything twice — the way out of a failure that is
// usually transient, like a failed install (hub#2244).
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

const { reloadForModuleUpdate } = vi.hoisted(() => ({ reloadForModuleUpdate: vi.fn() }));
vi.mock('../lib/module-loader', () => ({ reloadForModuleUpdate }));

const updateModule = vi.fn();

vi.mock('../lib/system', () => ({ fetchSystemInfo: async () => ({ hubVersion: 'v1.4.0' }) }));
vi.mock('../lib/cloud', () => ({ cloudMarketplaceModules: async () => [] }));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ on: () => () => {} }),
  requestInstall: vi.fn(),
  listInstalledModules: async () => [{ id: 'sales', name: 'Sales', version: '1.0.0', status: 'active' }],
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  uninstallModule: vi.fn(),
  getModuleCapabilities: vi.fn(),
  putModuleCapabilities: vi.fn(),
  InstallBlockedError: class InstallBlockedError extends Error {},
  ModuleActionError: class ModuleActionError extends Error {},
  updateModule: (...args: unknown[]) => updateModule(...args),
  listModuleUpdates: async () => [
    {
      module_id: 'sales',
      installed: '1.0.0',
      latest: '2.0.0',
      update_available: true,
      pinned: null,
      latest_min_erplora_version: null,
    },
  ],
  listModuleVersions: async (id: string) => ({
    module_id: id,
    installed: '1.0.0',
    latest: '2.0.0',
    versions: ['2.0.0'],
  }),
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
  const wrapper = mount(AppsPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
  mounted.push(wrapper);
  return wrapper;
}
type Wrapper = ReturnType<typeof mountApps>;

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
  await nextTick();
}

function toast(w: Wrapper) {
  const stub = w.findComponent({ name: 'IonToast' });
  return {
    message: stub.props('message') as string,
    color: stub.props('color') as string,
    duration: stub.props('duration') as number,
    buttons: (stub.props('buttons') ?? []) as ToastButton[],
  };
}

function mineTable(w: Wrapper): TableEl {
  const table = w
    .findAll('ok-data-table')
    .map((t) => t.element as TableEl)
    .find((t) => (t.rows ?? []).some((r) => r.id === 'sales' && 'status' in r));
  expect(table, 'the «My apps» table must list the app').toBeTruthy();
  return table!;
}

async function pressUpdate(w: Wrapper): Promise<void> {
  const row = mineTable(w).rows!.find((r) => r.id === 'sales')!;
  mineTable(w).dispatchEvent(new CustomEvent('rowAction', { detail: { actionId: 'update', row } }));
  await settle();
}

/** What `updateModule` throws for an update the runtime rolled back (lib/runtime.ts). */
const keptPrevious = (reason: string | null): Error =>
  Object.assign(new Error(`update sales kept 1.0.0 (${reason})`), {
    code: 'module.update_failed_kept_previous',
    reason,
    version: '1.0.0',
    detail: null,
  });

const fill = (s: string, params: Record<string, string>) =>
  Object.entries(params).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v), s);

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});
beforeEach(() => {
  updateModule.mockReset();
  reloadForModuleUpdate.mockClear();
});

describe('an update whose download ran out of time (hub#2556)', () => {
  for (const locale of ['en', 'es'] as const) {
    const catalogue = locale === 'en' ? enCatalogue : esCatalogue;

    it(`🔴 says so in red until closed, with «Retry» and «Close» (${locale})`, async () => {
      updateModule.mockRejectedValue(keptPrevious('install_cloud_timeout'));
      const w = mountApps(locale);
      await settle();
      await pressUpdate(w);

      const n = toast(w);
      expect(n.message).toBe(fill(catalogue.apps.updateTimedOut, { name: 'Sales' }));
      expect(n.color).toBe('danger');
      expect(n.duration).toBe(0);
      expect(n.buttons.map((b) => b.text)).toEqual([catalogue.apps.installRetry, catalogue.apps.noticeClose]);
      expect(n.buttons[1].role).toBe('cancel');
    });
  }

  it('🔴 «Retry» asks for the same update again, and a success reloads onto the new version', async () => {
    updateModule.mockRejectedValue(keptPrevious('install_cloud_timeout'));
    const w = mountApps('en');
    await settle();
    await pressUpdate(w);
    expect(updateModule).toHaveBeenCalledTimes(1);
    expect(updateModule).toHaveBeenLastCalledWith('sales', '2.0.0');

    updateModule.mockResolvedValue({ ok: true, module_id: 'sales', from: '1.0.0', to: '2.0.0', updated: true });
    await toast(w).buttons[0].handler?.();
    await settle();

    expect(updateModule).toHaveBeenCalledTimes(2);
    // The same request: the same app and the version it was going to, without asking again.
    expect(updateModule).toHaveBeenLastCalledWith('sales', '2.0.0');
    expect(toast(w).message).toBe(
      fill(enCatalogue.apps.updateSuccessReloading, { name: 'Sales', from: '1.0.0', to: '2.0.0' }),
    );
    expect(reloadForModuleUpdate).toHaveBeenCalledTimes(1);
  });

  it('any other reason says the honest generic line, and can be retried too', async () => {
    updateModule.mockRejectedValue(keptPrevious('install_bad_signature'));
    const w = mountApps('en');
    await settle();
    await pressUpdate(w);

    const n = toast(w);
    expect(n.message).toBe(fill(enCatalogue.apps.updateError, { name: 'Sales' }));
    expect(n.color).toBe('danger');
    expect(n.buttons.map((b) => b.text)).toEqual([enCatalogue.apps.installRetry, enCatalogue.apps.noticeClose]);
  });
});
