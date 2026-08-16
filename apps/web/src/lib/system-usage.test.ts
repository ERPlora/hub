// @vitest-environment happy-dom
// Client of `GET /api/system/usage-series?range=` (saas#1511): the runtime proxies the SaaS
// series endpoint and passes the JSON through untouched, so this client mirrors that contract.
// Same failure rule as `system.ts`: it never throws and never invents data — `null` on any
// failure, and the screen paints its own «we could not read this» state (ADR-0237).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { USAGE_RANGES, fetchUsageSeries, type UsageSeries } from './system-usage';

const contractBody: UsageSeries = {
  range: '3d',
  step_seconds: 900,
  generated_at: '2026-08-15T10:00:00Z',
  thresholds: { warning: 70, critical: 80 },
  metrics: {
    cpu: {
      known: true,
      unit: '%',
      current: 42.5,
      status: 'ok',
      points: [
        [1755100800, 38.2],
        [1755101700, 42.5],
      ],
      message: null,
    },
    ram: {
      known: true,
      unit: '%',
      current: 61,
      status: 'warning',
      points: [[1755100800, 58]],
      message: null,
    },
    db_connections: {
      known: true,
      unit: 'connections',
      current: 3,
      status: 'ok',
      points: [[1755100800, 2]],
      message: null,
    },
  },
  upgrade: { show: false, reason: null, message: null, url: null },
};

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn(async () => new Response(JSON.stringify(contractBody), { status: 200 }));
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchUsageSeries', () => {
  it('asks the runtime proxy for the requested range and returns the body verbatim', async () => {
    const series = await fetchUsageSeries('3d');

    expect(series).toEqual(contractBody);
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toContain('/api/system/usage-series');
    expect(url).toContain('range=3d');
  });

  it('a non-2xx answer is null, never a half-parsed object', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('{"metrics":{}}', { status: 502 }));

    expect(await fetchUsageSeries('24h')).toBeNull();
  });

  it('a network failure is null, never a throw that breaks the screen', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('network down'));

    expect(await fetchUsageSeries('3h')).toBeNull();
  });

  it('offers exactly 3h/24h/3d — the contract caps at three days on purpose', () => {
    expect(USAGE_RANGES).toEqual(['3h', '24h', '3d']);
  });
});
