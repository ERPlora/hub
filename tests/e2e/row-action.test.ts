// flow: ninguno — FIX tests/e2e (one `rowAction` for every spec; hub#1302)
// A row action of a `DataTable` (`@erplora/ui`) is a button of the row, or the same entry inside «⋮» when the row folds
// its actions, and the table folds them by measuring its box a frame or more after a resize or new rows. The helper of
// service-helpers.ts clicks whichever of the two is there when the click lands (hub#1279). Nineteen copies of the old
// one looked at the row first and then clicked what they had chosen, and hung until the test's time ran out when the
// fold came in between. They are gone: this keeps a second `rowAction` from coming back anywhere in the e2e.
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

/** The lines of `source` that define a `rowAction`: a function of that name, or a `const`/`let`/`var` given one. */
function rowActionDefinitions(source: string): string[] {
  return source.split('\n').filter((line) => /\bfunction\s*\*?\s*rowAction\b|\b(?:const|let|var)\s+rowAction\b\s*[:=]/.test(line));
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
    ];
    const uses = [
      "  await rowAction(page, 'inventory-products', product.id, 'edit');",
      "import { rowAction } from './service-helpers';",
      "  const form = await presented(page, () => rowAction(page, 'inventory-products', tea.id, 'edit'));",
      'async function printersRowAction(page: Page, action: string): Promise<void> {',
    ];
    expect(copies.map((line) => rowActionDefinitions(line).length)).toEqual(copies.map(() => 1));
    expect(uses.flatMap(rowActionDefinitions)).toEqual([]);
  });
});
