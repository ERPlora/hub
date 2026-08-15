// @vitest-environment happy-dom
// hub#925 — the login screen was painted INSIDE the authenticated shell.
//
// What QA saw: the sidebar complete — the account's name and email, Home, Employees, Files, My
// plan, Apps, System, Settings — and, in the middle of it, the «Sign in to your business» form. A
// state that contradicts itself: either there is a session, or a session is being asked for.
//
// The cause was that the chrome was gated on `isAuthed` ALONE, and `isAuthed` is
// `user != null` — which is not «there is a session», it is «there was one and its trace is still
// in localStorage». Any landing on /login with that trace intact (a dead hub session, hub#902 /
// hub#846; a boot race; a manual URL) painted the shell around the form.
//
// So the invariant this suite pins is not «fix that one `v-if`»: it is that the login route is a
// CLEAN SURFACE — no menu, no user card, no drawers — whatever the session ref happens to say. The
// last test is the control: the very same session on a route of the business does paint the shell,
// which is what proves the two before it are looking at something that can be seen.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { route } = vi.hoisted(() => ({
  route: { path: '/login', name: 'login' as string, meta: {} as Record<string, unknown> },
}));

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue');
  const shared = reactive(route);
  return {
    useRoute: () => shared,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  };
});

// Everything the shell wakes up on mount is scenery here: this suite is about WHAT IS PAINTED, not
// about what the shell fetches once it is.
vi.mock('../lib/nav', () => ({ refreshModuleNav: vi.fn(async () => {}) }));
vi.mock('../lib/entitlement', async () => {
  const { ref } = await import('vue');
  return { resolveEntitlement: vi.fn(async () => {}), needsActivation: ref(false) };
});
// `resolveDeviceId` too: since hub#456 the shell asks the hub what kind of device this is from
// INSIDE the session (`loadDeviceMode` in `gateAndRefresh`), and that reads the device's id first.
vi.mock('../lib/device', () => ({
  getDeviceContext: vi.fn(async () => null),
  resolveDeviceId: vi.fn(async () => null),
}));
vi.mock('../lib/hub-settings', () => ({ getHubSettings: vi.fn(async () => ({ language: 'en' })) }));
vi.mock('../lib/user-profile', () => ({ getUserProfile: vi.fn(async () => null) }));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn(async () => {}) }));
vi.mock('../lib/app-update', () => ({ bootAppUpdateWatch: vi.fn() }));
vi.mock('../lib/dead-letter', () => ({ bootDeadLetterWatch: vi.fn() }));
vi.mock('../lib/idle-logout', () => ({ installIdleLogout: vi.fn() }));
vi.mock('../lib/toast', () => ({ toastError: vi.fn() }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/upgrade-plan-link', () => ({
  planUpgradeIsOfferable: () => true,
  upgradePlanUrl: () => 'https://erplora.com/plan',
}));
vi.mock('../lib/shell-menu', () => ({
  SHELL_MENU_ID: 'shell-menu',
  runAfterShellMenuCloses: vi.fn(async (fn: () => unknown) => fn()),
}));
vi.mock('../lib/api-docs', async () => {
  const { ref } = await import('vue');
  return { apiDocsEnabled: ref(false) };
});
vi.mock('../lib/runtime', () => ({ getClient: () => ({ on: () => () => {} }) }));
vi.mock('../i18n', () => ({ bootHubLanguage: vi.fn() }));
vi.mock('./AssistantDrawer.vue', () => ({
  default: { name: 'AssistantDrawer', template: '<div />' },
}));
vi.mock('./ElevationDialog.vue', () => ({
  default: { name: 'ElevationDialog', template: '<div />' },
}));
vi.mock('./SidebarAppUpdate.vue', () => ({
  default: { name: 'SidebarAppUpdate', template: '<div />' },
}));
vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));

import App from '../App.vue';
import { setUser } from '../lib/session';
import en from '../i18n/locales/en';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
});

/** The trace of an account in the session — exactly what `isAuthed` reads. */
function seedSignedInUser(): void {
  setUser({
    id: 'u-sofia',
    name: 'Sofía Marín',
    email: 'sofia@erplora.test',
    role: 'owner',
    permissions: ['*'],
  });
}

