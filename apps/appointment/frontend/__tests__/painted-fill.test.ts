// The old `form-fields-painted-fill` guard: Ionic paints `fill` on ion-input, ion-select and ion-textarea
// only in `md` mode, and the shell pins `ios` — a field with `fill` and no `mode="md"` shows no box.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const FRONTEND = dirname(dirname(fileURLToPath(import.meta.url)));

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

describe('form fields of the appointment pages', () => {
  it('pair every fill with mode="md"', () => {
    const unpainted = vueFiles(FRONTEND).flatMap((file) =>
      [...readFileSync(file, 'utf8').matchAll(/<(ion-(?:input|select|textarea))\b([^>]*)>/g)]
        .filter(([, , attrs]) => /\bfill=/.test(attrs) && !/\bmode="md"/.test(attrs))
        .map(([, tag]) => `${file.slice(FRONTEND.length)}: ${tag}`),
    );
    expect(vueFiles(FRONTEND).length).toBeGreaterThan(10);
    expect(unpainted).toEqual([]);
  });
});
