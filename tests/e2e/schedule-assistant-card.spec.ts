// hub#675: since hub#416 the assistant's card left out every id its schema does not mark, so «delete the Christmas
// special day» or «change the summer hours» said no special day and no temporary change. Now each one is named as the
// screens' «Delete» dialog names it — a special day by its name, a temporary change by its reason —, read as the person,
// in their language, never by its id. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). Cancelled, nothing changes. What this file creates is named «E2E …» (dates of 2099) and goes away; the app
// it turns on is turned off again.
// flow: SCHEDULE-F06 SCHEDULE-F13 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, untilStill } from './helpers';
import { post } from './pricing-helpers';
import { cleanupExceptions, TAG } from './schedule-helpers';

/** A business is born with every app off. */
const NEEDED = ['schedule'];

/** What the screens call each record, by the language of the card. */
const WORDS = {
  es: { specialDay: 'Día especial', override: 'Cambio temporal' },
  en: { specialDay: 'Special day', override: 'Temporary change' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

cardSpec(NEEDED, cleanupExceptions);

/** A special day and a temporary change, through Schedules' own API. */
async function aCalendar(context: BrowserContext) {
  const christmas = await post<{ id: string; name: string }>(context, '/schedule/special_days', {
    date: '2099-12-25',
    name: `${TAG} Navidad`,
  });
  const summer = await post<{ id: string; reason: string }>(context, '/schedule/overrides', {
    start_date: '2099-07-01',
    end_date: '2099-08-31',
    reason: `${TAG} Horario de verano`,
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '15:00' }],
  });
  return { christmas, summer };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`schedule-assistant-card — in ${language}, a write of Schedules says which special day or temporary change, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { christmas, summer } = await aCalendar(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra el festivo de Navidad», a dangerous write: the special day by its name, titled as its screen titles it, in
    // every size.
    const deleted = await datumOf(page, 'schedule__special_day__delete', { id: christmas.id });
    expect([deleted.label, deleted.value]).toEqual([words.specialDay, christmas.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.specialDay}: ${christmas.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-675-special-day-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Cambia el horario de verano a Verano»: a write that is not dangerous is said in one line; the temporary change by
    // its reason, beside the new one.
    const changed = await datumOf(page, 'schedule__override__update', { id: summer.id, reason: `${TAG} Verano` });
    expect([changed.label, changed.value]).toEqual([words.override, summer.reason]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(summer.reason);
      await expect(card(page)).toContainText(`${TAG} Verano`);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-675-override-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Borra el horario de verano»: titled as its screen titles it.
    const removed = await datumOf(page, 'schedule__override__delete', { id: summer.id });
    expect([removed.label, removed.value]).toEqual([words.override, summer.reason]);
    await expect(card(page)).toContainText(`${words.override}: ${summer.reason}`);
    await expect(card(page)).not.toContainText(GENERIC[language]);
    await cancel(page);

    // Cancelled, nothing changed: the special day and the temporary change still there, as they were.
    const days = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `/schedule/special_days?name=${encodeURIComponent(TAG)}`);
    expect(days.status, JSON.stringify(days.data)).toBe(200);
    expect(days.data.rows.map((row) => [row.id, row.name])).toEqual([[christmas.id, christmas.name]]);
    const changes = await api<{ rows: { id: string; reason: string }[] }>(context, A, 'GET', `/schedule/overrides?reason=${encodeURIComponent(TAG)}`);
    expect(changes.status, JSON.stringify(changes.data)).toBe(200);
    expect(changes.data.rows.map((row) => [row.id, row.reason])).toEqual([[summer.id, summer.reason]]);
    await context.close();
  });
}
