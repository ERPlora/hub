// The tests every catalogue of the SPA shares. An app keeps its texts in `frontend/locale/en.json` (the source) and
// `es.json`, under its own name; its `locale.test.ts` reads them with `appCatalogues`, calls `itChecksAppCatalogues`
// inside its describe for the tests they all make, and adds its own (`expectWords` for the screens' words).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, it } from 'vitest';

/** The hub's root, three levels up. Not imported from frontend-sources.ts, which loads TypeScript: every app's
 *  catalogue test would pay for it. */
const HUB = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

export type Catalogue = { [key: string]: string | Catalogue };

/** An app's catalogues as imported, flattened (`EN`, `ES`), and the frontend whose sources use them. */
export interface AppCatalogues {
  app: string;
  frontend: string;
  en: object;
  es: object;
  EN: Map<string, string>;
  ES: Map<string, string>;
}

/** Which files of a frontend `appSources` lists. */
export interface SourceFilter {
  /** Folders it does not look into: `__tests__` unless told otherwise. */
  skip?: readonly string[];
  /** The endings that count: `.vue` and `.ts` unless told otherwise. */
  extensions?: readonly string[];
  /** Whether a declaration (`.d.ts`) counts. A test never does. */
  declarations?: boolean;
}

/** A key a source names. */
export interface UsedKey {
  file: string;
  key: string;
}

/** The variants of the shared tests an app's catalogue test asks for. */
export interface SharedTests {
  /** Spanish keeps English's placeholders and, with `'and plural forms'`, its number of forms («one | other»); `'own'`
   *  where the app's own test checks more. */
  placeholders: 'and plural forms' | 'only' | 'own';
  /** Keys whose Spanish is the English on purpose, and why: given, a Spanish that is the English pasted across fails. */
  sameInBoth?: Readonly<Record<string, string>>;
  /** More than `moreFilesThan` sources (none by default) naming more than `moreKeysThan` keys; `'own'` where the app
   *  reads its sources its own way. */
  coverage?: { moreFilesThan?: number; moreKeysThan?: number } | 'own';
}

type Check = readonly [title: string, check: (catalogues: AppCatalogues) => void];

/** Every message of `catalogue` by its dotted key (a list's by its place). */
export function flatten(catalogue: object, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value as object, path)) out.set(k, v);
  }
  return out;
}

