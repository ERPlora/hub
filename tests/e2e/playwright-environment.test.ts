// @vitest-environment node
// Guardrail: every Vitest file that loads Playwright runs in Node's environment. Playwright's bundled
// source-map-support takes a global `window` with an `XMLHttpRequest` for a browser: loaded in happy-dom (the
// config's default, vite.config.ts), it fetched its own files by synchronous XHR from happy-dom's
// http://localhost:3000, and every request crashed a Node child process (`ECONNREFUSED 127.0.0.1:3000`) behind a
// green run (playwright.config.test.ts, 3 of 3 runs on 2026-10-19; the SaaS fixed the same in saas#46).
import { globSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';

import config from '../../vite.config';

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** The modules a file loads: `import … from`, `import '…'`, `export … from` and `import('…')` (types load nothing). */
const RUNTIME_IMPORTS =
  /^(?:import|export) (?!type )[^;]*?\bfrom ['"]([^'"]+)['"]|^import ['"]([^'"]+)['"]|(?<!typeof )\bimport\(['"]([^'"]+)['"]\)/gm;

/** Playwright's packages: the test runner (and its subpaths, like `@playwright/test/reporter`) and the libraries under it. */
const PLAYWRIGHT = /^(?:@playwright\/test|playwright(?:-core)?)(?:\/|$)/;

/** The file a relative import names: as written, with `.ts` or its directory's `index.ts`. */
function resolveRelative(from: string, specifier: string): string | undefined {
  const base = resolve(dirname(from), specifier);
  return [base, `${base}.ts`, join(base, 'index.ts')].find((path) => statSync(path, { throwIfNoEntry: false })?.isFile());
}

/** Whether loading the module at `path` loads Playwright: it imports Playwright or a module of the project that does. */
function loadsPlaywright(path: string, seen = new Set<string>()): boolean {
  if (seen.has(path)) return false;
  seen.add(path);
  return [...readFileSync(path, 'utf8').matchAll(RUNTIME_IMPORTS)].some(([, ...specifiers]) => {
    const specifier = specifiers.find(Boolean) ?? '';
    if (PLAYWRIGHT.test(specifier)) return true;
    const module = specifier.startsWith('.') ? resolveRelative(path, specifier) : undefined;
    return module !== undefined && loadsPlaywright(module, seen);
  });
}

/** The environment Vitest gives a test file: its docblock's (read anywhere in the file, as Vitest does), else the config's. */
function environmentOf(code: string): string | undefined {
  return code.match(/@(?:vitest|jest)-environment\s+([\w-]+)\b/)?.[1] ?? config.test?.environment;
}

/** The test files Vitest runs (the config's `include`), relative to the Hub. */
function testFiles(): string[] {
  return globSync(config.test?.include ?? [], { cwd: HUB_DIR }).filter((file) => !file.split(sep).includes('node_modules'));
}

describe('the tests that load Playwright', () => {
  it("run this file in Node's environment, with no browser for Playwright to fetch from", () => {
    expect(['window', 'XMLHttpRequest'].filter((name) => name in globalThis)).toEqual([]);
  });

  it("give every test file that loads Playwright Node's environment", () => {
    const loading = testFiles().filter((file) => loadsPlaywright(join(HUB_DIR, file)));
    expect(loading).toEqual(expect.arrayContaining([join('tests', 'e2e', 'playwright.config.test.ts')]));
    const outsideNode = loading.filter((file) => environmentOf(readFileSync(join(HUB_DIR, file), 'utf8')) !== 'node');
    expect(outsideNode).toEqual([]);
  });

  describe('loadsPlaywright', () => {
    let work: string;

    afterEach(() => rmSync(work, { recursive: true, force: true }));

    it('sees Playwright loaded through a helper, the config, a subpath or a dynamic import, and not through types', () => {
      work = mkdtempSync(join(tmpdir(), 'hub-loads-playwright-'));
      // In a template, so that this file's own source does not read as a dynamic import of Playwright.
      const playwright = '@playwright/test';
      const modules: Record<string, string> = {
        'helpers.ts': "import {\n  expect,\n  type Page,\n} from '@playwright/test';\nexport const check = expect;\n",
        'playwright.config.ts': "import { defineConfig } from '@playwright/test';\nexport default defineConfig({});\n",
        'resource-timing.ts': "import type { Page } from '@playwright/test';\nexport type Screen = Page;\nexport const kind = 'page';\n",
        'through-helper.test.ts': "import { check } from './helpers';\n",
        'through-config.test.ts': "import config from './playwright.config.ts';\n",
        'reexport.test.ts': "export * from './helpers';\n",
        'reporter.test.ts': "import { list } from '@playwright/test/reporter';\n",
        'core.test.ts': "import { chromium } from 'playwright-core';\n",
        'dynamic.test.ts': `it('loads', async () => {\n  await import('${playwright}');\n});\n`,
        'types.test.ts':
          "import type { Screen } from './resource-timing';\nimport { kind } from './resource-timing';\nimport type { Reporter } from 'playwright';\nlet helper: typeof import('./helpers');\n",
        'lookalike.test.ts': "import { mark } from 'playwright-helpers';\n",
        'comment.test.ts': "// import { test } from '@playwright/test';\nimport { describe } from 'vitest';\n",
        'ping.ts': "import { pong } from './pong';\nexport const ping = 1;\n",
        'pong.ts': "import { ping } from './ping';\nexport const pong = 2;\n",
        'cycle.test.ts': "import { ping } from './ping';\n",
      };
      for (const [name, code] of Object.entries(modules)) writeFileSync(join(work, name), code);
      const tests = Object.keys(modules).filter((name) => name.endsWith('.test.ts'));
      expect(tests.filter((name) => loadsPlaywright(join(work, name)))).toEqual([
        'through-helper.test.ts',
        'through-config.test.ts',
        'reexport.test.ts',
        'reporter.test.ts',
        'core.test.ts',
        'dynamic.test.ts',
      ]);
    });
  });

  it("reads the environment from the file's docblock, else the config's", () => {
    expect(environmentOf('// @vitest-environment node\nimport x from "y";\n')).toBe('node');
    expect(environmentOf('/**\n * @jest-environment node\n */\n')).toBe('node');
    expect(environmentOf('import x from "y";\n')).toBe('happy-dom');
  });
});
