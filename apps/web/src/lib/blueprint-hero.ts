// The rules behind the hero card of an empty business (hub#368, PLAN step 10).
//
// A brand new hub has nothing: no apps, no catalogue, no roles. The shortest way out of that is not
// installing apps one by one — it is starting from a sector template, which brings the apps, seeds
// their catalogue and pre-activates the role set of the vertical (hub#354). This file owns every
// decision that card makes; the card itself only paints.
//
// **"One click = configured" is not literally true, and the card must not pretend it is.** A
// template deliberately travels WITHOUT the identity of the business it came from — the tax id, the
// legal name and the certificate are outside `PORTABLE_SETTING_KEYS` on purpose (ADR-0195 §4,
// hub#405) — and it never carries people (§5). So after the click the checklist below is NOT empty:
// «your business details» (⛔) and «your team» are still the owner's to answer. The copy says that
// before the click and again after it.
import { ADMINISTER_PERMISSION } from './management-link';
import {
  moduleInstallStatusInfo,
  sectionStatusInfo,
  type BlueprintManifest,
  type CatalogBlueprint,
  type ImportReport,
  type ImportSelection,
} from './runtime';
import { permissionsInclude } from './session';
import { STATE_DONE, type SetupStatus } from './setup-status';

/**
 * Key of the core item that answers *"does this business have apps yet"*
 * (`crates/runtime/src/setup_status.rs`, [`ITEM_APPS`]).
 */
export const ITEM_APPS = 'apps';

/**
 * How many templates the card offers at once.
 *
 * Four is a hero, more is a list — and a list is what Settings › Data already is, with its search
 * and its table. The card's job is to make the first choice easy, not to be the catalogue.
 */
export const MAX_OFFERS = 4;

/**
 * Does this business still have no apps?
 *
 * Read from the ONE query that owns the configuration state (ADR-0222), never re-derived from the
 * navigation or from a module list: a second source is exactly the divergence hub#369 closed.
 *
 * Two absences mean **no** rather than *"empty"*, and that direction is deliberate:
 *
 * * **no document** — the query has not answered (early boot, a failed read). An absence is not
 *   evidence of an empty business.
 * * **no `apps` item in it** — the runtime drops items this session cannot configure (hub#435) and
 *   omits checks it could not make (best-effort). Reading a gap as *"empty"* would offer a sector
 *   template on top of a business that is already running, which is the one mistake here that
 *   cannot be undone by closing the card.
 */
export function hubIsEmpty(status: SetupStatus | null): boolean {
  const apps = status?.items.find((i) => i.key === ITEM_APPS);
  // `unavailable` counts as empty too (hub#371). That state says the MODULE catalogue offers this
  // hub nothing; the templates come from a different endpoint entirely, so shutting the door that
  // is still open because the other one is shut would leave an empty business with no way in.
  return !!apps && apps.state !== STATE_DONE;
}

/**
 * May a session holding these permissions press this card?
 *
 * It reuses the ONE permission the core already owns (`hub.administer`, ADR-0248) instead of minting
 * a second name for the same thing — and no `module.json` could mint it anyway, because
 * `permissions_for_role` ignores the reserved `hub.` namespace. La regla del comodín vive en
 * `permissionsInclude` (hub#506), compartida con el resto de la UI.
 */
export function mayAdminister(permissions: readonly string[] | undefined): boolean {
  return permissionsInclude(permissions, ADMINISTER_PERMISSION);
}

/** Where this business is, as far as the offer is concerned. Both halves may be unknown. */
export interface HeroAudience {
  /** ISO-3166-1 alpha-2 fiscal country of the hub (`hub_settings.country_code`). */
  country?: string | null;
  /** Language the hub is being used in. */
  language?: string | null;
}

/** A click that is in flight, or one that has finished and is waiting to be read. */
export type HeroRun =
  | { phase: 'working'; name: string }
  | { phase: 'finished'; outcome: HeroOutcome };

/** Everything the card needs to know to decide whether it is on screen at all. */
export interface HeroInput {
  /** May this session administer the business? (`hub.administer`, ADR-0248.) */
  canAdminister: boolean;
  /** The `hub.setup.status` document, or `null` while there is no answer. */
  status: SetupStatus | null;
  /** The templates already picked for this business (see [`heroOffers`]). */
  offers: readonly CatalogBlueprint[];
  /** `null` until the owner presses something. */
  run: HeroRun | null;
  /** The outcome has been read and closed. */
  dismissed: boolean;
  /**
   * The card has ALREADY been on screen in this session (hub#1120).
   *
   * Latched by the card the first time it legitimately came up. It is what keeps the offer from
   * being pulled out from under the pointer — see [`heroVisible`].
   */
  shown: boolean;
}

