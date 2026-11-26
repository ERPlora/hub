// Every search box of the Hub is announced by its hint, in the person's language. Ionic 8 renders the input of an
// `ion-searchbar` with a fixed `aria-label="search text"`, in English, and ignores an `aria-label` on the searchbar
// itself, so a screen reader reads «search text» unless the component names it with `syncSearchbarInputName` of
// @erplora/ui (or an app's `useSearchbarName`, built on it). This guard reads the components of base, of each app and
// of the shared `ui`, and there may be none whose template has more searchbars than its script names.
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { findingsByApp, hubFrontends, linesWhere } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

const NAME_IT =
  'name every ion-searchbar by its hint with syncSearchbarInputName of @erplora/ui/components (or the app’s useSearchbarName): Ionic announces it as «search text»';

const NAMERS = new Set(['syncSearchbarInputName', 'useSearchbarName']);
const SEARCHBAR = /<(?:ion-searchbar|IonSearchbar)(?=[\s/>]|$)/;

const namesASearchbar = (node: ts.Node): boolean =>
  ts.isCallExpression(node) && ts.isIdentifier(node.expression) && NAMERS.has(node.expression.text);

/** The lines of a component's template with a searchbar, when its script names fewer searchbars than that. */
export function unnamedSearchbars(text: string, name: string): number[] {
  if (!name.endsWith('.vue')) return [];
  const start = text.indexOf('<template>');
  const end = text.lastIndexOf('</template>');
  if (start === -1 || end === -1) return [];
  const before = text.slice(0, start).split('\n').length;
  const bars = text
    .slice(start, end)
    .split('\n')
    .flatMap((line, index) => (SEARCHBAR.test(line) ? [before + index] : []));
  return linesWhere(text, name, namesASearchbar).length >= bars.length ? [] : bars;
}

describe('guardrail: every search box of the Hub and of @erplora/ui is named for a screen reader', () => {
  it('finds a searchbar its component does not name, and nothing else', () => {
    const component = (script: string, ...template: string[]) =>
      ['<script setup lang="ts">', script, '</script>', '<template>', ...template, '</template>'].join('\n');

    const unnamed = component(
      '// syncSearchbarInputName(root, hint) is only a comment here',
      '  <ion-searchbar :placeholder="hint" />',
      '  <IonSearchbar',
      '    :value="text"',
      '  />',
      '  <ion-searchbar-like />',
    );
    expect(unnamedSearchbars(unnamed, 'Unnamed.vue')).toEqual([5, 6]);

    const named = component(
      "watch(root, (el) => syncSearchbarInputName(el, () => t('search')));",
      '  <div ref="root"><ion-searchbar /></div>',
    );
    expect(unnamedSearchbars(named, 'Named.vue')).toEqual([]);

    const byTheApp = component("useSearchbarName(useTemplateRef('bar'), () => hint.value);", '  <ion-searchbar ref="bar" />');
    expect(unnamedSearchbars(byTheApp, 'ByTheApp.vue')).toEqual([]);

    const oneOfTwo = component(
      "useSearchbarName(useTemplateRef('bar'), () => hint.value);",
      '  <ion-searchbar ref="bar" />',
      '  <ion-searchbar />',
    );
    expect(unnamedSearchbars(oneOfTwo, 'OneOfTwo.vue')).toEqual([5, 6]);

    expect(unnamedSearchbars('<template><ion-searchbar /></template>', 'notes.ts')).toEqual([]);
  });

  it('none is left in base, the apps or @erplora/ui', async () => {
    const found = await findingsByApp(hubFrontends({ ui: true }), unnamedSearchbars);
    expect(found, NAME_IT).toEqual({});
  }, NO_CLOCK);
});
