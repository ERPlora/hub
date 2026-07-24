import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

describe('puente de módulos del shell de desarrollo', () => {
  it('incluye Printing para que sus rutas no terminen en el fallback HTML de Vite', () => {
    const sync = readFileSync(join(WEB, 'sync-modules.mjs'), 'utf8');
    expect(sync).toMatch(/['"]printing['"]/);
  });
});
