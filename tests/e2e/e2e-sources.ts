// The e2e's own code, for the Vitest checks that read it.
import { globSync } from 'node:fs';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The e2e's helpers and specs under `root`, relative to it and in its subfolders too: not Vitest's own tests nor what
 *  a run leaves (dot folders) or installed packages. */
export const helpersAndSpecs = (root = E2E_DIR): string[] =>
  globSync('**/*.ts', { cwd: root, exclude: (name) => name === 'node_modules' || name.startsWith('.') || name.endsWith('.test.ts') }).sort();
