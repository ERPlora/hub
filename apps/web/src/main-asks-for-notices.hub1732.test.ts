// hub#1732 — the WIRING guard, because the machinery being right is not what failed.
//
// `PermissionPolicy` listed the permission, both manifests declared it, the plugin could ask for
// it in a scope, and `peripherals.notify()` did ask. Everything was in place except a caller that
// runs in a real day: the only one was the kitchen-order path, so a clean install used for 40
// minutes was never asked, and `dumpsys` showed the permission with no `USER_SET` flag.
//
// `main.ts` is the shell's boot and cannot be mounted in a unit test — it opens sockets, registers
// the service worker and mounts the app. So this reads the SOURCE, which is the only way to pin a
// wire that lives there. It is a weak assertion on purpose: it proves the two calls are present,
// not that they behave. The behaviour is pinned by `lib/notification-permission.test.ts` and
// `lib/print-host.notification-primer.hub1732.test.ts`; what THIS catches is somebody deleting the
// wire while every one of those stays green — which is precisely the shape of the original defect.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

/**
 * The `bootPrintComanda(...)` call ALONE.
 *
 * Scoping matters more than it looks: asserting `shouldSendNotice` against the whole file passes
 * on the IMPORT line, so reverting the notice back to a bare `peripherals.notify()` — the exact
 * regression this file exists to stop — left the guard green. Measured: that mutant survived.
 */
function comandaCall(source: string): string {
  const start = source.indexOf('bootPrintComanda(getClient()');
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf('\n});', start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe('the shell asks for the notification permission', () => {
  it('asks when this device is registered as a print host', () => {
    // The alta is the in-context moment: the device just became the one that gets told an order
    // came in, and somebody is standing at it.
    expect(MAIN).toMatch(/bootPrintHost\([\s\S]*?onRegistered/);
  });

  it('puts our explanation in front of the notice, and never Android’s dialog alone', () => {
    // The comanda notice is the fallback trigger for a device that never registers as a host (a
    // KDS screen with no printer). `ensureNotificationPermission` is idempotent, so this costs one
    // storage read once the answer is on record.
    //
    // Asserted INSIDE the call, not against the file: an unused import would satisfy the file.
    expect(comandaCall(MAIN)).toContain('shouldSendNotice');
    expect(MAIN).toContain('ensureNotificationPermission');
    expect(MAIN).toContain('primerLabelsFrom');
  });

  it('and the region that is asserted really is only that call', () => {
    // The positive control of the scoping above, placed AFTER the region: a slice that ran to the
    // end of the file would swallow this and quietly turn the assertion back into a file-wide one.
    expect(MAIN).toContain('setOnSessionExpired');
    expect(comandaCall(MAIN)).not.toContain('setOnSessionExpired');
  });

  it('never hardcodes the sheet: the strings come through i18n (ADR-0055/0199)', () => {
    expect(MAIN).not.toMatch(/Turn on notices|Activar los avisos/);
  });
});
