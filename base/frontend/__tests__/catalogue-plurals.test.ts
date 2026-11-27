// The shared checks that no catalogue spells a plural with «(s)» (hub#1124) nor counts with the noun in the plural
// whatever the figure («1 usadas»): what they catch and what they let through, and the guard of every catalogue of the
// Hub's SPA (hub#1147): the platform's and each app's, in `en` and `es`, and of the code that paints them.
import { existsSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { flatten } from './app-catalogues';
import { countsWithoutForms, pluralsInParentheses } from './catalogue-plurals';
import { bare, findingsByApp, hubFrontends } from './frontend-sources';
import { flattened, HUB, hubCatalogues } from './hub-catalogues';
import { NO_CLOCK } from '../../../vitest.load';

const catalogue = (entries: Record<string, string>): Map<string, string> => new Map(Object.entries(entries));

describe('pluralsInParentheses', () => {
  it('names every message that spells a plural in parentheses, in each catalogue it is given', () => {
    const en = catalogue({ 'a.import': 'Import {n} product(s)', 'a.links': 'It stops applying to {count} category(ies)', 'a.ok': 'Add {n} selected' });
    const es = catalogue({ 'a.import': 'Importar {n} producto(s)', 'a.options': 'Se borrarán {count} opción(es)', 'a.ok': 'Añadir {n} seleccionado | Añadir {n} seleccionados' });
    expect(pluralsInParentheses(en, es)).toEqual([
      'a.import: Import {n} product(s)',
      'a.links: It stops applying to {count} category(ies)',
      'a.import: Importar {n} producto(s)',
      'a.options: Se borrarán {count} opción(es)',
    ]);
  });

  it('lets through the forms of vue-i18n and the parentheses that are not a plural', () => {
    const messages = catalogue({
      plural: '{n} row | {n} rows',
      count: 'Tick all of «{category}» ({n})',
      note: 'Slug (optional)',
      unit: 'Price (€)',
      sent: 'Send the order (3)',
    });
    expect(pluralsInParentheses(messages)).toEqual([]);
  });
});

describe('every catalogue of the Hub (hub#1147)', () => {
  it('says a count in the singular or the plural, never «(s)»', () => {
    expect(pluralsInParentheses(...hubCatalogues().map(flattened))).toEqual([]);
  });
});

describe('countsWithoutForms', () => {
  it('names every message whose Spanish counts something with a figure and lacks the singular and plural forms', () => {
    const en = catalogue({
      'a.uses': '{used} used · {remaining} left',
      'a.rows': 'Showing the first {shown} rows.',
      'a.half': '{n} created | {n} created',
      'a.english': '{n} clocked in',
    });
    const es = catalogue({
      'a.uses': '{used} usadas · quedan {remaining}',
      'a.rows': 'Mostrando las primeras {shown} filas.',
      'a.half': '{n} creadas',
      'a.english': '{n} fichado | {n} fichados',
    });
    expect(countsWithoutForms(en, es)).toEqual([
      'a.uses: {used} usadas · quedan {remaining}',
      'a.rows: Mostrando las primeras {shown} filas.',
      'a.half: {n} creadas',
      'a.english: {n} fichado | {n} fichados',
    ]);
  });

  it('lets through the forms of vue-i18n and the figures that count nothing', () => {
    const messages = {
      forms: ['{n} row | {n} rows', '{n} fila | {n} filas'],
      same: ['{n} created | {n} created', '{n} creada | {n} creadas'],
      name: ['{name} becomes the general list', '{name} pasa a ser la tarifa general'],
      verb: ['{amount} is more than the rest', '{amount} es más que el resto'],
      more: ['You sold {amount} more than yesterday', 'Has vendido {amount} más que ayer'],
      less: ['There is {amount} less than expected', 'Hay {amount} menos de lo previsto'],
      after: ['{name} comes after this one', 'Sigue {name} después de esta'],
      order: ['Order {n} sent', 'Comanda {n} enviada'],
      label: ['People with this role: {n}', 'Personas con este rol: {n}'],
      unit: ['{n} min', '{n} min'],
      seats: ['{count} pax', '{count} pax'],
    };
    const en = catalogue(Object.fromEntries(Object.entries(messages).map(([key, [english]]) => [key, english])));
    const es = catalogue(Object.fromEntries(Object.entries(messages).map(([key, [, spanish]]) => [key, spanish])));
    expect(countsWithoutForms(en, es)).toEqual([]);
  });
});

/** The catalogues of the platform and of each app that has them, flattened, by the folder of its frontend. */
function hubCataloguePairs(): { frontend: string; EN: Map<string, string>; ES: Map<string, string> }[] {
  const read = (dir: string, lang: string): Map<string, string> => flatten(JSON.parse(readFileSync(join(dir, 'locale', `${lang}.json`), 'utf8')) as object);
  return hubFrontends({ ui: false })
    .filter(({ dir }) => existsSync(join(dir, 'locale', 'es.json')))
    .map(({ dir }) => ({ frontend: relative(HUB, dir), EN: read(dir, 'en'), ES: read(dir, 'es') }));
}

/** A call that translates a key written out whole: `t('<key>'`, `$t("<key>"`; the key is the second group. */
const TRANSLATE_CALL = /\bt\(\s*(['"`])([\w.-]+)\1/g;

/** The text of the call that opens at `open` (its «(»), to its closing «)»: strings and their brackets skipped. */
function callText(text: string, open: number): string {
  let depth = 0;
  let quote = '';
  for (let at = open; at < text.length; at++) {
    const char = text[at];
    if (quote) {
      if (char === '\\') at++;
      else if (char === quote) quote = '';
    } else if (char === "'" || char === '"' || char === '`') quote = char;
    else if (char === '(') depth++;
    else if (char === ')' && --depth === 0) return text.slice(open, at + 1);
  }
  return text.slice(open);
}

/** The name of a property written as one (`n`, `'count'`, `{ n }`). */
function propertyName(property: ts.ObjectLiteralElementLike): string | undefined {
  const name = property.name;
  return name && (ts.isIdentifier(name) || ts.isStringLiteral(name)) ? name.text : undefined;
}

/** Whether a translation passes vue-i18n the number its forms are chosen by: `t(key, n)`, `t(key, { …, n })` or
 *  `{ count }` (the names vue-i18n reads it from), or `t(key, values, n)`. A variable is not read: it may be either. */
function passesTheNumber(call: string): boolean {
  const source = ts.createSourceFile('call.ts', `t${call}`, ts.ScriptTarget.Latest, true);
  const statement = source.statements[0];
  const expression = statement && ts.isExpressionStatement(statement) ? statement.expression : undefined;
  if (!expression || !ts.isCallExpression(expression)) return false;
  const [, values, number] = expression.arguments;
  if (number) return true;
  if (!values) return false;
  const given = bare(values);
  if (ts.isObjectLiteralExpression(given)) {
    return given.properties.some((property) => ts.isSpreadAssignment(property) || ['n', 'count'].includes(propertyName(property) ?? ''));
  }
  return !(ts.isStringLiteralLike(given) || ts.isTemplateExpression(given) || ts.isArrayLiteralExpression(given));
}

/** The translations of a message with forms in `text`, by line, and whether each passes its number. */
function translationsOf(text: string, withForms: ReadonlySet<string>): { key: string; line: number; passes: boolean }[] {
  return [...text.matchAll(TRANSLATE_CALL)]
    .filter((match) => withForms.has(match[2]))
    .map((match) => {
      const open = (match.index ?? 0) + match[0].indexOf('(');
      return { key: match[2], line: text.slice(0, open).split('\n').length, passes: passesTheNumber(callText(text, open)) };
    });
}

describe('translationsOf', () => {
  const withForms = new Set(['a.rows', 'a.uses']);

  it('reads whether each translation of a message with forms passes its number, in a script or a template', () => {
    const source = [
      "const a = t('a.rows', { n: rows.length });",
      "const b = t('a.rows', { count });",
      "const c = t('a.uses', { used: format(used), n: used });",
      "const d = t('a.rows', rows.length);",
      "const e = t('a.uses', { used }, used);",
      '<p>{{ $t("a.rows", { ...values, n }) }}</p>',
      "const f = t('a.uses', { used: format(used) });",
      "const g = t('a.rows');",
      "const h = t('a.rows', `${rows.length}`);",
      "const i = t('a.title', { n: 1 });",
      "const j = t(`a.${kind}`, { used });",
    ].join('\n');
    expect(translationsOf(source, withForms)).toEqual([
      { key: 'a.rows', line: 1, passes: true },
      { key: 'a.rows', line: 2, passes: true },
      { key: 'a.uses', line: 3, passes: true },
      { key: 'a.rows', line: 4, passes: true },
      { key: 'a.uses', line: 5, passes: true },
      { key: 'a.rows', line: 6, passes: true },
      { key: 'a.uses', line: 7, passes: false },
      { key: 'a.rows', line: 8, passes: false },
      { key: 'a.rows', line: 9, passes: false },
    ]);
  });

  it('reads a call that spans lines and carries brackets in its strings', () => {
    const source = ["<ion-note :aria-label=\"t('a.uses', {", "  used: label('(a)'),", '})">', '</ion-note>'].join('\n');
    expect(translationsOf(source, withForms)).toEqual([{ key: 'a.uses', line: 1, passes: false }]);
  });
});

describe('every catalogue of the Hub, and the code that paints it', () => {
  it('says a count with its singular and plural forms, in English and in Spanish', () => {
    const pairs = hubCataloguePairs();
    expect(pairs.map(({ frontend }) => frontend)).toEqual(expect.arrayContaining([join('base', 'frontend'), join('apps', 'service', 'frontend')]));
    expect(pairs.flatMap(({ frontend, EN, ES }) => countsWithoutForms(EN, ES).map((found) => `${frontend} › ${found}`))).toEqual([]);
  });

  it('passes every message with forms the number they are chosen by, translating it by its name', async () => {
    const withForms = new Set(hubCataloguePairs().flatMap(({ EN }) => [...EN].filter(([, message]) => message.includes('|')).map(([key]) => key)));
    const named = new Set<string>();
    const find = (text: string): number[] => {
      const found = translationsOf(text, withForms);
      for (const { key } of found) named.add(key);
      return found.filter(({ passes }) => !passes).map(({ line }) => line);
    };
    expect(await findingsByApp(hubFrontends({ ui: false }), find)).toEqual({});
    expect(withForms.size).toBeGreaterThan(50);
    expect([...withForms].filter((key) => !named.has(key))).toEqual([]);
  }, NO_CLOCK);
});
