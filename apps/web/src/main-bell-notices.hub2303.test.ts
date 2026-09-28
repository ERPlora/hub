// hub#2303 — the WIRING guard of the bell's system notice.
//
// `main.ts` cannot be mounted in a unit test (see `main-asks-for-notices.hub1732.test.ts`), so this
// reads the SOURCE of the one call. The behaviour is pinned in `lib/bell-notice.hub2303.test.ts`;
// what this catches is the wire losing the permission gate (Android's bare dialog in the middle of
// a service, hub#1732), losing the exclusion of the appointments that already notify on their own
// (a WhatsApp booking ringing twice), or being deleted while every unit test stays green.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

function bellNoticesCall(source: string): string {
  const start = source.indexOf('bootBellNotices({');
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf('\n});', start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe('the shell sends a system notice when a bell counter goes up', () => {
  it('goes through the permission gate and the same notify as the kitchen and the appointments', () => {
    const call = bellNoticesCall(MAIN);
    expect(call).toMatch(/if \(!shouldSendNotice\(await askToWarn\(\)\)\) return;/);
    // Since hub#2305 the shared door is the one that remembers where a tap leads.
    expect(call).toContain('await notices.notify(title, body, path);');
    expect(call).not.toContain('peripherals.notify(');
  });

  it('leaves out the module whose bookings the shell already announces', () => {
    expect(bellNoticesCall(MAIN)).toMatch(/ownNotice: new Set\(\[APPOINTMENT_NOTICE_MODULE\]\)/);
  });

  it('passes the params to i18n, not only the key', () => {
    expect(bellNoticesCall(MAIN)).toContain('i18n.global.t(key, params)');
  });

  it('and the region that is asserted really is only that call', () => {
    expect(MAIN).toContain('setOnSessionExpired');
    expect(bellNoticesCall(MAIN)).not.toContain('setOnSessionExpired');
  });
});
