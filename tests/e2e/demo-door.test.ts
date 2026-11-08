// flow: ninguno — arnés e2e del Hub (hub#1048)
// A second pass of demo.spec.ts in the same hour waited 15 s for the demo's host and failed with
// «page.waitForURL: Timeout 15000ms exceeded»: the SaaS of the stack had answered «Try the demo» with its door's
// `?state=throttled` (3 new demos an hour per address, `DEMO_SPAWN_RATELIMIT`, and every pass starts two from
// 127.0.0.1). These keep the run saying why, and the README's recipes starting that SaaS with the limit raised.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { doorOutcome, E2E_DEMO_SPAWN_RATELIMIT, noDemoBecause } from './demo-door';

const HERE = dirname(fileURLToPath(import.meta.url));
const DOOR = 'http://localhost:30481/demo/';

/** The commands of the README's `bash` blocks, each one with its `\`-continued lines joined. */
function commandsOf(markdown: string): string[] {
  const blocks = [...markdown.matchAll(/^```bash\n([\s\S]*?)^```/gm)].map((match) => match[1] ?? '');
  return blocks.flatMap((block) => block.replace(/\\\n/g, ' ').split('\n'));
}

/** The README's commands that start the SaaS of a stack: a `runserver` with the return to its Hub
 *  (`HUB_CALLBACK_TEMPLATE`), which the Hub's own runserver never takes. */
function saasRunservers(markdown: string): string[] {
  return commandsOf(markdown).filter((command) => /manage\.py runserver\b/.test(command) && command.includes('HUB_CALLBACK_TEMPLATE='));
}

describe('doorOutcome(): where «Try the demo» lands when the SaaS opens no demo', () => {
  it('reads the outcome the door answered with', () => {
    expect(doorOutcome(`${DOOR}?state=throttled`, DOOR)).toBe('throttled');
    expect(doorOutcome(`${DOOR}?state=full`, DOOR)).toBe('full');
  });

  it('is null on the door without an outcome: a demo being prepared is waited for there', () => {
    expect(doorOutcome(DOOR, DOOR)).toBeNull();
    expect(doorOutcome(`${DOOR}?state=`, DOOR)).toBeNull();
  });

  it('is null on the demo and on any other page', () => {
    expect(doorOutcome('http://demo-0a1b2c3d.localhost:30480/auth/login?code=x&state=throttled', DOOR)).toBeNull();
    expect(doorOutcome('http://localhost:8001/demo/?state=throttled', DOOR)).toBeNull();
    expect(doorOutcome('http://localhost:30481/demo/start/?state=throttled', DOOR)).toBeNull();
  });
});

describe('noDemoBecause(): the failure of a run whose door refused the demo', () => {
  it('names the outcome', () => {
    expect(noDemoBecause('unavailable')).toContain('state=unavailable');
    expect(noDemoBecause('throttled')).toContain('state=throttled');
  });

  it('says, for throttled, the limit that refused it and how the SaaS is started instead', () => {
    const said = noDemoBecause('throttled');
    expect(said).toContain('DEMO_SPAWN_RATELIMIT');
    expect(said).toContain(`DEMO_SPAWN_RATELIMIT=${E2E_DEMO_SPAWN_RATELIMIT}`);
    expect(said).toContain('tests/e2e/README.md');
  });

  it('gives that advice for throttled only', () => {
    expect(noDemoBecause('unavailable')).not.toContain('DEMO_SPAWN_RATELIMIT');
  });
});

describe('the README starts the SaaS of a stack with its demo limit raised', () => {
  const readme = readFileSync(join(HERE, 'README.md'), 'utf8');

  it('finds the SaaS of each recipe (the general one, the assistant\'s and WhatsApp\'s)', () => {
    expect(saasRunservers(readme).length).toBeGreaterThanOrEqual(3);
  });

  it('every one sets DEMO_SPAWN_RATELIMIT to what the failure tells to set', () => {
    const without = saasRunservers(readme).filter((command) => !command.includes(`DEMO_SPAWN_RATELIMIT=${E2E_DEMO_SPAWN_RATELIMIT} `));
    expect(without).toEqual([]);
  });
});
