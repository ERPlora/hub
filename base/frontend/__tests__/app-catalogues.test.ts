// What the tests every app's catalogues share catch and what they let through, on a made-up app «shop» whose sources
// are written to a folder of their own.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative } from 'node:path';

import { afterAll, describe, expect, it } from 'vitest';

import {
  appCatalogues,
  appSources,
  type AppCatalogues,
  type Catalogue,
  expectInCatalogue,
  expectSamePlaceholders,
  expectWords,
  flatten,
  itChecksAppCatalogues,
  literalKeys,
  placeholders,
  sharedCatalogueChecks,
  type SharedTests,
  usedKeys,
} from './app-catalogues';
import { HUB } from './frontend-sources';

const folders: string[] = [];

/** A new folder holding `files` (path → text). */
function folderWith(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), 'app-catalogues-'));
  folders.push(dir);
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(dir, path)), { recursive: true });
    writeFileSync(join(dir, path), text);
  }
  return dir;
}

afterAll(() => {
  for (const dir of folders) rmSync(dir, { recursive: true, force: true });
});

const EN = {
  shop: { list: { title: 'Products', empty: 'No products.' }, status: { open: 'Open', closed: 'Closed' }, count: '{n} product | {n} products' },
};
const ES = {
  shop: { list: { title: 'Productos', empty: 'Sin productos.' }, status: { open: 'Abierto', closed: 'Cerrado' }, count: '{n} producto | {n} productos' },
};

/** A page and a helper naming three keys and building the statuses from a prefix; a test, a declaration and a test
 *  helper name keys the catalogues lack, and are no sources. */
const SOURCES: Record<string, string> = {
  'pages/ListPage.vue': [
    "<template><h1>{{ $t('shop.list.title') }}</h1></template>",
    '<script setup lang="ts">',
    'const label = (status: string) => t(`shop.status.' + '${status}`);',
    '</script>',
  ].join('\n'),
  'lib/labels.ts': "export const empty = () => t('shop.list.empty');\nexport const count = (n: number) => t('shop.count', n);\n",
  'lib/labels.test.ts': "t('shop.only.in.a.test');\n",
  'lib/env.d.ts': "// t('shop.only.in.a.declaration')\n",
  '__tests__/mount.ts': "t('shop.only.in.a.test.helper');\n",
};

const SHOP = folderWith(SOURCES);

const shop = (en: object, es: object, frontend: string = SHOP): AppCatalogues => appCatalogues('shop', en, es, frontend);

/** `catalogue` with the message at `key` replaced by `message`, or taken out without one. */
function edited(catalogue: object, key: string, message?: string): Catalogue {
  const copy = structuredClone(catalogue) as Catalogue;
  const path = key.split('.');
  const last = path.pop() as string;
  const parent = path.reduce((node, part) => node[part] as Catalogue, copy);
  if (message === undefined) delete parent[last];
  else parent[last] = message;
  return copy;
}

const PREFIX = 'live under the app prefix, so merging them into the shell never collides';
const SAME_KEYS = 'have exactly the same keys';
const NOT_EMPTY = 'have no empty message';
const NOT_PASTED = 'have no empty message, and no Spanish that is the English pasted across';
const PLURALS = 'keep the same placeholders and plural forms in both languages';
const PLACEHOLDERS = 'keep the same placeholders in both languages';
const COVERAGE = 'cover every key the app’s sources use, literal or built from a known prefix';

const titles = (tests: SharedTests): string[] => sharedCatalogueChecks(tests).map(([title]) => title);

/** The shared test called `title` among those `tests` asks for; looked up before it runs, so that a missing one fails
 *  the test rather than passing for an error it was expected to throw. */
function checkNamed(title: string, tests: SharedTests = { placeholders: 'and plural forms' }): (catalogues: AppCatalogues) => void {
  const found = sharedCatalogueChecks(tests).find(([name]) => name === title);
  expect(found, title).toBeDefined();
  return found?.[1] ?? (() => undefined);
}

describe('flatten and placeholders', () => {
  it('give every message by its dotted key, a list’s by its place', () => {
    expect([...flatten({ a: { b: 'x', c: ['y', 'z'] }, d: 'w' })]).toEqual([
      ['a.b', 'x'],
      ['a.c.0', 'y'],
      ['a.c.1', 'z'],
      ['d', 'w'],
    ]);
  });

  it('name each placeholder of a message once, in alphabetical order', () => {
    expect(placeholders('{name} owes {total}; {name} pays | {count} left')).toEqual(['count', 'name', 'total']);
    expect(placeholders('No placeholder')).toEqual([]);
  });

  it('expectSamePlaceholders fails on another placeholder, and on another number of forms only when asked', () => {
    expect(() => expectSamePlaceholders(shop(EN, ES), { pluralForms: true })).not.toThrow();
    const renamed = shop(EN, edited(ES, 'shop.count', '{count} producto | {count} productos'));
    expect(() => expectSamePlaceholders(renamed, { pluralForms: false })).toThrow('shop.count');
    const oneForm = shop(EN, edited(ES, 'shop.count', '{n} productos'));
    expect(() => expectSamePlaceholders(oneForm, { pluralForms: false })).not.toThrow();
    expect(() => expectSamePlaceholders(oneForm, { pluralForms: true })).toThrow('shop.count');
  });
});

