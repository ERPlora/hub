// kitchen#168 — a round already printed at the station and then cancelled (by hand in Kitchen ›
// Orders, or because its bill was deleted, KITCHEN-F28) left the paper on the rail: the kitchen
// cooked it. The screen drops the card, but a paper-only station never looks at a screen. Toast,
// Square and Lightspeed print a VOID chit at the same printer; so does this, by the comanda's own
// route (HUB_SHELL-F72) and with the comanda's own document, so an installed app that cannot be
// updated still prints it.
import { describe, it, expect, vi } from 'vitest';
import { bootPrintVoid, onKitchenItemVoided, onKitchenOrderCancelled } from './print-void';
import { CLIENT_INSTANCE } from './client-instance';
import type { PrintRequest, PrintResult } from './print';

// Echoes the key and its params: a test pins WHICH words are asked for, not their prose (ADR-0055).
const t = (key: string, params?: Record<string, unknown>) => (params ? `${key}${JSON.stringify(params)}` : key);

// `kitchen.orders.items` does not filter by status: after the cancel the lines are still there, with
// the station and printer role frozen when the round was fired.
const CROQUETAS = {
  product_name: 'Croquetas',
  quantity: 2_000_000,
  notes: 'sin gluten',
  status: 'cancelled',
  destination: 'printer',
  printer_role: 'kitchen',
};
const CANAS = {
  product_name: 'Cañas',
  quantity: 2_000_000,
  status: 'cancelled',
  destination: 'display',
  printer_role: 'bar',
};
const FLAN = {
  product_name: 'Flan',
  quantity: 500_000,
  status: 'cancelled',
  destination: 'both',
  printer_role: 'bar',
};

function fakeClient(
  items: unknown[] = [CROQUETAS, CANAS],
  header: Record<string, unknown> = {
    id: 'k-1',
    label: 'Mesa 4',
    round_number: 2,
    order_number: 'C-018',
    status: 'cancelled',
  },
) {
  return {
    query: vi.fn(async (name: string) => {
      if (name === 'kitchen.orders.items') return items;
      if (name === 'kitchen.orders.get') return [header];
      return [];
    }),
  } as never;
}

const printed = () =>
  vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));

