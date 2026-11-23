// hub#2315: asked from the assistant to take Reservations off the menu, the card only said «App: Reservas», though its
// yes turned off Tables too, which came along only with it; turning it back on said nothing of what came with it. Now
// each card names those apps before the yes, in the very words of the question the Apps screen asks on its switch. Each
// card is set beside that question, at each size, and cancelled. Reservations goes off once, through Apps' own command,
// to see the card of turning it on, and is turned on again at the end. End to end with the stack's SaaS gateway and
// the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this
// folder, «El asistente»).
// flow: BASE-F23 BASE-F24 BASE-F98
import { expect, type Page, test } from '@playwright/test';

import { flipApp } from './apps-switch-helpers';
import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { cancel, card, openPanelAtTheDesk, ownerIn } from './assistant-panel';
import { A, api, capture, testid } from './helpers';

cardSpec(['reservation'], () => undefined);

/** What goes with Reservations in `a` as it is seeded (every app on, the roots chosen): Tables, which only it needs. */
const OFF_WITH = 'Mesas se desactiva con ella: solo la necesitaba Reservas.';
const ON_WITH = 'Reservas necesita Mesas: se activa con ella.';

/** What the Apps screen asks on flipping Reservations' switch, answered «Cancelar». */
async function appsAsks(page: Page): Promise<string> {
  await page.goto(`${A}/apps#all`);
  await testid(page, 'apps-search').locator('input').fill('Reservas');
  await flipApp(page, 'reservation');
  const asks = page.locator('.ep-confirm-dialog').last();
  await expect(asks).toBeVisible();
  const said = await asks.innerText();
  await asks.getByRole('button', { name: 'Cancelar' }).click();
  await expect(asks).toBeHidden();
  return said;
}

/** The assistant's card of `tool` for Reservations, showing `line` at each size (captured as `key`) and cancelled: what
 *  its datum of the apps along says. */
async function cardSays(page: Page, tool: string, line: string, key: string): Promise<string> {
  await openPanelAtTheDesk(page);
  const fields = await fieldsOf(page, tool, { app: 'reservation' });
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(line);
    await capture(page, `hub-2315-assistant-app-card-${key}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await cancel(page);
  return String(fields.find((field) => field.name === 'along')?.value ?? '');
}

test('BASE-F23 BASE-F24 — the cards of turning Reservations off and on name what goes with it, as Apps asks', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  try {
    expect(await appsAsks(page)).toContain(OFF_WITH);
    expect(await cardSays(page, 'base__app__disable', `Otras apps: ${OFF_WITH}`, 'off')).toBe(OFF_WITH);

    const off = await api<{ along: { id: string }[] }>(context, A, 'POST', '/apps/disable', { app: 'reservation' });
    expect(off.data.along.map((app) => app.id)).toEqual(['table']);
    expect(await appsAsks(page)).toContain(ON_WITH);
    expect(await cardSays(page, 'base__app__enable', ON_WITH, 'on')).toBe(ON_WITH);
  } finally {
    await api(context, A, 'POST', '/apps/enable', { app: 'reservation' });
    await context.close();
  }
});
