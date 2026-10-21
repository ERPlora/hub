// gh:hub#1060, gh:inventory#59, gh:inventory#121 (INVENTORY-F01, F13): the shell starts in iOS mode, and there an
// `ion-input`, `ion-select` or `ion-textarea` with `fill="outline"` paints no box: the old product form and the
// Reception and Count dialogs showed their fields without a frame. Every outlined control of the app's pages and
// components carries `mode="md"` (working-rules §2.4), and this test keeps it so.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const FRONTEND = dirname(fileURLToPath(import.meta.url));

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

/** Each opening tag of an Ionic text control, with the line it starts on. */
function controls(source: string): Array<{ line: number; tag: string }> {
  return [...source.matchAll(/<ion-(?:input|select|textarea)\b[^>]*>/g)].map((match) => ({
    line: source.slice(0, match.index).split('\n').length,
    tag: match[0],
  }));
}

describe('inventory text controls', () => {
  it('outlined, they are in «md» mode, the only one that paints the box', () => {
    const boxless: string[] = [];
    let outlined = 0;
    for (const file of vueFiles(FRONTEND)) {
      for (const { line, tag } of controls(readFileSync(file, 'utf8'))) {
        if (!/\bfill="outline"/.test(tag)) continue;
        outlined += 1;
        if (!/\bmode="md"/.test(tag)) boxless.push(`${file.slice(FRONTEND.length + 1)}:${line}`);
      }
    }
    // The form, category, stock, import and settings fields: if this count drops, a control lost its box.
    expect(outlined).toBeGreaterThanOrEqual(10);
    expect(boxless).toEqual([]);
  });
});
