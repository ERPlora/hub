// print-void — the VOID slip when a round already sent to the kitchen is cancelled (kitchen#168),
// or when the till voids ONE dish of it (hub#2640, KITCHEN-F29: `kitchen.item.voided`).
//
// The comanda left on paper when the round was fired (`print-comanda.ts`, HUB_SHELL-F72). When that
// round is cancelled —by hand in Kitchen › Orders (KITCHEN-F22) or because its bill was deleted
// (KITCHEN-F28)— the screen drops the card, but a station that cooks from paper never looks at a
// screen: the docket stays on the rail and the dish is cooked. Toast, Square and Lightspeed print a
// void chit at the same printer; so does this.
//
// Same road as the comanda, on purpose:
//  - **Same printer.** One slip per printer role, built by `buildComandaGroups` from the lines the
//    kitchen froze when the round was fired (`kitchen.orders.items` keeps them after the cancel), so
//    it reaches exactly the stations that got the comanda; screen-only lines print nothing.
//  - **Same till.** `comandaRoute`: the tab that cancelled prints by its usual route (its printer,
//    else the queue); another tab stays quiet; a cancel no tab made goes only to the hub queue, one
//    job for everybody. A bill deleted at a till carries that till through the relay (hub#2029).
//  - **Same document.** `kitchen_order`, untouched: the ESC/POS renderer lives in installed apps
//    that do not update, and a new field would be ignored there — the slip would come out as a NEW
//    comanda and the dish would be cooked twice. So the void is said with what an old app already
//    prints: the floor label, in double height, becomes «VOID · Table 4», and every dish goes with a
//    negative quantity («-2x Croquetas»).
//
// One dish voided gets a slip of its own with only that dish (a menu, all its components), worded
// «VOID ITEM» so the cook does not bin the rest of the table; the round's slip, if the round is
// cancelled later, leaves out what was voided before (its slip already came out).
//
// Never blocks and never reroutes, like the comanda: a slip that does not come out tells the till
// that cancelled, which must say it out loud.
import type { ErploraClient } from '@erplora/module-sdk';
import type { PrintRequest, PrintResult } from './print';
import {
  buildComandaGroups,
  comandaRoute,
  orderIdOf,
  type ComandaGroup,
  type ComandaItem,
  type ComandaPrintFailure,
  type ComandaRoute,
} from './print-comanda';

type Deps = {
  print: (req: PrintRequest) => Promise<PrintResult>;
  /** The caller owns i18n (ADR-0055): the word VOID goes on the paper in the app's language. */
  t: (key: string, params?: Record<string, unknown>) => string;
  onFailure?: (f: ComandaPrintFailure) => void;
};

/** A kitchen line as `kitchen.orders.items` returns it, with what the void slip reads. */
type VoidItem = ComandaItem & { id?: string; status?: string | null; sales_order_item_id?: string | null };

/** Starts both listeners at shell boot. Returns the function that stops them. */
export function bootPrintVoid(client: ErploraClient, deps: Deps): () => void {
  const printed = new Set<string>();
  const stopRound = client.onEvent('kitchen.order.cancelled', (payload, meta) => {
    void onKitchenOrderCancelled(client, payload, deps, comandaRoute(meta)).catch((e) =>
      console.warn('[print-void]', e),
    );
  });
  const stopDish = client.onEvent('kitchen.item.voided', (payload, meta) => {
    void onKitchenItemVoided(client, payload, deps, comandaRoute(meta), printed).catch((e) =>
      console.warn('[print-void]', e),
    );
  });
  return () => {
    stopRound();
    stopDish();
  };
}

export async function onKitchenOrderCancelled(
  client: ErploraClient,
  payload: unknown,
  deps: Deps,
  route: ComandaRoute = 'here',
): Promise<void> {
  const orderId = orderIdOf(payload);
  if (!orderId) return;
  // Somebody else cancelled it: that till prints the slip, as it would have printed the comanda.
  if (route === 'elsewhere') return;

  const items = await client
    .query<VoidItem[]>('kitchen.orders.items', { order_id: orderId })
    .catch(() => [] as VoidItem[]);
  // A dish the till voided before got its own slip (hub#2640): taking it back again would read as
  // two fewer, and an installed app cannot tell the slips apart.
  const groups = buildComandaGroups((items ?? []).filter((line) => line.status !== 'voided'));
  if (!groups.length) return; // nothing went to paper, so there is nothing to take back

  const header = await orderHeader(client, orderId);
  const label = str(header?.label);
  const slipLabel = label ? deps.t('print.voidLabel', { label }) : deps.t('print.voidLabelBare');
  await printVoidSlips(
    deps,
    route,
    groups,
    header,
    slipLabel,
    { orderId, label },
    (role) => `kitchen-void-${orderId}-${role}`,
  );
}

