// What the guards of every catalogue of the Hub's SPA read: which files, and how a finding names where it is.
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { flattened, HUB, hubCatalogues } from './hub-catalogues';

describe('hubCatalogues', () => {
  it('reads the platform’s and every app’s catalogue, in English and in Spanish', () => {
    const files = hubCatalogues().map((file) => relative(HUB, file));
    expect(files).toContain(join('base', 'frontend', 'locale', 'en.json'));
    expect(files).toContain(join('apps', 'service', 'frontend', 'locale', 'es.json'));
    expect(files.length).toBeGreaterThan(40);
  });
});

describe('flattened', () => {
  it('names each message by its file and its dotted key', () => {
    const file = join(HUB, 'base', 'frontend', 'locale', 'en.json');
    const where = [...flattened(file).keys()];
    expect(where.length).toBeGreaterThan(100);
    expect(where.every((key) => key.startsWith(`${join('base', 'frontend', 'locale', 'en.json')} › base.`))).toBe(true);
  });
});
