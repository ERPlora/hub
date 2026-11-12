// @vitest-environment node
// Guardrail: every Vitest file that loads Playwright runs in Node's environment. Playwright's bundled
// source-map-support takes a global `window` with an `XMLHttpRequest` for a browser: loaded in happy-dom (the
// config's default, vite.config.ts), it fetched its own files by synchronous XHR from happy-dom's
// http://localhost:3000, and every request crashed a Node child process (`ECONNREFUSED 127.0.0.1:3000`) behind a
// green run (playwright.config.test.ts, 3 of 3 runs on 2026-10-19; the SaaS fixed the same in saas#46).
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import config from '../../vite.config';
import { NO_CLOCK } from '../../vitest.load';
import { listAll, readText, readTexts } from '../../vitest.offload';

// The real reads, watched: the guardrail must read each module once (see `readImports`).
vi.mock('node:fs/promises', async (importOriginal) => {
  const fs = await importOriginal<typeof import('node:fs/promises')>();
  return { ...fs, readFile: vi.fn(fs.readFile) };
});

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** The modules a file loads: `import … from`, `import '…'`, `export … from` and `import('…')` (types load nothing). */
const RUNTIME_IMPORTS =
  /^(?:import|export) (?!type )[^;]*?\bfrom ['"]([^'"]+)['"]|^import ['"]([^'"]+)['"]|(?<!typeof )\bimport\(['"]([^'"]+)['"]\)/gm;

/** Playwright's packages: the test runner (and its subpaths, like `@playwright/test/reporter`) and the libraries under it. */
const PLAYWRIGHT = /^(?:@playwright\/test|playwright(?:-core)?)(?:\/|$)/;

/** The file a relative import names: as written, with `.ts` or its directory's `index.ts`. */
async function resolveRelative(from: string, specifier: string): Promise<string | undefined> {
  const base = resolve(dirname(from), specifier);
  const candidates = [base, `${base}.ts`, join(base, 'index.ts')];
  const files = await Promise.all(candidates.map((path) => stat(path).then((found) => found.isFile(), () => false)));
  return candidates.find((_path, index) => files[index]);
}

/** What a module loads: whether it imports Playwright itself, and the modules of the project it imports. */
interface ModuleImports {
  readonly playwright: boolean;
  readonly modules: readonly string[];
}

/**
 * Each module's imports, read once per run (see `readImports`). The ~700 test files share their pages, components and
 * helpers: walking each test's imports from the disk again read 12,766 files for 1,474 modules (2026-10-21), and on a
 * loaded machine that took this test past Vitest's 5 s.
 */
const importsByPath = new Map<string, ModuleImports>();

/**
 * Reads the modules `files` load, the ones those load and so on, before they are walked: each level's files read at
 * once and their imports looked for at once, without holding the worker (hub#1315), and each module once.
 */
async function readImports(files: readonly string[]): Promise<void> {
  for (let level = [...new Set(files)].filter((path) => !importsByPath.has(path)); level.length > 0; ) {
    const texts = await readTexts(level);
    const found = await Promise.all(
      level.map(async (path, index): Promise<ModuleImports> => {
        const specifiers = [...texts[index].matchAll(RUNTIME_IMPORTS)].map(([, ...match]) => match.find(Boolean) ?? '');
        const modules = await Promise.all(specifiers.filter((specifier) => specifier.startsWith('.')).map((specifier) => resolveRelative(path, specifier)));
        return {
          playwright: specifiers.some((specifier) => PLAYWRIGHT.test(specifier)),
          modules: modules.filter((module): module is string => module !== undefined),
        };
      }),
    );
    level.forEach((path, index) => importsByPath.set(path, found[index]));
    level = [...new Set(found.flatMap(({ modules }) => modules))].filter((path) => !importsByPath.has(path));
  }
}

/** Whether loading the module at `path`, read ahead by `readImports`, loads Playwright: it imports Playwright or a
 *  module of the project that does. */
function loadsPlaywright(path: string, seen = new Set<string>()): boolean {
  if (seen.has(path)) return false;
  seen.add(path);
  const imports = importsByPath.get(path);
  if (!imports) throw new Error(`${path} was not read ahead (readImports)`);
  return imports.playwright || imports.modules.some((module) => loadsPlaywright(module, seen));
}

/** Which of `files` load Playwright, their imports read ahead. */
async function playwrightLoaders(files: readonly string[]): Promise<string[]> {
  await readImports(files);
  return files.filter((file) => loadsPlaywright(file));
}

