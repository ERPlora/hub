// @vitest-environment happy-dom
//
// hub#2621 — a manager whose role may change an app's settings saw them read-only in its tab.
//
// hub#2588 made the «Settings» tab follow the permission of the app's save command (`settings.set`
// → its `commands[...].permission`): only whoever may save sees it. But the generic form behind the
// tab still let only an owner/admin edit (`canEdit = isAdmin`), so a manager holding
// `sales.manage_settings` — granted by the factory `manager` role, and accepted by the hub on Save
// (the assistant saves them for him) — opened the tab and found every field locked under «Only an
// administrator can change these settings.», with no «Save».
//
// The fix asks the form the same question the tab and the hub ask: the save permission. These
// tests mount the REAL ModuleView with the REAL ModuleSettingsForm, so they prove the whole screen
// path: the view hands the permission down and the form lets the holder edit and save.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, reactive } from 'vue';

const routeParams = reactive<{ moduleId: string; navId?: string }>({ moduleId: 'sales', navId: 'settings' });

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId ?? ''}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId ?? ''}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('../lib/toast', () => ({ toastInfo: vi.fn(), toastError: vi.fn(), toastSuccess: vi.fn() }));

const POS_TAB = { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'pos', label: 'POS', icon: 'cart-outline' } };

/** The manifest the shell reads from `/modules/sales/module.json`, cut to what matters here. */
function manifest(savePermission: string | undefined) {
  return {
    id: 'sales',
    settings: { schema: 'schemas/settings.json', get: 'sales.settings_get', set: 'sales.settings_update' },
    commands: {
      'sales.settings_update': savePermission ? { permission: savePermission } : {},
    },
  };
}

const SCHEMA = {
  type: 'object',
  properties: {
    print_receipt: { type: 'boolean', default: true, title: 'Print receipt' },
    receipt_footer: { type: 'string', default: '', title: 'Receipt footer' },
  },
};

const { loadManifestMock, query, command } = vi.hoisted(() => ({
  loadManifestMock: vi.fn(),
  query: vi.fn(async (): Promise<Record<string, unknown>[]> => [{ print_receipt: true, receipt_footer: 'Thanks' }]),
  command: vi.fn(async () => undefined),
}));
vi.mock('../lib/module-loader', () => ({
  loadMenu: vi.fn(async () => [POS_TAB]),
  loadManifest: loadManifestMock,
  loadComponent: vi.fn(async () => 'erp-sales-pos'),
  loadInstalledManifests: vi.fn(async () => []),
  loadModuleComponent: vi.fn(async (_m: unknown, tag: string) => tag),
  loadModuleLocale: vi.fn(async () => undefined),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ query, command, forModule: () => ({ query, command }), on: () => () => {} }),
}));
vi.mock('../lib/protects', () => ({ resolveProtectsGuard: vi.fn(async () => null) }));
vi.mock('../lib/entitlement', () => ({
  isModuleBlocked: () => false,
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/immersive', () => ({ chromeControlsFor: () => [], installChrome: () => () => {} }));
vi.mock('@erplora/outfitkit/tabbar', () => ({ scrollActiveTabIntoView: vi.fn() }));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/ModulePlanPanel.vue', () => ({
  default: { name: 'ModulePlanPanel', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ModuleView from './ModuleView.vue';
import { IonInput, IonToggle } from '@ionic/vue';
import { setUser } from '../lib/session';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const mounted: Array<{ unmount: () => void }> = [];

function mountModuleView() {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(ModuleView, { global: { plugins: [i18n] } });
  mounted.push(wrapper);
  return wrapper;
}

async function settle(): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await flushPromises();
    await nextTick();
  }
}

function signIn(role: string, permissions: string[]): void {
  setUser({ id: 'u-1', name: 'Marta', email: '', role, permissions });
}

type Wrapper = ReturnType<typeof mountModuleView>;

function footerInput(wrapper: Wrapper) {
  return wrapper.findAllComponents(IonInput).find((i) => i.attributes('aria-label') === 'Receipt footer');
}

/** The form is editable: Save is there, nothing is locked and no read-only line is painted. */
function expectEditable(wrapper: Wrapper): void {
  expect(wrapper.find('[data-testid="module-settings-save"]').exists(), 'no «Save» button').toBe(true);
  expect(wrapper.find('[data-testid="module-settings-read-only"]').exists(), 'read-only line painted').toBe(false);
  expect(footerInput(wrapper)?.props('readonly'), 'text field locked').toBe(false);
  expect(wrapper.findComponent(IonToggle).props('disabled'), 'switch locked').toBe(false);
}

beforeEach(() => {
  routeParams.moduleId = 'sales';
  routeParams.navId = 'settings';
  loadManifestMock.mockReset();
  loadManifestMock.mockResolvedValue(manifest('sales.manage_settings'));
  query.mockClear();
  command.mockClear();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => SCHEMA })),
  );
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
  setUser(null);
  vi.unstubAllGlobals();
});

