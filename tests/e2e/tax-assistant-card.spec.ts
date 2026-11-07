// hub#678: since hub#416 the assistant's card left out every id its schema does not mark, so «deactivate this rule»,
// «end it on 31 December» or «add the equivalence surcharge to it» said no rule, and a country went by its ISO code
// («DE»). Now a rule is named as the Rules screen tells one from another — its category, its country and its rate —,
// read as the person, in their language, never by its id or its category's key; and a country by its name. End to end
// with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must
// be seeded with it (README of this folder, «El asistente»). Cancelled, nothing changes. What this file creates hangs
// from a category `e2e.card_…` and goes away before and after (tax-helpers' `cleanUp`); Taxes, if this file turned it
// on, is turned off again.
// flow: TAX-F04 TAX-F06 TAX-F07 TAX-F08 TAX-F12 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, untilStill } from './helpers';
import { cleanUp, createRule, freshCategory, rulesOf } from './tax-helpers';

/** A business is born with every app off. */
const NEEDED = ['tax'];
const NBSP = ' ';

/** What the screens call a rule and each country, and how each language writes a rate, by the language of the card. */
const WORDS = {
  es: {
    rule: 'Regla',
    root: 'Regla raíz',
    country: 'País',
    spain: 'España',
    germany: 'Alemania',
    france: 'Francia',
    rate: (n: string) => `${n}${NBSP}%`,
  },
  en: {
    rule: 'Rule',
    root: 'Root rule',
    country: 'Country',
    spain: 'Spain',
    germany: 'Germany',
    france: 'France',
    rate: (n: string) => `${n}%`,
  },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

cardSpec(NEEDED, cleanUp);

/** A category of this run and its 10 % rule in Spain, through the app's own API. */
async function aRule(context: BrowserContext) {
  const key = await freshCategory(context, 'card');
  const category = await api<{ display_name: string }>(context, A, 'GET', `/tax/categories/detail?key=${key}`);
  expect(category.status, JSON.stringify(category.data)).toBe(200);
  const rule = await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: '10' });
  return { key, name: category.data.display_name, rule };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`tax-assistant-card — in ${language}, a write of Taxes says which rule and which country, never an id or a code`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { key, name, rule } = await aRule(context);
    const said = `${name} · ${words.spain} · ${words.rate('10')}`;
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Desactiva esta regla», a dangerous write: the rule by its category, country and rate (never its id nor its
    // category's key), titled as the Rules list calls one, in every size.
    const deactivated = await datumOf(page, 'tax__rule__deactivate', { id: rule.id });
    expect([deactivated.label, deactivated.value]).toEqual([words.rule, said]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.rule}: ${said}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(key);
      await untilStill(page);
      await capture(page, `hub-678-rule-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Desactiva la regla de esta categoría en Alemania», by its slot: the country by its name, never «DE».
    const bySlot = await datumOf(page, 'tax__rule__deactivate', { country_code: 'DE', tax_category_key: key }, 'country_code');
    expect([bySlot.label, bySlot.value]).toEqual([words.country, words.germany]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.country}: ${words.germany}`);
      await untilStill(page);
      await capture(page, `hub-678-country-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Añádele el recargo de equivalencia»: the root rule the component hangs from by its name, under its field's name.
    const component = await fieldsOf(page, 'tax__rule__create', {
      country_code: 'ES',
      tax_category_key: key,
      rate_pct: '5.2',
      parent_id: rule.id,
      component_label: 'Recargo de equivalencia',
    });
    const root = component.find((field) => field.name === 'parent_id');
    expect([root?.label, root?.value]).toEqual([words.root, said]);
    expect(component.find((field) => field.name === 'country_code')?.value).toBe(words.spain);
    await cancel(page);

    // «Crea estas dos reglas»: each line of the batch carries its country by its name, in the order sent.
    const batch = await datumOf(
      page,
      'tax__rule__bulk_create',
      {
        rules: [
          { country_code: 'DE', tax_category_key: key, rate_pct: '19' },
          { country_code: 'FR', tax_category_key: key, rate_pct: '20' },
        ],
      },
      'rules',
    );
    expect((batch.value as { country_code: string }[]).map((line) => line.country_code)).toEqual([
      words.germany,
      words.france,
    ]);
    await cancel(page);

    // Cancelled, nothing changed: the one rule of the category, still active, with no component.
    const rules = await rulesOf(context, key);
    expect(rules.map((one) => [one.id, one.is_active, one.parent_id])).toEqual([[rule.id, true, null]]);
    await context.close();
  });
}
