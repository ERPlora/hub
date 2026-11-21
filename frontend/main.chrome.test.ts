// base's chrome mounts with the screen: its pieces load on demand, but the hub
// mounts only once they are here. The apps followed beside the pane (background) read a live query: mounted after the
// screen, it came more than 150 ms after its queries on a slow device, and the one live stream was cut and opened
// again with it (tests/e2e/base-home.spec.ts, «when base's chrome arrives late»). Its own file: the pieces' modules are
// held from the first import of main.ts, which boots on import.
import { describe, expect, it, vi } from 'vitest';
import { createApp, h } from 'vue';

const chrome = vi.hoisted(() => {
  let arrive!: () => void;
  const late = new Promise<void>((resolve) => (arrive = resolve));
  return { late, arrive: () => arrive() };
});

vi.mock('@erplora/ui/shell', async () => (await import('./__tests__/main-boot')).shellModule());
vi.mock('@erplora/ui/sdk', async (importOriginal) => (await import('./__tests__/main-boot')).sdkModule(importOriginal));
// Each piece a stub of its own (`__esModule`: Vue takes `default` from a module it recognises; Vitest's mock is not
// tagged `Module`). The one beside the pane is held until the test lets it arrive; the menu's foot («Upgrade plan»,
// «Manage on erplora.com») never loads (a chunk the network lost): the piece's own load reports it at render.
vi.mock('../base/frontend/components/TopbarChrome.vue', () => ({ __esModule: true, default: { render: () => null } }));
vi.mock('../base/frontend/components/BackgroundChrome.vue', async () => {
  await chrome.late;
  return { __esModule: true, default: { render: () => h('span', { 'data-testid': 'background-chrome' }) } };
});
vi.mock('../base/frontend/components/SidebarFooter.vue', () => {
  throw new Error('chunk lost');
});

import { createShell } from '@erplora/ui/shell';

import { useHubActionNotices } from '../base/frontend/lib/action-notices';
import { embedPage, shellFakes } from './__tests__/main-boot';

const { app, router } = shellFakes();

// Importing main.ts boots it, with the file: out of any test's or hook's clock, which its module graph (Ionic, every
// component, every app's routes and catalogues) outlasted on a loaded machine (a 10 s hook at load ~22).
embedPage();
vi.mocked(createShell).mockResolvedValue({ app, router } as never);
const main = await import('./main');

describe("main.ts — base's chrome mounts with the screen", () => {
  it('mounts #app only once the pieces of the chrome have loaded, and a piece that fails to load does not keep it from mounting', async () => {
    await vi.waitFor(() => expect(router.isReady).toHaveBeenCalled());
    // The router is ready and the other pieces are here: the one beside the pane is still on its way.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(app.mount).not.toHaveBeenCalled();

    chrome.arrive();
    await vi.waitFor(() => expect(app.mount).toHaveBeenCalledExactlyOnceWith('#app'));

    // Mounted, the piece paints in the same render as the screen around it, with no task in between: a module
    // imported again would resolve in a later one, after the screen's stream opened.
    const host = document.createElement('div');
    createApp({ render: () => h(main.CHROME.background!) }).mount(host);
    expect(host.querySelector('[data-testid="background-chrome"]')).not.toBeNull();
  });

  it("hands the shell the hub's notices: the bell, its arrivals and its panel are the shell's", () => {
    expect(vi.mocked(createShell).mock.calls[0][0].actionNotices).toBe(useHubActionNotices);
  });
});
