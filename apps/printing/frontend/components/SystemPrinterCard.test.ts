// «Your printer», Printing's card in System › «Usage and plan» (hub#683; the old hub's of «Resources», HUB_SHELL-F137 and
// F138): base mounts it while Printing is on, for everybody with Printing. It says who prints, leads to Printing with
// «Set up printing» and, in a browser, says where to get the ERPlora app for Windows, Linux or Android (erplora.com's
// doors, `hub-home.app_downloads`), each opening outside the hub. Inside the installed app, no download: it would be the
// app offering itself. Whether the printer answers now is not said: Printing has no such read yet (hub#683's own issue).
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { embedHubHome, forgetHubHome } from '../../../../base/frontend/__tests__/hub-home';
import { flush, mountPrinting } from '../__tests__/mount-printing';
import SystemPrinterCard from './SystemPrinterCard.vue';

const SAAS = 'http://localhost:8001';
const DOWNLOADS = {
  windows: `${SAAS}/app/download/windows/`,
  linux: `${SAAS}/app/download/linux/`,
  android: `${SAAS}/app/download/android/`,
};

const embed = (downloads: Record<string, string> | null) => embedHubHome(downloads && { name: 'Bar', app_downloads: downloads });

async function card(locale: 'en' | 'es' = 'en') {
  const m = await mountPrinting(SystemPrinterCard, { locale, path: '/system' });
  await flush();
  return m;
}

afterEach(forgetHubHome);

describe('SystemPrinterCard', () => {
  it('says who prints and leads to Printing', async () => {
    embed(DOWNLOADS);
    const m = await card();
    expect(m.find('printing-system-card-title').text()).toBe('Your printer');
    expect(m.find('printing-system-card-intro').text()).toBe(
      'Receipts, kitchen orders and labels are printed by the ERPlora app on the device next to the printer.',
    );
    expect(m.find('printing-system-card-setup').text()).toBe('Set up printing');
    await m.find('printing-system-card-setup').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/printing/printers');
    // It reads nothing: whether the printer answers is no read of Printing yet.
    expect(m.client.stream.subscriptions('printing.device.coverage')).toEqual([]);
  });

  it('in a browser, where to get the ERPlora app: Windows first, then Linux and Android, each outside the hub', async () => {
    embed(DOWNLOADS);
    const m = await card();
    expect(m.find('printing-system-card-download-title').text()).toBe('Download the ERPlora app');
    expect(m.find('printing-system-card-download-intro').text()).toBe(
      'The ERPlora app is what talks to your printers, the cash drawer and the scanners. Choose your system to continue.',
    );
    // Ionic's button takes its link as properties (its own `<a>` lives in its shadow), not as attributes.
    const buttons = m.wrapper
      .findAll('[data-testid^="printing-system-card-download-"]')
      .filter((button) => button.element.tagName === 'ION-BUTTON')
      .map((button) => ({ text: button.text(), el: button.element as HTMLElement & Record<string, unknown> }));
    expect(buttons.map(({ text, el }) => [text, el.href, el.target, el.rel])).toEqual([
      ['Windows', DOWNLOADS.windows, '_blank', 'noopener'],
      ['Linux', DOWNLOADS.linux, '_blank', 'noopener'],
      ['Android', DOWNLOADS.android, '_blank', 'noopener'],
    ]);
    // The till's own system stands out; each one says what it downloads.
    expect(buttons.map(({ el }) => el.fill)).toEqual(['solid', 'outline', 'outline']);
    expect(buttons.map(({ el }) => el.getAttribute('aria-label'))).toEqual([
      'Download the ERPlora app for Windows',
      'Download the ERPlora app for Linux',
      'Download the ERPlora app for Android',
    ]);
  });

  it('in Spanish', async () => {
    embed(DOWNLOADS);
    const m = await card('es');
    expect(m.find('printing-system-card-title').text()).toBe('Tu impresora');
    expect(m.find('printing-system-card-intro').text()).toBe(
      'Los tiques, las comandas y las etiquetas los imprime la app de ERPlora del dispositivo que está junto a la impresora.',
    );
    expect(m.find('printing-system-card-setup').text()).toBe('Configurar la impresión');
    expect(m.find('printing-system-card-download-title').text()).toBe('Descargar la app de ERPlora');
    expect(m.find('printing-system-card-download-intro').text()).toBe(
      'La app de ERPlora es la que habla con tus impresoras, el cajón y los escáneres. Elige tu sistema para continuar.',
    );
  });

  it.each(['desktop', 'mobile'] as const)('inside the installed app (%s), no download, and Printing still a tap away', async (surface) => {
    embed(DOWNLOADS);
    applySurface(surface);
    const m = await card();
    expect(m.find('printing-system-card-download-title').exists()).toBe(false);
    expect(m.wrapper.findAll('[data-testid^="printing-system-card-download-"]')).toHaveLength(0);
    expect(m.find('printing-system-card-setup').exists()).toBe(true);
  });

  it('without the addresses of erplora.com, no download buttons that lead nowhere', async () => {
    embed(null);
    const m = await card();
    expect(m.wrapper.findAll('[data-testid^="printing-system-card-download-"]')).toHaveLength(0);
    expect(m.find('printing-system-card-title').text()).toBe('Your printer');
  });
});