describe('the void slip of a cancelled round (kitchen#168)', () => {
  it('prints one slip per printer role, unattended, on the comanda document', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient([CROQUETAS, CANAS, FLAN]), { order_id: 'k-1' }, { print, t });

    expect(print.mock.calls.map((c) => c[0].role).sort()).toEqual(['bar', 'kitchen']);
    const req = print.mock.calls.find((c) => c[0].role === 'kitchen')![0];
    // The document an installed app already renders: a new type would print nothing on it.
    expect(req.documentType).toBe('kitchen_order');
    expect(req.fallbackToBrowser).toBe(false);
  });

  it('says VOID with the floor label, in the app language', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient(), { order_id: 'k-1' }, { print, t });
    expect(print.mock.calls[0]![0].data?.label).toBe('print.voidLabel{"label":"Mesa 4"}');
  });

  it('with no floor label says VOID alone, never a hole', async () => {
    const print = printed();
    await onKitchenOrderCancelled(
      fakeClient([CROQUETAS], { id: 'k-1', label: '', round_number: 1, order_number: 'C-018' }),
      { order_id: 'k-1' },
      { print, t },
    );
    expect(print.mock.calls[0]![0].data?.label).toBe('print.voidLabelBare');
  });

  it('lists the cancelled dishes with a NEGATIVE quantity, so nobody reads it as a new round', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient([CROQUETAS, FLAN]), { order_id: 'k-1' }, { print, t });

    const kitchen = print.mock.calls.find((c) => c[0].role === 'kitchen')![0];
    expect(kitchen.data?.items).toEqual([{ name: 'Croquetas', quantity: -2, notes: 'sin gluten' }]);
    const bar = print.mock.calls.find((c) => c[0].role === 'bar')![0];
    expect(bar.data?.items).toEqual([{ name: 'Flan', quantity: -0.5 }]);
  });

  it('carries the order number and the round, like the comanda it cancels', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient(), { order_id: 'k-1' }, { print, t });
    const data = print.mock.calls[0]![0].data!;
    expect(data.receipt_id).toBe('C-018');
    expect(data.round_number).toBe(2);
  });

  it('never prints the URGENT banner: a cancelled rush round is not a dish to hurry', async () => {
    const print = printed();
    await onKitchenOrderCancelled(
      fakeClient([CROQUETAS], { id: 'k-1', label: 'Mesa 4', order_number: 'C-018', priority: 'rush' }),
      { order_id: 'k-1' },
      { print, t },
    );
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('priority');
  });

  it('has a job key of its own: the queue must not drop it as a repeat of the comanda', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient(), { order_id: 'k-1' }, { print, t });
    expect(print.mock.calls[0]![0].jobId).toBe('kitchen-void-k-1-kitchen');
  });

  it('a round that only went to a screen prints nothing: there is no paper to take back', async () => {
    const print = printed();
    const client = fakeClient([CANAS]) as unknown as { query: ReturnType<typeof vi.fn> };
    await onKitchenOrderCancelled(client as never, { order_id: 'k-1' }, { print, t });
    expect(print).not.toHaveBeenCalled();
    // Nor asks for the header: one query less on every screen-only cancel.
    expect(client.query.mock.calls.map((c) => c[0])).toEqual(['kitchen.orders.items']);
  });

  it('an order with no dishes (made by hand) prints nothing', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient([]), { order_id: 'k-1' }, { print, t });
    expect(print).not.toHaveBeenCalled();
  });

  it('an event with no order does nothing', async () => {
    const print = printed();
    await onKitchenOrderCancelled(fakeClient(), {}, { print, t });
    expect(print).not.toHaveBeenCalled();
  });

  it('with no printer for that station it warns the till, and does not print it at another one', async () => {
    const print = vi.fn(async () => ({ via: 'none' as const, role: 'kitchen' }));
    const onFailure = vi.fn();
    await onKitchenOrderCancelled(fakeClient(), { order_id: 'k-1' }, { print, t, onFailure });
    expect(print).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ orderId: 'k-1', role: 'kitchen', label: 'Mesa 4' });
    // The reason is for the log, as a code (hub#2257).
    expect(onFailure.mock.calls[0]![0].error).toMatch(/^[a-z][a-z_]*$/);
  });

  it('queued with nobody to print that station, it warns that it is waiting', async () => {
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen', awaitingHost: true }));
    const onFailure = vi.fn();
    await onKitchenOrderCancelled(fakeClient(), { order_id: 'k-1' }, { print, t, onFailure });
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ orderId: 'k-1', awaitingHost: true });
  });

  it('queued with somebody draining it says nothing: it comes out', async () => {
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen', awaitingHost: false }));
    const onFailure = vi.fn();
    await onKitchenOrderCancelled(fakeClient(), { order_id: 'k-1' }, { print, t, onFailure });
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('a printer that throws does not stop the other station from getting its slip', async () => {
    const print = vi.fn(async (req: PrintRequest) => {
      if (req.role === 'kitchen') throw new Error('out of paper');
      return { via: 'bridge' as const, role: req.role ?? 'bar' };
    });
    const onFailure = vi.fn();
    await expect(
      onKitchenOrderCancelled(fakeClient([CROQUETAS, FLAN]), { order_id: 'k-1' }, { print, t, onFailure }),
    ).resolves.toBeUndefined();
    expect(print).toHaveBeenCalledTimes(2);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ role: 'kitchen' });
  });
});

describe('the void slip comes out once, where the comanda came out (kitchen#168, hub#2029)', () => {
  const TILL_NEXT_DOOR = 'till-next-door-7c1e';

  function tillHearing() {
    const listeners: ((payload: unknown, meta: { clientInstance?: string }) => void)[] = [];
    const client = {
      ...(fakeClient() as object),
      onEvent: (event: string, cb: (typeof listeners)[number]) => {
        if (event === 'kitchen.order.cancelled') listeners.push(cb);
        return () => {};
      },
    } as never;
    const emit = async (payload: unknown, meta: { clientInstance?: string }) => {
      for (const cb of listeners) cb(payload, meta);
      await new Promise((r) => setTimeout(r, 0));
    };
    return { client, emit };
  }

  it('the tab that cancelled it prints the slip, by its usual route', async () => {
    const print = printed();
    const { client, emit } = tillHearing();
    bootPrintVoid(client, { print, t });

    await emit({ order_id: 'k-1' }, { clientInstance: CLIENT_INSTANCE });

    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].queueOnly).toBeFalsy();
  });

  it('a cancel made at another till prints nothing here', async () => {
    const print = printed();
    const onFailure = vi.fn();
    const { client, emit } = tillHearing();
    bootPrintVoid(client, { print, t, onFailure });

    await emit({ order_id: 'k-1' }, { clientInstance: TILL_NEXT_DOOR });

    expect(print).not.toHaveBeenCalled();
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('a cancel no till made (API, a flow) goes ONLY to the hub queue, one job for every till', async () => {
    const print = printed();
    const { client, emit } = tillHearing();
    bootPrintVoid(client, { print, t });

    await emit({ order_id: 'k-1' }, {});

    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].queueOnly).toBe(true);
    expect(print.mock.calls[0]![0].jobId).toBe('kitchen-void-k-1-kitchen');
  });
});

