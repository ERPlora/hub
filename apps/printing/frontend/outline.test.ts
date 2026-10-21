// gh:printing#50, gh:printing#54, gh:hub#1060 (PRINTING-F03, F04, F06): the shell starts in iOS mode, and
// there an `ion-input`, `ion-select` or `ion-textarea` without `fill` paints no box — the old screen showed
// the IP, the port, the paper width and the role as loose text. Every text control of the printing app's
// pages and components is outlined and in «md» mode, the only one that paints the box (working-rules §2.4),
// and this test keeps it so.
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

/** Each opening tag of an Ionic text control (not `ion-select-option`), with the line it starts on. A `>`
 *  inside a quoted attribute (`Exclude<…>`, `=>`) does not close the tag. */
function controls(source: string): Array<{ line: number; tag: string }> {
  return [...source.matchAll(/<ion-(?:input|select|textarea)(?=[\s>])(?:[^>"']|"[^"]*"|'[^']*')*>/g)].map((match) => ({
    line: source.slice(0, match.index).split('\n').length,
    tag: match[0],
  }));
}

describe('printing text controls', () => {
  it('every one has its box: outlined, in «md» mode', () => {
    const boxless: string[] = [];
    let seen = 0;
    for (const file of vueFiles(FRONTEND)) {
      for (const { line, tag } of controls(readFileSync(file, 'utf8'))) {
        seen += 1;
        if (!/\bfill="outline"/.test(tag) || !/\bmode="md"/.test(tag)) boxless.push(`${file.slice(FRONTEND.length + 1)}:${line}`);
      }
    }
    // The printer window's name, connection, address, port, paper and role; the settings' copies and printers.
    expect(seen).toBeGreaterThanOrEqual(8);
    expect(boxless).toEqual([]);
  });
});