/**
 * The till voided ONE dish already sent (`kitchen.item.voided`, KITCHEN-F29). The kitchen emits one
 * event per kitchen line, so a menu voided whole arrives as one event per component: the slip is
 * per SALES line (the dish the till voided), printed once per tab (`printed`) and once in the queue
 * (its key).
 */
export async function onKitchenItemVoided(
  client: ErploraClient,
  payload: unknown,
  deps: Deps,
  route: ComandaRoute = 'here',
  printed: Set<string> = new Set(),
): Promise<void> {
  const orderId = orderIdOf(payload);
  const itemId = str((payload as { order_item_id?: unknown } | null)?.order_item_id);
  if (!orderId || !itemId) return;
  if (route === 'elsewhere') return;

  const items = await client
    .query<VoidItem[]>('kitchen.orders.items', { order_id: orderId })
    .catch(() => [] as VoidItem[]);
  const line = (items ?? []).find((it) => str(it.id) === itemId);
  if (!line || line.status !== 'voided') return;
  const salesLine = str(line.sales_order_item_id);
  const dishLines = salesLine
    ? (items ?? []).filter((it) => it.status === 'voided' && str(it.sales_order_item_id) === salesLine)
    : [line];
  const dishKey = salesLine || itemId;

  // Checked and taken in the same tick as the read resolves: the other events of the same menu
  // are still waiting on theirs.
  const once = `${orderId}-${dishKey}`;
  if (printed.has(once)) return;
  printed.add(once);

  const groups = buildComandaGroups(dishLines);
  if (!groups.length) return; // the dish only went to a screen

  const header = await orderHeader(client, orderId);
  const label = str(header?.label);
  const slipLabel = label ? deps.t('print.voidDishLabel', { label }) : deps.t('print.voidDishLabelBare');
  const dish = str(line.combo_name) || str(line.product_name);
  await printVoidSlips(
    deps,
    route,
    groups,
    header,
    slipLabel,
    { orderId, label, dish },
    (role) => `kitchen-void-${orderId}-${dishKey}-${role}`,
  );
}

async function orderHeader(client: ErploraClient, orderId: string): Promise<Record<string, unknown> | undefined> {
  const rows = await client
    .query<Record<string, unknown>[]>('kitchen.orders.get', { order_id: orderId })
    .catch(() => undefined);
  return Array.isArray(rows) ? rows[0] : rows;
}

async function printVoidSlips(
  deps: Deps,
  route: ComandaRoute,
  groups: ComandaGroup[],
  header: Record<string, unknown> | undefined,
  slipLabel: string,
  who: { orderId: string; label: string; dish?: string },
  jobId: (role: string) => string,
): Promise<void> {
  const { orderId, label } = who;
  const named = who.dish ? { dish: who.dish } : {};
  for (const group of groups) {
    try {
      const result = await deps.print({
        role: group.role,
        documentType: 'kitchen_order',
        fallbackToBrowser: false,
        ...(route === 'queue' ? { queueOnly: true } : {}),
        // Not the comanda's key: the queue would drop the slip as a repeat of it. Cancelling is
        // final, so one slip per order (or voided dish) and station.
        jobId: jobId(group.role),
        data: {
          receipt_id: str(header?.order_number),
          label: slipLabel,
          round_number: num(header?.round_number ?? 1),
          // No `priority`: a cancelled rush round is not a dish to hurry.
          items: group.items.map((line) => ({ ...line, quantity: -line.quantity })),
        },
      });
      if (result.via === 'none') {
        fail(deps, { orderId, role: group.role, label, ...named, error: result.error ?? 'void_slip_not_delivered' });
      } else if (result.via === 'queue' && result.awaitingHost) {
        fail(deps, {
          orderId,
          role: group.role,
          label,
          ...named,
          error: result.error ?? 'station_has_no_printer',
          awaitingHost: true,
        });
      }
    } catch (e) {
      fail(deps, { orderId, role: group.role, label, ...named, error: e instanceof Error ? e.message : String(e) });
    }
  }
}

function fail(deps: Deps, f: ComandaPrintFailure): void {
  console.warn(`[print-void] ${f.role} void slip of order ${f.orderId} not printed: ${f.error}`);
  deps.onFailure?.(f);
}

function num(v: unknown): number {
  return typeof v === 'number' ? v : Number(v ?? 0) || 0;
}

function str(v: unknown): string {
  return v == null ? '' : String(v);
}
