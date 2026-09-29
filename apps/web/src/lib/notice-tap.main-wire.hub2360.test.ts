// hub#2360 — the wire in `main.ts` for the taps the shell KEEPS: a click on the computer and a tap
// that had to start the app on Android. `notice-tap.ts` pins how a kept tap is claimed; what only
// `main.ts` can break is the cable — the command that hands the tap over and the event that says
// one is waiting. `main.ts` cannot be mounted in a unit test (main-asks-for-notices.hub1732), so the
// wire is read from the source, and both names are the ones the shell's own test pins
// (`apps/tauri/src-tauri/tests/notice_tap.rs`).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const MAIN = readFileSync(fileURLToPath(new URL('../main.ts', import.meta.url)), 'utf8');

describe('main.ts claims the tap the shell kept (hub#2360)', () => {
  it('claims through the shell command and again on every poke of the shell event', () => {
    const from = MAIN.indexOf('void claimNoticeTaps(notices, {');
    expect(from, 'main.ts does not claim the taps the shell keeps').toBeGreaterThan(-1);
    const call = MAIN.slice(from, MAIN.indexOf('\n});', from));
    expect(call).toContain("take: () => invokeTauri('erplora_take_notice_tap'),");
    expect(call).toContain("onPoke: (cb) => listenTauriEvent('erplora://notice-tapped', cb),");
  });

  it('claims AFTER the door exists, so a claimed tap has somewhere to go', () => {
    expect(MAIN.indexOf('void claimNoticeTaps(notices, {')).toBeGreaterThan(
      MAIN.indexOf('const notices = createNoticeDoor({'),
    );
  });
});
