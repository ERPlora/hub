// Guards for the bench's boot recovery (ERPlora/hub#1806).
//
// These live in `tests/` and NOT in `tests/e2e/` on purpose: Playwright's default `testMatch`
// picks up `*.test.ts` as well as `*.spec.ts`, so a vitest file inside `testDir` would be handed
// to Playwright and fail there. `bench-ports.test.ts` sits here for the same reason.

import { describe, expect, it } from 'vitest';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  BOOT_RELOAD_LIMIT,
  declaresTestMatch,
  isBootTransportFailure,
  listE2eSpecs,
  specTakesTestFromPlaywright,
  TRANSIENT_TRANSPORT_ERRORS,
} from './bench-boot';

const APP_ORIGIN = 'http://localhost:8915';
const MODULE_URL = `${APP_ORIGIN}/src/lib/money.ts`;

describe('isBootTransportFailure', () => {
  // THE measured case (hub#1806, run 34532770133): one network-configuration change on the runner
  // cancelled 79 in-flight requests to the dev server inside 33.7 ms, so the app's module graph
  // arrived half-loaded and Vue never mounted. The page was blank and `import-lead` was never in
  // the DOM. Nothing about the PR under test was involved.
  it('is true for a network change that killed a request for the app own code', () => {
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_NETWORK_CHANGED', APP_ORIGIN)).toBe(true);
  });

  // What the e2e reproduction (`BenchBootRecovery.spec.ts`) injects, because `route.abort()` has
  // no code for a network change. Same class, same code path.
  it('is true for a connection reset', () => {
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_CONNECTION_RESET', APP_ORIGIN)).toBe(true);
  });

  // 🔴 The exclusions are the point of this list. A reload that fires on ANY failed request is a
  // blanket retry, and a blanket retry is exactly the gate-that-lies this issue exists to remove:
  // it would turn a real defect into an intermittent green.
  it('is false when the page itself cancelled the request', () => {
    // Routine: a navigation away, an AbortController, an <img> removed mid-flight.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_ABORTED', APP_ORIGIN)).toBe(false);
  });

  it('is false when the browser blocked the request', () => {
    // A CSP violation is a defect of ours (root CLAUDE.md), never something to retry away.
    // `.Inspector` is not a typo: it is what this Chromium reports verbatim for a blocked request
    // (measured against the shipped binary), and the reason the list excludes by allow-list rather
    // than by a deny-list — a deny-list of exact spellings is a guard that misses by one suffix.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_BLOCKED_BY_CSP', APP_ORIGIN)).toBe(false);
    expect(
      isBootTransportFailure(MODULE_URL, 'net::ERR_BLOCKED_BY_CLIENT.Inspector', APP_ORIGIN),
    ).toBe(false);
  });

  it('is false for the generic failure the browser reports when it gives no reason', () => {
    // The code a careless widening of the list reaches for first, and the one
    // `BenchBootRecovery.spec.ts` injects to prove the reload does not fire.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_FAILED', APP_ORIGIN)).toBe(false);
  });

  it('is false when nothing is listening on the dev server', () => {
    // The bench failed to come up. Retrying only delays a failure that has to be loud and fast.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_CONNECTION_REFUSED', APP_ORIGIN)).toBe(false);
  });

  it('is false for a request that is not the app own code', () => {
    // Only the app's own origin counts: a third party dying is a fact about the product, and the
    // spec that cares must assert on it.
    expect(
      isBootTransportFailure('https://erplora.com/api/x', 'net::ERR_NETWORK_CHANGED', APP_ORIGIN),
    ).toBe(false);
  });

  it('is false when the browser reported no error text', () => {
    expect(isBootTransportFailure(MODULE_URL, undefined, APP_ORIGIN)).toBe(false);
  });

  it('is false when the bench has no origin to compare against', () => {
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_NETWORK_CHANGED', undefined)).toBe(false);
  });

  it('keeps the excused codes to transport failures that lose the connection', () => {
    // Pinned so that widening the list is a deliberate edit with a reason, not a drive-by.
    expect([...TRANSIENT_TRANSPORT_ERRORS].sort()).toEqual([
      'net::ERR_ADDRESS_UNREACHABLE',
      'net::ERR_CONNECTION_ABORTED',
      'net::ERR_CONNECTION_CLOSED',
      'net::ERR_CONNECTION_RESET',
      'net::ERR_EMPTY_RESPONSE',
      'net::ERR_INTERNET_DISCONNECTED',
      'net::ERR_NETWORK_CHANGED',
      'net::ERR_NETWORK_IO_SUSPENDED',
      'net::ERR_SOCKET_NOT_CONNECTED',
    ]);
  });
});