/** The placeholders of `message`, each once, in alphabetical order. */
export function placeholders(message: string): string[] {
  return [...new Set([...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort();
}

/** `app`'s catalogues; their sources are in its frontend (base's for `base`) unless `frontend` says where. */
export function appCatalogues(app: string, en: object, es: object, frontend?: string): AppCatalogues {
  const dir = frontend ?? (app === 'base' ? join(HUB, 'base', 'frontend') : join(HUB, 'apps', app, 'frontend'));
  return { app, frontend: dir, en, es, EN: flatten(en), ES: flatten(es) };
}

/** The sources under `dir` that may name a key: pages, components, composables and helpers, by `filter`. */
export function appSources(dir: string, filter: SourceFilter = {}): string[] {
  const { skip = ['__tests__'], extensions = ['.vue', '.ts'], declarations = false } = filter;
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return skip.includes(entry.name) ? [] : appSources(path, filter);
    const { name } = entry;
    const counts = extensions.some((ending) => name.endsWith(ending)) && !name.endsWith('.test.ts') && (declarations || !name.endsWith('.d.ts'));
    return counts ? [path] : [];
  });
}

/** `t('<app>.…')` and `$t('<app>.…')`: a key of `app` written out whole. */
export function literalKeys(app: string): RegExp {
  return new RegExp(String.raw`\bt\(\s*'(${app}\.[^']+)'`, 'g');
}

/** `t(`<app>.…${…}`)`: the start of a key of `app` built when it runs. */
function keyPrefixes(app: string): RegExp {
  return new RegExp(String.raw`\bt\(\s*\`(${app}\.[^\`$]+)\$\{`, 'g');
}

/** What the first group of `pattern` finds in each of `files`. */
export function usedKeys(files: readonly string[], pattern: RegExp): UsedKey[] {
  return files.flatMap((file) => [...readFileSync(file, 'utf8').matchAll(pattern)].map((match) => ({ file, key: match[1] })));
}

/** Each of `keys` is a key of `catalogue`. */
export function expectInCatalogue(catalogue: ReadonlyMap<string, string>, keys: readonly UsedKey[]): void {
  for (const { file, key } of keys) expect(catalogue.has(key), `${file}: ${key}`).toBe(true);
}

/** Each Spanish message keeps the placeholders of its English and, with `pluralForms`, its number of forms. */
export function expectSamePlaceholders({ EN, ES }: AppCatalogues, { pluralForms }: { pluralForms: boolean }): void {
  for (const [key, message] of EN) {
    const spanish = ES.get(key) ?? '';
    expect(placeholders(spanish), key).toEqual(placeholders(message));
    if (pluralForms) expect(spanish.split('|').length, key).toBe(message.split('|').length);
  }
}

/** «ticket» or the Catalan «tiquet» as a word: the sales receipt, which Spanish calls «tique» (RAE, and the word of
 *  the invoicing rules, RD 1619/2012). In capitals it is TICKET, the code of the receipts' series, which the business
 *  sees as it is written. */
const ANGLICISED_RECEIPT = /\b[Tt]i(?:ck|qu)ets?\b/;

/** Every Spanish message of `ES` that says «ticket» or «tiquet», as «key: message». The keys (`tickets`,
 *  `settingsTickets`) are a published contract, not text, and never count. */
export function anglicisedReceipts(ES: ReadonlyMap<string, string>): string[] {
  return [...ES].filter(([, message]) => ANGLICISED_RECEIPT.test(message)).map(([key, message]) => `${key}: ${message}`);
}

function expectNoEmptyMessage({ EN, ES }: AppCatalogues): void {
  for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
}

function expectSourcesCovered({ app, frontend, EN }: AppCatalogues, moreFilesThan = 0, moreKeysThan?: number): void {
  const files = appSources(frontend);
  expect(files.length).toBeGreaterThan(moreFilesThan);
  const keys = usedKeys(files, literalKeys(app));
  expectInCatalogue(EN, keys);
  const known = [...EN.keys()];
  for (const { file, key: prefix } of usedKeys(files, keyPrefixes(app))) {
    expect(known.some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
  }
  if (moreKeysThan !== undefined) expect(keys.length, 'the scanner found no key: it is broken').toBeGreaterThan(moreKeysThan);
}

/** The shared tests `tests` asks for, by the title each app's catalogue test gives them. */
export function sharedCatalogueChecks(tests: SharedTests): Check[] {
  const { placeholders: kind, sameInBoth, coverage = {} } = tests;
  const checks: Check[] = [
    [
      'live under the app prefix, so merging them into the shell never collides',
      ({ app, en, es }) => {
        expect(Object.keys(en)).toEqual([app]);
        expect(Object.keys(es)).toEqual([app]);
      },
    ],
    ['have exactly the same keys', ({ EN, ES }) => expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort())],
  ];
  if (sameInBoth) {
    checks.push([
      'have no empty message, and no Spanish that is the English pasted across',
      (catalogues) => {
        expectNoEmptyMessage(catalogues);
        for (const [key, message] of catalogues.EN) {
          if (!Object.hasOwn(sameInBoth, key)) expect(catalogues.ES.get(key), key).not.toBe(message);
        }
      },
    ]);
  } else {
    checks.push(['have no empty message', expectNoEmptyMessage]);
  }
  checks.push([
    'say «tique» in Spanish, never «ticket»',
    ({ ES }) => {
      const found = anglicisedReceipts(ES);
      expect(found, found.join(' · ')).toEqual([]);
    },
  ]);
  if (kind === 'and plural forms') {
    checks.push(['keep the same placeholders and plural forms in both languages', (catalogues) => expectSamePlaceholders(catalogues, { pluralForms: true })]);
  } else if (kind === 'only') {
    checks.push(['keep the same placeholders in both languages', (catalogues) => expectSamePlaceholders(catalogues, { pluralForms: false })]);
  }
  if (coverage !== 'own') {
    checks.push([
      'cover every key the app’s sources use, literal or built from a known prefix',
      (catalogues) => expectSourcesCovered(catalogues, coverage.moreFilesThan, coverage.moreKeysThan),
    ]);
  }
  return checks;
}

/** One test per shared test `tests` asks for, in the describe that calls it. */
export function itChecksAppCatalogues(catalogues: AppCatalogues, tests: SharedTests): void {
  for (const [title, check] of sharedCatalogueChecks(tests)) it(title, () => check(catalogues));
}

/** Each key says, word for word, its English and its Spanish. */
export function expectWords({ EN, ES }: Pick<AppCatalogues, 'EN' | 'ES'>, words: ReadonlyArray<readonly [key: string, english: string, spanish: string]>): void {
  for (const [key, english, spanish] of words) {
    expect(EN.get(key), key).toBe(english);
    expect(ES.get(key), key).toBe(spanish);
  }
}
