// hub#2305 — the wire in `main.ts`. `notice-tap.ts` and the three notices each pin their half
// (which id leads where, which screen each notice names); what only `main.ts` can break is the
// cable between them: a notice that goes back to `peripherals.notify` loses its destination, one
// that drops the `path` it is handed sends it nowhere, and a door nobody listens to never opens.
// `main.ts` is the shell's boot and cannot be mounted in a unit test
// (main-asks-for-notices.hub1732.test.ts), so the wire is read from the source, scoped per call.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

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

  it('the taps of the notification plugin reach the door', () => {
    expect(MAIN).toContain(
      "void listenForNoticeTaps(notices, (cb) => listenTauriPlugin('notification', 'actionPerformed', cb));",
    );
  });
});
