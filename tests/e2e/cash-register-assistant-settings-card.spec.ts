// Asking the assistant to make the drawer require an opening float and a count to close: its card says each setting by
// its name beside its value, as «Cash register › Settings» calls them («Exigir fondo de apertura: Sí»), never a row of
// bare «Sí» that says nothing of what it turns on. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder,
// «El asistente»). Cancelled, nothing changes.
// flow: CASH_REGISTER-F01 BASE-F97
import { expect, test } from '@playwright/test';

import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { cancel, card, openPanelAtTheDesk, ownerIn } from './assistant-panel';
import { A, api, capture, untilStill } from './helpers';

cardSpec(['cash_register'], () => undefined);

interface Settings {
  require_opening_balance: boolean;
  require_closing_balance: boolean;
}

const EXPECTED = {
  es: {
    line: 'Cambiar en Caja: Exigir fondo de apertura: Sí · Exigir recuento al cierre: Sí',
    labels: ['Exigir fondo de apertura', 'Exigir recuento al cierre'],
  },
  en: {
    line: 'Change in Cash register: Require an opening float: Yes · Require a count to close: Yes',
    labels: ['Require an opening float', 'Require a count to close'],
  },
};

for (const language of ['es', 'en'] as const) {
  test(`cash-register-settings-card — in ${language}, the card names each setting it turns on`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    await openPanelAtTheDesk(page);
    const before = await api<Settings>(context, A, 'GET', '/cash_register/settings');
    expect(before.status).toBe(200);

    const fields = await fieldsOf(page, 'cash_register__settings__update', {
      require_opening_balance: true,
      require_closing_balance: true,
    });
    expect(fields.map(({ name, label, kind, value }) => ({ name, label, kind, value }))).toEqual([
      { name: 'require_opening_balance', label: EXPECTED[language].labels[0], kind: 'bool', value: true },
      { name: 'require_closing_balance', label: EXPECTED[language].labels[1], kind: 'bool', value: true },
    ]);

    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(EXPECTED[language].line);
      await untilStill(page);
      await capture(page, `hub-2176-cash-register-settings-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    const after = await api<Settings>(context, A, 'GET', '/cash_register/settings');
    expect(after.status).toBe(200);
    expect([after.data.require_opening_balance, after.data.require_closing_balance]).toEqual([
      before.data.require_opening_balance,
      before.data.require_closing_balance,
    ]);
    await context.close();
  });
}