describe('BOOT_RELOAD_LIMIT', () => {
  // The budget is the only thing between this recovery and the blanket retry the whole file
  // argues against: every extra reload is one more re-roll of the dice on a REAL defect. The
  // excused-codes list above is pinned so that widening it has to be a deliberate edit with a
  // reason; the budget was not, and that asymmetry is ERPlora/hub#1838.
  //
  // Measured on develop@04f9a471 before this guard existed: with the budget moved to 5 and
  // nothing else touched, `BenchBootRecovery.spec.ts` stayed at `3 passed` and this file at
  // `87 passed`. The bench had quietly become a five-retry gate and the suite had nothing to say
  // about it. Raising it is allowed — deciding it here, in the open, is the point.
  it('spends at most two reloads, so a real defect is not re-rolled into green', () => {
    expect(BOOT_RELOAD_LIMIT).toBe(2);
  });
});

// The mechanical half of the guard (root CLAUDE.md: when the incident is a PATTERN, the fix
// includes the rule that stops it reappearing in ANY new file). The recovery only reaches a spec
// that takes `test` from the bench, so a spec that imports it straight from Playwright opts out of
// it in silence — which is how this would come back a third time in a spec nobody has written yet.
describe('every e2e spec takes its `test` from the bench', () => {
  const E2E_DIR = fileURLToPath(new URL('./e2e', import.meta.url));

  const specs = listE2eSpecs(E2E_DIR);

  it('finds the specs to check', () => {
    // Without this the loop below is vacuously green if the directory ever moves.
    expect(specs.length).toBeGreaterThanOrEqual(11);
  });

  // Regression test for ERPlora/hub#1816: `UsersCrudTestids.spec.ts` landed taking `test` straight
  // from Playwright 36 min before this guard did, so each PR was measured without seeing the other
  // and `develop` went red for everyone (ERPlora/hub#1818 is the same break seen from the queue,
  // where every PR turned red without touching `apps/web`). The named case below is the one that
  // would have caught it; the loop is what keeps it caught for files nobody has written yet.
  it('covers the spec that broke develop in hub#1816', () => {
    expect(specs).toContain('UsersCrudTestids.spec.ts');
  });

  it.each(specs)('%s does not import `test` from @playwright/test', (name) => {
    const source = readFileSync(join(E2E_DIR, name), 'utf8');
    expect(
      specTakesTestFromPlaywright(source),
      `${name} must take \`test\` from '../bench-boot'`,
    ).toBe(false);
  });
});

