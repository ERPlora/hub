// Test helper of base's Home and its pieces of the chrome: `mountInShell` with base's catalogues and the shared
// assistant's words merged in, the assistant configured as the Hub's (both as main.ts does), the shell's config, a
// memory router with the routes a test names and Ionic's router API on it (`useIonRouter`).
import { type SessionMe, type SessionStatus, type ShellSidebar } from '@erplora/ui/shell';
import { assistantMessages, configureAssistant } from '@erplora/ui/components';
import { type BaseWrapper } from '@vue/test-utils';
import { vi } from 'vitest';
import { type Component } from 'vue';
import { createMemoryHistory, createRouter, type RouteLocationRaw, type Router, type RouteRecordRaw } from 'vue-router';

import { type ApiCall, type ApiHandler, flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import PlanUpgradeLink from '../components/PlanUpgradeLink.vue';
import { HUB_ASSISTANT } from '../lib/assistant-hub';
import { forgetAppDistribution } from '../lib/management';
import en from '../locale/en.json';
import es from '../locale/es.json';
import { mountInShell } from './mount-in-shell';

export * from './mount-in-shell';

configureAssistant(HUB_ASSISTANT);

export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['base.view_home', 'base.administer_hub', 'demo.view', 'demo.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

export const EMPLOYEE: SessionMe = { ...OWNER, user: { id: 'u2', label: 'Leo' }, permissions: ['base.view_home', 'demo.view'] };

export { business, POLISH } from './business';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

/** The installed app's bridge, from the copy it is (`device_context`'s `distribution`: `direct`, `play`, `msstore`);
 *  its `invoke`, to look at. `leaveInstalledApp` takes it away and forgets the copy (`managementOffered`). */
export function installedApp(distribution: string) {
  const invoke = vi.fn(async (command: string) => (command === 'device_context' ? { id: 'd1', distribution } : undefined));
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

export function leaveInstalledApp(): void {
  delete (window as TauriWindow).__TAURI__;
  forgetAppDistribution();
}

/** A click on `element` as a person's tap, and whether the page stopped the link (`defaultPrevented`). The test
 *  environment never follows the link afterwards (happy-dom would fetch its address). */
export function tap(element: Element): { defaultPrevented: boolean } {
  const click = new MouseEvent('click', { bubbles: true, cancelable: true });
  const seen = { defaultPrevented: false };
  const last = (event: Event) => {
    seen.defaultPrevented = event.defaultPrevented;
    event.preventDefault();
  };
  window.addEventListener('click', last);
  try {
    element.dispatchEvent(click);
  } finally {
    window.removeEventListener('click', last);
  }
  return seen;
}

/** What `base.saas_pass.create` signs in these tests (BASE-F11). */
export const SIGNED = 'http://localhost:8001/hub-pass/?pass=abc';

/** `base.saas_pass.create` refusing to sign (a session opened without the account): the usual address must open. */
export function passRefused(): Response {
  return Response.json({ error: { code: 'base.saas_pass_needs_account', message: 'No.' } }, { status: 403 });
}

/** Taps, in a browser, a link of the mounted `m` that goes with the pass to erplora.com (`useSaasPass`): what it asked
 *  the pass for (`next`, none when it asked nothing) and where its new tab was sent (`to`): the signed address, or the
 *  usual one when the pass could not be signed. */
export async function followPass(m: { net: { api: ApiCall[] } }, link: Element): Promise<{ next?: string; to: string }> {
  const tab = { opener: {} as unknown, location: { href: 'about:blank' } };
  const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
  try {
    tap(link);
    await flush();
    const pass = m.net.api.filter((call) => call.url.includes('/saas-pass')).at(-1);
    const next = pass ? (JSON.parse(pass.init.body as string) as { next: string }).next : undefined;
    return { next, to: tab.location.href };
  } finally {
    open.mockRestore();
  }
}

/** The «Upgrade plan» a screen places in `within`, as the person and the pass see it, when it is the platform's
 *  PlanUpgradeLink (BASE-F11); `null` when there is none, or only a copy of its click. */
export function placedUpgrade(within: Pick<BaseWrapper<Node>, 'findComponent'>): { url: string; testid?: string; says: string } | null {
  const piece = within.findComponent(PlanUpgradeLink);
  if (!piece.exists()) return null;
  return { url: piece.props('url'), testid: piece.attributes('data-testid'), says: piece.text() };
}

const BLANK = { template: '<div />' };

/** The browser's localStorage (the test environment has none): `vi.stubGlobal('localStorage', memoryStorage())`. */
/** The name a screen reader reads. Attached, `ion-button` moves `aria-label` from its host to the native button of its
 *  shadow root (Ionic's `inheritAriaAttributes`), as in a browser — its native link when it has an `href`;
 *  packages/ui's FormModal tests read it the same. */
export function accessibleName(element: Element): string | null | undefined {
  return element.shadowRoot?.querySelector('button, a')?.getAttribute('aria-label') ?? element.getAttribute('aria-label');
}

export function memoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => store.get(key) ?? null,
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => void store.delete(key),
    setItem: (key, value) => void store.set(key, String(value)),
  };
}

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  /** `null`: no session arrived (yet, or ever: see `status`). */
  session?: SessionMe | null;
  status?: SessionStatus;
  /** Paths the router knows (besides the 404 catch-all named `not-found`, as the shell's). */
  routes?: string[];
  stubs?: Record<string, Component | boolean>;
  sidebar?: ShellSidebar;
  /** What the fake API answers, set before mounting (a component may ask on mount). */
  onApi?: ApiHandler;
}

/** Ionic's router API (`useIonRouter`) as the shell's Ionic router provides it app-wide (`navManager`), on the test's
 *  router: `handleNavigate(location, action, direction)` is a spy that navigates. */
function navManager(router: Router) {
  return {
    handleNavigate: vi.fn((location: RouteLocationRaw, action = 'push') =>
      action === 'replace' ? router.replace(location) : router.push(location),
    ),
    canGoBack: () => Boolean(window.history.state?.back),
    goBack: () => router.back(),
    goForward: () => router.forward(),
  };
}

export async function mountBase(component: Component, options: MountOptions = {}) {
  const known: RouteRecordRaw[] = (options.routes ?? []).map((path) => ({ path, component: BLANK }));
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'base-home', component: BLANK, meta: { auth: true } },
      ...known,
      { path: '/:pathMatch(.*)*', name: 'not-found', component: BLANK },
    ],
  });
  const ionRouter = navManager(router);
  const mounted = await mountInShell(
    component,
    { ...options, api: options.onApi, attachTo: document.body },
    {
      path: '/',
      session: OWNER,
      messages: { en: { ...assistantMessages.en, ...en }, es: { ...assistantMessages.es, ...es } },
      router,
      provide: { navManager: ionRouter },
      shell: { homePath: '/', home: true, sidebar: options.sidebar },
    },
  );
  return { ...mounted, ionRouter, result: mounted.resultOn };
}
