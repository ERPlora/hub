// hub#829 — what an outlined dropdown has chosen reads whole with the field closed, on as many lines as it takes. Ionic
// keeps the select's `text` part on one line ending in «…»: at 320 the printer of each role in Printing › Settings cut
// «The first active one of this role» (15 px in English, 17 in Spanish), the agenda's status filter cut «Todos los
// estados» at 375 and the issuer's country its longest names. The rule is the shared theme's (@erplora/ui, polish.css,
// ui#98), for every outlined select. Each field is measured against its own box with every option it offers set in
// turn: the text against its box (`scrollWidth`, `scrollHeight`), the painted text against the field and its floating
// label; never a capture. In Chrome, against hub `a`, in English and in Spanish, at 320 (the narrowest phone still in
// use), 375, a tablet and a desktop. Nothing is saved: an option is set on the field, never chosen in its list, and the
// field gets its own back.
// flow: PRINTING-F06, INVOICE-F21, ui:theme
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, hostPage, settled, shown, signedInSpanish } from './helpers';

const SIZES = [
  { label: '320x568', width: 320, height: 568 },
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
] as const;
type Size = (typeof SIZES)[number];
const LANGS = ['en', 'es'] as const;
type Lang = (typeof LANGS)[number];

const PRINTERS = ['receipt', 'kitchen', 'bar', 'label'].map((usage) => `[data-testid=printing-setting-${usage}_printer]`);
/** Ionic's outlined field (`mode="md"`): what fits on one line keeps it, as every other field of a form. */
const ONE_LINE = 56;
const STATUS = '[data-testid=appointment-toolbar-status]';
const COUNTRY = '[data-testid=invoice-issuer-country]';

interface Choice {
  text: string;
  /** How far the text runs past its own box, sideways and downwards: what `overflow: hidden` cuts. */
  pastWidth: number;
  pastHeight: number;
  /** How far the painted text runs past the outlined box of the field. */
  pastField: number;
  /** How far the first line climbs into the label floating on the field's edge (negative: clear of it). */
  overLabel: number;
  /** The lines the painted text takes. */
  lines: number;
  /** The field's height. */
  height: number;
}

/**
 * The closed field as it is, then with each of its options set in turn (as `value` leaves it, two frames later), then
 * its own value back. Runs in the page, so self-contained.
 */
async function everyChoice(select: Element): Promise<Choice[]> {
  const field = select as HTMLElement & { value: unknown };
  const frame = () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));
  const read = (): Choice => {
    const root = field.shadowRoot!;
    const text = root.querySelector<HTMLElement>('[part~="text"]');
    if (!text) throw new Error(`${field.dataset.testid}: no text part with value ${JSON.stringify(field.value)}`);
    const range = document.createRange();
    range.selectNodeContents(text);
    const painted = range.getBoundingClientRect();
    const box = field.getBoundingClientRect();
    const label = root.querySelector<HTMLElement>('[part~="label"]')?.getBoundingClientRect();
    return {
      text: text.textContent!.trim(),
      pastWidth: text.scrollWidth - text.clientWidth,
      pastHeight: text.scrollHeight - text.clientHeight,
      pastField: Math.ceil(Math.max(painted.right - box.right, painted.bottom - box.bottom, box.left - painted.left, box.top - painted.top)),
      overLabel: label ? Math.ceil(label.bottom - painted.top) : 0,
      lines: new Set([...range.getClientRects()].filter((line) => line.width > 0).map((line) => Math.round(line.top))).size,
      height: box.height,
    };
  };
  const own = field.value;
  const seen = [read()];
  for (const option of field.querySelectorAll<HTMLElement & { value: unknown }>('ion-select-option')) {
    field.value = option.value;
    await frame();
    seen.push(read());
  }
  field.value = own;
  await frame();
  return seen;
}

const cut = (choice: Choice): boolean => choice.pastWidth > 0 || choice.pastHeight > 0 || choice.pastField > 0 || choice.overLabel > 0;
const said = (where: string, choice: Choice): string =>
  `${where} «${choice.text}»: ${choice.pastWidth}px sideways, ${choice.pastHeight}px down, ${choice.pastField}px out of the field, ` +
  `${choice.overLabel}px into the label`;

