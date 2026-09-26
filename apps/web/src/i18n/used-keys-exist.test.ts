// Every key the shell asks for exists in the source catalogue (hub#2197).
//
// `locales.parity.test.ts` guards `en` against its translations, but nothing guarded the code
// against `en`: Files called `t('files.moveSuccess')` and passed `'files.moveError'` as a fallback,
// neither was ever declared, and vue-i18n answered with the key path — the person moving a file read
// «files.moveSuccess» in the toast. The API docs retry button had the same hole (`apiDocs.retry`).
//
// The sweep reads the source of every view, component and lib as text and collects the literal keys
// in the three shapes the shell uses to name a string: a `t('…')` / `$t('…')` call, a `…Key: '…'` /
// `…Key = '…'` field (nav sections, health rows, error keys) and the fallback of Files' `reasonFor`.
// Only literals whose first segment is a namespace of `en` count, so error codes such as
// `print.not_ready` or storage keys never enter. Keys built at runtime (`t(\`x.${code}\`)`) are out of
// reach by design: their helpers check with `te()` and fall back to a literal, which IS swept.
import { describe, expect, it } from 'vitest';
import en from './locales/en';

const sources = import.meta.glob<string>(
  ['../**/*.vue', '../**/*.ts', '!../**/*.test.ts', '!../**/*.spec.ts', '!./locales/**'],
  { eager: true, query: '?raw', import: 'default' },
);

const KEY = String.raw`(['"])([A-Za-z_][\w-]*(?:\.[\w-]+)+)\1`;
const KEY_SITES = [
  new RegExp(String.raw`(?<![\w.])\$?t\(\s*` + KEY, 'g'),
  new RegExp(String.raw`[A-Za-z]Key\s*[:=]\s*` + KEY, 'g'),
  new RegExp(String.raw`\breasonFor\([^()]*?,\s*` + KEY, 'g'),
];

/** The leaf a dotted key points at in a catalogue, or `undefined` when a segment is missing. */
function lookup(catalogue: unknown, key: string): unknown {
  let node: unknown = catalogue;
  for (const part of key.split('.')) {
    if (node === null || typeof node !== 'object' || !(part in node)) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

/** `file: key` for every literal key in `source` that `en` does not resolve to a string. */
function missingKeys(file: string, source: string): string[] {
  const missing: string[] = [];
  for (const site of KEY_SITES) {
    for (const match of source.matchAll(site)) {
      const key = match[2];
      if (!(key.split('.')[0] in en)) continue;
      if (typeof lookup(en, key) !== 'string') missing.push(`${file}: ${key}`);
    }
  }
  return missing;
}

describe('keys used by the shell exist in `en` (hub#2197)', () => {
  it('the sweep reads the views, components and libs', () => {
    // Without this the sweep below would pass vacuously on a glob that matched nothing.
    const files = Object.keys(sources);
    expect(files.some((f) => f.endsWith('/views/FilesPage.vue'))).toBe(true);
    expect(files.length).toBeGreaterThan(100);
  });

  it('catches a key the catalogue does not declare (positive control)', () => {
    expect(missingKeys('probe.vue', "t('files.noSuchKey')")).toEqual(['probe.vue: files.noSuchKey']);
    expect(missingKeys('probe.vue', "reasonFor(outcome, 'files.noSuchKey')")).toEqual([
      'probe.vue: files.noSuchKey',
    ]);
    expect(missingKeys('probe.ts', "labelKey: 'nav.noSuchKey'")).toEqual(['probe.ts: nav.noSuchKey']);
    // A namespace (an object, not a sentence) is not a string either.
    expect(missingKeys('probe.vue', "t('files.errors')")).toEqual(['probe.vue: files.errors']);
    // Error codes and other dotted literals outside the catalogue namespaces are not keys.
    expect(missingKeys('probe.ts', "onRefusal('print.not_ready', 'x')")).toEqual([]);
  });

  it('every literal key in the shell resolves to a sentence in `en`', () => {
    const missing = Object.entries(sources).flatMap(([file, source]) => missingKeys(file, source));
    expect(missing, `keys missing from en.ts:\n${missing.join('\n')}`).toEqual([]);
  });
});
