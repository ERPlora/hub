// Client of `GET /api/system/usage-series?range=` — the runtime's proxy to the SaaS series
// endpoint (`GET /api/v1/hub/device/metrics/series/`, saas#1511). The runtime signs with its
// machine token (ADR-0003: the browser never holds it) and passes the SaaS JSON through
// untouched, so these types mirror the SaaS contract verbatim (snake_case included).
//
// Failure rule, same as `system.ts`: never throw, never invent — `null` on any failure. The
// screen then paints its own «we could not read this» state (ADR-0237): a series nobody could
// read is not a flat green line at zero.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** The only ranges the contract offers. Three days is the maximum on purpose. */
export type UsageRange = '3h' | '24h' | '3d';

/** Selector options, in display order. Never offer more than the SaaS records. */
export const USAGE_RANGES: readonly UsageRange[] = ['3h', '24h', '3d'];

/** Verdict the SaaS computed for a metric against the plan thresholds. */
export type UsageStatus = 'ok' | 'warning' | 'critical' | 'unknown';

/** One metric of the series (CPU, RAM or DB connections). */
export interface SeriesMetric {
  /** `false` = the SaaS could not measure this — never dressed up as a zero. */
  known: boolean;
  /** Display unit, `%` for cpu/ram. */
  unit?: string;
  /** Latest value as the SaaS knows it. `null`/absent = only the points speak. */
  current?: number | null;
  status?: UsageStatus;
  /** `[unix_seconds, value]` samples, oldest first. */
  points?: [number, number][];
  /** Why it could not be measured, when the SaaS says so. */
  message?: string | null;
}

/** Warning/critical percentages the SaaS colors the series with (70/80 by contract). */
export interface UsageThresholds {
  warning: number;
  critical: number;
}

/** Upgrade call-to-action the SaaS may attach when a hub keeps hitting its plan ceiling. */
export interface UpgradeHint {
  show: boolean;
  reason?: string | null;
  message?: string | null;
  url?: string | null;
}

/** Response of `GET /api/system/usage-series?range=` — the SaaS body, passed through. */
export interface UsageSeries {
  range: string;
  step_seconds: number;
  generated_at: string;
  thresholds: UsageThresholds;
  metrics: {
    cpu: SeriesMetric;
    ram: SeriesMetric;
    db_connections: SeriesMetric;
  };
  upgrade?: UpgradeHint;
}

/**
 * Fetches the usage series for `range` from the runtime proxy.
 *
 * `null` on any failure (non-2xx, network, bad JSON): the runtime already answers `424` with an
 * all-unknown body when the SaaS is unreachable (hub#1763 — a `5xx` would be replaced by the edge
 * with its own page), and the screen treats both the same way.
 */
export async function fetchUsageSeries(range: UsageRange): Promise<UsageSeries | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/system/usage-series?range=${range}`, {
      headers: runtimeHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as UsageSeries;
  } catch {
    return null;
  }
}
