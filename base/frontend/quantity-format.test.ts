// base-quantity-one-format (hub#974): the Hub writes a quantity one way, with the platform's `formatQuantity`
// (`@erplora/ui/components`, `format/quantity.ts`): up to three decimals and none it does not need, its thousands
// grouped from four digits on as an amount groups them (hub#692). Each app's copy of its own grouped as it pleased:
// «12500» in Inventory beside «12.500» on the till, «1500» on the till beside «1.500» on the assistant's card. This
// guard looks, by app (and base), for a quantity formatter of its own, and there may be none:
// - a number format with `maximumFractionDigits: 3`, a quantity's thousandths (every copy had it): in an
//   `Intl.NumberFormat`, in the options given to an app's helper, or in a table of options;
// - a function or constant named `formatQuantity` written in the app: the shared one is imported or re-exported.
// What a person types is no written quantity: a field shows its figure ungrouped, as typed (QtyStepper; a till's field
// does not group, PLAN-HUB «lo que se teclea no se agrupa»), and needs only the decimal mark of the language.
// `packages/ui` is not read: it holds the one formatter.
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { bare, findingsByApp, hubFrontends, linesWhere } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

const WRITE_IT_WITH_THE_PLATFORM =
  'write the quantity with formatQuantity of @erplora/ui/components (the platform\'s one way to write a quantity), ' +
  "re-exported from the app's lib/format.ts if its screens import it from there";

/** The name of a property or a declaration, when it is written as one (`maximumFractionDigits`, `'maximumFractionDigits'`). */
function nameOf(name: ts.Node | undefined): string | undefined {
  return name && (ts.isIdentifier(name) || ts.isStringLiteral(name)) ? name.text : undefined;
}

/** Whether `node` writes a quantity of its own: three decimals at most, or a `formatQuantity` declared here. */
function ownQuantityFormat(node: ts.Node): boolean {
  if (ts.isPropertyAssignment(node) && nameOf(node.name) === 'maximumFractionDigits') {
    const value = bare(node.initializer);
    return ts.isNumericLiteral(value) && Number(value.text) === 3;
  }
  if (ts.isFunctionDeclaration(node) || ts.isVariableDeclaration(node)) return nameOf(node.name) === 'formatQuantity';
  return false;
}

/** The lines of `text` (a `.ts`, or a `.vue` whose `<script>` blocks are read) with a quantity formatter of its own. */
export function ownQuantityFormats(text: string, name: string): number[] {
  return /maximumFractionDigits|formatQuantity/.test(text) ? linesWhere(text, name, ownQuantityFormat) : [];
}

describe('guardrail: every quantity of the Hub is written by the platform (base-quantity-one-format)', () => {
  it('counts every quantity format of an app’s own, and no use of the shared one', () => {
    const planted = [
      // The copies the apps had: Intl's grouping, none, and in a helper's options or a table of them (lines 1–4).
      "const a = new Intl.NumberFormat(locale, { maximumFractionDigits: 3 });",
      "const b = new Intl.NumberFormat(locale, { maximumFractionDigits: 3, useGrouping: false });",
      "const c = numberFormat(locale, 'quantity', { maximumFractionDigits: 3 }).format(Number(value));",
      "const options = { quantity: { 'maximumFractionDigits': (3 as const), useGrouping: 'always' } };",
      // Its own formatQuantity, whatever it does inside (lines 5 and 6).
      'export function formatQuantity(value, locale) { return String(value); }',
      'const formatQuantity = (value, locale) => String(value);',
      // Not a quantity: a percentage, a rating; and the shared one imported, re-exported, renamed and called.
      "const percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 });",
      "const rating = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });",
      "import { formatQuantity } from '@erplora/ui/components';",
      "export { formatQuantity } from '@erplora/ui/components';",
      "import { formatQuantity as quantityText } from '@erplora/ui/components';",
      'const shown = formatQuantity(line.quantity, locale);',
      '// A comment that says maximumFractionDigits: 3 writes nothing.',
      "const field = String(Number(quantity)).replace('.', decimalMark);",
    ].join('\n');
    expect(ownQuantityFormats(planted, 'format.ts')).toEqual([1, 2, 3, 4, 5, 6]);
    // A component's script, at its own line of the file.
    const component = [
      '<template>{{ shown }}</template>',
      '<script setup lang="ts">',
      'const number = computed(() => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 3, useGrouping: false }));',
      '</script>',
    ];
    expect(ownQuantityFormats(component.join('\n'), 'QtyStepper.vue')).toEqual([3]);
  });

  it('no app, nor base, writes a quantity with a formatter of its own', () => {
    expect(findingsByApp(hubFrontends({ ui: false }), ownQuantityFormats), WRITE_IT_WITH_THE_PLATFORM).toEqual({});
    // It reads every frontend file of the Hub (some 1,600), synchronously: as long as the machine makes it (hub#1200).
  }, NO_CLOCK);
});
