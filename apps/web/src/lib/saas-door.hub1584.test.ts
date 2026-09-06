// @vitest-environment happy-dom
// hub#1584 — **the till changes hands while the pass to erplora.com is in flight.**
//
// `saasDoor` asks the runtime for a one-time address and, when it arrives, opens it. The runtime
// mints that pass from the headers of whoever ASKED (`runtimeHeaders()` reads the session per
// call), which is right — the wrong part is that the door spends it whenever it arrives, without
// looking at whether the device is still in the same hands.
//
// The window is short (the round trip to the runtime, a few tenths of a second) and it takes a PIN
// takeover landing exactly inside it, so it is not something that happens by accident. But when it
// does, the system browser opens on the previous person's erplora.com account: her e-mail, her
// password, her second factor, the invoices of the business — handed to somebody who typed no
// credential of her own. Four links share this code (`upgrade-plan`, `management`,
// `representation-grant`, `cloud-account`), so the hole is one hole, in one place.
//
// What is pinned here:
//   - a pass that comes back to a DIFFERENT session is not spent: the plain link opens instead,
//     and the plain link asks for credentials — which is exactly what the person who just took
//     over should meet;
//   - a pass that comes back to the SAME session IS spent. The guard must not degrade into "never
//     open the pass", which would quietly undo hub#1400 and put the owner back on a login form;
//   - the refusal is not silent, and it names the door: four callers share this code.
//
// The session module is deliberately REAL, not a `vi.fn()`. Whose session this is, is a statement
// about the very box `switchUser` writes into (`setHubSession`, `lib/user-switch.ts`); a stub
// standing in for it could only say that a call happened, and would keep agreeing with the code no
// matter which storage the door ended up reading.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { runtimeBrowserHandoff } = vi.hoisted(() => ({
  runtimeBrowserHandoff: vi.fn(async () => PASS),
}));
vi.mock('./cloud', () => ({ runtimeBrowserHandoff }));

const { reportClientError } = vi.hoisted(() => ({ reportClientError: vi.fn() }));
vi.mock('./error-report', () => ({ reportClientError }));

// Adopting a session makes `setHubSession` reach for these two through a dynamic import (the media
// cookie of hub#791 and the SDK's active-module set of hub#1211). Neither has anything to do with
// the door; left alone they fire requests at a runtime that is not running.
vi.mock('./runtime', () => ({
  ensureMediaCookie: vi.fn(async () => {}),
  refreshActiveModuleIds: vi.fn(async () => {}),
}));

import { saasDoor } from './saas-door';
import { setHubSession } from './session';

const PASS = 'https://erplora.com/auth/handoff/code-abc/?next=%2Fx';
const FALLBACK = 'https://erplora.com/dashboard/hubs/hub-1/change-plan/?utm_source=hub';
const PATH = '/dashboard/hubs/hub-1/change-plan/?utm_source=hub';

/** A pass the test hands over on demand, so the takeover really lands mid-flight. */
function passInFlight(): { arrives: (url?: string) => void } {
  let resolve!: (url: string) => void;
  runtimeBrowserHandoff.mockImplementation(
    () =>
      new Promise<string>((r) => {
        resolve = r;
      }),
  );
  return { arrives: (url = PASS) => resolve(url) };
}

beforeEach(() => {
  localStorage.clear();
  runtimeBrowserHandoff.mockReset();
  runtimeBrowserHandoff.mockResolvedValue(PASS);
  reportClientError.mockClear();
  // Marta is signed in with her erplora.com password: the one session the pass is minted for.
  setHubSession('sess-marta', 'cloud');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('saasDoor across a change of hands (hub#1584)', () => {
  it('does not spend a pass that comes back to somebody else', async () => {
    const flight = passInFlight();
    const opening = saasDoor(PATH, FALLBACK, 'upgrade-plan');

    // Lucía takes the till over with her PIN while the runtime is still minting Marta's pass.
    setHubSession('sess-lucia', 'pin');
    flight.arrives();

    expect(await opening).toBe(FALLBACK);
  });

  it('spends the pass when the same person is still there', async () => {
    // The other half of the guard, and the reason it cannot simply be «never open the pass»: with
    // nobody taking over, hub#1400 must still carry the session into the browser.
    const flight = passInFlight();
    const opening = saasDoor(PATH, FALLBACK, 'upgrade-plan');

    flight.arrives();

    expect(await opening).toBe(PASS);
  });

  it('does not spend it either when the session was closed mid-flight', async () => {
    const flight = passInFlight();
    const opening = saasDoor(PATH, FALLBACK, 'management');

    setHubSession(null);
    flight.arrives();

    expect(await opening).toBe(FALLBACK);
  });

  it('says out loud that it dropped the pass, and for which door', async () => {
    const flight = passInFlight();
    const opening = saasDoor(PATH, FALLBACK, 'representation-grant');

    setHubSession('sess-lucia', 'pin');
    flight.arrives();
    await opening;

    expect(reportClientError).toHaveBeenCalledTimes(1);
    const reported = reportClientError.mock.calls[0][0] as { message: string; component: string };
    // On the stable code, never on the prose around it (ADR-0055).
    expect(reported.message).toContain('handoff_session_changed');
    expect(reported.message).toContain('representation-grant');
    expect(reported.component).toBe('saas-door');
  });

  it('reports nothing when the pass is spent by the session that asked for it', async () => {
    await saasDoor(PATH, FALLBACK, 'cloud-account');

    expect(reportClientError).not.toHaveBeenCalled();
  });
});
