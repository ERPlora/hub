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

/** The operation a busy row is running: the install progress or an update in flight. */
export type CatalogBusyAction = 'install' | 'update' | null;

/**
 * Which action a catalog row PAINTS, or `null` for none (hub#2019).
 *
 * The one that does not apply is left out rather than greyed out: a dead button next to a live one
 * reads as «something is blocked». While the row is busy the running operation stays painted — with
 * its spinner, and disabled — so the person sees what is happening on the button they pressed.
 */
export function catalogVisibleAction(state: CatalogRowState, busy: CatalogBusyAction): 'install' | 'update' | null {
  if (state === 'installing') return busy;
  return catalogActionFor(state);
}

// --- Publication status of a module in the marketplace (ADR-0380, hub#1134) ------------------

/**
 * Whether the marketplace still OFFERS a module — the second axis of "is this on the shelf?".
 *
 * `listed` is on the shelf, `unlisted` is off the listing but still installable by direct
 * reference, and `retired` is the offer closed: what already runs keeps running and keeps
 * updating, and no new hub will ever install it.
 */
export type PublicationStatus = 'listed' | 'unlisted' | 'retired';

const PUBLICATION_STATUSES: readonly PublicationStatus[] = ['listed', 'unlisted', 'retired'];

/**
 * What the Cloud said, or `listed` when it said nothing this screen understands.
 *
 * Silence is NOT "retired". A SaaS older than the field (saas#1542) omits it entirely, and a value
 * we do not know is a newer rung of a ladder this build has not learnt — reading either as a closed
 * offer would put a warning on every app of every hub that talks to an older or newer Cloud. The
 * only safe reading of silence is the state that changes nothing on screen.
 */
export function publicationStatusOf(raw: unknown): PublicationStatus {
  return PUBLICATION_STATUSES.includes(raw as PublicationStatus)
    ? (raw as PublicationStatus)
    : 'listed';
}

/**
 * Which installed modules still need their publication status asked for, one by one.
 *
 * **The catalogue answers for everything it lists.** `GET /api/v1/marketplace/modules/` only ever
 * serves `publication_status='listed'` (the SaaS filters it in the `list` action), so a module that
 * came back in the catalogue is `listed` by construction and asking about it again is pure cost.
 * The suspects are the installed ids the catalogue did NOT list — a set that is empty on a healthy
 * hub, which is what keeps this off the `window.focus` refresh path.
 *
 * `known` is what has already been answered: a status is asked for once per screen, never again on
 * every refresh.
 */
export function modulesWithUnknownPublication(
  installedIds: readonly string[],
  listedIds: ReadonlySet<string>,
  known: ReadonlyMap<string, PublicationStatus | null>,
): string[] {
  return installedIds.filter((id) => !listedIds.has(id) && !known.has(id));
}

/**
 * The publication status of ONE installed module, from the two things the screen knows.
 *
 * Listed in the catalogue ⇒ `listed`, with no round-trip: that is what being in the catalogue
 * MEANS. Otherwise it is whatever was asked for and answered — and `null` when it could not be
 * asked, which is neither `listed` nor `retired` and must not be painted as either.
 */
export function publicationOf(
  id: string,
  listedIds: ReadonlySet<string>,
  known: ReadonlyMap<string, PublicationStatus | null>,
): PublicationStatus | null {
  if (listedIds.has(id)) return 'listed';
  return known.get(id) ?? null;
}

// --- What an install dragged in, named (ADR-0060 closure, hub#1130) ---------------------------

/**
 * Names the modules an install-plan/manifest resolution dragged in as dependencies, in the order
 * `request-install` reported them (its own topological/installation order).
 *
 * The response only ever carries ids (`also_installed: string[]`) — the owner asked to install
 * "Verifactu", not "invoice"/"sales"/"inventory", so the notice must read by name. A dependency
 * the catalogue does not (yet) know about — not loaded, or a manifest id with no catalogue entry —
 * falls back to its own id: dropping it from the notice would hide that something was installed.
 */
export function alsoInstalledNames(
  alsoInstalled: readonly string[],
  catalog: ReadonlyArray<{ id: string; name: string }>,
): string[] {
  const nameById = new Map(catalog.map((m) => [m.id, m.name]));
  return alsoInstalled.map((id) => nameById.get(id) ?? id);
}
