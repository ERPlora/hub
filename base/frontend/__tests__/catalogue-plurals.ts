// Test helper of the SPA's catalogues (hub#1124): a count is said in the singular or in the plural, never as
// «product(s)» or «opción(es)», which shows the parentheses on screen whatever the number, and never with the noun in
// the plural whatever the figure («1 usadas»). A message with a count has vue-i18n's forms instead («{n} row | {n}
// rows»), and the code passes the number when it translates. An app's catalogue test asserts
// `expect(pluralsInParentheses(EN, ES)).toEqual([])` with its flattened catalogues. For the tests of every app: free
// of side effects.

/** A plural ending glued to a word in parentheses: «row(s)», «opción(es)», «categoría(s)», «category(ies)». */
const IN_PARENTHESES = /\p{L}\((?:s|es|as|os|ies)\)/u;

/** Every message of `catalogues` (key → message) that spells a plural in parentheses, as «key: message». */
export function pluralsInParentheses(...catalogues: ReadonlyMap<string, string>[]): string[] {
  return catalogues.flatMap((catalogue) =>
    [...catalogue].filter(([, message]) => IN_PARENTHESES.test(message)).map(([key, message]) => `${key}: ${message}`),
  );
}

/** A placeholder and the word right after it: «{used} usadas», «{n} filas», «{name} pasa». */
const PLACEHOLDER_AND_WORD = /\{\w+\}\s+(\p{L}{3,})/gu;

/** Whether the Spanish `message` says a plural word right after a placeholder, so the figure in it counts something.
 *  Spanish is read because a noun or an adjective a figure counts ends in «s» in the plural, and a verb after a name
 *  does not («{name} pasa»), as it does in English («{name} has»). */
function countsSomething(message: string): boolean {
  return [...message.matchAll(PLACEHOLDER_AND_WORD)].some(([, word]) => word.endsWith('s'));
}

/** Every message of an app's catalogues (`EN`, `ES`, key → message) that counts something with a figure and lacks
 *  vue-i18n's singular and plural forms («one | other») in English or in Spanish, as «key: Spanish message». */
export function countsWithoutForms(EN: ReadonlyMap<string, string>, ES: ReadonlyMap<string, string>): string[] {
  return [...ES]
    .filter(([key, message]) => countsSomething(message) && !(message.includes('|') && (EN.get(key) ?? '').includes('|')))
    .map(([key, message]) => `${key}: ${message}`);
}