describe('hub2621 — whoever may save an app settings can edit them in its tab', () => {
  it('lets a manager holding the save permission edit the settings form', async () => {
    signIn('manager', ['sales.view', 'sales.manage_settings']);
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.findComponent(IonToggle).exists(), 'the form did not mount').toBe(true);
    expectEditable(wrapper);
  });

  it('saves the whole form through the app save command when the manager presses «Save»', async () => {
    signIn('manager', ['sales.view', 'sales.manage_settings']);
    const wrapper = mountModuleView();
    await settle();

    await wrapper.find('[data-testid="module-settings-save"]').trigger('click');
    await settle();

    expect(command).toHaveBeenCalledWith('sales.settings_update', { print_receipt: true, receipt_footer: 'Thanks' });
  });

  // An owner/admin passes by ROLE, as the tab does: the permission list of a PIN session only names
  // the apps installed when it was opened (hub#2588).
  for (const role of ['admin', 'owner']) {
    it(`lets an ${role} whose session predates the app edit the settings`, async () => {
      signIn(role, ['hub.users.view', 'hub.administer']);
      const wrapper = mountModuleView();
      await settle();

      expectEditable(wrapper);
    });
  }

  it('lets anybody edit when the save command declares no permission (the hub lets anybody run it)', async () => {
    loadManifestMock.mockResolvedValue(manifest(undefined));
    signIn('employee', ['sales.view']);
    const wrapper = mountModuleView();
    await settle();

    expectEditable(wrapper);
  });

  // The control: the fix must not turn into «everybody may edit». If the session changes to a
  // person without the save permission while the form is open, it locks again and says why — and
  // pressing nothing can reach the save command.
  it('locks the open form when the session changes to a person without the save permission', async () => {
    signIn('manager', ['sales.view', 'sales.manage_settings']);
    const wrapper = mountModuleView();
    await settle();
    expectEditable(wrapper);

    signIn('employee', ['sales.view']);
    await settle();

    expect(wrapper.find('[data-testid="module-settings-save"]').exists(), '«Save» still offered').toBe(false);
    expect(footerInput(wrapper)?.props('readonly'), 'text field still editable').toBe(true);
    expect(wrapper.findComponent(IonToggle).props('disabled'), 'switch still editable').toBe(true);
    const line = wrapper.find('[data-testid="module-settings-read-only"]');
    expect(line.exists(), 'no line says why it is locked').toBe(true);
    expect(line.text()).toBe(enCatalogue.moduleSettings.noSavePermission);
    expect(command).not.toHaveBeenCalled();
  });
});

describe('hub2621 — the read-only line is translated and no longer blames the role', () => {
  it('has an English source and a Spanish translation that do not say only an administrator', () => {
    const en = enCatalogue.moduleSettings as Record<string, string>;
    const es = esCatalogue.moduleSettings as Record<string, string>;
    expect(en.noSavePermission).toBeTruthy();
    expect(es.noSavePermission).toBeTruthy();
    expect(es.noSavePermission).not.toBe(en.noSavePermission);
    expect(en.adminOnly, 'the old «Only an administrator…» line is still in the catalogue').toBeUndefined();
    expect(es.adminOnly).toBeUndefined();
  });
});
