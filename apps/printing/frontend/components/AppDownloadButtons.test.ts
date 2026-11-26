// Where to get the ERPlora app, one button per system erplora.com publishes: Windows first and highlighted, then
// Linux and Android, each opening outside the hub. Only in a browser and only with their addresses: inside the
// installed app it would be the app offering itself, and a button without an address leads nowhere.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { embedHubHome, forgetHubHome } from '../../../../base/frontend/__tests__/hub-home';
import { flush, mountPrinting } from '../__tests__/mount-printing';
import AppDownloadButtons from './AppDownloadButtons.vue';

const SAAS = 'http://localhost:8001';
const DOWNLOADS = {
  windows: `${SAAS}/app/download/windows/`,
  linux: `${SAAS}/app/download/linux/`,
  android: `${SAAS}/app/download/android/`,
};

const embed = (downloads: Record<string, string> | null) => embedHubHome(downloads && { name: 'Bar', app_downloads: downloads });

async function buttons(locale: 'en' | 'es' = 'en') {
  const m = await mountPrinting(AppDownloadButtons, { locale, path: '/printing/devices', props: { testid: 'downloads' } });
  await flush();
  const found = m.wrapper
    .findAll('[data-testid^="downloads-"]')
    .filter((button) => button.element.tagName === 'ION-BUTTON')
    .map((button) => button.element as HTMLElement & Record<string, unknown>);
  return { m, found };
}

afterEach(forgetHubHome);

describe('AppDownloadButtons', () => {
  it('in a browser, one button per system, Windows first, each outside the hub and saying what it downloads', async () => {
    embed(DOWNLOADS);
    const { m, found } = await buttons();
    expect(m.find('downloads').attributes()).toMatchObject({ role: 'group', 'aria-label': 'Download the ERPlora app' });
    // Ionic's button takes its link as properties (its own `<a>` lives in its shadow), not as attributes.
    expect(found.map((el) => [el.textContent?.trim(), el.href, el.target, el.rel, el.fill])).toEqual([
      ['Windows', DOWNLOADS.windows, '_blank', 'noopener', 'solid'],
      ['Linux', DOWNLOADS.linux, '_blank', 'noopener', 'outline'],
      ['Android', DOWNLOADS.android, '_blank', 'noopener', 'outline'],
    ]);
    expect(found.map((el) => el.getAttribute('aria-label'))).toEqual([
      'Download the ERPlora app for Windows',
      'Download the ERPlora app for Linux',
      'Download the ERPlora app for Android',
    ]);
  });

  it('in Spanish', async () => {
    embed(DOWNLOADS);
    const { m, found } = await buttons('es');
    expect(m.find('downloads').attributes('aria-label')).toBe('Descargar la app de ERPlora');
    expect(found.map((el) => el.getAttribute('aria-label'))).toEqual([
      'Descargar la app de ERPlora para Windows',
      'Descargar la app de ERPlora para Linux',
      'Descargar la app de ERPlora para Android',
    ]);
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface, where the app is installed, nothing', async (surface) => {
    embed(DOWNLOADS);
    applySurface(surface);
    const { m, found } = await buttons();
    expect(found).toHaveLength(0);
    expect(m.find('downloads').exists()).toBe(false);
  });

  it('without the addresses of erplora.com, no button that leads nowhere', async () => {
    embed(null);
    const { m } = await buttons();
    expect(m.find('downloads').exists()).toBe(false);
  });
});