describe('appCatalogues', () => {
  it('reads an app’s sources from its own frontend, and base’s from base’s', () => {
    expect(appCatalogues('combo', {}, {}).frontend).toBe(join(HUB, 'apps', 'combo', 'frontend'));
    expect(appCatalogues('base', {}, {}).frontend).toBe(join(HUB, 'base', 'frontend'));
  });

  it('holds both catalogues as they are and flattened', () => {
    const catalogues = shop(EN, ES);
    expect(catalogues).toMatchObject({ app: 'shop', en: EN, es: ES, frontend: SHOP });
    expect(catalogues.EN.get('shop.list.title')).toBe('Products');
    expect(catalogues.ES.get('shop.list.title')).toBe('Productos');
  });
});

describe('appSources', () => {
  const dir = folderWith({ ...SOURCES, 'locale/strings.ts': "t('shop.next.to.the.catalogues');\n" });
  const names = (files: string[]): string[] => files.map((file) => relative(dir, file)).sort();

  it('lists the pages and helpers, without tests, declarations or anything under __tests__', () => {
    expect(names(appSources(dir))).toEqual(['lib/labels.ts', 'locale/strings.ts', 'pages/ListPage.vue']);
  });

  it('skips the folders it is told, and lets declarations in when asked', () => {
    expect(names(appSources(dir, { skip: ['locale'], declarations: true }))).toEqual([
      '__tests__/mount.ts',
      'lib/env.d.ts',
      'lib/labels.ts',
      'pages/ListPage.vue',
    ]);
  });

  it('keeps only the endings it is told', () => {
    expect(names(appSources(dir, { skip: [], extensions: ['.vue'] }))).toEqual(['pages/ListPage.vue']);
  });
});

describe('usedKeys and expectInCatalogue', () => {
  it('find each of the app’s keys a source names, in a template as in a script, and no other', () => {
    const dir = folderWith({ 'Page.vue': "{{ $t('shop.a') }} {{ t('shop.b') }} {{ t('other.c') }} {{ format('shop.d') }}" });
    expect(usedKeys(appSources(dir), literalKeys('shop'))).toEqual([
      { file: join(dir, 'Page.vue'), key: 'shop.a' },
      { file: join(dir, 'Page.vue'), key: 'shop.b' },
    ]);
  });

  it('fail on a key the catalogue lacks, naming the file', () => {
    expect(() => expectInCatalogue(flatten(EN), [{ file: 'Page.vue', key: 'shop.list.title' }])).not.toThrow();
    expect(() => expectInCatalogue(flatten(EN), [{ file: 'Page.vue', key: 'shop.list.missing' }])).toThrow('Page.vue: shop.list.missing');
  });
});

