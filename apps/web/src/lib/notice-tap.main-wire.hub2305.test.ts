// hub#2305 — the wire in `main.ts`. `notice-tap.ts` and the three notices each pin their half
// (which id leads where, which screen each notice names); what only `main.ts` can break is the
// cable between them: a notice that goes back to `peripherals.notify` loses its destination, one
// that drops the `path` it is handed sends it nowhere, and a door nobody listens to never opens.
// `main.ts` is the shell's boot and cannot be mounted in a unit test
// (main-asks-for-notices.hub1732.test.ts), so the wire is read from the source, scoped per call.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

const MAIN = readFileSync(fileURLToPath(new URL('../main.ts', import.meta.url)), 'utf8');

function callOf(start: string): string {
  const from = MAIN.indexOf(start);
  expect(from, `${start} is not in main.ts`).toBeGreaterThan(-1);
  const end = MAIN.indexOf('\n});', from);
  expect(end).toBeGreaterThan(from);
  return MAIN.slice(from, end);
}

const NOTICES = ['bootPrintComanda(getClient()', 'bootAppointmentNotices(getClient()', 'bootBellNotices({'];

describe('main.ts wires every system notice to the screen it is about (hub#2305)', () => {
  for (const start of NOTICES) {
    it(`${start} sends through the door that remembers the screen, with the path it is handed`, () => {
      const call = callOf(start);
      expect(call).toContain('notify: async (title, body, path) => {');
      expect(call).toContain('await notices.notify(title, body, path);');
      expect(call).not.toContain('peripherals.notify(');
      // The permission gate stays in front of every notice (hub#1732).
      expect(call).toContain('if (!shouldSendNotice(await askToWarn())) return;');
    });
  }

  it('the door sends through the id-carrying notice and follows a tap with the router', () => {
    const door = callOf('const notices = createNoticeDoor({');
    expect(door).toContain('send: sendSystemNotice,');
    expect(door).toMatch(/navigate: \(path\) => router\.push\(path\),/);
    expect(door).toMatch(/firstId: /);
  });

  // The seed is where this session's ids start. The plugin holds an `i32` and the shell drops an id
  // out of range (the notice goes out, its tap leads nowhere), so a seed in milliseconds would lose
  // every destination with the rest of the suite green; and a fixed seed would hand a new session
  // the ids of notices still sitting in the tray, so their taps would open the wrong screen.
  it('the ids start from the clock, inside what the plugin can hold', () => {
    const seed = /firstId: (.+),$/m.exec(callOf('const notices = createNoticeDoor({'))?.[1];
    expect(seed, 'firstId is not a one-line expression').toBeDefined();
    const seedAt = (ms: number): unknown => {
      vi.setSystemTime(ms);
      return new Function(`return (${seed});`)();
    };
    vi.useFakeTimers();
    try {
      // Room for the ids a long session hands out after the seed.
      const MAX_SEED = 2 ** 31 - 1 - 10_000_000;
      for (const at of [Date.UTC(2026, 8, 28, 9), Date.UTC(2038, 0, 19, 4), Date.UTC(2100, 0, 1)]) {
        const id = seedAt(at);
        expect(Number.isInteger(id), `seed at ${new Date(at).toISOString()}: ${String(id)}`).toBe(true);
        expect(id as number).toBeGreaterThanOrEqual(0);
        expect(id as number).toBeLessThanOrEqual(MAX_SEED);
      }
      const start = Date.UTC(2026, 8, 28, 9);
      expect(seedAt(start + 60_000)).not.toBe(seedAt(start));
    } finally {
      vi.useRealTimers();
    }
  });

  it('the taps of the notification plugin reach the door', () => {
    expect(MAIN).toContain(
      "void listenForNoticeTaps(notices, (cb) => listenTauriPlugin('notification', 'actionPerformed', cb));",
    );
  });
});
