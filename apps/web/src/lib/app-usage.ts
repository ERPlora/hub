// How often each app is opened from the launcher — the order of the «My apps» grid (hub#367).
//
// The panel of the first day has no data, so the grid cannot be sorted by anything the hub knows:
// it is sorted by what THIS person does. The count is local on purpose (a device preference, not
// hub data): it never travels to the runtime and it is not worth a migration.
//
// Two rules hold the whole module up: what nobody has opened keeps the order the runtime answered
// (no guessing), and a broken store degrades to «nobody has opened anything» instead of taking the
// only widget that works with zero data down with it.

/** `localStorage` key with the per-app open counter. */
export const APP_USAGE_KEY = 'erplora.apps.usage';

/** How many times each app (by shell route) has been opened from the launcher. */
export type AppUsage = Record<string, number>;

/** Reads the counters. Anything that is not a map of finite numbers reads as no counters at all. */
export function readAppUsage(): AppUsage {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(APP_USAGE_KEY);
  } catch {
    return {}; // no localStorage (private mode / restricted webview): the grid still paints
  }
  if (!raw) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {};
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
  const usage: AppUsage = {};
  for (const [path, count] of Object.entries(parsed as Record<string, unknown>)) {
    // A count that is not a number would sort by NaN, which is no order at all.
    if (typeof count === 'number' && Number.isFinite(count)) usage[path] = count;
  }
  return usage;
}

/** Counts one open of `path`. Never throws: a lost count is not worth a failed navigation. */
export function recordAppLaunch(path: string): void {
  if (!path) return;
  const usage = readAppUsage();
  usage[path] = (usage[path] ?? 0) + 1;
  try {
    localStorage.setItem(APP_USAGE_KEY, JSON.stringify(usage));
  } catch {
    /* the store is full or denied: the grid keeps the order it had */
  }
}

/**
 * The installed apps, most used first. Ties keep the order they arrived in (stable sort), so an
 * untouched hub shows exactly what the runtime answered. The input list is never mutated: the shell
 * shares that ref with the topbar launcher.
 */
export function orderAppsByUsage<T extends { path: string }>(
  apps: readonly T[],
  usage: AppUsage = readAppUsage(),
): T[] {
  return [...apps].sort((a, b) => (usage[b.path] ?? 0) - (usage[a.path] ?? 0));
}
