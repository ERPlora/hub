// erplora.com's addresses of the ERPlora app for each system, as base embeds them in the page (`hub-home`), for the
// tests of what offers the app.
import { embedHubHome } from '../../../../base/frontend/__tests__/hub-home';

const SAAS = 'http://localhost:8001';

export const DOWNLOADS = {
  windows: `${SAAS}/app/download/windows/`,
  linux: `${SAAS}/app/download/linux/`,
  android: `${SAAS}/app/download/android/`,
};

/** Puts `downloads` in the page; `null`: no addresses at all. */
export const embedDownloads = (downloads: Record<string, string> | null = DOWNLOADS): void =>
  embedHubHome(downloads && { name: 'Bar', app_downloads: downloads });