/** The environment Vitest gives a test file: its docblock's (read anywhere in the file, as Vitest does), else the config's. */
function environmentOf(code: string): string | undefined {
  return code.match(/@(?:vitest|jest)-environment\s+([\w-]+)\b/)?.[1] ?? config.test?.environment;
}

/** The test files Vitest runs (the config's `include`), relative to the Hub, listed without holding the worker. */
async function testFiles(): Promise<string[]> {
  return (await listAll(config.test?.include ?? [], HUB_DIR)).filter((file) => !file.split(sep).includes('node_modules'));
}

describe('the tests that load Playwright', () => {
  it("run this file in Node's environment, with no browser for Playwright to fetch from", () => {
    expect(['window', 'XMLHttpRequest'].filter((name) => name in globalThis)).toEqual([]);
  });

  // Reads every module the tests load from the disk, so its time is the machine's: with several test runs on one
  // machine (load 20–40) and every opened file scanned, it took up to 9.4 s reading each module once (2026-10-21),
  // against Vitest's 5 s. Read ahead without holding the worker, as long as the machine makes it (hub#1315).
  it("give every test file that loads Playwright Node's environment", async () => {
    const loading = (await playwrightLoaders((await testFiles()).map((file) => join(HUB_DIR, file)))).map((file) => relative(HUB_DIR, file));
    expect(loading).toEqual(expect.arrayContaining([join('tests', 'e2e', 'playwright.config.test.ts')]));
    const outsideNode = loading.filter((file) => environmentOf(readText(join(HUB_DIR, file)) ?? '') !== 'node');
    expect(outsideNode).toEqual([]);
  }, NO_CLOCK);

  describe('loadsPlaywright', () => {
    let work: string;

    afterEach(() => rmSync(work, { recursive: true, force: true }));

    it('sees Playwright loaded through a helper, the config, a subpath or a dynamic import, and not through types', async () => {
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
      expect((await playwrightLoaders(tests.map((name) => join(work, name)))).map((file) => relative(work, file))).toEqual([
        'through-helper.test.ts',
        'through-config.test.ts',
        'reexport.test.ts',
        'reporter.test.ts',
        'core.test.ts',
        'dynamic.test.ts',
      ]);
    });

    it('reads each module once, however many test files load it', async () => {
      work = mkdtempSync(join(tmpdir(), 'hub-loads-playwright-'));
      const modules: Record<string, string> = {
        'shared.ts': 'export const shared = 1;\n',
        'helper.ts': "import { shared } from './shared';\nexport const helper = shared;\n",
        'first.test.ts': "import { helper } from './helper';\n",
        'second.test.ts': "import { helper } from './helper';\nimport { shared } from './shared';\n",
      };
      for (const [name, code] of Object.entries(modules)) writeFileSync(join(work, name), code);
      vi.mocked(readFile).mockClear();
      expect(await playwrightLoaders(['first.test.ts', 'second.test.ts'].map((name) => join(work, name)))).toEqual([]);
      const read = vi.mocked(readFile).mock.calls.map(([path]) => relative(work, String(path)));
      expect(read.sort()).toEqual(['first.test.ts', 'helper.ts', 'second.test.ts', 'shared.ts']);
    });

    it('sees Playwright through a module that another test file already walked', async () => {
      work = mkdtempSync(join(tmpdir(), 'hub-loads-playwright-'));
      const modules: Record<string, string> = {
        'page.ts': "import { test } from '@playwright/test';\nexport const page = test;\n",
        'helper.ts': "import { page } from './page';\nexport const helper = page;\n",
        'first.test.ts': "import { helper } from './helper';\n",
        'second.test.ts': "import { helper } from './helper';\n",
      };
      for (const [name, code] of Object.entries(modules)) writeFileSync(join(work, name), code);
      expect((await playwrightLoaders(['first.test.ts', 'second.test.ts'].map((name) => join(work, name)))).map((file) => relative(work, file))).toEqual([
        'first.test.ts',
        'second.test.ts',
      ]);
    });
  });

  it("reads the environment from the file's docblock, else the config's", () => {
    expect(environmentOf('// @vitest-environment node\nimport x from "y";\n')).toBe('node');
    expect(environmentOf('/**\n * @jest-environment node\n */\n')).toBe('node');
    expect(environmentOf('import x from "y";\n')).toBe('happy-dom');
  });
});