// Regression test for ERPlora/hub#1820. The guard above is only worth what its FILE LIST is worth,
// and the list was flat while Playwright's walk is recursive (`testDir: './e2e'` + the default
// `testMatch`). Measured on this branch before the fix: a spec at `tests/e2e/zz-mutant/` taking
// `test` straight from Playwright left the guard at `37 passed` while `playwright --list` reported
// `30 tests in 14 files` — it ran for real, outside the recovery, in silence.
//
// This is a `mkdtemp` rather than a real folder under `tests/e2e/` on purpose: a fixture spec left
// in the bench's own directory would be COLLECTED BY PLAYWRIGHT and run as a test.
describe('listE2eSpecs', () => {
  function withTempE2eDir<T>(body: (dir: string) => T): T {
    const dir = mkdtempSync(join(tmpdir(), 'erplora-e2e-list-'));
    try {
      return body(dir);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }

  it('finds a spec in a subdirectory, because Playwright runs it', () => {
    withTempE2eDir((dir) => {
      mkdirSync(join(dir, 'nested', 'deeper'), { recursive: true });
      writeFileSync(join(dir, 'Flat.spec.ts'), '');
      writeFileSync(join(dir, 'nested', 'Nested.spec.ts'), '');
      writeFileSync(join(dir, 'nested', 'deeper', 'Deeper.spec.ts'), '');

      expect(listE2eSpecs(dir)).toEqual([
        'Flat.spec.ts',
        join('nested', 'Nested.spec.ts'),
        join('nested', 'deeper', 'Deeper.spec.ts'),
      ]);
    });
  });

  it('returns paths that resolve against the directory it was given', () => {
    // The guard reads each entry back with `join(E2E_DIR, name)`. A listing of bare basenames
    // would make that path point at a file that does not exist, and the guard would blow up
    // instead of checking — so the relative shape is part of the contract, not an accident.
    withTempE2eDir((dir) => {
      mkdirSync(join(dir, 'nested'));
      writeFileSync(join(dir, 'nested', 'Nested.spec.ts'), 'import { test } from "@playwright/test";');

      const [name] = listE2eSpecs(dir);
      expect(specTakesTestFromPlaywright(readFileSync(join(dir, name), 'utf8'))).toBe(true);
    });
  });

  it('ignores helpers and anything that is not a spec', () => {
    withTempE2eDir((dir) => {
      mkdirSync(join(dir, 'nested'));
      writeFileSync(join(dir, 'Real.spec.ts'), '');
      writeFileSync(join(dir, 'shell-visual-helpers.ts'), '');
      writeFileSync(join(dir, 'notes.md'), '');
      writeFileSync(join(dir, 'nested', 'helper.ts'), '');
      // Near misses of the widened pattern below. Each one is a file Playwright does NOT collect,
      // so the guard must not claim it does either — a list that over-reaches would read a helper
      // as a spec and fail the build over an import it is entitled to have.
      writeFileSync(join(dir, 'Near.spect.ts'), '');
      writeFileSync(join(dir, 'Near.specs.ts'), '');
      writeFileSync(join(dir, 'Near.testing.ts'), '');
      writeFileSync(join(dir, 'Near.spec.ts.bak'), '');
      writeFileSync(join(dir, 'Near.spec.txt'), '');

      expect(listE2eSpecs(dir)).toEqual(['Real.spec.ts']);
    });
  });

  // ── ERPlora/hub#1824 ─────────────────────────────────────────────────────────────────────────
  //
  // The guard above is only worth what its file list is worth (same lesson as hub#1820, one field
  // over): the list matched `.spec.ts` and nothing else, while Playwright's default `testMatch` is
  // `**/*.@(spec|test).?(c|m)[jt]s?(x)` — TWENTY-FOUR endings, not one. Measured on this branch
  // before the fix: a `ZZMutant.test.ts` dropped under `tests/e2e/` taking `test` straight from
  // Playwright left this file at `41 passed` while `playwright --list` reported
  // `ZZMutant.test.ts:2:1 › x` in `30 tests in 14 files`. It ran for real, outside the boot
  // recovery, in silence — which is exactly the hole hub#1816 cost us, reopened by a file suffix.
  //
  // The list below is not derived from the glob: it is what @playwright/test 1.62.1 COLLECTED from
  // a directory holding one file per ending (`Total: 24 tests in 24 files`), with the near misses
  // in the case above left behind. Deriving it would only restate our own reading of the glob.
  const PLAYWRIGHT_SPEC_ENDINGS = [
    '.spec.js',
    '.spec.jsx',
    '.spec.cjs',
    '.spec.cjsx',
    '.spec.mjs',
    '.spec.mjsx',
    '.spec.ts',
    '.spec.tsx',
    '.spec.cts',
    '.spec.ctsx',
    '.spec.mts',
    '.spec.mtsx',
    '.test.js',
    '.test.jsx',
    '.test.cjs',
    '.test.cjsx',
    '.test.mjs',
    '.test.mjsx',
    '.test.ts',
    '.test.tsx',
    '.test.cts',
    '.test.ctsx',
    '.test.mts',
    '.test.mtsx',
  ];

  it('covers every ending Playwright collects, and only those', () => {
    // Without this, dropping an ending from the table above would quietly shrink the guard.
    // These are the canonical SPELLINGS of the 24; Playwright accepts any casing of them, which
    // is its own block further down.
    expect(PLAYWRIGHT_SPEC_ENDINGS).toHaveLength(24);
  });

  it.each(PLAYWRIGHT_SPEC_ENDINGS)('finds Spec%s, because Playwright runs it', (ending) => {
    withTempE2eDir((dir) => {
      writeFileSync(join(dir, `Spec${ending}`), '');

      expect(listE2eSpecs(dir)).toEqual([`Spec${ending}`]);
    });
  });

  it('finds a mis-named spec in a subdirectory too', () => {
    // The two holes compose: hub#1820 was the walk, this is the suffix. A `.test.ts` one folder
    // down is the file that slips through both at once.
    withTempE2eDir((dir) => {
      mkdirSync(join(dir, 'nested', 'deeper'), { recursive: true });
      writeFileSync(join(dir, 'nested', 'deeper', 'Deeper.test.ts'), '');

      expect(listE2eSpecs(dir)).toEqual([join('nested', 'deeper', 'Deeper.test.ts')]);
    });
  });

  // ── ERPlora/hub#1824, third field over ───────────────────────────────────────────────────────
  //
  // The endings above are the canonical SPELLINGS; Playwright does not require that spelling, and
  // it does not accept every other one either. `collectFilesForProject` (`playwright/lib/runner/
  // index.js`) puts a file through TWO gates that disagree about case:
  //
  //   1. `new Set(['.js','.ts','.mjs','.mts',…]).has(path.extname(file))` — a Set lookup, so the
  //      FINAL extension has to be lowercase, letter for letter;
  //   2. `minimatch(filePath, testMatch, { nocase: true, dot: true })` (`util.js`,
  //      `createFileMatcher`) — so the `spec`/`test` WORD is case-blind.
  //
  // Measured with @playwright/test 1.62.1 over one file per name, each in its own directory (a
  // Mac folds two names that differ only in case into one file, which would have tested nothing):
  // `Cased.Spec.ts`, `Cased.SPEC.ts`, `Cased.Test.tsx` and `Cased.tEsT.mts` came back in
  // `Total: 5 tests in 5 files`; `Shouty.spec.TS`, `Shouty.test.MTS`, `Shouty.Spec.Ts` and
  // `Shouty.spec.tS` did not come back at all.
  //
  // Both halves matter and in opposite directions. Missing the first half is the hub#1824 hole
  // over again — measured on this branch, a `ZZCase.Spec.ts` under `tests/e2e/` was listed by
  // `playwright --list` inside `Total: 30 tests in 14 files` while this suite stayed at
  // `77 passed`. Over-reaching on the second is the mirror: the guard would fail the build over a
  // `Shouty.spec.TS` that Playwright never runs, and the way that gets "fixed" is by deleting the
  // guard. `nocase` is minimatch's and not the filesystem's, so this is the behaviour on the
  // case-sensitive Linux of CI too, not a local curiosity.
  it.each([
    'Cased.Spec.ts',
    'Cased.SPEC.ts',
    'Cased.Test.tsx',
    'Cased.tEsT.mts',
  ])('finds %s, because Playwright matches the spec word case-blind', (name) => {
    withTempE2eDir((dir) => {
      writeFileSync(join(dir, name), '');

      expect(listE2eSpecs(dir)).toEqual([name]);
    });
  });

  it.each([
    'Shouty.spec.TS',
    'Shouty.test.MTS',
    'Shouty.Spec.Ts',
    'Shouty.spec.tS',
  ])('leaves %s alone, because Playwright checks the extension letter for letter', (name) => {
    withTempE2eDir((dir) => {
      writeFileSync(join(dir, name), '');

      expect(listE2eSpecs(dir)).toEqual([]);
    });
  });

  it('leaves the near misses behind when they are shouted, too', () => {
    // Going case-blind on the word must widen the CASE OF THE WORD and nothing else: `.SPEC.txt`
    // is no more a spec than `.spec.txt` is.
    withTempE2eDir((dir) => {
      writeFileSync(join(dir, 'Real.SPEC.ts'), '');
      writeFileSync(join(dir, 'Near.SPECT.ts'), '');
      writeFileSync(join(dir, 'Near.SPECS.ts'), '');
      writeFileSync(join(dir, 'Near.TESTING.ts'), '');
      writeFileSync(join(dir, 'Near.SPEC.txt'), '');

      expect(listE2eSpecs(dir)).toEqual(['Real.SPEC.ts']);
    });
  });
});

// The other half of ERPlora/hub#1824, and the one that keeps the half above honest.
//
// `listE2eSpecs` COPIES Playwright's default `testMatch`, and a copy is only true while the
// original does not move. `playwright.config.ts` leaves `testMatch` unset today, so the default
// rules; the day someone declares one — a `testMatch: '**/*.e2e.ts'` is a one-line change nobody
// would think to weigh against this file — the copy silently describes a set of files that is no
// longer the set Playwright runs, and the guard goes back to passing over specs it never read.
// That failure has no symptom: it is green.
//
// So the config is pinned. If this goes red, the fix is NOT to delete the check: it is to make
// `listE2eSpecs` follow the `testMatch` the config now declares.
describe('declaresTestMatch', () => {
  it.each([
    ['a top-level key', "export default defineConfig({ testDir: './e2e', testMatch: '**/*.e2e.ts' });"],
    ['a key on a project', "projects: [{ name: 'chromium', testMatch: /.*\\.e2e\\.ts/ }]"],
    // Legal JS, and the spelling a regex over `testMatch:` would miss by one character.
    ['a quoted key', 'export default defineConfig({ "testMatch": ["**/*.e2e.ts"] });'],
    ['a key with space before the colon', 'export default defineConfig({ testMatch : [] });'],
    // 🔴 The case that decides whether the reader is worth having. This config is full of URLs,
    // and a comment stripper that does not know it is inside a string treats the `//` of
    // `http://` as the start of a comment and drops THE REST OF THE LINE — including the
    // declaration. The guard would then report "no testMatch here" about a config that declares
    // one: a miss that reads exactly like a pass. Same class of mute parser bug as ERPlora/sales#291.
    [
      'a key sitting after a URL on the same line',
      "const url = 'http://127.0.0.1:1'; export default defineConfig({ testMatch: '**/*.e2e.ts' });",
    ],
  ])('is true when the config declares %s', (_, source) => {
    expect(declaresTestMatch(source)).toBe(true);
  });

  it.each([
    ['the config says nothing about it', "export default defineConfig({ testDir: './e2e' });"],
    // This very file, and `bench-boot.ts`, explain the default in prose. Prose is not a decision:
    // a guard that reads it as one cries wolf until someone deletes the guard.
    ['a line comment mentions it', "// leaves the default `testMatch`, which is recursive\nexport default {};"],
    ['a block comment mentions it', '/* testMatch is left at its default */\nexport default {};'],
    ['a comment mentions it after a URL', "const u = 'http://x'; // the default testMatch applies\nexport default {};"],
  ])('is false when %s', (_, source) => {
    expect(declaresTestMatch(source)).toBe(false);
  });

  it('the bench config leaves `testMatch` at its default, which is what listE2eSpecs copies', () => {
    const source = readFileSync(
      fileURLToPath(new URL('./playwright.config.ts', import.meta.url)),
      'utf8',
    );

    expect(
      declaresTestMatch(source),
      'playwright.config.ts now declares `testMatch`: make `listE2eSpecs` follow THAT pattern, ' +
        'because the default it copies is no longer what Playwright runs.',
    ).toBe(false);
  });
});

// The detector behind the directory guard above, as a decision table. Measured while reviewing
// hub#1815: with the check written as one regex over `import { … } from '@playwright/test'`, a
// spec written with double quotes — nothing in this package pins the quote style — or with
// Playwright's DEFAULT export (`import test from '@playwright/test'`, which IS `test`) passed the
// guard in green. That is the silent opt-out the guard exists to stop, so every way of reaching
// `test` is pinned here, one line each.
describe('specTakesTestFromPlaywright', () => {
  it.each([
    ['named import, single quotes', "import { test, expect } from '@playwright/test';"],
    ['named import, double quotes', 'import { test, expect } from "@playwright/test";'],
    ['named import, aliased', "import { test as base } from '@playwright/test';"],
    ['named import, multi-line', "import {\n  expect,\n  test,\n} from '@playwright/test';"],
    ['named import next to an inline type', "import { type Page, test } from '@playwright/test';"],
    ["the default export (Playwright's default export IS `test`)", "import test from '@playwright/test';"],
    ['the default export next to named ones', "import test, { expect } from '@playwright/test';"],
    ['a namespace import (`pw.test` is one dot away)', "import * as pw from '@playwright/test';"],
  ])('is true for %s', (_, source) => {
    expect(specTakesTestFromPlaywright(source)).toBe(true);
  });

  it.each([
    ['the bench', "import { test, expect } from '../bench-boot';"],
    ['a type-only import', "import type { Page } from '@playwright/test';"],
    ['inline type specifiers only', "import { type Page, type Locator } from '@playwright/test';"],
    ['`expect` alone', "import { expect } from '@playwright/test';"],
    [
      'a comment that quotes the forbidden line',
      "// never: import { test } from '@playwright/test'\nimport { test } from '../bench-boot';",
    ],
  ])('is false for %s', (_, source) => {
    expect(specTakesTestFromPlaywright(source)).toBe(false);
  });
});
