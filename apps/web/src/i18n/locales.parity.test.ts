// The guard the family of 42 i18n defects never left behind (hub#1241).
//
// #39 → #273 → #762 → #768 → #781 → #863 → #868 → #869 → #959 → #1070 → #1094 → #1102 → #1159 →
// #1178 → #1190: sixteen fixes, screen by screen, and not one of them left a rule. Every one of
// them is the same shape — a string that exists in one language and not in the other, so a hub in
// Spanish reads English (or a key path) at the counter.
//
// `en` is the SOURCE (ADR-0055/0199) and every other locale is its translation, so the contract is
// exact equality of key paths: a key present in `en` and missing elsewhere is an untranslated
// string, and a key present elsewhere and missing in `en` is an ORPHAN — dead weight that vue-i18n
// will never look up, and that hides the fact its English source was deleted.
//
// The sweep is over `./locales/*.ts` (the same glob `index.ts` loads), so adding `fr.ts` tomorrow
// puts it under the guard with no edit here — which is the whole point of "adding a language = one
// file".
import { describe, expect, it } from 'vitest';

const localeModules = import.meta.glob<{ default: Record<string, unknown> }>('./locales/*.ts', {
  eager: true,
});

/** Every leaf key path of a catalogue, dotted (`nav.home`), sorted. Arrays count as leaves. */
function keyPaths(node: unknown, prefix = ''): string[] {
  if (node === null || typeof node !== 'object' || Array.isArray(node)) return [prefix];
  const paths: string[] = [];
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    paths.push(...keyPaths(value, prefix ? `${prefix}.${key}` : key));
  }
  return paths.sort();
}

const catalogues = new Map<string, Record<string, unknown>>(
  Object.entries(localeModules).map(([path, mod]) => [
    path.match(/\/([^/]+)\.ts$/)?.[1] ?? path,
    mod.default,
  ]),
);

const SOURCE = 'en';

describe('paridad de los catálogos del shell (hub#1241)', () => {
  it('el catálogo fuente `en` existe y no está vacío', () => {
    // Without this the two sweeps below would pass vacuously on an empty source.
    expect(catalogues.has(SOURCE)).toBe(true);
    expect(keyPaths(catalogues.get(SOURCE)).length).toBeGreaterThan(100);
  });

  const source = keyPaths(catalogues.get(SOURCE) ?? {});

  for (const [code, catalogue] of catalogues) {
    if (code === SOURCE) continue;

    it(`\`${code}\` traduce TODAS las claves de \`en\` (hub#1190: el usuario lee inglés)`, () => {
      const missing = source.filter((key) => !keyPaths(catalogue).includes(key));
      expect(missing, `sin traducir en ${code}.ts: ${missing.join(', ')}`).toEqual([]);
    });

    it(`\`${code}\` no tiene claves HUÉRFANAS que \`en\` ya no declara`, () => {
      const translated = keyPaths(catalogue);
      const orphans = translated.filter((key) => !source.includes(key));
      expect(orphans, `huérfanas en ${code}.ts (no están en en.ts): ${orphans.join(', ')}`).toEqual(
        [],
      );
    });
  }
});
