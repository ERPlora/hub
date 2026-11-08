// Android's Back button of the installed app, in Chrome (BASE-F05, base/frontend/lib/system-back.ts). Tauri does not run
// in Playwright: the installed app's bridge is simulated at the edge (`window.__TAURI__`, which records what it is asked
// and keeps the listener the shell registers on the `app` plugin's `back-button`, what Tauri's `onBackButtonPress`
// listens to); a press calls that listener, as the app does. Hub, SaaS and the screens are the real ones.
import { expect, type Page } from '@playwright/test';

type BackBridge = { asked: string[]; listeners: ((payload: unknown) => Promise<void>)[] };

/** From the next page load on, the page runs inside the installed app (after the login, which is the SaaS's page). */
export async function insideTheApp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const bridge: BackBridge = { asked: [], listeners: [] };
    const win = window as unknown as { __TAURI__: unknown; __back: BackBridge };
    win.__back = bridge;
    win.__TAURI__ = {
      core: {
        invoke: async (command: string) => {
          bridge.asked.push(command);
          return null;
        },
        addPluginListener: async (plugin: string, event: string, listener: (payload: unknown) => Promise<void>) => {
          if (plugin === 'app' && event === 'back-button') bridge.listeners.push(listener);
          return {
            unregister: async () => {
              bridge.listeners = bridge.listeners.filter((kept) => kept !== listener);
            },
          };
        },
      },
    };
  });
}

/** One press of the Back button, on the one listener the shell holds. */
export async function pressBack(page: Page): Promise<void> {
  const held = () => page.evaluate(() => (window as unknown as { __back: BackBridge }).__back.listeners.length);
  await expect.poll(held, { message: 'the shell holds the Back button' }).toBe(1);
  await page.evaluate(() => (window as unknown as { __back: BackBridge }).__back.listeners[0]({ canGoBack: false }));
}

/** Did a press ask the app to leave (`leave_app`, what Back does on Home)? */
export const leftTheApp = (page: Page): Promise<boolean> =>
  page.evaluate(() => (window as unknown as { __back: BackBridge }).__back.asked.includes('plugin:erplora-android|leave_app'));