/**
 * Is the card on screen?
 *
 * The permission comes first and admits no exception. Importing a template is a **task**, not a
 * wall: nothing about it stops a cashier from selling, so the rule of ADR-0248 applies whole — the
 * task that is not yours goes away. (The runtime already drops the `apps` item for such a session,
 * so `hubIsEmpty` would say no anyway; the permission is checked here because it is the *reason*,
 * and a runtime older than hub#435 hands that item to everybody.)
 *
 * A run in flight or unread keeps the card up **even though the business has stopped being empty**:
 * the import installs apps, which ticks the very item this card reads, so the card that started the
 * job would otherwise vanish half-way and take its own report with it.
 *
 * **And once it is up it does not close on its own** (`shown`, hub#1120). `hubIsEmpty` stops saying
 * "empty" for three things that are not the owner acting, and the panel re-reads
 * `hub.setup.status` while the owner is still on the card: the document coming back `null` because
 * the re-read failed (hub#1120 turned out to be the 429 of saas#1640), the `apps` item dropping out
 * of it for this session (hub#435), and the import THIS card started ticking the very item it
 * reads. Without the latch the card is pulled out of the DOM mid-reading and the press aimed at
 * «Use this» lands on empty space: no spinner, no error, no request, which is exactly how a live
 * button gets reported as dead. The offer now leaves for one of the two reasons the owner can see:
 * they used a template, or they closed it. The protection is untouched, because `shown` only
 * latches AFTER the business legitimately counted as empty — a hub that already had apps never
 * sees the card at all.
 *
 * What is **not** one of those reasons, despite what this comment used to claim (hub#1179): a FREE
 * hub arriving with `customers` preinstalled. Nothing installs a module into a newborn hub — the
 * boot import of the deploy-declared blueprint is gone (a hub is born empty), the `HUB_MODULES_DIR`
 * scan is developer-mode only and no deployment asks for developer mode, and the SaaS holds no
 * credential that could make a hub install anything. `crates/server/tests/newborn_hub_is_empty.rs`
 * and `crates/runtime/tests/setup_status_apps_ignores_preinstalled_hub1179.rs` are what keep it
 * that way.
 */
export function heroVisible(input: HeroInput): boolean {
  if (!input.canAdminister || input.dismissed) return false;
  if (input.run) return true;
  if (input.offers.length === 0) return false;
  return input.shown || hubIsEmpty(input.status);
}

/**
 * The templates to put in front of this business, closest first.
 *
 * It **orders, it never hides**: a border business is the one most likely to want the template of
 * the country next door, and dropping it would leave that owner with no explanation. What ranks
 * first is the country, then the language, then everything else — and the catalogue's own order is
 * kept inside each tier, so the SaaS stays the one that decides what is popular.
 */
export function heroOffers(
  catalog: readonly CatalogBlueprint[],
  audience: HeroAudience,
  max: number = MAX_OFFERS,
): CatalogBlueprint[] {
  const tiers: CatalogBlueprint[][] = [[], [], []];
  for (const blueprint of catalog) tiers[tierOf(blueprint, audience)].push(blueprint);
  return [...tiers[0], ...tiers[1], ...tiers[2]].slice(0, max);
}

/** 0 = same country · 1 = same language · 2 = everything else. An unknown half ranks nothing. */
function tierOf(blueprint: CatalogBlueprint, audience: HeroAudience): number {
  const country = fold(audience.country);
  if (country && fold(blueprint.country) === country) return 0;
  const language = fold(audience.language);
  if (language && fold(blueprint.locale) === language) return 1;
  return 2;
}

