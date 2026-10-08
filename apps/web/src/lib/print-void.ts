// print-void — the VOID slip when a round already sent to the kitchen is cancelled (kitchen#168).
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
// Never blocks and never reroutes, like the comanda: a slip that does not come out tells the till
// that cancelled, which must say it out loud.
import type { ErploraClient } from '@erplora/module-sdk';
import type { PrintRequest, PrintResult } from './print';
import {
  buildComandaGroups,
  comandaRoute,
  orderIdOf,
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

/** Starts the listener at shell boot. Returns the function that stops it. */
export function bootPrintVoid(client: ErploraClient, deps: Deps): () => void {
  return client.onEvent('kitchen.order.cancelled', (payload, meta) => {
    void onKitchenOrderCancelled(client, payload, deps, comandaRoute(meta)).catch((e) =>
      console.warn('[print-void]', e),
    );
  });
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
    .query<ComandaItem[]>('kitchen.orders.items', { order_id: orderId })
    .catch(() => [] as ComandaItem[]);
  const groups = buildComandaGroups(items ?? []);
  if (!groups.length) return; // nothing went to paper, so there is nothing to take back

  const rows = await client
    .query<Record<string, unknown>[]>('kitchen.orders.get', { order_id: orderId })
    .catch(() => undefined);
  const header = Array.isArray(rows) ? rows[0] : rows;
  const label = str(header?.label);
  const slipLabel = label ? deps.t('print.voidLabel', { label }) : deps.t('print.voidLabelBare');

  for (const group of groups) {
    try {
      const result = await deps.print({
        role: group.role,
        documentType: 'kitchen_order',
        fallbackToBrowser: false,
        ...(route === 'queue' ? { queueOnly: true } : {}),
        // Not the comanda's key: the queue would drop the slip as a repeat of it. Cancelling is
        // final, so one slip per order and station.
        jobId: `kitchen-void-${orderId}-${group.role}`,
        data: {
          receipt_id: str(header?.order_number),
          label: slipLabel,
          round_number: num(header?.round_number ?? 1),
          // No `priority`: a cancelled rush round is not a dish to hurry.
          items: group.items.map((line) => ({ ...line, quantity: -line.quantity })),
        },
      });
      if (result.via === 'none') {
        fail(deps, { orderId, role: group.role, label, error: result.error ?? 'void_slip_not_delivered' });
      } else if (result.via === 'queue' && result.awaitingHost) {
        fail(deps, {
          orderId,
          role: group.role,
          label,
          error: result.error ?? 'station_has_no_printer',
          awaitingHost: true,
        });
      }
    } catch (e) {
      fail(deps, { orderId, role: group.role, label, error: e instanceof Error ? e.message : String(e) });
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
