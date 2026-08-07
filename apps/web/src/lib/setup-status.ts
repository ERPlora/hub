// The hub's configuration state, read from the ONE query that owns it (hub#372).
//
// **The configuration state is a single query. The checklist widget and the assistant are two
// reads of the same query** (`architecture/hub/setup-status.md`, ADR-0224/0227). Until hub#372 they
// were not: this file walked the installed manifests and fired N queries from the browser, so it
// only ever knew about modules — your apps, your business identity and your team were invisible —
// and the assistant received a paragraph built from that in-memory array instead of the data.
//
// What is left here is the reading and the SHAPE the card paints, and nothing else:
//
// * **Nothing is re-decided.** The runtime already ordered the list, already dropped what does not
//   apply to this country, what the session cannot configure and what it could not evaluate. A
//   second filter here is the divergence hub#369 closed: two surfaces deciding the same thing
//   separately end up disagreeing.
// * **The counters are the query's.** `done` is `total - pending - unavailable`, the split the
//   runtime guarantees. Re-counting the rows on screen would report a different hub than the one
//   the assistant and the blocking strip describe.
// * **`unavailable` is not an action.** It is our breakdown, not the user's task, so it is painted
//   and never offered: a CTA there sends someone to a screen where nothing can be done.
import { computed, ref } from 'vue';
import type { ErploraClient } from '@erplora/module-sdk';

/** The one query. A core query of the reserved `hub.` namespace (`crates/runtime/src/hub_users.rs`). */
export const SETUP_STATUS_QUERY = 'hub.setup.status';

/** The item is done. */
export const STATE_DONE = 'done';
/** The item is still the user's to do — a job with a screen behind it. */
export const STATE_PENDING = 'pending';
/**
 * Evaluated, not done, and **the user cannot do it yet** (hub#371): an empty marketplace or an
 * entitlement that lets this hub install nothing. Ours to fix, so it is never offered as a task.
 */
export const STATE_UNAVAILABLE = 'unavailable';

/** ⛔ the runtime rejects the operation without it. */
export const LEVEL_LEGAL = 'legal';
/** 🔴 no gate, but the till cannot do its job. */
export const LEVEL_FUNCTIONAL = 'functional';
/** 🟡 the business runs; you notice it is missing. Folded behind «view all». */
export const LEVEL_RECOMMENDED = 'recommended';

/**
 * How many rows the card shows before folding the rest.
 *
 * The full list is ten items and the practice of the trade is 3-5 in sight: a checklist you have to
 * scroll reads as a chore, and the ones past the fold are exactly the 🟡 that never block anybody.
 */
export const MAX_VISIBLE_ROWS = 5;

/** One item of the checklist, exactly as `hub.setup.status` emits it. */
export interface SetupItem {
  /** Stable key. For a CORE item it is ALSO its i18n key; for a module it is `<module_id>.setup`. */
  key: string;
  source: string;
  moduleId: string | null;
  /** `done` · `pending` · `unavailable`. An item the runtime could not evaluate never arrives. */
  state: string;
  /** What the module DECLARED. Read `level`, never this: `required` cannot express ⛔. */
  required: boolean;
  /** The core's verdict: `legal` ⛔ · `functional` 🔴 · `recommended` 🟡. */
  level: string;
  /** English canonical (the fallback; a core item is translated by its key). */
  title: string;
  description: string;
  icon: string;
  /** The screen that completes it. */
  route: string;
  order: number;
  /** `template` · `catalog` · `manual` · `assistant` — of the ITEM, not of the session. */
  actions: string[];
}

/** The document: one row with the whole answer, counters included. */
export interface SetupStatus {
  items: SetupItem[];
  total: number;
  pending: number;
  unavailable: number;
  blockingPending: number;
  /** `total - pending - unavailable`. Derived from the counters, never from the rows on screen. */
  done: number;
}

/** What the card paints for a given document. */
export interface ChecklistView extends Omit<SetupStatus, 'items'> {
  /** The rows to render right now, in the query's order. */
  rows: SetupItem[];
  /** How many more items exist behind «view all». */
  hidden: number;
  /** Nothing left for the user and nothing broken — the finished state. */
  complete: boolean;
  /** The query said nothing worth painting: no card at all. */
  empty: boolean;
}