function fold(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

/**
 * What one click asks the engine for.
 *
 * **One click is a click with no review screen**, and that is what decides the two `false` below.
 * The step this card removes is precisely the one where a human eye could veto somebody else's
 * identities, so it must not ask for them: not the people (ADR-0195 §5) and not the fiscal identity
 * or the certificate. The engine refuses them anyway for a `template` bundle, but putting the whole
 * protection on one server-side check with nobody watching is not a protection, it is a bet.
 *
 * Everything else the bundle carries goes in, because that is what makes a template a template: the
 * apps, the data that fills their catalogue, the portable settings of the sector and the images.
 */
export function heroSelection(manifest: BlueprintManifest): ImportSelection {
  const sections = manifest.sections ?? [];
  const has = (...keys: string[]): boolean => keys.some((k) => sections.includes(k));
  return {
    users: false,
    fiscal: false,
    settings: has('hub_settings', 'settings'),
    media: has('media'),
    modules: (manifest.modules ?? []).map((m) => m.id),
  };
}

/** What did NOT make it in. Empty on every count ⇒ the outcome is `ready`. */
export interface HeroTrouble {
  /** Apps left out because the plan requires subscribing first (ADR-0060, hub#409). */
  blockedApps: string[];
  /** Apps that could not be installed at all. */
  failedApps: string[];
  /**
   * The OTHER parts of the template that did not go in, as the ENGINE names them (`hub_settings`,
   * `media`, `modules/<id>`), in the order it reported them.
   *
   * This was a count, and the reason written here was that those names are OURS, not words the
   * owner ever chose. True about the raw keys — and what it left on screen was *«something else did
   * not go in»*, a second «something» on the one screen where she is checking whether her business
   * is inside (hub#899). She could not tell a missing service from a missing till, so she could not
   * decide whether to start working or import again.
   *
   * So the KEY travels and the words are the card's job: [`heroPart`] says what each one is, and the
   * card renders it translated. Nothing here is dropped for being unpronounceable — a part that
   * failed and nobody ever mentioned is the defect, not the ugly name.
   */
  failedSections: string[];
}

/**
 * One part of a template that did not go in, ready to be put into the owner's words.
 *
 * The card does the talking (it holds the i18n catalogue and the app names); this decides WHAT each
 * section is, which is a rule and belongs with the other rules.
 */
export type HeroPart =
  /** The DATA of an app (`modules/<id>`): its catalogue, its services, its tables. */
  | { kind: 'app_data'; moduleId: string }
  /** A part of the hub itself, with the i18n key of the words that name it. */
  | { kind: 'named'; i18nKey: string }
  /** A section this shell does not know — a runtime newer than the app on this counter. */
  | { kind: 'unknown'; section: string };

/**
 * The words for each part of the hub a bundle can carry.
 *
 * Both spellings of the two sections that have one: the engine writes `hub_settings`/`hub_users`
 * and a manifest may carry the short name, which the full report at Settings › Data already reads
 * as the same thing.
 */
const PART_KEYS: Readonly<Record<string, string>> = {
  hub_settings: 'setup.hero.partSettings',
  settings: 'setup.hero.partSettings',
  hub_users: 'setup.hero.partTeam',
  users: 'setup.hero.partTeam',
  roles: 'setup.hero.partRoles',
  fiscal: 'setup.hero.partFiscal',
  media: 'setup.hero.partMedia',
};

/** What this section IS, so the card can say it (see [`HeroPart`]). */
export function heroPart(section: string): HeroPart {
  // `modules/<id>` is the app's DATA, never the app: the app itself may be installed and running
  // with an empty catalogue, and «Hairdressing did not go in» would send the owner to reinstall
  // something that is right there instead of telling her that her services are missing.
  const moduleId = section.startsWith('modules/') ? section.slice('modules/'.length) : '';
  if (moduleId) return { kind: 'app_data', moduleId };
  const i18nKey = PART_KEYS[section];
  return i18nKey ? { kind: 'named', i18nKey } : { kind: 'unknown', section };
}

/** What the owner is told happened, in the four shapes that are actually different. */
export type HeroOutcome =
  /** Everything the template carried went in. NOT «the business is configured». */
  | { kind: 'ready' }
  /** The engine is best-effort: it got most of the way and something is missing. */
  | ({ kind: 'partial' } & HeroTrouble)
  /** The template could not even be opened (download, checksum, inspect): nothing changed here. */
  | { kind: 'not_started'; reason: string }
  /** The import itself broke. We do NOT claim nothing changed, because we do not know. */
  | { kind: 'interrupted'; reason: string };

/**
 * Reads the engine's report.
 *
 * The subtle half is what does **not** count as trouble. A section the engine `Ignored`, or applied
 * only in `PartiallyApplied` part, is a template behaving exactly as designed — the other business's
 * identities being left at the door (ADR-0195 §4/§5, hub#331/#405). Reporting that as *"something
 * did not make it"* would raise an alarm on every single import that worked perfectly. The other
 * one is `blocked`: an app that needs subscribing is a purchase decision, not a breakage, and it
 * has been its own state since hub#409 precisely so it stops being painted as a red failure.
 */
export function importOutcome(report: ImportReport): HeroOutcome {
  const blockedApps: string[] = [];
  const failedApps: string[] = [];
  for (const module of report.installed_modules ?? []) {
    const info = moduleInstallStatusInfo(module);
    if (info.kind === 'blocked') blockedApps.push(module.id);
    else if (info.kind === 'failed') failedApps.push(module.id);
  }

  // Media is materialised by the server, not by the engine, which reports its row as `Skipped` and
  // the real result in `report.media` — the same rule the full report follows. ANY missing object
  // keeps the import out of `ready`: product rows already point at those paths, so even a partial
  // copy leaves broken catalogue tiles and must lead the owner to the persisted report/retry.
  const media = report.media;
  const failedSections = (report.sections ?? [])
    .filter((s) => !(media && s.section === 'media') && sectionStatusInfo(s.status).kind === 'failed')
    .map((s) => s.section);
  // The server's verdict on the images goes in under the same name the engine would have used, so
  // the card has ONE list to put into words and the photos are still counted exactly once.
  if (media && media.failed > 0) failedSections.push('media');

  if (!blockedApps.length && !failedApps.length && !failedSections.length) return { kind: 'ready' };
  return { kind: 'partial', blockedApps, failedApps, failedSections };
}
