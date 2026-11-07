// hub#671: since hub#416 the assistant's card left out every id its schema does not mark, so «cancel ticket 12», «delete
// the grill», «the burger and the omelette of table 4 are ready», «send the burgers to the grill» or «send the terrace's
// check to the kitchen, takeaway» said no ticket, no station, no dish, no product and no check, and the ticket type went
// as its code. Now each one is named as the screens name it — a ticket by its number, a dish, a station and a product
// by their name, a check of Sales by its title, the type by its label —, read as the person, in their language, never
// by its id. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). Cancelled, nothing
// changes. What this file creates is named «E2E Tarjeta …» (the check «e2e tarjeta …», SKU `E2E-TJK-…`) and goes away
// before and after; the apps it turns on are turned off again.
// flow: KITCHEN-F03 KITCHEN-F04 KITCHEN-F11 KITCHEN-F18 KITCHEN-F22 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql } from './helpers';
import { cleanInventory, createProduct, stamp } from './inventory-helpers';
import { cleanSales } from './sale-helpers';
import { post } from './service-helpers';

/** A business is born with every app off; Kitchen requires Sales and Inventory, and they Taxes and Customers. */
const NEEDED = ['tax', 'customer', 'inventory', 'sale', 'kitchen'];
const TAG = 'E2E Tarjeta';

