// @vitest-environment node
// What the WhatsApp e2e ask erplora.com's own Python (its WhatsApp seed, a plan of its own) is a cold process each
// time: a couple of seconds on a quiet machine, a minute or more on a loaded one (hub#848). That time is not the
// test's, so `inErplora` of whatsapp-helpers.ts gives the test or hook it runs in the time a cold start may take before
// starting it, and no spec or helper starts one of its own. And the e2e reads `a`'s WhatsApp channel as the Hub keeps it:
// the one row of `a`'s own database, whose business column the code leaves empty (hub#1424).
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { type TestInfo, test } from '@playwright/test';
import ts from 'typescript';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';

import { E2E_DIR, helpersAndSpecs } from './e2e-sources';
import { WORKER_START_TIMEOUT_MS } from './global-setup';
import { STACK } from './stack';
import { inErplora } from './whatsapp-helpers';

const ERPLORA = vi.hoisted(() => {
  const before = { dir: process.env.E2E_SAAS_DIR, db: process.env.E2E_SAAS_DB };
  process.env.E2E_SAAS_DIR = 'erplora-checkout';
  process.env.E2E_SAAS_DB = 'saas_e2e_checkout';
  return before;
});

vi.mock('node:child_process', async (original) => ({
  ...(await original<typeof import('node:child_process')>()),
  execFileSync: vi.fn(),
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(execFileSync).mockReset();
});

afterAll(() => {
  for (const [name, value] of [['E2E_SAAS_DIR', ERPLORA.dir], ['E2E_SAAS_DB', ERPLORA.db]] as const) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
});

/** A Playwright test or hook whose time is `timeout` ms, as `test.info()` tells it; `setTimeout` changes it. */
function inATestOf(timeout: number): { timeout: number } {
  const info = { timeout, setTimeout: (next: number) => void (info.timeout = next) };
  vi.spyOn(test, 'info').mockReturnValue(info as unknown as TestInfo);
  return info;
}

/** The test's time each process saw as it started, and what it printed: noise, then its one JSON line. */
function processesSee(info: { timeout: number }): number[] {
  const seen: number[] = [];
  vi.mocked(execFileSync).mockImplementation(() => {
    seen.push(info.timeout);
    return 'Seeded a and b.\n{"delivered": true, "hub_error": ""}\n';
  });
  return seen;
}

describe('inErplora, a cold Python process of erplora.com', () => {
  it('gives the test or hook it runs in the time of a cold start before starting it, once per process', () => {
    const info = inATestOf(180_000);
    const seen = processesSee(info);
    expect(inErplora(['tests/e2e/panel/whatsapp_hub_seed.py', 'id-a', 'id-b'])).toEqual({ delivered: true, hub_error: '' });
    inErplora(['manage.py', 'shell', '-c', 'print("{}")']);
    expect(seen).toEqual([180_000 + WORKER_START_TIMEOUT_MS, 180_000 + 2 * WORKER_START_TIMEOUT_MS]);
    expect(info.timeout).toBe(180_000 + 2 * WORKER_START_TIMEOUT_MS);
  });

  it('leaves a test or hook without a limit without one', () => {
    const info = inATestOf(0);
    const seen = processesSee(info);
    inErplora(['manage.py', 'shell', '-c', 'print("{}")']);
    expect(seen).toEqual([0]);
  });

  it("runs Python in erplora.com's checkout, on the run's database, with this Hub as its Hub", () => {
    processesSee(inATestOf(180_000));
    inErplora(['manage.py', 'shell', '-c', 'print("{}")'], { WA_LIMIT: '0' });
    expect(execFileSync).toHaveBeenCalledWith('uv', ['run', 'python', 'manage.py', 'shell', '-c', 'print("{}")'], {
      cwd: resolve('erplora-checkout'),
      encoding: 'utf8',
      env: expect.objectContaining({
        DEBUG: 'True',
        DB_NAME: 'saas_e2e_checkout',
        HUB_INTERNAL_URL: `http://127.0.0.1:${STACK.hubPort}`,
        WA_LIMIT: '0',
      }),
    });
  });
});

const STARTS_A_PROCESS = new Set(['execFileSync', 'execSync', 'spawnSync', 'spawn', 'execFile', 'exec']);

/** How many processes `source` starts in erplora.com's checkout: a `cwd` naming it (`SAAS_DIR`, `saasDir`…). */
function erploraProcesses(source: string): number {
  let count = 0;
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && STARTS_A_PROCESS.has(node.expression.text)) {
      const inErploraDir = node.arguments.some(
        (argument) =>
          ts.isObjectLiteralExpression(argument) &&
          argument.properties.some(
            (property) => ts.isPropertyAssignment(property) && property.name.getText() === 'cwd' && /saas/i.test(property.initializer.getText()),
          ),
      );
      if (inErploraDir) count += 1;
    }
    ts.forEachChild(node, visit);
  };
  visit(ts.createSourceFile('e2e.ts', source, ts.ScriptTarget.Latest, true));
  return count;
}