/** Mounts the shell on `path`; `auth` is the route's own `meta.auth` (what the router declares). */
async function mountShellOn(path: string, name: string, auth: boolean) {
  route.path = path;
  route.name = name;
  route.meta = auth ? { auth: true } : {};
  const wrapper = mount(App, {
    shallow: true,
    global: {
      plugins: [i18n],
      // The `ion-*` are stubbed (this is the shell's contract, not Ionic's) but their slots are
      // rendered, so the user card inside the menu is really in the output when the menu is.
      renderStubDefaultSlot: true,
      // …and the gate itself is NOT stubbed: a stub would render its slot unconditionally, which
      // is precisely the behaviour under test.
      stubs: { AuthenticatedChrome: false },
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  setUser(null);
});

describe('the login route is outside the authenticated shell', () => {
  it('paints no side menu, even with a user left in the session', async () => {
    seedSignedInUser();
    const wrapper = await mountShellOn('/login', 'login', false);

    expect(wrapper.find('ion-menu-stub').exists(), 'the sidebar is painted on /login').toBe(false);
  });

  it('and no user card: /login never says whose account it is', async () => {
    seedSignedInUser();
    const wrapper = await mountShellOn('/login', 'login', false);
    const html = wrapper.html();

    expect(html, 'the user card is painted on /login').not.toContain('sidebar-user');
    expect(html, 'the account email is painted on /login').not.toContain('sofia@erplora.test');
    expect(html, 'the account name is painted on /login').not.toContain('Sofía Marín');
  });

  it('and no assistant nor elevation dialog: there is nothing to assist or elevate yet', async () => {
    seedSignedInUser();
    const wrapper = await mountShellOn('/login', 'login', false);

    expect(wrapper.find('assistant-drawer-stub').exists()).toBe(false);
    expect(wrapper.find('elevation-dialog-stub').exists()).toBe(false);
  });

  it('control — the SAME session on a screen of the business does paint the shell', async () => {
    // Without this one the three above would also pass if the mount painted nothing at all.
    seedSignedInUser();
    const wrapper = await mountShellOn('/dashboard', 'dashboard', true);
    const html = wrapper.html();

    expect(wrapper.find('ion-menu-stub').exists(), 'the sidebar never painted').toBe(true);
    expect(html).toContain('sidebar-user');
    expect(html).toContain('sofia@erplora.test');
    expect(wrapper.find('assistant-drawer-stub').exists()).toBe(true);
    expect(wrapper.find('elevation-dialog-stub').exists()).toBe(true);
  });

  it('and with no session at all the shell stays out of the way', async () => {
    const wrapper = await mountShellOn('/dashboard', 'dashboard', true);

    expect(wrapper.find('ion-menu-stub').exists()).toBe(false);
    expect(wrapper.find('assistant-drawer-stub').exists()).toBe(false);
  });
});

describe('the invariant is written once, so the next piece of chrome inherits it', () => {
  // The bug was not that one `v-if` was wrong: it was that the rule lived in the `v-if`s, copied
  // per site, where each new piece of chrome had to remember it (and the second one, the assistant
  // drawer, was wrong in exactly the same way). What this pins is that the shell has no second
  // opinion about who sees chrome — App.vue asks the gate, and asks it nowhere else.
  // Resolved with `node:path` and not with `new URL(...)`: under happy-dom the global `URL` is the
  // DOM one, and neither `node:fs` nor `fileURLToPath` accept it.
  const here = dirname(fileURLToPath(import.meta.url));
  const app = readFileSync(join(here, '..', 'App.vue'), 'utf8');
  const template = app.slice(0, app.indexOf('<script'));

  it('App.vue never gates its template on the session by hand', () => {
    expect(template, 'chrome gated on `isAuthed` again — wrap it in <AuthenticatedChrome>')
      .not.toContain('isAuthed');
  });

  it('every piece of the authenticated chrome hangs off the gate', () => {
    for (const chrome of ['<ion-menu', '<AssistantDrawer', '<ElevationDialog']) {
      const gate = template.lastIndexOf('<AuthenticatedChrome>', template.indexOf(chrome));
      const closed = template.lastIndexOf('</AuthenticatedChrome>', template.indexOf(chrome));
      expect(gate, `${chrome} is outside <AuthenticatedChrome>`).toBeGreaterThan(closed);
    }
  });
});