/** Every choice of `field` that cannot be read whole with it closed, said: empty when each one can. */
async function cutChoices(field: Locator, where: string): Promise<{ choices: Choice[]; cuts: string[] }> {
  await expect(field).toBeVisible();
  const choices = await field.evaluate(everyChoice);
  expect(choices.length, `${where}: its options`).toBeGreaterThan(1);
  return { choices, cuts: choices.filter(cut).map((choice) => said(where, choice)) };
}

/** The owner of `a` on `path`, speaking `lang`. */
async function pageIn(browser: Browser, lang: Lang, path: string) {
  if (lang === 'es') return signedInSpanish(browser, SIZES[0], path);
  const opened = await hostPage(browser, A, { next: path, viewport: SIZES[0] });
  await expect(opened.page.locator('html')).toHaveAttribute('lang', /^en/);
  return opened;
}

async function atSize(page: Page, size: Size): Promise<void> {
  await page.setViewportSize(size);
  await settled(page);
}

for (const lang of LANGS) {
  test(`PRINTING-F06: the printer of each role reads whole with its field closed, at each size, in ${lang}`, async ({ browser }) => {
    const { context, page } = await pageIn(browser, lang, '/printing/settings');
    for (const size of SIZES) {
      await atSize(page, size);
      const cuts: string[] = [];
      let lines = 0;
      for (const selector of PRINTERS) {
        const measured = await cutChoices(shown(page).locator(selector), `${size.label} ${selector}`);
        cuts.push(...measured.cuts);
        lines = Math.max(lines, ...measured.choices.map((choice) => choice.lines));
        for (const choice of measured.choices.filter((c) => c.lines === 1)) expect(choice.height, `${size.label} ${selector} «${choice.text}»`).toBe(ONE_LINE);
      }
      expect(cuts).toEqual([]);
      // At 320 the longest choice needs a second line: the case Ionic cut, measured, not assumed.
      if (size.width === 320) expect(lines, `${size.label}: the lines of the longest choice`).toBeGreaterThan(1);
      expect(await horizontalOverflow(page), `${size.label}: sideways scroll`).toBe(0);
      await shown(page).locator(PRINTERS[0]).scrollIntoViewIfNeeded();
      await capture(page, `FIX-HUB-SELECT-CHOSEN-TEXT-PRINTING-${lang}-${size.label}`);
    }
    await context.close();
  });

  test(`the agenda's status filter reads whole with its field closed, at each size, in ${lang}`, async ({ browser }) => {
    const { context, page } = await pageIn(browser, lang, '/appointment/agenda');
    for (const size of SIZES) {
      await atSize(page, size);
      const { cuts } = await cutChoices(shown(page).locator(STATUS), `${size.label} ${STATUS}`);
      expect(cuts).toEqual([]);
      expect(await horizontalOverflow(page), `${size.label}: sideways scroll`).toBe(0);
      await capture(page, `FIX-HUB-SELECT-CHOSEN-TEXT-AGENDA-${lang}-${size.label}`);
    }
    await context.close();
  });

  test(`INVOICE-F21: every country of the issuer reads whole with its field closed, at each size, in ${lang}`, async ({ browser }) => {
    const { context, page } = await pageIn(browser, lang, '/invoice/issuer');
    for (const size of SIZES) {
      await atSize(page, size);
      const { choices, cuts } = await cutChoices(shown(page).locator(COUNTRY), `${size.label} ${COUNTRY}`);
      expect(choices.length).toBeGreaterThan(200);
      expect(cuts).toEqual([]);
      expect(await horizontalOverflow(page), `${size.label}: sideways scroll`).toBe(0);
      await shown(page).locator(COUNTRY).scrollIntoViewIfNeeded();
      await capture(page, `FIX-HUB-SELECT-CHOSEN-TEXT-COUNTRY-${lang}-${size.label}`);
    }
    await context.close();
  });
}
