// Test helper of the SPA's catalogues (hub#1124): a count is said in the singular or in the plural, never as
// «product(s)» or «opción(es)», which shows the parentheses on screen whatever the number. A message with a count
// has vue-i18n's forms instead («{n} row | {n} rows»), and the code passes the number when it translates. An app's
// catalogue test asserts `expect(pluralsInParentheses(EN, ES)).toEqual([])` with its flattened catalogues. For the
// tests of every app: free of side effects.

/** A plural ending glued to a word in parentheses: «row(s)», «opción(es)», «categoría(s)», «category(ies)». */
const IN_PARENTHESES = /\p{L}\((?:s|es|as|os|ies)\)/u;

/** Every message of `catalogues` (key → message) that spells a plural in parentheses, as «key: message». */
export function pluralsInParentheses(...catalogues: ReadonlyMap<string, string>[]): string[] {
  return catalogues.flatMap((catalogue) =>
    [...catalogue].filter(([, message]) => IN_PARENTHESES.test(message)).map(([key, message]) => `${key}: ${message}`),
  );
}