/** Where the e2e starts erplora.com's Python, and how many times: `inErplora` itself, and the relay of
 *  whatsapp-inbox-offered-options.spec.ts, which runs inside its test, which gives itself 600 s for its relays. */
const ERPLORA_PROCESSES: Record<string, number> = {
  'whatsapp-helpers.ts': 1,
  'whatsapp-inbox-offered-options.spec.ts': 1,
};

describe("the e2e starts erplora.com's Python through inErplora", () => {
  it('there are helpers and specs to look at, the shared helper and the spec of the plan among them', () => {
    expect(helpersAndSpecs()).toEqual(expect.arrayContaining(['whatsapp-helpers.ts', 'whatsapp-inbox-plan-cap.spec.ts', 'qa/assistant-battery.spec.ts']));
  });

  it('no spec or helper starts a process in erplora.com’s checkout of its own', () => {
    const own = Object.fromEntries(
      helpersAndSpecs()
        .map((name) => [name, erploraProcesses(readFileSync(join(E2E_DIR, name), 'utf8'))] as const)
        .filter(([, processes]) => processes > 0),
    );
    expect(own, "a preparation in erplora.com is inErplora(args, env) of whatsapp-helpers.ts: its cold start is not the test's time").toEqual(
      ERPLORA_PROCESSES,
    );
  });

  it('the check counts a process started in erplora.com’s checkout, and none elsewhere', () => {
    const inErploraDir = [
      "execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', SET_PLAN], { cwd: SAAS_DIR, encoding: 'utf8' });",
      "const out = execFileSync('uv', ['run', 'python', script], {\n  cwd: saasDir,\n  env: { ...process.env },\n});",
      "spawnSync('uv', ['run', 'python', 'manage.py', 'index_docs'], { cwd: join(REPO_DIR, 'saas') });",
    ];
    const elsewhere = [
      "execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RUN], { cwd: HUB_DIR, encoding: 'utf8' });",
      "inErplora(['manage.py', 'shell', '-c', SET_PLAN], { WA_LIMIT: '0' });",
      "execFileSync('docker', ['compose', 'exec'], { cwd: REPO_DIR, env: { DB_NAME: SAAS_DB } });",
    ];
    expect(inErploraDir.map(erploraProcesses)).toEqual([1, 1, 1]);
    expect(elsewhere.map(erploraProcesses)).toEqual([0, 0, 0]);
  });
});

/** The lines of `source` whose SQL picks the rows of an inbox table by the business column, `host`. */
const byBusinessColumn = (source: string): string[] =>
  source.split('\n').filter((line) => /whatsapp_inbox_\w+/.test(line) && /\b(?:\w+\.)?host\s*(?:=|in\b|is\b)/i.test(line));

describe("the e2e reads the inbox's tables as the Hub keeps them, without the business column", () => {
  it('no spec or helper picks the rows of an inbox table by its business column, which the code leaves empty', () => {
    const picking = helpersAndSpecs().flatMap((name) => byBusinessColumn(readFileSync(join(E2E_DIR, name), 'utf8')).map((line) => `${name}: ${line.trim()}`));
    expect(picking, "each business has its own database: psql() of helpers.ts already runs the statement in `a`'s").toEqual([]);
  });

  it('the check reads the shapes that picked by it, and the same statements without it as none', () => {
    const picking = [
      `allowance = Number(psql("select monthly_limit from whatsapp_inbox_channel where host = 'a'"));`,
      `"select coalesce(json_agg(c), '[]') as channel from whatsapp_inbox_channel c where c.host = 'a'",`,
      `"delete from whatsapp_inbox_channel where host = 'a'",`,
      `psql("select id from whatsapp_inbox_template where host in ('a', 'b')");`,
    ].join('\n');
    const without = [
      `allowance = Number(psql('select monthly_limit from whatsapp_inbox_channel'));`,
      `"select coalesce(json_agg(c), '[]') as channel from whatsapp_inbox_channel c",`,
      `psql("select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug")`,
      `psql("select host from base_membership where host = 'a'")`,
    ].join('\n');
    expect(byBusinessColumn(picking)).toHaveLength(4);
    expect(byBusinessColumn(without)).toEqual([]);
  });
});
