// The dangerous card of the assistant calls each datum by the title its app wrote for it (BASE-F97 step 2 and
// BASE-F98): transferring a check (TABLE-F15, dangerous) must not say «Registro: 5 (Terraza)», the card's own word for
// a datum named `id`, where Tables titles it «Cuenta». End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). The owner asks,
// in Spanish, to transfer the check of table 5 of the terrace to table 2 of the dining room: the card says «Cuenta» and
// «Mesa de destino», never «Registro»; and to remove a device of the platform (BASE-F98), named «Barra» in Settings ›
// Devices: the card says «Dispositivo: Barra», as every dangerous write of the platform titles the record it acts on.
// Cancelled, nothing changes. What this file creates carries `E2EDcl` and goes away; the apps it turns on are turned off
// again, and the device gets its name back.
// flow: base-assistant-danger-card-labels
// flow: BASE-F97 BASE-F98 TABLE-F15
import { expect, type Page, test } from '@playwright/test';

import { ask, cancelledAtTheDesk, cardSpec, ownerIn, thisDeviceNamed } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, exposeMovingInPage, untilStill } from './helpers';
import { cleanRoom } from './sale-helpers';

const KEY = 'FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME';
const TAG = 'E2EDcl';
const TERRACE = `${TAG}Terraza`;
const ROOM = `${TAG}Comedor`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
/** The apps a table needs, in the order they require each other: a business is born with every app off. */
const NEEDED = ['customer', 'tax', 'sale', 'table'];

type Table = { id: string; label: string };
type Check = { id: string; label: string; table_id: string | null; status: string };

// The room this file made goes away before each test and after the last, with the checks its seating opened.
cardSpec(NEEDED, () => cleanRoom(TAG));


/** The dangerous card ready for its capture, as base-assistant.spec.ts waits for it: «Confirmación» focused, its
 *  label floated and nothing moving on the page, the label's move included, two frames apart. */
async function confirmationSettled(page: Page): Promise<boolean> {
  const field = card(page).locator('[data-testid="assistant-confirm-input"]');
  await expect(field).toHaveClass(/\bhas-focus\b/);
  await expect(field).toHaveClass(/\blabel-floating\b/);
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
  await untilStill(page);
  await exposeMovingInPage(page);
  return field.evaluate(async (input) => {
    const label = input.querySelector('.label-text-wrapper');
    const look = () =>
      label && `${JSON.stringify(label.getBoundingClientRect())} ${getComputedStyle(label).transform} ${getComputedStyle(label).opacity}`;
    const before = look();
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    const moving = (window as unknown as { __movingInPage: () => string[] }).__movingInPage();
    return input.classList.contains('has-focus') && label !== null && look() === before && moving.length === 0;
  });
}

test('base-assistant-danger-card-labels — in Spanish transferring a check calls it «Cuenta», the title Tables gives it, never «Registro»', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  const tables: Table[] = [];
  for (const [name, number] of [
    [TERRACE, '5'],
    [ROOM, '2'],
  ]) {
    const zone = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name });
    expect(zone.status, JSON.stringify(zone.data)).toBe(201);
    const table = await api<Table>(context, A, 'POST', '/table/tables', { zone_id: zone.data.id, number });
    expect(table.status, JSON.stringify(table.data)).toBe(201);
    tables.push(table.data);
  }
  const [five, two] = tables;
  const seated = await api<Check>(context, A, 'POST', '/table/sessions/open', { table_id: five.id, guests_count: 2 });
  expect(seated.status, JSON.stringify(seated.data)).toBe(201);
  expect(seated.data.label).toBe(`5 (${TERRACE})`);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK table__session__transfer ${JSON.stringify({ id: seated.data.id, to_table_id: two.id })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Cuenta: 5 (${TERRACE})`);
    await expect(card(page)).toContainText(`Mesa de destino: 2 (${ROOM})`);
    await expect(card(page)).not.toContainText('Registro:');
    for (const id of [seated.data.id, two.id]) await expect(card(page)).not.toContainText(id);
    expect(await confirmationSettled(page), `${KEY}-check-${vp.label} caught before it settled`).toBe(true);
    await capture(page, `${KEY}-check-${vp.label}`);
  }
  await cancelledAtTheDesk(page);
  const after = await api<Check>(context, A, 'GET', `/table/sessions/detail?id=${seated.data.id}`);
  expect([after.data.table_id, after.data.status]).toEqual([five.id, 'open']);
  // The session, for ui-clip-sweep.sh over the screen behind the card (its pages are behind the login).
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test('base-assistant-danger-card-labels — in Spanish removing a device calls it «Dispositivo», the title the platform gives it, never «Registro»', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  // Named as the business names it in Settings › Devices, and given its name back at the end.
  const { device, stays } = await thisDeviceNamed(context, 'Barra');
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK base__device__remove ${JSON.stringify({ id: device!.id })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Quitar en Ajustes. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText('Dispositivo: Barra');
    await expect(card(page)).not.toContainText('Registro:');
    await expect(card(page)).not.toContainText(device!.id);
    expect(await confirmationSettled(page), `${KEY}-${vp.label} caught before it settled`).toBe(true);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await cancelledAtTheDesk(page);
  await stays();
  await context.close();
});
