// Settings › Printing (BASE-G96; the old hub's «Impresión», HUB_SHELL-F165): one row, «Printers and ticket», that opens
// the Printing app, where printers are added and the ticket is set up; while Printing is not on, it says to install it
// and opens Apps.
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { flush, mountBase, OWNER } from '../../__tests__/mount-base';
import TicketsPanel from './TicketsPanel.vue';

/** A part of the row (Ionic's hydrated elements give happy-dom no text of their own). */
const part = (wrapper: { get: (s: string) => { text: () => string } }, which: 'title' | 'hint') =>
  wrapper.get(`[data-testid="tickets-printers"] [data-testid="settings-row-${which}"]`).text();

const withPrinting = (state: 'on' | 'off'): SessionMe => ({ ...OWNER, apps: [{ label: 'printing', state }] });

async function panel(session: SessionMe, locale: 'en' | 'es' = 'es') {
  return mountBase(TicketsPanel, { session, locale, routes: ['/printing/printers', '/apps'] });
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('TicketsPanel', () => {
  it('«Printers and ticket» opens the Printing app', async () => {
    const m = await panel(withPrinting('on'));
    expect(part(m.wrapper, 'title')).toBe('Impresoras y tique');
    expect(part(m.wrapper, 'hint')).toBe('Da de alta tu impresora y configura el tique impreso y digital');
    await m.wrapper.get('[data-testid="tickets-printers"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/printing/printers');
  });

  it('while Printing is not on, it says to install it and opens Apps', async () => {
    for (const session of [OWNER, withPrinting('off')]) {
      const m = await panel(session);
      expect(part(m.wrapper, 'hint')).toBe('Instala la app Impresión para dar de alta tu impresora y configurar el tique');
      await m.wrapper.get('[data-testid="tickets-printers"]').trigger('click');
      await flush();
      expect(m.router.currentRoute.value.path).toBe('/apps');
      m.wrapper.unmount();
    }
  });

  it('in English', async () => {
    const m = await panel(withPrinting('on'), 'en');
    expect(part(m.wrapper, 'title')).toBe('Printers and ticket');
  });
});
