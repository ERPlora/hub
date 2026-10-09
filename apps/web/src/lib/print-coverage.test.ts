// **The owner can finally SEE that nobody is printing the kitchen's tickets** (hub#800).
//
// The whole observation mechanism was built end to end — `GET /api/print/hosts` returns, per
// printer role, how much work is waiting and how many live hosts drain it — and no screen ever
// read it. A coverage failure does not look like a failure: the sale closes with a 200 and the
// paper just never comes out, in another room. This lib is the read model the Settings screen
// paints.
//
// The classification these tests pin down is the issue's own "when does it shout" decision:
//
//   - a role NEVER used does not appear in the API's answer at all (no host row, no pending job),
//     so a salon without a kitchen is never nagged about kitchen tickets;
//   - a role with a live host is reassurance, not noise ("the kitchen is ready");
//   - a role with waiting work and no live host is THE alarm — tickets are piling up and no
//     device is taking them out;
//   - a role with no live host and nothing waiting can only appear because a host WAS registered
//     and stopped reporting — coverage that existed and was lost, which is an incident, but a
//     softer one than work already piling up.
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  classifyRole,
  coverageRows,
  fetchPrintHosts,
  type PrintHostEntry,
  type PrintRoleCoverage,
} from './print-coverage';

const host = (over: Partial<PrintHostEntry> = {}): PrintHostEntry => ({
  deviceId: 'dev-1',
  name: '',
  role: 'kitchen',
  label: 'Kitchen tablet',
  live: true,
  ...over,
});

const cov = (over: Partial<PrintRoleCoverage> = {}): PrintRoleCoverage => ({
  role: 'kitchen',
  waiting: 0,
  liveHosts: 0,
  ...over,
});

describe('classifyRole — the three states a role can be in', () => {
  it('a live host is "ready", even with work in flight (somebody is draining it)', () => {
    expect(classifyRole(cov({ liveHosts: 1, waiting: 0 }))).toBe('ready');
    expect(classifyRole(cov({ liveHosts: 2, waiting: 5 }))).toBe('ready');
  });

  it('waiting work and no live host is "stalled" — the alarm the issue is about', () => {
    expect(classifyRole(cov({ liveHosts: 0, waiting: 3 }))).toBe('stalled');
  });

  it('no live host and nothing waiting is "unattended": a host existed and stopped reporting', () => {
    // The API only returns a role that has EITHER a registered host row OR pending work, so
    // liveHosts=0 & waiting=0 can only mean a registered host that is no longer live.
    expect(classifyRole(cov({ liveHosts: 0, waiting: 0 }))).toBe('unattended');
  });
});

describe('coverageRows — what the screen paints, worst first', () => {
  it('joins each role with the labels of its LIVE hosts only', () => {
    const rows = coverageRows(
      [cov({ role: 'kitchen', liveHosts: 1 })],
      [
        host({ deviceId: 'a', label: 'Kitchen tablet', live: true }),
        host({ deviceId: 'b', label: 'Old till', live: false }),
        host({ deviceId: 'c', role: 'receipt', label: 'Counter till', live: true }),
      ],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]!.hosts).toEqual(['Kitchen tablet']);
  });

  it('falls back to the device id when a host has no label', () => {
    const rows = coverageRows(
      [cov({ liveHosts: 1 })],
      [host({ deviceId: 'till-9', label: '', live: true })],
    );
    expect(rows[0]!.hosts).toEqual(['till-9']);
  });

  // hub#2551: the device id is the proof of a trusted device. A cashier's read carries no
  // `deviceId` for other devices, and the hub names a nameless host by the tail of its id.
  it('hub2551: names a nameless host by the name the hub gives, never by its device id', () => {
    const rows = coverageRows(
      [cov({ liveHosts: 2 })],
      [
        // An administrator's read: the id is there, and still not what the screen paints.
        host({ deviceId: 'dev_3f9c2b1c4d5e6f708192a3b4c5d6e7f8', name: '…e7f8', label: '' }),
        // A cashier's read: no id at all, and the row is never blank.
        host({ deviceId: '', name: '…e8f9', label: '' }),
      ],
    );
    expect(rows[0]!.hosts).toEqual(['…e7f8', '…e8f9']);
  });

  it('orders the alarm first, then lost coverage, then reassurance', () => {
    const rows = coverageRows(
      [
        cov({ role: 'receipt', liveHosts: 1 }),
        cov({ role: 'bar', liveHosts: 0, waiting: 0 }),
        cov({ role: 'kitchen', liveHosts: 0, waiting: 4 }),
      ],
      [],
    );
    expect(rows.map((r) => r.role)).toEqual(['kitchen', 'bar', 'receipt']);
    expect(rows.map((r) => r.status)).toEqual(['stalled', 'unattended', 'ready']);
  });

  it('keeps the API order (alphabetical) within the same status', () => {
    const rows = coverageRows(
      [cov({ role: 'bar', liveHosts: 1 }), cov({ role: 'receipt', liveHosts: 1 })],
      [],
    );
    expect(rows.map((r) => r.role)).toEqual(['bar', 'receipt']);
  });

  it('an empty coverage answer is an empty screen, never an invented row', () => {
    expect(coverageRows([], [])).toEqual([]);
  });
});

describe('fetchPrintHosts — the wire read, fetch stubbed (hub#770: real function, stubbed fetch)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('GETs /api/print/hosts and returns hosts + coverage typed', async () => {
    const payload = {
      ok: true,
      hosts: [
        {
          deviceId: 'dev-1',
          role: 'kitchen',
          label: 'Kitchen tablet',
          live: true,
          registeredAt: '2026-08-14T00:00:00Z',
          registeredBy: 'u1',
          lastSeenAt: '2026-08-14T00:01:00Z',
        },
      ],
      coverage: [{ role: 'kitchen', waiting: 2, liveHosts: 1 }],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const answer = await fetchPrintHosts();

    const [url] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain('/api/print/hosts');
    expect(answer.coverage).toEqual([{ role: 'kitchen', waiting: 2, liveHosts: 1 }]);
    expect(answer.hosts[0]).toMatchObject({ deviceId: 'dev-1', role: 'kitchen', live: true });
  });

  it('throws on a refusal instead of resolving to a lying empty screen', async () => {
    // A swallowed 401 would render "no roles" — which reads as "nothing to worry about" on a hub
    // where the kitchen queue might be piling up. The caller decides how to show "could not check".
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: false }), { status: 401 })),
    );
    await expect(fetchPrintHosts()).rejects.toThrow();
  });

  it('hub2551: reads the name the hub gives and a host without deviceId (a cashier\'s read)', async () => {
    const payload = {
      ok: true,
      hosts: [{ name: '…e7f8', role: 'receipt', label: '', live: true }],
      coverage: [],
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 })),
    );
    const answer = await fetchPrintHosts();
    expect(answer.hosts[0]).toEqual({
      deviceId: '',
      name: '…e7f8',
      role: 'receipt',
      label: '',
      live: true,
    });
  });

  it('tolerates malformed rows without inventing numbers', async () => {
    const payload = { ok: true, hosts: [{}], coverage: [{ role: 'kitchen' }] };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 })),
    );
    const answer = await fetchPrintHosts();
    expect(answer.coverage[0]).toEqual({ role: 'kitchen', waiting: 0, liveHosts: 0 });
  });
});
