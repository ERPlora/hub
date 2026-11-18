// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { E2E_DIR, helpersAndSpecs } from './e2e-sources';

const made: string[] = [];

afterEach(() => {
  for (const dir of made.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/** A folder with `files` in it (empty), for helpersAndSpecs to walk. */
function folderWith(files: string[]): string {
  const root = mkdtempSync(join(tmpdir(), 'e2e-sources-'));
  made.push(root);
  for (const file of files) {
    mkdirSync(dirname(join(root, file)), { recursive: true });
    writeFileSync(join(root, file), '');
  }
  return root;
}

describe('helpersAndSpecs, the e2e code the Vitest checks read', () => {
  it('lists the helpers and specs, in subfolders too, and leaves out Vitest tests, run evidence and packages', () => {
    const root = folderWith([
      'helpers.ts',
      'login.spec.ts',
      'qa/assistant-battery.spec.ts',
      'helpers.test.ts',
      'README.md',
      '.artifacts/test-results/trace.ts',
      'node_modules/pkg/index.ts',
    ]);
    expect(helpersAndSpecs(root)).toEqual(['helpers.ts', 'login.spec.ts', 'qa/assistant-battery.spec.ts']);
  });

  it('walks the e2e folder by default', () => {
    expect(E2E_DIR.endsWith(join('tests', 'e2e'))).toBe(true);
    expect(helpersAndSpecs()).toEqual(expect.arrayContaining(['helpers.ts', 'whatsapp-helpers.ts', 'qa/assistant-battery.spec.ts']));
  });
});
