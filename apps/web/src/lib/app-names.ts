// The human name of an app, for the sentences that ask the owner to DO something with it (hub#488).
//
// The import report used to name apps by their manifest id: «Estas hay que añadirlas antes a tu
// plan: invoice, cash_register». That sentence is actionable — it sends a restaurant owner to the
// marketplace to subscribe — and `cash_register` is not a word he ever chose; it is a key of ours,
// and in the marketplace that very app is listed under its translated name. Same defect ADR-0254
// (hub#365) took out of the login → till path.
//
// **The name is resolved when the report is painted, never baked into it.** The engine keeps
// reporting ids and that is right: the id is the stable key everything else uses (undo, retry,
// install), a name frozen into a report goes stale when the app is renamed, and it would be stuck
// in the language of whoever ran the import — since hub#763 that report is persisted and read again
// later, possibly by somebody else.
//
// Two sources, because one is not enough: the runtime knows the apps this hub INSTALLED (and
// already localises them, ADR-0055), but a module `blocked` on the plan was never installed — and
// that is precisely the row the sentence is about. The marketplace catalogue covers it.
import { listInstalledModules } from './runtime';
import { cloudMarketplaceModules } from './cloud';

/** Human names by app id. Missing entries are normal, not an error — see [`appLabel`]. */
export type AppNames = ReadonlyMap<string, string>;

/**
 * How this app is named to the owner: its human name, or the id verbatim when there is none.
 *
 * The fallback is the RAW id on purpose. Prettifying it («Cash Register») would invent a name the
 * marketplace does not use either, so the owner would go looking for something that is not there —
 * worse than showing the developer's key and being honest about it.
 */
export function appLabel(id: string, names: AppNames): string {
  return names.get(id) || id;
}

/**
 * Collects the names of every app this hub could be talking about, best-effort.
 *
 * Neither source is load-bearing: the screen that calls this is the import report, and a report
 * that refuses to appear because a catalogue was unreachable is a worse outcome than one that names
 * an app by its id. So both failures are absorbed, and what is left is a smaller map.
 *
 * The runtime wins on a collision: it is the version this business actually runs, and the SaaS
 * catalogue may be listing a different one.
 */
export async function loadAppNames(): Promise<AppNames> {
  const [installed, catalog] = await Promise.all([
    listInstalledModules().catch(() => []),
    cloudMarketplaceModules().catch(() => []),
  ]);
  const names = new Map<string, string>();
  // Catalogue first so the runtime's entries overwrite it, not the other way round.
  for (const m of catalog) if (m.name) names.set(m.id, m.name);
  for (const m of installed) if (m.name) names.set(m.id, m.name);
  return names;
}
