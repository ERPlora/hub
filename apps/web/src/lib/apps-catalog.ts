// Lógica pura del catálogo de Apps (AppsPage), extraída para poder testearla en el entorno node.

/**
 * ¿Está instalado un módulo del catálogo en ESTE hub?
 *
 * El catálogo Cloud es un proxy al SaaS y su `cloudInstalled` puede ir por detrás de la realidad de
 * este hub (`mark_installed/` es best-effort). El runtime es la fuente de verdad local, así que
 * cruzamos con el conjunto de módulos instalados localmente: si está en cualquiera de los dos,
 * cuenta como instalado. Evita mostrar "Disponible" (y el botón Instalar activo) en un módulo ya
 * instalado (bug del demo 2026-07-12).
 */
export function isModuleInstalled(
  cloudInstalled: boolean,
  id: string,
  localInstalledIds: ReadonlySet<string>,
): boolean {
  return cloudInstalled || localInstalledIds.has(id);
}

/** What a catalog row is, as far as the screen and the buttons are concerned. */
export type CatalogRowState = 'installing' | 'updatable' | 'installed' | 'available' | 'unavailable';

/**
 * The state of one catalog row — the single place install-or-update is decided (hub#795).
 *
 * It used to be decided twice: here (to paint «Update to 1.2.22» in the status column) and again
 * inside the click handler, from the CLOUD's `installed` flag alone. The two disagreed exactly when
 * it matters — `mark_installed` is best-effort, so right after installing, the Cloud still answers
 * `false` while the runtime already has the module — and the row would go down the INSTALL branch of
 * something it should have updated.
 *
 * `busy` comes first on purpose. A row that is already working says only that: offering a second
 * press while the first is in flight is how a module gets installed twice.
 */
export function catalogRowState(row: {
  cloudInstalled: boolean;
  id: string;
  localInstalledIds: ReadonlySet<string>;
  hasUpdate: boolean;
  available: boolean;
  busy: boolean;
}): CatalogRowState {
  if (row.busy) return 'installing';
  const installed = isModuleInstalled(row.cloudInstalled, row.id, row.localInstalledIds);
  // An update is only an update over something this hub HAS. A newer version in the marketplace of a
  // module nobody installed here is just the version you would get if you installed it.
  if (installed) return row.hasUpdate ? 'updatable' : 'installed';
  return row.available ? 'available' : 'unavailable';
}

/**
 * Which action a row offers, or `null` when it offers none.
 *
 * The point of this existing at all: the actions are icon-only (Ioan 2026-07-16 on ADR-0133), so the
 * `label` IS the accessible name and the tooltip. A single «Install» button serving both operations
 * told a keyboard and a screen reader the wrong verb — which is the whole of hub#795.
 */
export function catalogActionFor(state: CatalogRowState): 'install' | 'update' | null {
  if (state === 'available') return 'install';
  if (state === 'updatable') return 'update';
  return null;
}