export interface ChecklistOptions {
  /** Show everything the query returned instead of the short view. */
  expanded?: boolean;
  /**
   * Keys another card on the SAME screen already offers (decision 1 of the plan: the panel has its
   * own apps card, so the checklist starts at item 2 while that card is up). Deduplicating a
   * surface is not filtering the list: the item is still counted, and `/setup` still lists it.
   */
  alreadyOnScreen?: readonly string[];
}

const _status = ref<SetupStatus | null>(null);
/** The last document the runtime answered. `null` until the first successful read. */
export const setupStatus = computed<SetupStatus | null>(() => _status.value);

/**
 * Reads `hub.setup.status` — once, for the whole hub.
 *
 * Best-effort, like everything around this subsystem: a query that fails (early boot, denied
 * session, runtime restarting) leaves the previous answer standing rather than emptying the card.
 * An absence is not evidence that the hub is configured.
 */
export async function refreshSetupStatus(client: ErploraClient): Promise<void> {
  try {
    const parsed = parseSetupStatus(await client.query<unknown>(SETUP_STATUS_QUERY));
    if (parsed) _status.value = parsed;
  } catch {
    /* keep what we had: a failed read is not an answer */
  }
}

/**
 * Reads the runtime's payload. `null` when it is not the document (an error body, a shape we do not
 * know), so a broken answer can never be mistaken for a configured hub.
 */
export function parseSetupStatus(raw: unknown): SetupStatus | null {
  // The core path returns the document as the single row of a normal query result.
  const doc = Array.isArray(raw) ? raw[0] : raw;
  if (!isRecord(doc) || !Array.isArray(doc.items)) return null;
  const items = doc.items.filter(isRecord).map(toItem);
  const total = int(doc.total, items.length);
  const pending = int(doc.pending, 0);
  const unavailable = int(doc.unavailable, 0);
  return {
    items,
    total,
    pending,
    unavailable,
    blockingPending: int(doc.blocking_pending, 0),
    // The split the runtime guarantees (`done + pending + unavailable = total`). Reading "done" as
    // `total - pending` instead would book our own breakdown as a success.
    done: Math.max(0, total - pending - unavailable),
  };
}

/** What the card renders for this document, with the counters untouched. */
export function checklistView(status: SetupStatus | null, opts: ChecklistOptions = {}): ChecklistView {
  const items = (status?.items ?? []).filter((i) => !isDuplicated(i, opts.alreadyOnScreen));
  const counters = {
    total: status?.total ?? 0,
    pending: status?.pending ?? 0,
    unavailable: status?.unavailable ?? 0,
    blockingPending: status?.blockingPending ?? 0,
    done: status?.done ?? 0,
  };
  // A hub with nothing to show is not a hub that finished: an empty answer is silence, and
  // celebrating silence is the false "done" this subsystem exists to avoid.
  const empty = !status || items.length === 0;
  const complete = !empty && counters.pending === 0 && counters.unavailable === 0;

  let rows: SetupItem[] = [];
  if (opts.expanded) rows = items;
  else if (!complete) {
    const left = items.filter((i) => i.state !== STATE_DONE);
    // ⛔ and 🔴 in sight, 🟡 folded — unless the only thing left is 🟡, in which case folding it
    // would leave the card with a headline and an empty body.
    const upfront = left.filter((i) => i.level !== LEVEL_RECOMMENDED);
    rows = (upfront.length ? upfront : left).slice(0, MAX_VISIBLE_ROWS);
  }

  return { ...counters, rows, hidden: items.length - rows.length, complete, empty };
}

/** What the blocking strip paints for a document (hub#374). */
export interface BlockingView {
  /** Paint the strip at all. */
  visible: boolean;
  /** The ⛔ items still pending, in the query's order — exactly what the runtime will reject. */
  items: SetupItem[];
  /** The query's `blocking_pending`, never a recount of the rows above. */
  count: number;
}

export interface BlockingOptions {
  /**
   * This screen already paints the whole checklist (the panel's card). The strip stands down there:
   * the card says strictly more about the same items, with the same way in, a screenful below.
   */
  checklistOnScreen?: boolean;
}

