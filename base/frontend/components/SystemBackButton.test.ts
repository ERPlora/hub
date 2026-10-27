// BASE-F05 · gh:hub#1906: base takes the installed app's Back button beside the pane (`chrome.background`) while a
// person is signed in. Its layers are pinned in `lib/system-back.test.ts`; here, the wiring: on the root of an app a
// press goes Home the way the menu's «Home» does, on Home it leaves the app, and the button is let go when the person
// signs out (the component goes); in a browser nothing is registered.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import BackgroundChrome from './BackgroundChrome.vue';
import SystemBackButton from './SystemBackButton.vue';

type TauriWindow = { __TAURI__?: unknown };
type BackHandler = (payload: unknown) => Promise<void>;

afterEach(() => {
  delete (window as TauriWindow).__TAURI__;
  document.body.innerHTML = '';
});

/** The installed app's bridge (`window.__TAURI__`, as DeviceNotices.test.ts): what it is asked, and the listener. */
function installedApp(opts: { answer?: Promise<void> } = {}) {
  const state: { handler?: BackHandler; unregister: ReturnType<typeof vi.fn> } = { unregister: vi.fn(async () => undefined) };
  const invoke = vi.fn(async () => null);
  const addPluginListener = vi.fn(async (_plugin: string, _event: string, handler: BackHandler) => {
    await opts.answer;
    state.handler = handler;
    return { unregister: state.unregister };
  });
  (window as TauriWindow).__TAURI__ = { core: { invoke, addPluginListener } };
  return { state, invoke, addPluginListener };
}

describe('SystemBackButton (the installed app\'s Back button)', () => {
  it('on the root of an app a press goes Home, as the menu\'s «Home» (root, not a push on top)', async () => {
    const app = installedApp();
    const m = await mountBase(SystemBackButton, { path: '/demo/items', routes: ['/demo/items'] });
    await flush();

    await app.state.handler!({ canGoBack: false });
    await flush();

    expect(m.ionRouter.handleNavigate).toHaveBeenCalledWith('/', 'push', 'root', undefined);
    expect(m.router.currentRoute.value.path).toBe('/');
    expect(app.invoke).not.toHaveBeenCalledWith('plugin:erplora-android|leave_app');
  });

  it('on Home a press leaves the app', async () => {
    const app = installedApp();
    const m = await mountBase(SystemBackButton, { path: '/' });
    await flush();

    await app.state.handler!({ canGoBack: true });

    expect(app.invoke).toHaveBeenCalledWith('plugin:erplora-android|leave_app');
    expect(m.ionRouter.handleNavigate).not.toHaveBeenCalled();
  });

  it('lets go of the button when it goes (the person signs out)', async () => {
    const app = installedApp();
    const { wrapper } = await mountBase(SystemBackButton);
    await flush();

    wrapper.unmount();

    expect(app.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('gone before the app answered: lets go as soon as it answers', async () => {
    let answer!: () => void;
    const app = installedApp({ answer: new Promise<void>((resolve) => (answer = resolve)) });
    const { wrapper } = await mountBase(SystemBackButton);

    wrapper.unmount();
    answer();
    await flush();

    expect(app.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('in a browser registers nothing and paints nothing', async () => {
    const { wrapper } = await mountBase(SystemBackButton);
    await flush();

    expect(wrapper.get('[data-testid="system-back"]').attributes('hidden')).toBeDefined();
    expect(wrapper.text()).toBe('');
  });

  it('is one of base\'s pieces beside the pane', async () => {
    const { wrapper } = await mountBase(BackgroundChrome);

    expect(wrapper.find('[data-testid="system-back"]').exists()).toBe(true);
  });
});
