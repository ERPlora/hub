// **Print coverage, read for the owner's screen** (hub#800, ADR-0196 §6).
//
// The print chain is complete — producer → gate → queue → host registration → drain → ESC/POS —
// and every way it fails is silent: the till that hosted the kitchen role ran out of battery,
// somebody closed the installed app, the hub updated and the host never re-registered. In all of
// them the POS keeps charging and the sale closes with a 200; only the paper stops coming out, in
// another room. `GET /api/print/hosts` already answers, per printer role, how much work is
// waiting and how many live hosts drain it (`crates/runtime/src/print_hosts.rs::coverage`). This
// module turns that answer into the rows Settings › Receipts paints.
//
// ## When it shouts (the issue's open decision, resolved here)
//
// The API only returns a role that has **either** a registered host row **or** pending work — a
// role this business never used does not appear at all. That gives the screen the distinction
// hub#800 asks for, for free:
//
//   - `ready` — at least one live host. Reassurance ("the kitchen is ready"), never a warning.
//   - `stalled` — work waiting and no live host. THE alarm: tickets are piling up unseen.
//   - `unattended` — no live host and nothing waiting. The only way this row can exist is a host
//     that WAS registered and stopped reporting: coverage that was lost, softer than `stalled`.
//
// A salon without a kitchen never sees a kitchen row, so the warning cannot become the weekly
// noise everybody learns to ignore.
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** A registered print host, as `GET /api/print/hosts` returns it (camelCase over the wire). */
export interface PrintHostEntry {
  deviceId: string;
  role: string;
  label: string;
  live: boolean;
}

/** Per-role coverage as the runtime computes it: facts, not a sentence. */
export interface PrintRoleCoverage {
  role: string;
  /** Jobs still `pending` — waiting for ANY host to take them. */
  waiting: number;
  /** Registered hosts that reported within the TTL. `0` with `waiting > 0` is the alarm. */
  liveHosts: number;
}

export type PrintRoleStatus = 'ready' | 'stalled' | 'unattended';

/** One row of the coverage screen: a role, its state, and who (if anybody) is printing it. */
export interface PrintRoleRow extends PrintRoleCoverage {
  status: PrintRoleStatus;
  /** Human names of the LIVE hosts draining this role (device id when a host has no label). */
  hosts: string[];
}

/** The three states, worst first — also the order the screen lists them in. */
const STATUS_RANK: Record<PrintRoleStatus, number> = { stalled: 0, unattended: 1, ready: 2 };

/** See the header: live host = ready; waiting with nobody = stalled; neither = lost coverage. */
export function classifyRole(coverage: PrintRoleCoverage): PrintRoleStatus {
  if (coverage.liveHosts > 0) return 'ready';
  return coverage.waiting > 0 ? 'stalled' : 'unattended';
}

/**
 * Joins the runtime's coverage with the host registry into the rows the screen paints, alarm
 * first. Only LIVE hosts are named: a dead registration is exactly what the row is warning about,
 * and naming it as if it printed would make the warning contradict itself.
 */
export function coverageRows(
  coverage: PrintRoleCoverage[],
  hosts: PrintHostEntry[],
): PrintRoleRow[] {
  const rows = (coverage ?? []).map((c) => ({
    ...c,
    status: classifyRole(c),
    hosts: (hosts ?? [])
      .filter((h) => h.live && h.role === c.role)
      .map((h) => h.label.trim() || h.deviceId),
  }));
  // Stable within a status: the API already orders roles alphabetically.
  return rows.sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status]);
}

/** A row of the wire payload before it is trusted. */
type WireHost = Partial<Record<'deviceId' | 'role' | 'label', unknown>> & { live?: unknown };
type WireCoverage = Partial<Record<'role', unknown>> & { waiting?: unknown; liveHosts?: unknown };

const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

/**
 * `GET /api/print/hosts` — the registry plus per-role coverage. **A refusal throws**, it never
 * resolves empty: an empty screen reads as "nothing to worry about", which on a hub whose kitchen
 * queue is piling up would be the same lie this feature exists to end. The caller renders its own
 * honest "could not check" state (hub#375: our failed probe is not the owner's homework, and it
 * is never green).
 */
export async function fetchPrintHosts(): Promise<{
  hosts: PrintHostEntry[];
  coverage: PrintRoleCoverage[];
}> {
  const res = await fetch(`${RUNTIME_URL}/api/print/hosts`, { headers: runtimeHeaders() });
  const payload = (await res.json().catch(() => null)) as {
    ok?: boolean;
    hosts?: WireHost[];
    coverage?: WireCoverage[];
  } | null;
  if (!res.ok || payload?.ok !== true) {
    throw new Error(`GET /api/print/hosts → HTTP ${res.status}`);
  }
  return {
    hosts: (payload.hosts ?? []).map((h) => ({
      deviceId: str(h.deviceId),
      role: str(h.role),
      label: str(h.label),
      live: h.live === true,
    })),
    coverage: (payload.coverage ?? []).map((c) => ({
      role: str(c.role),
      waiting: num(c.waiting),
      liveHosts: num(c.liveHosts),
    })),
  };
}
