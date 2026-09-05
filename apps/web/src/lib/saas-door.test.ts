// pm#196 — the ONE door out to erplora.com, shared by every link that lands on a page the SaaS
// only shows to a signed-in person.
//
// The mechanism arrived with hub#1400 and it was wired to exactly one caller ("manage your
// business"), which left the issue's own headline half-answered: the plan page and the fiscal
// representation grant still dropped the owner on a login form, inside the installed app, right
// when she was trying to pay. Same trip, same cookie jar, same second factor. So the pass is not a
// detail of the management link: it is how this app leaves for the SaaS.
//
// What is pinned here:
//   - The door SPENDS the pass — it opens the one-time address, not the plain URL.
//   - It DEGRADES instead of dying: no pass, no answer, an exception — the plain link still opens,
//     which is exactly the behaviour from before this issue, so trying is never worse than not.
//   - Degrading is never SILENT. A failure nobody sees is a failure nobody fixes.
//   - The runtime is asked with a PATH, never a full URL: the address is built by the side that
//     knows where the SaaS is. A page that could choose the host would be choosing where the pass
//     gets spent.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { runtimeBrowserHandoff } = vi.hoisted(() => ({
  runtimeBrowserHandoff: vi.fn(async () => 'https://erplora.com/auth/handoff/code-abc/?next=%2Fx'),
}));
vi.mock('./cloud', () => ({ runtimeBrowserHandoff }));

const { reportClientError } = vi.hoisted(() => ({ reportClientError: vi.fn() }));
vi.mock('./error-report', () => ({ reportClientError }));

import { saasDoor } from './saas-door';

const FALLBACK = 'https://erplora.com/dashboard/hubs/hub-1/change-plan/?utm_source=hub';
const PATH = '/dashboard/hubs/hub-1/change-plan/?utm_source=hub';

beforeEach(() => {
  runtimeBrowserHandoff.mockClear();
  runtimeBrowserHandoff.mockResolvedValue('https://erplora.com/auth/handoff/code-abc/?next=%2Fx');
  reportClientError.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('saasDoor', () => {
  it('opens the one-time address when the runtime mints a pass', async () => {
    expect(await saasDoor(PATH, FALLBACK, 'upgrade-plan')).toBe(
      'https://erplora.com/auth/handoff/code-abc/?next=%2Fx',
    );
  });

  it('asks the runtime with the PATH, so the address is built where the SaaS is known', async () => {
    await saasDoor(PATH, FALLBACK, 'upgrade-plan');

    expect(runtimeBrowserHandoff).toHaveBeenCalledWith(PATH);
  });

  it('falls back to the plain link when the runtime refuses the pass', async () => {
    // The refusals are the point of the lock (hub#1400): a PIN session, a role without
    // `hub.administer`, a JWT naming somebody else. None of them may turn the button dead — the
    // person just arrives at the SaaS the way they did before this issue existed.
    runtimeBrowserHandoff.mockRejectedValue(new Error('handoff_requires_cloud_login'));

    expect(await saasDoor(PATH, FALLBACK, 'upgrade-plan')).toBe(FALLBACK);
  });

  it('falls back when the runtime answers without an address', async () => {
    runtimeBrowserHandoff.mockResolvedValue('');

    expect(await saasDoor(PATH, FALLBACK, 'upgrade-plan')).toBe(FALLBACK);
  });

  it('says WHY it degraded, and which door it was', async () => {
    // Naming the door matters: four callers share this code, and "handoff failed" with no subject
    // cannot be acted on. The failure that is not reported is the one that stays broken.
    runtimeBrowserHandoff.mockRejectedValue(new Error('handoff_requires_administer'));

    await saasDoor(PATH, FALLBACK, 'upgrade-plan');

    expect(reportClientError).toHaveBeenCalledTimes(1);
    const reported = reportClientError.mock.calls[0][0] as { message: string; component: string };
    expect(reported.message).toContain('upgrade-plan');
    expect(reported.message).toContain('handoff_requires_administer');
    expect(reported.component).toBe('saas-door');
  });

  it('does not report anything when the pass was minted', async () => {
    await saasDoor(PATH, FALLBACK, 'upgrade-plan');

    expect(reportClientError).not.toHaveBeenCalled();
  });
});