/**
 * The strip's shape.
 *
 * `blocking_pending` is what raises it — the count of items that are ⛔ **and** pending, which is the
 * runtime's own statement that `enforce_fiscal_precondition` (ADR-0203) is going to say no. The list
 * is what it can name; and it only rises if it CAN name something, because a band that cannot be
 * dismissed and does not say what to do or where to go is a dead end on every screen of the product.
 */
export function blockingView(status: SetupStatus | null, opts: BlockingOptions = {}): BlockingView {
  const items = (status?.items ?? []).filter(isBlocking);
  const count = status?.blockingPending ?? 0;
  return { visible: count > 0 && items.length > 0 && !opts.checklistOnScreen, items, count };
}

/**
 * Is this item one of the gates? ⛔ **and** still pending.
 *
 * The two axes stay separate on purpose: an item keeps its level once it is done, so fusing them
 * would give a counter that either never disappears or never appears.
 */
export function isBlocking(item: SetupItem): boolean {
  return item.level === LEVEL_LEGAL && item.state === STATE_PENDING;
}

/**
 * Does this item offer the user something to do? **Only a pending one.**
 *
 * `done` has nothing left; `unavailable` has nothing the user can do at all — and a state this
 * shell does not know is not one it may turn into a call to action on a guess.
 */
export function isActionable(item: SetupItem): boolean {
  return item.state === STATE_PENDING;
}

/** A module pending configuration, in the shape the assistant drawer still reads (hub#373). */
export interface PendingSetup {
  moduleId: string;
  title: string;
  description?: string;
  icon: string;
  route: string;
}

/**
 * The pending items, for the surfaces that have not moved to the document yet.
 *
 * `unavailable` is deliberately NOT here: it is not pending for the user, and offering the
 * assistant a task nobody can complete would have it invent a way to complete it.
 */
export const pendingSetups = computed<PendingSetup[]>(() =>
  (_status.value?.items ?? [])
    .filter((i) => i.state === STATE_PENDING)
    .map((i) => ({
      moduleId: i.moduleId ?? i.key,
      title: i.title,
      description: i.description || undefined,
      icon: i.icon,
      route: i.route,
    })),
);

/**
 * Deterministic seed for the assistant, from the SAME document the card paints.
 *
 * Still prose, and still a stop-gap: hub#373 replaces this with the assistant reading the query
 * itself. What it no longer does is describe a different hub than the card.
 */
export function seedSetupContext(): string {
  const list = pendingSetups.value;
  const header = 'Eres el asistente de configuración del hub ERPlora. Ayuda al usuario a dejar todo configurado.';
  if (!list.length) {
    return `${header}\n\nEstado: no queda nada pendiente de configurar. Si el usuario pregunta por algo concreto, explícale cómo funciona y ofrécele ir a su pantalla.`;
  }
  const items = list
    .map((s) => `• ${s.title}${s.description ? ` — "${s.description}"` : ''}\n  Pantalla: ${s.route}`)
    .join('\n');
  return (
    `${header}\n\nQueda(n) ${list.length} cosa(s) por configurar:\n${items}\n\n` +
    'Cuando el usuario pregunte cómo configurar algo, explica los pasos con la descripción de arriba y dile a qué pantalla ir (la ruta). ' +
    'Puedes usar las tools disponibles para consultar el estado real de los módulos. Ofrece ayudar a configurar cada uno.'
  );
}

/**
 * Is this item already offered by another card on the same screen?
 *
 * Never for an `unavailable` one: the other card is offering a path that works, and this state is
 * the statement that the path does not — nobody else on the screen says it.
 */
function isDuplicated(item: SetupItem, alreadyOnScreen?: readonly string[]): boolean {
  return item.state !== STATE_UNAVAILABLE && !!alreadyOnScreen?.includes(item.key);
}

function toItem(raw: Record<string, unknown>): SetupItem {
  return {
    key: str(raw.key),
    source: str(raw.source),
    moduleId: typeof raw.module_id === 'string' ? raw.module_id : null,
    state: str(raw.state),
    required: raw.required !== false,
    level: str(raw.level),
    title: str(raw.title),
    description: str(raw.description),
    icon: str(raw.icon) || 'settings-outline',
    route: str(raw.route),
    order: int(raw.order, 0),
    actions: Array.isArray(raw.actions) ? raw.actions.filter((a): a is string => typeof a === 'string') : [],
  };
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function int(v: unknown, fallback: number): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}
