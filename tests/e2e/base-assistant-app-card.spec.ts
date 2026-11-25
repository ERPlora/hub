// hub#2315: asked from the assistant to take Reservations off the menu, the card only said «App: Reservas», though its
// yes turned off Tables too, which came along only with it; turning it back on said nothing of what came with it. Now
// each card names those apps before the yes, in the one sentence the Apps screen's question shows on its switch (each
// row of `base.app.list` carries it). Each card is set beside that question, at each size, and cancelled, with one app
// and with two. Reservations goes off once, through Apps' own command, to see the card of turning it on, and is turned
// on again at the end. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»).
// flow: BASE-F19 BASE-F23 BASE-F24 BASE-F98
import { expect, type Page, test } from '@playwright/test';

import { flipApp } from './apps-switch-helpers';
import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { cancel, card, openPanelAtTheDesk, ownerIn, panel } from './assistant-panel';
import { A, api, capture, testid } from './helpers';

cardSpec(['reservation', 'online_booking'], () => undefined);

/** What goes with each app in `a` as it is seeded (every app on, the roots chosen). */
const OFF_WITH = 'Mesas se desactiva con ella: solo la necesitaba Reservas.';
const TWO_OFF_WITH = 'Citas y Servicios se desactivan con ella: solo las necesitaba Reservas online.';
const ON_WITH = 'Reservas necesita Mesas: se activa con ella.';

/** What the Apps screen asks on flipping `id`'s switch, found by `name`, at each size (captured as `key`), answered
 *  «Cancelar». */
async function appsAsks(page: Page, id: string, name: string, key: string): Promise<string> {
  let said = '';
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/apps#all`);
    await testid(page, 'apps-search').locator('input').fill(name);
    await flipApp(page, id);
    const asks = page.locator('.ep-confirm-dialog').last();
    await expect(asks).toBeVisible();
    said = await asks.innerText();
    await capture(page, `hub-2315-apps-question-${key}-${vp.label}`);
    await asks.getByRole('button', { name: 'Cancelar' }).click();
    await expect(asks).toBeHidden();
  }
  return said;
}

/** The assistant's card of `tool` for `app`, showing `line` at each size (captured as `key`) and cancelled: what its
 *  datum of the apps along says. */
async function cardSays(page: Page, tool: string, app: string, line: string, key: string): Promise<string> {
  await openPanelAtTheDesk(page);
  const fields = await fieldsOf(page, tool, { app });
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(line);
    await capture(page, `hub-2315-assistant-app-card-${key}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await cancel(page);
  // Closed, or it stays open over Apps when the next question is asked on a phone.
  await panel(page).locator('[data-testid="assistant-close"]').click();
  await expect(panel(page)).toBeHidden();
  return String(fields.find((field) => field.name === 'along')?.value ?? '');
}

test('BASE-F23 BASE-F24 — the cards of turning an app off and on name what goes with it, as Apps asks', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  try {
    // Online orders needs Tables too: off, Reservations is the only app on that needs it.
    expect((await api(context, A, 'POST', '/apps/disable', { app: 'online_order' })).status).toBe(200);
    expect(await appsAsks(page, 'reservation', 'Reservas', 'off')).toContain(OFF_WITH);
    expect(await cardSays(page, 'base__app__disable', 'reservation', `Otras apps: ${OFF_WITH}`, 'off')).toBe(OFF_WITH);

    expect(await appsAsks(page, 'online_booking', 'Reservas online', 'two-off')).toContain(TWO_OFF_WITH);
    const two = await cardSays(page, 'base__app__disable', 'online_booking', `Otras apps: ${TWO_OFF_WITH}`, 'two-off');
    expect(two).toBe(TWO_OFF_WITH);

    const off = await api<{ along: { id: string }[] }>(context, A, 'POST', '/apps/disable', { app: 'reservation' });
    expect(off.data.along.map((app) => app.id)).toEqual(['table']);
    expect(await appsAsks(page, 'reservation', 'Reservas', 'on')).toContain(ON_WITH);
    expect(await cardSays(page, 'base__app__enable', 'reservation', ON_WITH, 'on')).toBe(ON_WITH);
  } finally {
    await api(context, A, 'POST', '/apps/enable', { app: 'reservation' });
    await api(context, A, 'POST', '/apps/enable', { app: 'online_order' });
    await context.close();
  }
});
