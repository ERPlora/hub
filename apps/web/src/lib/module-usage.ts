/**
 * What a module has SPENT of what its plan includes — ERPlora/whatsapp_inbox#131.
 *
 * The «Plan» tab knew what a plan INCLUDES (`billing.tiers[].quota`, painted by `module-quota.ts`)
 * and never what the hub had USED of it. For a metered channel those are not the same fact: a salon
 * on 30 conversations a month found out it had run out because WhatsApp stopped answering, and the
 * number that would have warned it existed, was computed with the very expression that cuts the
 * channel off, and had no screen (ADR-0470 sends the counters here).
 *
 * ## Why the manifest DECLARES the query instead of the shell guessing it
 *
 * The shell cannot know that `inbound_this_month` is a consumption and `conversations_per_month` is
 * its allowance: those words belong to whoever wrote the module. Every other read the shell does on
 * a module's behalf is declared the same way — `settings.get`/`settings.set`, `protects[].
 * settings_query`, `widgets.*.query` — so `billing.usage` is that same door, not a new idea. A
 * convention over query names would work exactly until the second module named its column something
 * else.
 *
 * The block is transported, never executed by the runtime (`billing` is opaque to it, see
 * `crates/runtime/src/manifest.rs`): the shell calls the query through the normal dispatcher, so the
 * module's own permission still decides who may read it.
 *
 * This file is the PURE half — what counts as a readable number, and when a number turns worrying.
 * The I/O and the painting live in `ModulePlanPanel.vue`.
 */

/** The `billing.usage` block of a manifest: where the consumption of ONE metric comes from. */
export interface ModuleUsageDef {
  /** Namespaced query of the module the shell calls (its own permission gates it). */
  query: string;
  /** Which key of `billing.tiers[].quota` this counts, so the label can be looked up and localised. */
  metric: string;
  /** Column of the answer holding what has been consumed in the current period. */
  used: string;
  /** Column holding the allowance actually enforced. Absent → the tier's `quota` is the only figure. */
  limit?: string;
}

/** A reading: what has been spent, and the ceiling it is spent against (`null` = no cap). */
export interface ModuleUsage {
  used: number;
  limit: number | null;
}

/**
 * A cell as a count: a non-negative finite number, or `null` when it is not one.
 *
 * Strings are accepted because that is how a SQLite `COUNT(*)` reaches the browser once it has been
 * through JSON on some drivers; `''`, `null` and `true` are not numbers however leniently `Number()`
 * reads them, and a negative count is a module contradicting itself.
 */
function asCount(cell: unknown): number | null {
  if (typeof cell === 'number') return Number.isFinite(cell) && cell >= 0 ? cell : null;
  if (typeof cell !== 'string' || cell.trim() === '') return null;
  const parsed = Number(cell);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

/** The first row of whatever `client.query` handed back — an array of rows or a lone object. */
function firstRow(data: unknown): Record<string, unknown> | null {
  if (Array.isArray(data)) return (data[0] as Record<string, unknown>) ?? null;
  if (data && typeof data === 'object') return data as Record<string, unknown>;
  return null;
}

/**
 * The reading behind the meter, or `null` when there is nothing truthful to paint.
 *
 * Giving up on an unreadable `used` is the point: «NaN of 30» is a number the customer reads, and a
 * wrong one is worse than none on the screen that says whether the channel is about to go quiet. An
 * unreadable LIMIT is different — the consumption is still true, it just has no ceiling to sit
 * against, so it survives as `limit: null`.
 *
 * A limit of `0` means «no cap», which is what the manifests that declare one say out loud
 * (`whatsapp_inbox.usage.get`: «the monthly allowance of the plan (0 = no cap)»). Dividing by it
 * would paint an infinite bar.
 */
export function readModuleUsage(data: unknown, def: ModuleUsageDef): ModuleUsage | null {
  const row = firstRow(data);
  if (!row) return null;
  const used = asCount(row[def.used]);
  if (used === null) return null;
  const limit = def.limit ? asCount(row[def.limit]) : null;
  return { used, limit: limit && limit > 0 ? limit : null };
}

/**
 * How full the bar is, `null` when there is no ceiling to fill.
 *
 * Capped at 1 on purpose: over the allowance the bar is full, not overflowing. A progress bar fed
 * more than 1 renders as if it were exactly full anyway, and saying it here keeps the number the
 * component gets honest.
 */
export function usageFraction(usage: ModuleUsage): number | null {
  if (usage.limit === null) return null;
  return Math.min(usage.used / usage.limit, 1);
}

/** How worrying a fraction is, in the vocabulary of OutfitKit. */
export type UsageTone = 'success' | 'warning' | 'danger' | 'neutral';

/**
 * Green below 80 %, amber from 80 %, red from 90 %.
 *
 * The same three thresholds `PlanLimitsPanel.toneFor` uses for the hub's own plan: two screens about
 * what your plan includes disagreeing on when a number turns worrying is how a customer learns to
 * ignore both.
 */
export function usageTone(fraction: number | null): UsageTone {
  if (fraction === null) return 'neutral';
  if (fraction >= 0.9) return 'danger';
  if (fraction >= 0.8) return 'warning';
  return 'success';
}
