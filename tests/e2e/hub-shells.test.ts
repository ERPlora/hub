// flow: hub-e2e-tenancy — hub#593: reservation-whatsapp.spec.ts played the worker's relay with a `manage.py shell` that
// named no business, so it looked for the event in control's database and every viewport fell with
// `OutboxEvent.DoesNotExist`, for a reason that was not the flow. Since each business has its own database, a
// shell without `--hub` works on control (base/management/commands/shell.py): this keeps that from being an oversight.
// A call without `--hub` has to be listed here with what it works on, exactly as many times as the file makes it.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The calls that rightly name no business: the SaaS's own shell has none, and control's registry lives in no hub. */
const WITHOUT_A_HUB: Record<string, { calls: number; on: string }> = {
  'assistant-battery.ts': { calls: 2, on: "the SaaS's providers and accounts" },
  'assistant-probes.ts': { calls: 1, on: "the SaaS's accounts" },
  'base-recover-from-copy.spec.ts': {
    calls: 1,
    on: "control's registry: the separate copy, the staff member's session and the worker's recovery pass (its cards, products and services, with --hub a)",
  },
  'base-recoveries-long-result.spec.ts': {
    calls: 1,
    on: "control's registry: a separate copy of a with its failed recovery, and the staff member's session",
  },
  'fix-hub-csp-whatsapp-media-gate.spec.ts': { calls: 1, on: "control's registry of hubs" },
  'whatsapp-inbox-offered-options.spec.ts': { calls: 1, on: "the SaaS's WhatsApp number" },
  'whatsapp-inbox-plan-cap.spec.ts': { calls: 1, on: "the SaaS's plan of the business" },
};

/** `source` without its comment lines, which talk about these calls without making them. Line by line, never by matching
 *  a block's two ends: an opening inside a line comment or a string (a glob, a door's path) would take the code after it
 *  along, up to the next block's end, and a call there would go unseen. A comment read as code only asks for a listing. */
function code(source: string): string {
  return source
    .split('\n')
    .filter((line) => !/^\s*(\/\/|\/\*|\*)/.test(line))
    .join('\n');
}

/** The `manage.py shell` calls of `source` that name no business, as arguments (`'manage.py', 'shell'`), as a command, or
 *  as the arguments `managePy` of global-setup.ts runs `manage.py` with (`(['shell', '-c', code])`). */
function shellsWithoutHub(source: string): number {
  const asked =
    /manage\.py(?:['"`]\s*,\s*['"`]|\s+)shell\b(?!['"`]\s*,\s*['"`]--hub\b|\s+--hub\b)|\[\s*['"`]shell['"`](?!\s*,\s*['"`]--hub\b)/g;
  return code(source).match(asked)?.length ?? 0;
}

/** The specs and helpers of the e2e, its subfolders' too (`qa/`, whose specs Playwright runs as well), not Vitest's own
 *  tests, and their text (a subfolder's by its path, `qa/…`), read once while Vitest collects this file, like
 *  raw-screenshots.test.ts: reading ~290 files inside a test can pass Vitest's 5 s with the machine loaded. */
const E2E_SOURCES: ReadonlyArray<[string, string]> = readdirSync(E2E_DIR, { recursive: true, encoding: 'utf8' })
  .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts'))
  .map((name) => [name, readFileSync(join(E2E_DIR, name), 'utf8')]);

function callsByFile(): Record<string, number> {
  const found: Record<string, number> = {};
  for (const [name, source] of E2E_SOURCES) {
    const calls = shellsWithoutHub(source);
    if (calls > 0) found[name] = calls;
  }
  return found;
}

describe('a `manage.py shell` of the e2e names its business', () => {
  it('no spec or helper runs one without --hub, but those listed with what they work on', () => {
    const over = Object.entries(callsByFile())
      .filter(([name, calls]) => calls > (WITHOUT_A_HUB[name]?.calls ?? 0))
      .map(([name, calls]) => `${name}: ${calls} manage.py shell without --hub, ${WITHOUT_A_HUB[name]?.calls ?? 0} allowed`);
    expect(over).toEqual([]);
  });

  it('the list holds only what is still there: a call that went away leaves it', () => {
    const found = callsByFile();
    const stale = Object.entries(WITHOUT_A_HUB)
      .filter(([name, { calls }]) => (found[name] ?? 0) !== calls)
      .map(([name, { calls }]) => `${name}: ${found[name] ?? 0} found, the list says ${calls}`);
    expect(stale).toEqual([]);
  });

  it('the count sees both ways of writing the call, and not one that names its business or a comment about it', () => {
    expect(shellsWithoutHub("execFile('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY]);")).toBe(1);
    expect(shellsWithoutHub('execSync(`uv run python manage.py shell -c "${code}"`);')).toBe(1);
    expect(shellsWithoutHub("execFile('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY]);")).toBe(0);
    expect(shellsWithoutHub('execSync(`uv run python manage.py shell --hub a -c "${code}"`);')).toBe(0);
    expect(shellsWithoutHub('// a one-shot `manage.py shell` of its own\n/** `manage.py shell -c` in the SaaS */\n/**\n * manage.py shell\n */')).toBe(0);
  });

  it('the count sees a shell asked through managePy (global-setup.ts), and not one that names its business', () => {
    expect(shellsWithoutHub("managePy(STACK.database)(['shell', '-c', code]);")).toBe(1);
    expect(shellsWithoutHub("const manage = managePy(db);\nmanage([\n  'shell',\n  '-c',\n  code,\n]);")).toBe(1);
    expect(shellsWithoutHub("managePy(STACK.database)(['shell', '--hub', 'a', '-c', code]);")).toBe(0);
    expect(shellsWithoutHub("managePy(STACK.database)(['migrate', '--check']);")).toBe(0);
  });

  it('a `/*` in a line comment or a string hides no call after it', () => {
    const call = "execFile('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY]);";
    expect(shellsWithoutHub(`// the doors (\`/internal/whatsapp/*\`)\n${call}\n/** the next doc */`)).toBe(1);
    expect(shellsWithoutHub(`page.route('**/*.png', abort);\n${call}\n/** the next doc */`)).toBe(1);
  });

  it('reads the specs of the subfolders too', () => {
    expect(E2E_SOURCES.map(([name]) => name)).toContain(join('qa', 'assistant-probes.spec.ts'));
  });
});
