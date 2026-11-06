// Where to get the ERPlora app (hub#683, the old hub's HUB_SHELL-F138): erplora.com's door of each system it publishes,
// which `base/spa.py` embeds in `hub-home` (`app_downloads`), in the server's order: the till's Windows first, then Linux
// and Android (no macOS: nothing is published for it). Offered in a browser only: inside the installed app it would be
// the app offering to install itself.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { embedHubHome as embed, forgetHubHome } from '../__tests__/hub-home';
import { useAppDownloads } from './app-downloads';

const SAAS = 'http://localhost:8001';
const DOWNLOADS = {
  windows: `${SAAS}/app/download/windows/`,
  linux: `${SAAS}/app/download/linux/`,
  android: `${SAAS}/app/download/android/`,
};

afterEach(forgetHubHome);

describe('useAppDownloads', () => {
  it('on the web, the door of each system, Windows first', () => {
    // In whatever order the block lists them.
    const { windows, linux, android } = DOWNLOADS;
    embed({ name: 'Bar', plan_url: '', account_url: '', app_downloads: { android, linux, windows } });
    const app = useAppDownloads();
    expect(app.downloads).toEqual([
      { platform: 'windows', url: DOWNLOADS.windows },
      { platform: 'linux', url: DOWNLOADS.linux },
      { platform: 'android', url: DOWNLOADS.android },
    ]);
    expect(app.offered.value).toBe(true);
  });

  it('only the systems it knows, each with its address', () => {
    embed({ name: 'Bar', app_downloads: { macos: `${SAAS}/app/download/macos/`, linux: '', android: DOWNLOADS.android } });
    expect(useAppDownloads().downloads).toEqual([{ platform: 'android', url: DOWNLOADS.android }]);
  });

  it('offers nothing where no address comes', () => {
    embed(null);
    expect(useAppDownloads().offered.value).toBe(false);
    embed({ name: 'Bar', app_downloads: {} });
    expect(useAppDownloads().offered.value).toBe(false);
  });

  it.each(['desktop', 'mobile'] as const)('offers nothing inside the installed app (%s), and follows the surface', (surface) => {
    embed({ name: 'Bar', app_downloads: DOWNLOADS });
    const app = useAppDownloads();
    applySurface(surface);
    expect(app.offered.value).toBe(false);
    applySurface('web');
    expect(app.offered.value).toBe(true);
  });
});
