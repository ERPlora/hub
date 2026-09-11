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

      expect(listE2eSpecs(dir)).toEqual(['Real.spec.ts']);
    });
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
