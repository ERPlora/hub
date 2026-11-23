// Asking the assistant to have the till ask everyone for their PIN again after some minutes without use: its card says
// each control of the «PIN pad» card of Settings › General it sets, by its name there and the value it will show
// («Mostrar pinpad: Sí», «Volver a preguntar tras inactividad: 10 min»), never «Pedir el PIN: Siempre…» without its
// minutes. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool>
// <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). Cancelled, nothing changes.
// flow: BASE-F67 BASE-F97 BASE-F98
import { expect, test } from '@playwright/test';

import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { cancel, card, captureConfirmation, openPanelAtTheDesk, ownerIn } from './assistant-panel';
import { A, api } from './helpers';

cardSpec([], () => undefined);

interface PinPad {
  pin_policy: 'always' | 'per_shift' | 'never';
  pin_inactivity_minutes: number;
  pin_length: number;
}

const EXPECTED = {
  es: { show: 'Mostrar pinpad', again: 'Volver a preguntar tras inactividad', yes: 'Sí' },
  en: { show: 'Show PIN pad', again: 'Ask again after inactivity', yes: 'Yes' },
};

for (const language of ['es', 'en'] as const) {
  test(`pin-pad-card — in ${language}, the card says the controls of Settings it sets`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    await openPanelAtTheDesk(page);
    const before = await api<PinPad>(context, A, 'GET', '/access/settings');
    expect(before.status).toBe(200);
    try {
      // Until signing out before asking, as the business of the issue had it: a cancelled card that ran would show.
      const shift = await api<PinPad>(context, A, 'POST', '/access/settings/update', { pin_policy: 'per_shift' });
      expect(shift.status, JSON.stringify(shift.data)).toBe(200);

      const fields = await fieldsOf(page, 'base__access__settings_update', {
        pin_policy: 'always',
        pin_inactivity_minutes: 10,
      });
      const words = EXPECTED[language];
      expect(fields.map(({ name, label, kind, value }) => ({ name, label, kind, value }))).toEqual([
        { name: 'pin_pad', label: words.show, kind: 'bool', value: true },
        { name: 'ask_again', label: words.again, kind: 'text', value: '10 min' },
      ]);

      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await expect(card(page)).toContainText(`${words.show}: ${words.yes}`);
        await expect(card(page)).toContainText(`${words.again}: 10 min`);
        await captureConfirmation(page, `hub-2201-pin-pad-card-${language}-${vp.label}`);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await cancel(page);

      const after = await api<PinPad>(context, A, 'GET', '/access/settings');
      expect(after.data.pin_policy).toBe('per_shift');
    } finally {
      await api<PinPad>(context, A, 'POST', '/access/settings/update', {
        pin_policy: before.data.pin_policy,
        ...(before.data.pin_policy === 'always' ? { pin_inactivity_minutes: before.data.pin_inactivity_minutes } : {}),
      });
    }
    await context.close();
  });
}
