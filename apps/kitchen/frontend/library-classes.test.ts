// The look of the kitchen display lives in @erplora/ui (order-ticket.css and order-board.css, loaded by the shell):
// the components here only put its classes on Ionic's pieces. A class that the library does not define paints
// nothing and fails no other test, so every one the kitchen writes is looked up in the library's sheets.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const THEME = join(HERE, '../../../packages/ui/src/shell/theme');
const SHEETS = ['order-ticket.css', 'order-board.css'].map((sheet) => readFileSync(join(THEME, sheet), 'utf8')).join('\n');

/** The display's components: the cards, the bar, the totals, the loading board, and the page that holds them. */
const FILES = [
  ...readdirSync(join(HERE, 'components'))
    .filter((name) => /^Kds\w+\.vue$/.test(name))
    .map((name) => join('components', name)),
  join('pages', 'DisplayPage.vue'),
];
const source = (file: string): string => readFileSync(join(HERE, file), 'utf8');

/** The library's classes a template writes, in a static `class` or inside a bound one. */
function libraryClasses(sfc: string): string[] {
  const template = /<template>([\s\S]*)<\/template>/.exec(sfc)?.[1] ?? '';
  return [...new Set([...template.matchAll(/\bep-(?:order-[\w-]+|station-dot)\b/g)].map((m) => m[0]))];
}

describe('the kitchen display wears the order ticket of @erplora/ui', () => {
  it('writes only classes the library defines', () => {
    const used = FILES.flatMap((file) => libraryClasses(source(file)).map((name) => `${file}: ${name}`));
    expect(used.length).toBeGreaterThan(40);
    expect(used.filter((entry) => !new RegExp(`\\.${entry.split(': ')[1]}(?![\\w-])`).test(SHEETS))).toEqual([]);
  });

  it('keeps no stylesheet of its own in a component of the display', () => {
    const styled = FILES.filter((file) => file.startsWith('components') && /<style\b/.test(source(file)));
    expect(styled).toEqual([]);
  });
});
