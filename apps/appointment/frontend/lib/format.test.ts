// The diary's money is the business's (BASE-F50, hub#577): its country's currency with the decimals the server counts
// it in, as the platform reads it (`useBusinessMoney` of base), written with the platform's `formatMoney`. The diary
// keeps no money of its own: no screen of it names a currency, so a business in Poland never reads euros.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import * as platform from '../../../../base/frontend/lib/money';
import * as diary from './format';

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** The diary's screens and their code (`.ts` and `.vue`), its tests and their helpers left out. */
function sources(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.(ts|vue)$/.test(entry.name) && !/\.test\.ts$/.test(entry.name) && !entry.name.endsWith('.d.ts') ? [path] : [];
  });
}

describe("the diary's money", () => {
  it("is the platform's: the business's currency, written the platform's way", () => {
    expect(diary.useBusinessMoney).toBe(platform.useBusinessMoney);
    expect(diary.formatMoney).toBe(platform.formatMoney);
  });

  it('no screen of the diary names a currency of its own', () => {
    const fixed = sources(FRONTEND)
      .filter((path) => /currency:\s*['"`][A-Z]{3}['"`]|['"`]EUR['"`]/.test(readFileSync(path, 'utf8')))
      .map((path) => relative(FRONTEND, path));
    expect(fixed).toEqual([]);
  });
});