// hub#2640 — the till voids ONE dish already sent (SALES-F20 → KITCHEN-F29): the kitchen screen
// strikes it, but a paper-only station keeps cooking it. Toast and Square print a void chit with
// only that dish, at the printer that got it; the round's own slip (above) is for a whole round.
describe('the void slip of one dish the till voided (hub#2640)', () => {
  // `kitchen.orders.items` after kitchen.item.voided: the voided line is `voided`, the rest alive.
  const VOIDED = {
    id: 'ki-1',
    sales_order_item_id: 'sl-1',
    product_name: 'Croquetas',
    quantity: 2_000_000,
    notes: 'sin gluten',
    status: 'voided',
    void_reason: 'customer changed mind',
    destination: 'printer',
    printer_role: 'kitchen',
  };
  const ALIVE = {
    id: 'ki-2',
    sales_order_item_id: 'sl-2',
    product_name: 'Entrecot',
    quantity: 1_000_000,
    status: 'preparing',
    destination: 'printer',
    printer_role: 'kitchen',
  };
  const VOIDED_EARLIER = {
    id: 'ki-3',
    sales_order_item_id: 'sl-3',
    product_name: 'Gazpacho',
    quantity: 1_000_000,
    status: 'voided',
    destination: 'printer',
    printer_role: 'kitchen',
  };
  const HEADER = { id: 'k-1', label: 'Mesa 4', round_number: 2, order_number: 'C-018', status: 'preparing' };
  const EVENT = { order_id: 'k-1', order_item_id: 'ki-1', action: 'item_voided', notes: 'customer changed mind' };

  it('prints only that dish, with a negative quantity, at its station, on the comanda document', async () => {
    const print = printed();
    await onKitchenItemVoided(fakeClient([VOIDED, ALIVE, VOIDED_EARLIER], HEADER), EVENT, { print, t });

    expect(print).toHaveBeenCalledTimes(1);
    const req = print.mock.calls[0]![0];
    expect(req.role).toBe('kitchen');
    expect(req.documentType).toBe('kitchen_order');
    expect(req.fallbackToBrowser).toBe(false);
    // Neither the dish still cooking nor one voided before (its own slip already came out).
    expect(req.data?.items).toEqual([{ name: 'Croquetas', quantity: -2, notes: 'sin gluten' }]);
    expect(req.data?.receipt_id).toBe('C-018');
    expect(req.data?.round_number).toBe(2);
    expect(req.data).not.toHaveProperty('priority');
  });

  it('says it is ONE dish voided, not the round: the cook must not bin the rest of the table', async () => {
    const print = printed();
    await onKitchenItemVoided(fakeClient([VOIDED, ALIVE], HEADER), EVENT, { print, t });
    expect(print.mock.calls[0]![0].data?.label).toBe('print.voidDishLabel{"label":"Mesa 4"}');
  });

  it('with no floor label says it alone, never a hole', async () => {
    const print = printed();
    await onKitchenItemVoided(fakeClient([VOIDED], { ...HEADER, label: '' }), EVENT, { print, t });
    expect(print.mock.calls[0]![0].data?.label).toBe('print.voidDishLabelBare');
  });

  it("has a key of its own, per dish: neither the comanda's nor the round slip's", async () => {
    const print = printed();
    await onKitchenItemVoided(fakeClient([VOIDED], HEADER), EVENT, { print, t });
    expect(print.mock.calls[0]![0].jobId).toBe('kitchen-void-k-1-sl-1-kitchen');
  });

  it('a menu voided whole prints ONE slip per station, not one per component event', async () => {
    const STARTER = { ...VOIDED, id: 'ki-7', combo_ref: 'c-1', combo_name: 'Menú del día', product_name: 'Gazpacho' };
    const MAIN_DISH = { ...STARTER, id: 'ki-8', product_name: 'Entrecot' };
    const DRINK = { ...STARTER, id: 'ki-9', product_name: 'Caña', printer_role: 'bar' };
    const print = printed();
    const { client, emit } = tillHearingAll(fakeClient([STARTER, MAIN_DISH, DRINK, ALIVE], HEADER));
    bootPrintVoid(client, { print, t });

    for (const id of ['ki-7', 'ki-8', 'ki-9']) {
      void emit('kitchen.item.voided', { order_id: 'k-1', order_item_id: id }, { clientInstance: CLIENT_INSTANCE });
    }
    await new Promise((r) => setTimeout(r, 0));

    expect(print.mock.calls.map((c) => c[0].role).sort()).toEqual(['bar', 'kitchen']);
    const kitchen = print.mock.calls.find((c) => c[0].role === 'kitchen')![0];
    expect(kitchen.data?.items).toEqual([
      { name: 'Gazpacho', quantity: -2, notes: 'sin gluten', combo_ref: 'c-1', combo_name: 'Menú del día' },
      { name: 'Entrecot', quantity: -2, notes: 'sin gluten', combo_ref: 'c-1', combo_name: 'Menú del día' },
    ]);
  });

  it('a menu voided after its starter was served takes back only what was still being made', async () => {
    // Kitchen strikes only the lines still on the line (KITCHEN-F29): the served starter stays.
    const SERVED = {
      ...VOIDED,
      id: 'ki-7',
      combo_ref: 'c-1',
      combo_name: 'Menú del día',
      product_name: 'Gazpacho',
      status: 'served',
    };
    const MAIN_DISH = { ...SERVED, id: 'ki-8', product_name: 'Entrecot', status: 'voided' };
    const print = printed();
    await onKitchenItemVoided(
      fakeClient([SERVED, MAIN_DISH], HEADER),
      { order_id: 'k-1', order_item_id: 'ki-8' },
      {
        print,
        t,
      },
    );

    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].data?.items).toEqual([
      { name: 'Entrecot', quantity: -2, notes: 'sin gluten', combo_ref: 'c-1', combo_name: 'Menú del día' },
    ]);
  });

  it('the same event delivered twice prints once', async () => {
    const print = printed();
    const { client, emit } = tillHearingAll(fakeClient([VOIDED, ALIVE], HEADER));
    bootPrintVoid(client, { print, t });

    await emit('kitchen.item.voided', EVENT, { clientInstance: CLIENT_INSTANCE });
    await emit('kitchen.item.voided', EVENT, { clientInstance: CLIENT_INSTANCE });

    expect(print).toHaveBeenCalledTimes(1);
  });

  it('a dish that only went to a screen prints nothing, and does not ask for the header', async () => {
    const print = printed();
    const client = fakeClient([{ ...VOIDED, destination: 'display' }], HEADER) as unknown as {
      query: ReturnType<typeof vi.fn>;
    };
    await onKitchenItemVoided(client as never, EVENT, { print, t });
    expect(print).not.toHaveBeenCalled();
    expect(client.query.mock.calls.map((c) => c[0])).toEqual(['kitchen.orders.items']);
  });

  it('a line that is not voided (stale or wrong event) prints nothing', async () => {
    const print = printed();
    await onKitchenItemVoided(fakeClient([{ ...VOIDED, status: 'preparing' }], HEADER), EVENT, { print, t });
    // A line from before kitchen kept the sales line (no `sales_order_item_id`) is its own dish.
    const LEGACY = { ...VOIDED, sales_order_item_id: null, status: 'preparing' };
    await onKitchenItemVoided(fakeClient([LEGACY], HEADER), EVENT, { print, t });
    expect(print).not.toHaveBeenCalled();
  });

  it('an event with no line, or a line that is not in that order, prints nothing', async () => {
    const print = printed();
    await onKitchenItemVoided(fakeClient([VOIDED], HEADER), { order_id: 'k-1' }, { print, t });
    await onKitchenItemVoided(fakeClient([VOIDED], HEADER), { order_id: 'k-1', order_item_id: 'ki-x' }, { print, t });
    await onKitchenItemVoided(fakeClient([VOIDED], HEADER), { order_item_id: 'ki-1' }, { print, t });
    expect(print).not.toHaveBeenCalled();
  });

  it('if the lines cannot be read nothing prints and nobody is warned, like the comanda', async () => {
    const print = printed();
    const onFailure = vi.fn();
    const client = { query: vi.fn(async () => Promise.reject(new Error('offline'))) } as never;
    await onKitchenItemVoided(client, EVENT, { print, t, onFailure });
    expect(print).not.toHaveBeenCalled();
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('with no printer for that station it warns the till, naming the dish', async () => {
    const print = vi.fn(async () => ({ via: 'none' as const, role: 'kitchen' }));
    const onFailure = vi.fn();
    await onKitchenItemVoided(fakeClient([VOIDED], HEADER), EVENT, { print, t, onFailure });
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({
      orderId: 'k-1',
      role: 'kitchen',
      label: 'Mesa 4',
      dish: 'Croquetas',
    });
    expect(onFailure.mock.calls[0]![0].error).toMatch(/^[a-z][a-z_]*$/);
  });

  it('a voided menu is named by the menu in the warning', async () => {
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen', awaitingHost: true }));
    const onFailure = vi.fn();
    await onKitchenItemVoided(
      fakeClient([{ ...VOIDED, combo_ref: 'c-1', combo_name: 'Menú del día' }], HEADER),
      EVENT,
      { print, t, onFailure },
    );
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ dish: 'Menú del día', awaitingHost: true });
  });

  it('a printer that throws warns the till and does not stop the other station', async () => {
    const DRINK = { ...VOIDED, id: 'ki-9', product_name: 'Caña', printer_role: 'bar' };
    const print = vi.fn(async (req: PrintRequest) => {
      if (req.role === 'kitchen') throw new Error('out of paper');
      return { via: 'bridge' as const, role: req.role ?? 'bar' };
    });
    const onFailure = vi.fn();
    await expect(
      onKitchenItemVoided(fakeClient([VOIDED, DRINK], HEADER), EVENT, { print, t, onFailure }),
    ).resolves.toBeUndefined();
    expect(print).toHaveBeenCalledTimes(2);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ role: 'kitchen', dish: 'Croquetas' });
  });

  it('voided at another till prints nothing here; voided by no till goes only to the queue', async () => {
    const print = printed();
    const { client, emit } = tillHearingAll(fakeClient([VOIDED], HEADER));
    bootPrintVoid(client, { print, t });

    await emit('kitchen.item.voided', EVENT, { clientInstance: 'till-next-door-7c1e' });
    expect(print).not.toHaveBeenCalled();

    await emit('kitchen.item.voided', EVENT, {});
    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].queueOnly).toBe(true);
  });

  it('the tab that voided it prints by its usual route', async () => {
    const print = printed();
    const { client, emit } = tillHearingAll(fakeClient([VOIDED], HEADER));
    bootPrintVoid(client, { print, t });
    await emit('kitchen.item.voided', EVENT, { clientInstance: CLIENT_INSTANCE });
    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].queueOnly).toBeFalsy();
  });

  it('the boot returns one stop for both listeners', () => {
    const stops = [vi.fn(), vi.fn()];
    const events: string[] = [];
    const client = {
      onEvent: (event: string) => {
        events.push(event);
        return stops[events.length - 1];
      },
    } as never;
    const stop = bootPrintVoid(client, { print: printed(), t });
    expect(events.sort()).toEqual(['kitchen.item.voided', 'kitchen.order.cancelled']);
    stop();
    expect(stops[0]).toHaveBeenCalledTimes(1);
    expect(stops[1]).toHaveBeenCalledTimes(1);
  });

  describe('and the round slip does not void that dish a second time', () => {
    it('cancelling the round later leaves out the dish already voided', async () => {
      const print = printed();
      const CANCELLED_ALIVE = { ...ALIVE, status: 'cancelled' };
      await onKitchenOrderCancelled(fakeClient([VOIDED, CANCELLED_ALIVE], HEADER), { order_id: 'k-1' }, { print, t });
      expect(print).toHaveBeenCalledTimes(1);
      expect(print.mock.calls[0]![0].data?.items).toEqual([{ name: 'Entrecot', quantity: -1 }]);
    });

    it('voiding the last dish of a round prints ONE slip: the dish, and no round slip on top', async () => {
      const print = printed();
      const { client, emit } = tillHearingAll(fakeClient([VOIDED, VOIDED_EARLIER], { ...HEADER, status: 'cancelled' }));
      bootPrintVoid(client, { print, t });

      // The kitchen emits both, in this order, from the same void (KITCHEN-F29).
      await emit('kitchen.item.voided', EVENT, { clientInstance: CLIENT_INSTANCE });
      await emit('kitchen.order.cancelled', { order_id: 'k-1' }, { clientInstance: CLIENT_INSTANCE });

      expect(print).toHaveBeenCalledTimes(1);
      expect(print.mock.calls[0]![0].jobId).toBe('kitchen-void-k-1-sl-1-kitchen');
    });
  });
});

function tillHearingAll(base: unknown) {
  const listeners = new Map<string, ((payload: unknown, meta: { clientInstance?: string }) => void)[]>();
  const client = {
    ...(base as object),
    onEvent: (event: string, cb: (payload: unknown, meta: { clientInstance?: string }) => void) => {
      listeners.set(event, [...(listeners.get(event) ?? []), cb]);
      return () => {};
    },
  } as never;
  const emit = async (event: string, payload: unknown, meta: { clientInstance?: string }) => {
    for (const cb of listeners.get(event) ?? []) cb(payload, meta);
    await new Promise((r) => setTimeout(r, 0));
  };
  return { client, emit };
}
