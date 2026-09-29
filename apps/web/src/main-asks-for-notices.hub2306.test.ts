// hub#2306 — the WIRING guard for the two asks of the notice permission.
//
// The behaviour lives in `lib/notification-permission.ts` (with its test); `main.ts` cannot be
// mounted in a unit test, so this reads the SOURCE to pin what only lives there: both asks (the
// print-host alta and the sign-in) pass the modules with a bell counter, and the sign-in one is
// really wired to the session. Without it, a device with no printer — the usual WhatsApp tablet —
// is never asked while somebody is in front of it, with every unit test still green.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

/** The source of ONE call: from `opening` (which ends in its `(`) to the parenthesis that closes it. */
function callOf(opening: string): string {
  const start = MAIN.indexOf(opening);
  expect(start).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = start + opening.length - 1; i < MAIN.length; i++) {
    if (MAIN[i] === '(') depth++;
    else if (MAIN[i] === ')' && --depth === 0) return MAIN.slice(start, i + 1);
  }
  throw new Error(`unbalanced call: ${opening}`);
}

describe('the notice permission is asked where somebody is in front of the device', () => {
  it('the print-host alta counts the modules with a bell counter', () => {
    expect(callOf('void bootPrintHost(')).toContain('bellModules: loadBellCounterModuleIds');
  });

  it('and so does the ask when somebody signs in, wired to the session', () => {
    const call = callOf('askWhenSomeoneSignsIn(');
    expect(call).toMatch(/askWhenSomeoneSignsIn\(\s*\(\) => isAuthed\.value/);
    expect(call).toContain('warnIfThereIsSomethingToTell');
    expect(call).toContain('bellModules: loadBellCounterModuleIds');
    expect(call).toContain('ask: () => askToWarn()');
  });

  it('the regions asserted are only those calls', () => {
    expect(callOf('void bootPrintHost(')).not.toContain('bootPrintComanda');
    expect(callOf('askWhenSomeoneSignsIn(')).not.toContain('setOnSessionExpired');
  });
});
