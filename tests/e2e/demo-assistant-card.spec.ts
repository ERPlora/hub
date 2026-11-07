// hub#670: since hub#416 the assistant's card left out every id its schema does not mark, so «delete the item Mesa 4»,
// «close it» or «add a coffee to it» said no item at all. Now the item is named as the screens name it — by its name —,
// read as the person, in their language, never by its id; its status by its word («Hecho», «Done»). End to end with the
// stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded
// with it (README of this folder, «El asistente»). Cancelled, nothing changes. What this file creates is named «E2E
// card …» and goes away; the app it turns on is turned off again.
// flow: DEMO-F02 DEMO-F03 DEMO-F04 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, capture, createItem, itemDetail, psql, untilStill } from './helpers';

/** A business is born with every app off. */
const NEEDED = ['demo'];
const TAG = 'E2E card';

/** What the screens call each datum, by the language of the card (frontend/locale of Demo). */
const WORDS = {
  es: { item: 'Elemento', status: 'Estado', done: 'Hecho', text: 'Texto' },
  en: { item: 'Item', status: 'Status', done: 'Done', text: 'Text' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

function cleanUp(): void {
  psql(
    [
      `delete from demo_itemline where item_id in (select id from demo_item where name like '${TAG}%')`,
      `delete from demo_item where name like '${TAG}%'`,
    ].join('; '),
  );
}

cardSpec(NEEDED, cleanUp);

/** An open item without lines, through Demo's own API. */
async function anItem(context: BrowserContext) {
  return createItem(context, A, `${TAG} Mesa 4 ${Date.now().toString(36)}`);
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`demo-assistant-card — in ${language}, a write of Demo says which item by its name, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const item = await anItem(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra el elemento Mesa 4», a dangerous write: the item by its name, titled as its screen calls one, in every size.
    const deleted = await datumOf(page, 'demo__item__delete', { id: item.id });
    expect([deleted.label, deleted.value]).toEqual([words.item, item.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.item}: ${item.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-670-delete-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Márcalo como hecho»: a write that is not dangerous is said in one line; the item by its name, its new status by
    // its word, never «done».
    const closed = await fieldsOf(page, 'demo__item__update', { id: item.id, status: 'done' });
    expect(closed.map((field) => [field.name, field.label, field.value])).toEqual([
      ['id', words.item, item.name],
      ['status', words.status, words.done],
    ]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(item.name);
      await expect(card(page)).toContainText(words.done);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-670-update-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Añádele un café»: the item the line goes on by its name, beside the line's text.
    const coffee = `${TAG} café`;
    const line = await fieldsOf(page, 'demo__item__add_line', { id: item.id, text: coffee, qty: '2' });
    expect(line.find((field) => field.name === 'id')).toMatchObject({ label: words.item, value: item.name });
    expect(line.find((field) => field.name === 'text')).toMatchObject({ label: words.text, value: coffee });
    await expect(card(page)).toContainText(item.name);
    await expect(card(page)).toContainText(coffee);
    await cancel(page);

    // Cancelled, nothing changed: the item still there, open and without lines.
    const after = await itemDetail(context, A, item.id);
    expect([after.name, after.status, after.lines.length]).toEqual([item.name, 'open', 0]);
    await context.close();
  });
}
