// base-decimal-mark-one-way (hub#983): what a person types in a number field, a keypad or an amount being edited
// carries the decimal mark of their language («,» in Spanish, «.» in English), and the Hub learns it one way: the
// platform's `decimalMark(locale)` (`@erplora/ui/components`, `format/decimalMark.ts`). Twelve copies worked it out
// by hand (Inventory, Pricing, Payments, Services, Menus, Supplements and Staff in their lib/format.ts, the drawer's
// money.ts, the till's quantity field, its keypad, the charge keypad and the refund), each fixed apart from the rest.
// This guard looks, by app (and base), for a decimal mark of its own, and there may be none:
// - a lookup of the `decimal` part of Intl's parts (`formatToParts(…).find((part) => part.type === 'decimal')`), or a
//   `case 'decimal':` that walks them;
// - a function or constant named `decimalMark` written in the app: the shared one is imported or re-exported.
// `packages/ui` is not read: it holds the one decimal mark.
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { bare, findingsByApp, hubFrontends, scriptBlocks } from './__tests__/frontend-sources';

const LEARN_IT_FROM_THE_PLATFORM =
  "take the typed decimal mark from decimalMark of @erplora/ui/components (the platform's one way to learn it)";

const DECIMAL = 'decimal';

const EQUALITY = new Set([
  ts.SyntaxKind.EqualsEqualsEqualsToken,
  ts.SyntaxKind.EqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsToken,
]);

/** Whether `node` is the text `decimal`, as a string or a template without substitutions. */
function isDecimal(node: ts.Expression): boolean {
  const value = bare(node);
  return (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) && value.text === DECIMAL;
}

/** The name of a declaration, when it is written as one. */
function nameOf(name: ts.Node | undefined): string | undefined {
  return name && ts.isIdentifier(name) ? name.text : undefined;
}

/** Whether `node` learns a decimal mark of its own: the `decimal` part looked up or walked, or a `decimalMark` declared here. */
function ownDecimalMark(node: ts.Node): boolean {
  if (ts.isBinaryExpression(node) && EQUALITY.has(node.operatorToken.kind)) return isDecimal(node.left) || isDecimal(node.right);
  if (ts.isCaseClause(node)) return isDecimal(node.expression);
  if (ts.isFunctionDeclaration(node) || ts.isVariableDeclaration(node)) return nameOf(node.name) === 'decimalMark';
  return false;
}

/** The lines of `text` (a `.ts`, or a `.vue` whose `<script>` blocks are read) with a decimal mark of its own. */
export function ownDecimalMarks(text: string, name: string): number[] {
  if (!/decimal/.test(text)) return [];
  return scriptBlocks(text, name).flatMap(({ code, offset }) => {
    const file = ts.createSourceFile(name.endsWith('.vue') ? `${name}.ts` : name, code, ts.ScriptTarget.Latest, true);
    const lines: number[] = [];
    const visit = (node: ts.Node): void => {
      if (ownDecimalMark(node)) lines.push(file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1 + offset);
      ts.forEachChild(node, visit);
    };
    visit(file);
    return lines;
  });
}

describe('guardrail: the Hub learns the typed decimal mark from the platform (base-decimal-mark-one-way)', () => {
  it('counts every decimal mark of an app’s own, and no use of the shared one', () => {
    const planted = [
      // The copies the apps had (lines 1–3), and the same lookup written other ways (lines 4–6).
      "const a = new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';",
      "const b = formatter(locale, 'decimal-sign', { minimumFractionDigits: 1 }).formatToParts(1.5).find((part) => part.type === 'decimal')?.value;",
      "separator = new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === 'decimal')?.value ?? '.';",
      'const c = parts.find(({ type }) => `decimal` == type);',
      "const d = parts.filter((part) => part.type !== ('decimal' as const));",
      "for (const part of parts) { switch (part.type) { case 'decimal': mark = part.value; } }",
      // Its own decimalMark, whatever it does inside (lines 7 and 8).
      "export function decimalMark(locale) { return ','; }",
      "const decimalMark = (locale) => ',';",
      // Not a decimal mark: another part of the parts, the field's keyboard, a key named decimal; and the shared one
      // imported, re-exported, renamed and called.
      "const sign = new Intl.NumberFormat('en', { style: 'currency', currency }).formatToParts(1).find((part) => part.type === 'currency')?.value;",
      "const keyboard = { inputmode: 'decimal', type: 'decimal' };",
      "const formatted = formatter(locale, 'decimal-sign', { minimumFractionDigits: 1 }).format(1.5);",
      "import { decimalMark } from '@erplora/ui/components';",
      "export { decimalMark } from '@erplora/ui/components';",
      "import { decimalMark as markOf } from '@erplora/ui/components';",
      'const separator = computed(() => decimalMark(locale.value));',
      "// A comment that says part.type === 'decimal' learns nothing.",
    ].join('\n');
    expect(ownDecimalMarks(planted, 'format.ts')).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    // A component's script, at its own line of the file; its template's `inputmode="decimal"` is no script.
    const component = [
      '<template><input inputmode="decimal" :value="shown" /></template>',
      '<script setup lang="ts">',
      "const separator = computed(() => new Intl.NumberFormat(locale.value).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.');",
      '</script>',
    ];
    expect(ownDecimalMarks(component.join('\n'), 'QtyStepper.vue')).toEqual([3]);
  });

  it('no app, nor base, learns the typed decimal mark on its own', () => {
    expect(findingsByApp(hubFrontends({ ui: false }), ownDecimalMarks), LEARN_IT_FROM_THE_PLATFORM).toEqual({});
    // It reads every frontend file of the Hub (some 1,600): the limit of the guardrails that read a whole tree (60 s,
    // tsconfig.test.ts).
  }, 60_000);
});
