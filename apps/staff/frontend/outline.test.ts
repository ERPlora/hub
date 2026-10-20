// gh:staff#39, gh:hub#1060, gh:pm#152 (STAFF-F01, F02): the shell starts in iOS mode, and there an
// `ion-input`, `ion-select` or `ion-textarea` with `fill="outline"` paints no box: the old record form
// showed «Hourly rate» and «Commission» as invisible fields. Every outlined control of the staff app's
// pages and components carries `mode="md"` (working-rules §2.4), and this test keeps it so.
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

describe('staff text controls', () => {
  it('outlined, they are in «md» mode, the only one that paints the box', () => {
    const files = vueFiles(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    const boxless: string[] = [];
    let outlined = 0;
    for (const file of files) {
      for (const { line, tag } of controls(readFileSync(file, 'utf8'))) {
        if (!/\bfill="outline"/.test(tag)) continue;
        outlined += 1;
        if (!/\bmode="md"/.test(tag)) boxless.push(`${file.slice(FRONTEND.length + 1)}:${line}`);
      }
    }
    expect(outlined).toBeGreaterThan(0);
    expect(boxless).toEqual([]);
  });
});