describe('the shared tests', () => {
  it('are named as every app’s catalogue test names them', () => {
    expect(titles({ placeholders: 'and plural forms' })).toEqual([PREFIX, SAME_KEYS, NOT_EMPTY, PLURALS, COVERAGE]);
    expect(titles({ placeholders: 'only', sameInBoth: {}, coverage: { moreFilesThan: 5, moreKeysThan: 20 } })).toEqual([
      PREFIX,
      SAME_KEYS,
      NOT_PASTED,
      PLACEHOLDERS,
      COVERAGE,
    ]);
    expect(titles({ placeholders: 'own', coverage: 'own' })).toEqual([PREFIX, SAME_KEYS, NOT_EMPTY]);
  });

  it('let a sound app through', () => {
    const tests: SharedTests = { placeholders: 'and plural forms', sameInBoth: {}, coverage: { moreFilesThan: 1, moreKeysThan: 2 } };
    for (const [title, check] of sharedCatalogueChecks(tests)) expect(() => check(shop(EN, ES)), title).not.toThrow();
    for (const [title, check] of sharedCatalogueChecks({ placeholders: 'only' })) expect(() => check(shop(EN, ES)), title).not.toThrow();
  });

  it('catch a message outside the app’s prefix, in either language', () => {
    const check = checkNamed(PREFIX);
    expect(() => check(shop({ ...EN, other: { title: 'Other' } }, ES))).toThrow('other');
    expect(() => check(shop(EN, { ...ES, other: { title: 'Otro' } }))).toThrow('other');
  });

  it('catch a key one of the languages lacks', () => {
    const check = checkNamed(SAME_KEYS);
    expect(() => check(shop(EN, edited(ES, 'shop.list.empty')))).toThrow();
    expect(() => check(shop(edited(EN, 'shop.list.empty'), ES))).toThrow();
  });

  it('catch an empty message, in either language', () => {
    const check = checkNamed(NOT_EMPTY);
    expect(() => check(shop(EN, edited(ES, 'shop.list.empty', '  ')))).toThrow('shop.list.empty');
    expect(() => check(shop(edited(EN, 'shop.list.title', ''), ES))).toThrow('shop.list.title');
  });

  it('catch a Spanish that is the English pasted across, unless the app says it is so on purpose', () => {
    const check = checkNamed(NOT_PASTED, { placeholders: 'only', sameInBoth: {} });
    const onPurpose = checkNamed(NOT_PASTED, { placeholders: 'only', sameInBoth: { 'shop.status.open': 'the same word' } });
    const pasted = shop(EN, edited(ES, 'shop.status.open', 'Open'));
    expect(() => check(pasted)).toThrow('shop.status.open');
    expect(() => onPurpose(pasted)).not.toThrow();
    expect(() => check(shop(EN, edited(ES, 'shop.list.empty', ' ')))).toThrow('shop.list.empty');
  });

  it('catch another placeholder, with or without plural forms', () => {
    const plurals = checkNamed(PLURALS);
    const placeholdersOnly = checkNamed(PLACEHOLDERS, { placeholders: 'only' });
    const renamed = shop(EN, edited(ES, 'shop.count', '{count} producto | {count} productos'));
    expect(() => plurals(renamed)).toThrow('shop.count');
    expect(() => placeholdersOnly(renamed)).toThrow('shop.count');
  });

  it('catch another number of plural forms only where they are checked', () => {
    const oneForm = shop(EN, edited(ES, 'shop.count', '{n} productos'));
    expect(() => checkNamed(PLURALS)(oneForm)).toThrow('shop.count');
    expect(() => checkNamed(PLACEHOLDERS, { placeholders: 'only' })(oneForm)).not.toThrow();
  });

  it('catch a key a source names that the catalogue lacks', () => {
    const check = checkNamed(COVERAGE);
    expect(() => check(shop(edited(EN, 'shop.list.empty'), edited(ES, 'shop.list.empty')))).toThrow('shop.list.empty');
  });

  it('catch a prefix no key starts with', () => {
    const built = folderWith({ ...SOURCES, 'lib/kinds.ts': 'export const kind = (k: string) => t(`shop.kind.' + '${k}`);\n' });
    const check = checkNamed(COVERAGE);
    expect(() => check(shop(EN, ES, built))).toThrow('shop.kind.');
  });

  it('catch fewer sources or keys than the app says it has', () => {
    const moreFiles = checkNamed(COVERAGE, { placeholders: 'only', coverage: { moreFilesThan: 2 } });
    const moreKeys = checkNamed(COVERAGE, { placeholders: 'only', coverage: { moreKeysThan: 3 } });
    expect(() => moreFiles(shop(EN, ES))).toThrow('expected 2 to be greater than 2');
    expect(() => moreKeys(shop(EN, ES))).toThrow('the scanner found no key');
    expect(() => checkNamed(COVERAGE)(shop(EN, ES, folderWith({})))).toThrow('expected 0 to be greater than 0');
  });
});

describe('itChecksAppCatalogues', () => {
  itChecksAppCatalogues(shop(EN, ES), { placeholders: 'and plural forms', coverage: { moreFilesThan: 1, moreKeysThan: 2 } });

  it('registers one test per shared test in the describe that calls it', ({ task }) => {
    expect(task.suite?.tasks.map(({ name }) => name)).toEqual([
      PREFIX,
      SAME_KEYS,
      NOT_EMPTY,
      PLURALS,
      COVERAGE,
      'registers one test per shared test in the describe that calls it',
    ]);
  });
});

describe('expectWords', () => {
  it('passes when each key says its words in both languages', () => {
    expect(() => expectWords(shop(EN, ES), [['shop.list.title', 'Products', 'Productos']])).not.toThrow();
  });

  it('fails on other English, other Spanish or a key that is not there', () => {
    expect(() => expectWords(shop(EN, ES), [['shop.list.title', 'Items', 'Productos']])).toThrow('shop.list.title');
    expect(() => expectWords(shop(EN, ES), [['shop.list.title', 'Products', 'Artículos']])).toThrow('shop.list.title');
    expect(() => expectWords(shop(EN, ES), [['shop.list.subtitle', 'Products', 'Productos']])).toThrow('shop.list.subtitle');
  });
});