/** What the screens call each record, by the language of the card, and how they say a takeaway ticket. */
const WORDS = {
  es: { ticket: 'Comanda', station: 'Estación', dishes: 'Platos', product: 'Producto', check: 'Cuenta', type: 'Tipo de comanda', takeaway: 'Para llevar' },
  en: { ticket: 'Ticket', station: 'Station', dishes: 'Dishes', product: 'Product', check: 'Check', type: 'Ticket type', takeaway: 'Takeaway' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Every ticket, station and route this file made, from hub `a`'s database; then its check and its products. */
function cleanUp(): void {
  const tickets = `select id from kitchen_ticket where label like '${TAG}%'`;
  const stations = `select id from kitchen_station where name like '${TAG}%'`;
  psql(
    [
      `delete from kitchen_logentry where ticket_id in (${tickets}) or station_id in (${stations})`,
      `delete from kitchen_ticketitem where ticket_id in (${tickets})`,
      `delete from kitchen_ticket where id in (${tickets})`,
      `delete from kitchen_productroute where station_id in (${stations}) or product_id in (select id from inventory_product where sku like 'E2E-TJK-%')`,
      `delete from kitchen_categoryroute where station_id in (${stations})`,
      `delete from kitchen_station where id in (${stations})`,
    ].join('; '),
  );
  cleanSales();
  cleanInventory();
}

cardSpec(NEEDED, cleanUp);

interface Ticket {
  id: string;
  number: string;
  label: string;
  status: string;
  items: { id: string; name: string }[];
}

/** A burger, a station with its printer, a ticket made by hand with the burger and an omelette (each with its note) and
 *  an open check of Sales with the burger on it, through the apps' own APIs. */
async function aKitchen(context: BrowserContext) {
  const tag = stamp();
  const burger = await createProduct(context, { name: `${TAG} Hamburguesa ${tag}`, sku: `E2E-TJK-HAM-${tag}` });
  const station = await post<{ id: string; name: string; printer_name: string }>(context, '/kitchen/stations', {
    name: `${TAG} Plancha ${tag}`,
    printer_name: `Impresora ${tag}`,
  });
  const ticket = await post<Ticket>(context, '/kitchen/tickets', {
    label: `${TAG} Mesa 4 ${tag}`,
    items: [
      { product_id: burger.id, quantity: '2', notes: 'poco hecha' },
      { name: `${TAG} Tortilla ${tag}`, notes: 'sin cebolla' },
    ],
  });
  const check = await post<{ id: string; label: string }>(context, '/sale/orders', { label: `e2e tarjeta Terraza ${tag}` });
  await post(context, '/sale/orders/add_line', { order_id: check.id, product_id: burger.id, quantity: '1' }, 200);
  return { burger, station, ticket, check };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`kitchen-assistant-card — in ${language}, a write of Kitchen says which ticket, dish, station, product or check, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { burger, station, ticket, check } = await aKitchen(context);
    const [burgerDish, omelette] = ticket.items;
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Cancela la comanda de la mesa 4», a dangerous write: the ticket by its number (never its label), titled as its
    // list calls one, in every size.
    const cancelled = await datumOf(page, 'kitchen__ticket__cancel', { ticket_id: ticket.id }, 'ticket_id');
    expect([cancelled.label, cancelled.value]).toEqual([words.ticket, ticket.number]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.ticket}: ${ticket.number}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(ticket.label);
      await capture(page, `hub-671-ticket-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Elimina la plancha», a dangerous write: the station by its name (never its printer), in every size.
    const deleted = await datumOf(page, 'kitchen__station__delete', { station_id: station.id }, 'station_id');
    expect([deleted.label, deleted.value]).toEqual([words.station, station.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.station}: ${station.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(station.printer_name);
      await capture(page, `hub-671-station-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «La tortilla y la hamburguesa de la mesa 4 están listas»: the ticket by its number and its dishes by their names,
    // in the order sent, said one by one (never «2 items») and never by their notes.
    const bumped = await fieldsOf(page, 'kitchen__item__bump', { ticket_id: ticket.id, item_ids: [omelette.id, burgerDish.id] });
    expect(bumped.map((field) => [field.name, field.label, field.value])).toEqual([
      ['ticket_id', words.ticket, ticket.number],
      ['item_ids', words.dishes, [omelette.name, burgerDish.name]],
    ]);
    expect(bumped[1].named).toBe(true);
    await expect(card(page)).toContainText(omelette.name);
    await expect(card(page)).toContainText(burger.name);
    await expect(card(page)).not.toContainText('sin cebolla');
    await cancel(page);

    // «Manda las hamburguesas a la plancha»: the product and the station by their names, never the SKU.
    const routed = await fieldsOf(page, 'kitchen__routing__set', { product_id: burger.id, station_id: station.id });
    expect(routed.map((field) => [field.name, field.label, field.value])).toEqual([
      ['product_id', words.product, burger.name],
      ['station_id', words.station, station.name],
    ]);
    await expect(card(page)).toContainText(station.name);
    await expect(card(page)).not.toContainText(burger.sku);
    await cancel(page);

    // «Manda a cocina la cuenta de la terraza, para llevar»: the check by its title and the type by its label, never
    // its code.
    const sent = await fieldsOf(page, 'kitchen__ticket__send', { order_id: check.id, channel: 'takeaway' });
    expect(sent.map((field) => [field.name, field.label, field.value])).toEqual([
      ['order_id', words.check, check.label],
      ['channel', words.type, words.takeaway],
    ]);
    await expect(card(page)).toContainText(check.label);
    await expect(card(page)).toContainText(words.takeaway);
    await expect(card(page)).not.toContainText(/takeaway/);
    await cancel(page);

    // Cancelled, nothing changed: the ticket still to prepare, the station still there with nothing routed to it, and
    // nothing of the check sent to the kitchen.
    const detail = await api<Ticket>(context, A, 'GET', `/kitchen/tickets/detail?ticket_id=${ticket.id}`);
    expect([detail.status, detail.data.status], JSON.stringify(detail.data)).toEqual([200, 'pending']);
    const stations = await api<{ rows: { id: string; routes: number }[] }>(
      context, A, 'GET', `/kitchen/stations?search=${encodeURIComponent(station.name)}`,
    );
    expect(stations.data.rows.map((row) => [row.id, row.routes])).toEqual([[station.id, 0]]);
    const rounds = await api<{ tickets: unknown[] }>(context, A, 'GET', `/kitchen/tickets/by_order?order_id=${check.id}`);
    expect([rounds.status, rounds.data.tickets]).toEqual([200, []]);
    await context.close();
  });
}
