// @vitest-environment happy-dom
//
// hub#2588 — the «Settings» tab of an app is only there for whoever may SAVE those settings.
//
// What was seen reviewing `attendance` (07/10): an employee with no `attendance.manage_settings`
// opened the app, found the shell's synthetic «Settings» tab, filled the module's own settings
// screen («Use my current location», «Save») and got a permission refusal on Save. The shell added
// that tab to anybody who could open the app, while every other tab of the app is filtered by its
// permission (`/api/navigation` leaves out what the person may not open, hub#1052).
//
// The market does the same with settings (Square, Toast, Odoo, Shopify staff permissions): a person
// without the right does not see the settings entry at all. So the shell asks the same question the
// hub asks on Save — the permission of the module's save command (`settings.set` → its
// `commands[...].permission`) — and paints the tab only when the session has it. An address typed
// by hand (`/m/attendance/settings`) answers like any tab the menu took away by permission: «This
// page does not exist» (HUB_SHELL-F41 step 6). The hub keeps refusing the command regardless: this
// is the screen half, never the gate.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, reactive } from 'vue';

const routeParams = reactive<{ moduleId: string; navId?: string }>({ moduleId: 'attendance', navId: 'clock' });

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

const CLOCK_TAB = {
  moduleId: 'attendance',
  moduleName: 'Time clock',
  nav: { id: 'clock', label: 'Clock in', icon: 'time-outline' },
};
const RECORDS_TAB = {
  moduleId: 'attendance',
  moduleName: 'Time clock',
  nav: { id: 'records', label: 'Records', icon: 'list-outline' },
};

/** The manifest the shell reads from `/modules/attendance/module.json`, cut to what matters here. */
function manifest(savePermission: string | undefined, component?: string) {
  return {
    id: 'attendance',
    settings: {
      schema: 'schemas/settings_update.json',
      get: 'attendance.settings.get',
      set: 'attendance.settings.update',
      ...(component ? { component } : {}),
    },
    commands: {
      'attendance.clock_in': { permission: 'attendance.clock' },
      'attendance.settings.update': savePermission ? { permission: savePermission } : {},
    },
  };
}

const { loadManifestMock } = vi.hoisted(() => ({ loadManifestMock: vi.fn() }));
vi.mock('../lib/module-loader', () => ({
  loadMenu: vi.fn(async () => [CLOCK_TAB, RECORDS_TAB]),
  loadManifest: loadManifestMock,
  loadComponent: vi.fn(async () => 'erp-attendance-clock'),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ forModule: () => ({}), on: () => () => {} }),
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
vi.mock('../components/ModuleSettingsForm.vue', () => ({
  default: { name: 'ModuleSettingsForm', template: '<div data-testid="generic-settings-form" />' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ModuleView from './ModuleView.vue';
import { IonSegmentButton } from '@ionic/vue';
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
  await flushPromises();
  await nextTick();
  await flushPromises();
}

/** The ids of the tabs the bottom bar paints, in order. */
function tabIds(wrapper: ReturnType<typeof mountModuleView>): string[] {
  return wrapper.findAllComponents(IonSegmentButton).map((b) => String(b.props('value') ?? ''));
}

function signIn(role: string, permissions: string[]): void {
  setUser({ id: 'u-1', name: 'Ana', email: '', role, permissions });
}

beforeEach(() => {
  routeParams.moduleId = 'attendance';
  routeParams.navId = 'clock';
  loadManifestMock.mockReset();
  loadManifestMock.mockResolvedValue(manifest('attendance.manage_settings', 'erp-attendance-settings'));
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
  setUser(null);
});

describe('hub2588 — the Settings tab of an app follows the permission of its save command', () => {
  it('hides the tab from an employee who may not save the settings', async () => {
    signIn('employee', ['attendance.clock']);
    const wrapper = mountModuleView();
    await settle();

    expect(tabIds(wrapper)).toEqual(['clock', 'records']);
  });

  it('answers a typed /m/<app>/settings like a tab the menu took away: «This page does not exist»', async () => {
    signIn('employee', ['attendance.clock']);
    routeParams.navId = 'settings';
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="not-found"]').exists(), 'the settings screen opened anyway').toBe(true);
    // Neither the module's own settings screen nor the generic form is mounted behind it.
    expect(wrapper.find('erp-attendance-settings').exists()).toBe(false);
    expect(wrapper.find('[data-testid="generic-settings-form"]').exists()).toBe(false);
  });

  it('keeps the generic form away too when the app has no settings screen of its own', async () => {
    loadManifestMock.mockResolvedValue(manifest('attendance.manage_settings'));
    signIn('employee', ['attendance.clock']);
    routeParams.navId = 'settings';
    const wrapper = mountModuleView();
    await settle();

    expect(tabIds(wrapper)).toEqual(['clock', 'records']);
    expect(wrapper.find('[data-testid="generic-settings-form"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(true);
  });

  // The controls: without them the fix is «nobody sees Settings any more».
  it('shows the tab, last, to whoever holds the save permission', async () => {
    signIn('manager', ['attendance.clock', 'attendance.manage_settings']);
    const wrapper = mountModuleView();
    await settle();

    expect(tabIds(wrapper)).toEqual(['clock', 'records', 'settings']);
  });

  it('mounts the settings screen for whoever holds the save permission', async () => {
    signIn('manager', ['attendance.clock', 'attendance.manage_settings']);
    routeParams.navId = 'settings';
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(false);
    expect(wrapper.find('erp-attendance-settings').exists()).toBe(true);
  });

  it('shows the tab to an administrator through the wildcard', async () => {
    signIn('admin', ['*']);
    const wrapper = mountModuleView();
    await settle();

    expect(tabIds(wrapper)).toContain('settings');
  });

  // Seen on the bench (real runtime, real attendance): the PIN session of an administrator lists the
  // permissions of the apps installed WHEN it was opened (`["hub.users.view","hub.administer"]`
  // before attendance). Installing an app and opening it to configure it is the administrator's
  // daily path, and the hub lets an owner/admin run every command; so does the module's client
  // (`lib/runtime.ts` hands `*` to those roles). The tab must not depend on the session's list.
  for (const role of ['admin', 'owner']) {
    it(`shows the tab to an ${role} whose session predates the app (no permission of it listed)`, async () => {
      signIn(role, ['hub.users.view', 'hub.administer']);
      const wrapper = mountModuleView();
      await settle();

      expect(tabIds(wrapper)).toEqual(['clock', 'records', 'settings']);
    });

    it(`mounts the settings screen for an ${role} whose session predates the app`, async () => {
      signIn(role, ['hub.users.view', 'hub.administer']);
      routeParams.navId = 'settings';
      const wrapper = mountModuleView();
      await settle();

      expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(false);
      expect(wrapper.find('erp-attendance-settings').exists()).toBe(true);
    });
  }

  it('shows the tab to everybody when the save command declares no permission', async () => {
    // The hub lets anybody run a command without a permission, so the screen has nothing to hide.
    loadManifestMock.mockResolvedValue(manifest(undefined, 'erp-attendance-settings'));
    signIn('employee', ['attendance.clock']);
    const wrapper = mountModuleView();
    await settle();

    expect(tabIds(wrapper)).toContain('settings');
  });
});
