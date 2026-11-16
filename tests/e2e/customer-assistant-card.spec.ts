// hub#513: since hub#416 the assistant's card left out every id its schema does not mark, so «add a note to Ana»,
// «merge these two cards», «delete that group» or «this tab is Luis's» said no customer, no group and no order. Now each
// record of Customers is named as its screens show it, read as the person, in their language, never by its id; the open
// order as Sales names it. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). Cancelled, nothing
// changes. What this file creates carries the customers' prefix (`e2e.`) and goes away; the apps it turns on are turned
// off again.
// flow: CUSTOMER-F05 CUSTOMER-F06 CUSTOMER-F13 CUSTOMER-F19 CUSTOMER-F27 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { cleanUp as cleanCustomers, e2eName, PREFIX } from './customer-helpers';
import { A, api, capture, psql, untilStill } from './helpers';
import { post } from './pricing-helpers';

/** A business is born with every app off; Sales is the one that names an open order. */
const NEEDED = ['customer', 'sale'];

/** What each screen calls the record, by the language of the card. */
const WORDS = {
  es: { customer: 'Cliente', duplicate: 'Ficha duplicada', groups: 'Grupos', group: 'Grupo', order: 'Pedido abierto' },
  en: { customer: 'Customer', duplicate: 'Duplicate customer', groups: 'Groups', group: 'Group', order: 'Open order' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Deletes what this file created: the customers' own (cards, groups…) and the open checks titled `e2e.…`. */
function cleanUp(): void {
  cleanCustomers();
  const orders = `select id from sale_order where label like '${PREFIX}%'`;
  psql([`delete from sale_orderline where order_id in (${orders})`, `delete from sale_order where id in (${orders})`].join('; '));
}

cardSpec(NEEDED, cleanUp);

/** Two cards of the same person, a group and an open check, through Customers' and Sales' own APIs. */
async function aFile(context: BrowserContext) {
  const ana = await post<{ id: string; name: string }>(context, '/customer/customers', { name: e2eName('Ana López') });
  const duplicate = await post<{ id: string; name: string }>(context, '/customer/customers', { name: e2eName('Ana Lopez') });
  const group = await post<{ id: string; name: string }>(context, '/customer/groups', { name: e2eName('VIP') });
  const order = await post<{ id: string; label: string }>(context, '/sale/orders', { label: e2eName('Mesa 4') });
  return { ana, duplicate, group, order };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`customer-assistant-card — in ${language}, a write of Customers says which card, group or order, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const file = await aFile(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Añade una nota a Ana», the case the issue names: whose card it is, in every size (a write that is not dangerous
    // is said in one line, «Añadir en Clientes: Ana López · …»).
    const noted = await datumOf(page, 'customer__note__add', { customer_id: file.ana.id, content: 'Window table' }, 'customer_id');
    expect([noted.label, noted.value]).toEqual([words.customer, file.ana.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(file.ana.name);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-513-note-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Une estas dos fichas», a dangerous write: the card that stays and the duplicate, each by its name.
    const merged = await datumOf(page, 'customer__customer__merge', { id: file.ana.id, absorbed_id: file.duplicate.id }, 'absorbed_id');
    expect([merged.label, merged.value]).toEqual([words.duplicate, file.duplicate.name]);
    await expect(card(page)).toContainText(`${words.customer}: ${file.ana.name}`);
    await expect(card(page)).not.toContainText(GENERIC[language]);
    await cancel(page);

    // «Pon a Ana en el grupo VIP»: the groups by their names.
    const grouped = await datumOf(page, 'customer__customer__set_groups', { id: file.ana.id, group_ids: [file.group.id] }, 'group_ids');
    expect([grouped.label, grouped.value]).toEqual([words.groups, [file.group.name]]);
    await expect(card(page)).toContainText(file.group.name);
    await cancel(page);

    // «Borra el grupo VIP», a dangerous one: titled as its screen titles it, in every size.
    const removed = await datumOf(page, 'customer__group__delete', { id: file.group.id });
    expect([removed.label, removed.value]).toEqual([words.group, file.group.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.group}: ${file.group.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await untilStill(page);
      await capture(page, `hub-513-group-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Esta cuenta es de Ana»: the open order as Sales names it.
    const linked = await datumOf(page, 'customer__order__link', { order_id: file.order.id, customer_id: file.ana.id }, 'order_id');
    expect([linked.label, linked.value]).toEqual([words.order, file.order.label]);
    await expect(card(page)).toContainText(file.order.label);
    await expect(card(page)).toContainText(file.ana.name);
    await cancel(page);

    // Cancelled, nothing changed: no note, both cards and the group still there, the order without a customer.
    const activity = await api<{ total: number }>(context, A, 'GET', `/customer/activity?customer_id=${file.ana.id}`);
    expect(activity.status, JSON.stringify(activity.data)).toBe(200);
    expect(activity.data.total).toBe(0);
    for (const id of [file.ana.id, file.duplicate.id]) {
      const still = await api(context, A, 'GET', `/customer/customers/detail?id=${id}`);
      expect(still.status, JSON.stringify(still.data)).toBe(200);
    }
    const groups = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/customer/groups?search=${encodeURIComponent(file.group.name)}`);
    expect(groups.data.rows.map((row) => row.id)).toEqual([file.group.id]);
    const owner = await api<{ customer_id: string | null }>(context, A, 'GET', `/customer/orders/customer?order_id=${file.order.id}`);
    expect(owner.status, JSON.stringify(owner.data)).toBe(200);
    expect(owner.data.customer_id).toBeNull();
    await context.close();
  });
}
