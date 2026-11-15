// flow: ninguno — FIX tests/e2e (one `rowAction` for every spec; hub#1302, hub#1339)
// A row action of a `DataTable` (`@erplora/ui`) is a button of the row, or the same entry inside «⋮» when the row folds
// its actions, and the table folds them by measuring its box a frame or more after a resize or new rows. The helper of
// service-helpers.ts clicks whichever of the two is there when the click lands (hub#1279). Nineteen copies of the old
// one looked at the row first and then clicked what they had chosen, and hung until the test's time ran out when the
// fold came in between; eleven more did the same under other names or written in the test. They are gone: this keeps a
// second `rowAction` from coming back anywhere in the e2e, and any other helper or spec from building a row's «⋮» hook
// to open it on its own.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The e2e's helpers and specs (its `.ts` files, subfolders included), not Vitest's own tests nor what a run leaves. */
const e2eSources = (): string[] =>
  readdirSync(E2E_DIR, { recursive: true, encoding: 'utf8' }).filter(
    (name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && !name.split(sep).some((part) => part === 'node_modules' || part.startsWith('.')),
  );

/** The code of `source`, line by line: comment lines left out and a comment at the end of a line cut off. */
const codeLines = (source: string): string[] =>
  source
    .split('\n')
    .filter((line) => !/^\s*(?:\/\/|\/\*|\*)/.test(line))
    .map((line) => line.replace(/\s\/\/\s.*$/, ''));

/** The lines of `source` that define a `rowAction`: a function of that name, a `const`/`let`/`var` of that name
 *  (given one then or later), a value given to it, or another function imported or exported under that name. */
function rowActionDefinitions(source: string): string[] {
  return codeLines(source).filter((line) =>
    /\bfunction\s*\*?\s*rowAction\b|\b(?:const|let|var)\s+rowAction\b|(?:^|[\s;{(])rowAction\s*=(?![=>])|\bas\s+rowAction\b/.test(line),
  );
}

/** The lines of `source` that build the hook of a row's «⋮» (`<table>-row-<id>-menu`) for something other than an
 *  `expect`: what a spec does to open «⋮» itself after looking at the row's button. */
function rowMenuHooks(source: string): string[] {
  return codeLines(source).filter(
    (line) => /-row-\$\{[^}]+\}-menu\b|-row-['"`]\s*\+.*\+\s*['"`]-menu\b/.test(line) && !/\bexpect\s*\(/.test(line),
  );
}

describe('the e2e has one rowAction, the one of service-helpers.ts', () => {
  it('there are helpers and specs to look at, the shared helper and the specs that call it among them', () => {
    expect(e2eSources()).toEqual(
      expect.arrayContaining(['service-helpers.ts', 'reservation-book.spec.ts', 'pricing-flows.spec.ts', 'staff-members.spec.ts']),
    );
  });

  it('no helper or spec but service-helpers.ts defines a rowAction of its own', () => {
    const definitions = e2eSources().flatMap((name) =>
      rowActionDefinitions(readFileSync(join(E2E_DIR, name), 'utf8')).map((line) => `${name}: ${line.trim()}`),
    );
    expect(definitions.map((definition) => definition.split(':')[0])).toEqual(['service-helpers.ts']);
  });

  it('the check reads every shape the copies had as a definition, and a call, an import or a rename as none', () => {
    const copies = [
      'async function rowAction(page: Page, id: string, action: string): Promise<void> {',
      'export async function rowAction(page: Page, section: Section, id: string, action: string): Promise<void> {',
      'function rowAction(panel: Page, memberId: string, action: string) {',
      'const rowAction = async (page: Page, id: string, action: string): Promise<void> => {',
      'export const rowAction: (page: Page, id: string) => Promise<void> = (page, id) => shared(page, "x", id, "edit");',
      'let rowAction;',
      'let rowAction: (page: Page, id: string, action: string) => Promise<void>;',
      '  rowAction = async (page: Page, id: string, action: string): Promise<void> => {',
      'export { clickRow as rowAction };',
      "import { clickRow as rowAction } from './cart-checkout-helpers';",
    ];
    const uses = [
      "  await rowAction(page, 'inventory-products', product.id, 'edit');",
      "import { rowAction } from './service-helpers';",
      "  const form = await presented(page, () => rowAction(page, 'inventory-products', tea.id, 'edit'));",
      'async function printersRowAction(page: Page, action: string): Promise<void> {',
      '// The old function rowAction(page, id, action) looked at the row first.',
      ' * function rowAction(page, id, action) looked at the row first and then clicked what it had chosen.',
      "  await go(page); // and not function rowAction(page, id, action) of its own",
      '  if (rowAction === undefined) throw new Error("no rowAction");',
    ];
    expect(copies.map((line) => rowActionDefinitions(line).length)).toEqual(copies.map(() => 1));
    expect(uses.flatMap(rowActionDefinitions)).toEqual([]);
  });

  // hub#1339
  it('no helper or spec but service-helpers.ts builds a row’s «⋮» hook to open it on its own', () => {
    const hooks = e2eSources().flatMap((name) =>
      rowMenuHooks(readFileSync(join(E2E_DIR, name), 'utf8')).map((line) => `${name}: ${line.trim()}`),
    );
    expect([...new Set(hooks.map((hook) => hook.split(':')[0]))]).toEqual(['service-helpers.ts']);
  });

  it('the check reads every way the recipes built a row’s «⋮» hook as one, and an expect, a call or a comment as none', () => {
    const recipes = [
      '    const menu = shown(page).locator(`[data-testid=combo-menus-row-${id}-menu]`);',
      '    await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-menu]`).first().click();',
      '  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);',
      '  const more = shown(page).locator(`[data-testid=combo-menus-row-${menu.id}-menu]`);',
      '  const menuHook = `${table}-row-${id}-menu`;',
      "  await page.getByTestId('printing-jobs-row-' + id + '-menu').click();",
    ];
    const others = [
      '    await expect(sessions.locator(`[data-testid=table-sessions-row-${check.id}-detail], [data-testid=table-sessions-row-${check.id}-menu]`)).toHaveCount(0);',
      '        await expect(page.locator(`[data-testid^=cart-checkout-orders-row-${paid.id}-]:not([data-testid$=-menu])`)).toHaveCount(0);',
      "    await rowAction(page, 'combo-menus', id, 'edit');",
      "      control('book-row-r1-menu', '⋮', () => {",
      '  // The row’s «⋮» (`${table}-row-${id}-menu`) is rowAction’s to open.',
      ' * hooks as `${table}-row-${id}-menu`, opened by rowAction.',
    ];
    expect(recipes.map((line) => rowMenuHooks(line).length)).toEqual(recipes.map(() => 1));
    expect(others.flatMap(rowMenuHooks)).toEqual([]);
  });
});
