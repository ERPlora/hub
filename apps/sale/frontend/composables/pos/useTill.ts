// `useTill()`: the check on screen and every write to it (SALE-F01, F09, F13–F18, F38; the product's «cart →
// order» mapping, server first). The first line opens the check (`sale.order.open`, with the title typed
// before and the line sealed with the chosen professional) and the device remembers it; the next lines
// go to it; a second tap on a product raises its pending line (same professional, no note, discount or
// comp). Writes run ONE AT A TIME (five quick taps never open five checks) and each one reads the check
// as the previous answer left it. The screen shows only what the operations answer — the check comes
// back whole from every write and from the live `sale.order.get` (`follow`), the newer version wins —
// so nothing about money is decided here. A refusal shows the server's own sentence; when nobody
// answered, the product's sentence for that action. A discount above the business's cap goes through
// the manager's door for whoever holds `sale.discount_over_limit`.
import { useCommand } from '@erplora/ui/sdk';
import { toastError, useSession } from '@erplora/ui/shell';
import { computed, type ComputedRef, type Ref, shallowRef } from 'vue';

import { mergeableLine, mergeableServiceLine, plusOne } from '../../components/pos/till';
import { refusal } from '../../lib/refusal';
import type { ComboChoiceIn, OpenLineIn, OrderLineOut, OrderOut, SettingsOut } from '../../operations';
import { useT } from '../useT';
import { useCurrentCheck } from './useCurrentCheck';

/** What a sheet needs to know of its write: done, or the words of the refusal. */
export type WriteResult = { ok: true } | { ok: false; message: string };

export type OpenLine = Pick<OpenLineIn, 'unit_price' | 'department_id' | 'tax_category_key' | 'name'>;

export interface TillOptions {
  /** The till settings (`sale.pos_settings.get`): the discount cap. */
  settings: () => SettingsOut | undefined;
  /** A check was just opened: the page links its customer to it. */
  onOpened?: (orderId: string) => void;
}

export interface Till {
  /** The check on screen, as the server last answered it; `null` with none (or while it loads). */
  order: Readonly<Ref<OrderOut | null>>;
  /** The id of the check on screen (known before its first answer when resumed or reloaded). */
  orderId: Readonly<Ref<string | null>>;
  /** A write is in flight. */
  busy: ComputedRef<boolean>;
  /** The title typed before the check exists: it opens with it. */
  pendingLabel: Readonly<Ref<string>>;
  /** A product of the catalogue, with the options of Modifiers chosen for it (SALE-F11), in the order chosen;
   *  a refusal is a toast. */
  addProduct(product: { id: string }, staffId: string | null, optionIds?: readonly string[]): Promise<void>;
  /** The same, for a sheet: the refusal's words come back instead of a toast. */
  addProductLine(product: { id: string }, staffId: string | null, optionIds?: readonly string[]): Promise<WriteResult>;
  addOpenLine(line: OpenLine, staffId: string | null): Promise<WriteResult>;
  /** A service of Services: its own price, or `unitPrice` (cents) when it has no fixed price. */
  addService(service: { id: string }, staffId: string | null, unitPrice?: number): Promise<WriteResult>;
  /** A menu of Menus with the dishes picked (SALE-F12): always a line of its own; Menus prices it. */
  addComboLine(combo: { id: string }, staffId: string | null, choices: readonly ComboChoiceIn[]): Promise<WriteResult>;
  /** Kitchen sends what is pending as a new round, normal or rush (SALE-F20, KITCHEN-F18); the check is read
   *  back with its round. */
  sendToKitchen(rush: boolean): Promise<WriteResult & { round?: number; code?: string }>;
  setQuantity(line: OrderLineOut, quantity: string): Promise<void>;
  toggleGift(line: OrderLineOut): Promise<void>;
  setNote(line: OrderLineOut, notes: string): Promise<WriteResult>;
  setLineStaff(line: OrderLineOut, staffId: string | null): Promise<void>;
  setLineDiscount(line: OrderLineOut, percent: string): Promise<WriteResult>;
  setTicketDiscount(discount: { percent: string; amount: number }): Promise<WriteResult>;
  voidLine(line: OrderLineOut, reason: string): Promise<WriteResult>;
  rename(label: string): Promise<void>;
  park(label: string): Promise<WriteResult>;
  voidCheck(): Promise<WriteResult>;
  resume(orderId: string): void;
  /** The live `sale.order.get` of the check on screen. */
  follow(next: OrderOut): void;
  /** The check on screen no longer exists. */
  gone(): void;
  /** Lets the check go (charged whole, parked, voided): the screen starts empty. */
  release(): void;
}

const OVER_LIMIT = 'sale.discount_over_limit';

export function useTill(options: TillOptions): Till {
  const t = useT();
  const session = useSession();
  const check = useCurrentCheck();

  /** The words of a refusal; the screen's own sentence (`fallbackKey`) when nobody worded it. */
  const wordsOf = (error: unknown, fallbackKey: string): string => {
    const fallback = t(fallbackKey);
    return refusal(error, fallback)?.message ?? fallback;
  };

  const order = shallowRef<OrderOut | null>(null);
  const pendingLabel = shallowRef('');
  const inFlight = shallowRef(0);
  let tail: Promise<unknown> = Promise.resolve();

  const open = useCommand('sale.order.open');
  const addLine = useCommand('sale.order.add_line');
  const addOpen = useCommand('sale.order.add_open_line');
  const addServiceLine = useCommand('sale.order.add_service_line');
  const addCombo = useCommand('sale.order.add_combo_line');
  const kitchenSend = useCommand('kitchen.ticket.send');
  const readCheck = useCommand('sale.order.get');
  const updateLine = useCommand('sale.order.update_line');
  const removeLine = useCommand('sale.order.remove_line');
  const lineStaff = useCommand('sale.order.set_line_staff');
  const lineDiscount = useCommand('sale.order.set_line_discount');
  const lineDiscountOver = useCommand('sale.order.set_line_discount_over_limit');
  const ticketDiscount = useCommand('sale.order.set_discount');
  const ticketDiscountOver = useCommand('sale.order.set_discount_over_limit');
  const voidLineCommand = useCommand('sale.order.void_line');
  const label = useCommand('sale.order.set_label');
  const voidOrder = useCommand('sale.order.void');

  /** Runs `task` after every write before it: one in flight at a time. */
  function serial<T>(task: () => Promise<T>): Promise<T> {
    inFlight.value += 1;
    const run = tail.then(task);
    tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run.finally(() => {
      inFlight.value -= 1;
    });
  }

  function release(): void {
    check.forget();
    order.value = null;
    pendingLabel.value = '';
  }

  /** The check as a write answered it. */
  function accept(next: OrderOut): void {
    if (next.status !== 'open') {
      release();
      return;
    }
    const current = order.value;
    if (!current || current.id !== next.id || next.version >= current.version) order.value = next;
  }

  /** Runs a write on the check; on a refusal, its words (or `fallbackKey`'s when nobody answered). */
  function attempt(write: (orderId: string) => Promise<OrderOut>, fallbackKey: string): Promise<WriteResult> {
    return serial(async () => {
      const id = order.value?.id ?? check.id.value;
      if (!id) return { ok: false, message: t(fallbackKey) };
      try {
        accept(await write(id));
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, fallbackKey) };
      }
    });
  }

  async function toast(result: Promise<WriteResult>): Promise<void> {
    const done = await result;
    if (!done.ok) void toastError(done.message);
  }

  const staffOf = (staffId: string | null) => (staffId ? { staff_id: staffId } : {});
  const labelOf = () => (pendingLabel.value ? { label: pendingLabel.value } : {});

  async function opened(write: () => Promise<OrderOut>): Promise<void> {
    const created = await write();
    check.remember(created.id);
    pendingLabel.value = '';
    accept(created);
    options.onOpened?.(created.id);
  }

  function addProductLine(product: { id: string }, staffId: string | null, optionIds: readonly string[] = []): Promise<WriteResult> {
    // Only the ids travel: Modifiers values them on the server (a price from the browser buys nothing).
    const options = optionIds.length ? { option_ids: [...optionIds] } : {};
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) {
          await opened(() => open.run({ ...labelOf(), lines: [{ product_id: product.id, ...staffOf(staffId), ...options }] }));
          return { ok: true } as const;
        }
        // A line with options is a dish of its own: it never raises another, nor is raised.
        const merge = order.value && !optionIds.length ? mergeableLine(order.value.lines, product.id, staffId) : undefined;
        accept(
          merge
            ? await updateLine.run({ order_id: id, line_id: merge.id, quantity: plusOne(merge.quantity) })
            : await addLine.run({ order_id: id, product_id: product.id, ...staffOf(staffId), ...options }),
        );
        return { ok: true } as const;
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') } as const;
      }
    });
  }

  const addProduct = (product: { id: string }, staffId: string | null, optionIds: readonly string[] = []) =>
    toast(addProductLine(product, staffId, optionIds));

  function addOpenLine(line: OpenLine, staffId: string | null): Promise<WriteResult> {
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) await opened(() => open.run({ ...labelOf(), open_lines: [{ ...line, ...staffOf(staffId) }] }));
        else accept(await addOpen.run({ order_id: id, ...line, ...staffOf(staffId) }));
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') };
      }
    });
  }

  function addService(service: { id: string }, staffId: string | null, unitPrice?: number): Promise<WriteResult> {
    const priced = unitPrice === undefined ? {} : { unit_price: unitPrice };
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) {
          await opened(() => open.run({ ...labelOf(), service_lines: [{ service_id: service.id, ...priced, ...staffOf(staffId) }] }));
          return { ok: true };
        }
        const merge = unitPrice === undefined && order.value ? mergeableServiceLine(order.value.lines, service.id, staffId) : undefined;
        accept(
          merge
            ? await updateLine.run({ order_id: id, line_id: merge.id, quantity: plusOne(merge.quantity) })
            : await addServiceLine.run({ order_id: id, service_id: service.id, ...priced, ...staffOf(staffId) }),
        );
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') };
      }
    });
  }

  function addComboLine(combo: { id: string }, staffId: string | null, choices: readonly ComboChoiceIn[]): Promise<WriteResult> {
    // Only the choices travel: Menus prices the menu on the server. Each menu is a line of its own (its dishes
    // differ), so a second one never raises the first.
    const menu = { combo_id: combo.id, choices: [...choices], ...staffOf(staffId) };
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) {
          await opened(() => open.run({ ...labelOf(), combo_lines: [menu] }));
          return { ok: true };
        }
        accept(await addCombo.run({ order_id: id, ...menu }));
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') };
      }
    });
  }

  function sendToKitchen(rush: boolean): Promise<WriteResult & { round?: number; code?: string }> {
    return serial(async () => {
      const id = order.value?.id ?? check.id.value;
      if (!id) return { ok: false, message: t('sale.pos.kitchen.notSent') };
      try {
        const ticket = await kitchenSend.run({ order_id: id, priority: rush ? 'rush' : 'normal' });
        accept(await readCheck.run({ order_id: id }));
        return { ok: true, round: ticket.round_no };
      } catch (error) {
        const code = refusal(error, '')?.code;
        return { ok: false, message: wordsOf(error, 'sale.pos.kitchen.notSent'), ...(code ? { code } : {}) };
      }
    });
  }

  const setQuantity = (line: OrderLineOut, quantity: string) =>
    toast(
      attempt(
        (id) =>
          Number(quantity) === 0
            ? removeLine.run({ order_id: id, line_id: line.id })
            : updateLine.run({ order_id: id, line_id: line.id, quantity }),
        'sale.pos.lineChangeFailed',
      ),
    );

  const toggleGift = (line: OrderLineOut) =>
    toast(
      attempt(
        (id) =>
          updateLine.run({
            order_id: id,
            line_id: line.id,
            is_gift: !line.is_gift,
            gift_reason: line.is_gift ? '' : t('sale.pos.giftReason'),
          }),
        'sale.pos.lineChangeFailed',
      ),
    );

  const setNote = (line: OrderLineOut, notes: string) =>
    attempt((id) => updateLine.run({ order_id: id, line_id: line.id, notes }), 'sale.pos.lineChangeFailed');

  const setLineStaff = (line: OrderLineOut, staffId: string | null) =>
    toast(attempt((id) => lineStaff.run({ order_id: id, line_id: line.id, staff_id: staffId }), 'sale.pos.lineStaffFailed'));

  const canGoOver = () => session.can('sale.discount_over_limit');
  const overCap = (percent: string) => Number(percent) > (options.settings()?.max_discount_percent ?? 100);

  /** The ordinary door, or the manager's: above the cap, or when the server says it is above it. */
  async function throughDoor(ordinary: () => Promise<OrderOut>, manager: () => Promise<OrderOut>, aboveCap: boolean): Promise<OrderOut> {
    if (aboveCap && canGoOver()) return manager();
    try {
      return await ordinary();
    } catch (error) {
      const code = (error as { code?: string } | null)?.code;
      if (code === OVER_LIMIT && canGoOver()) return manager();
      throw error;
    }
  }

  const setLineDiscount = (line: OrderLineOut, percent: string) =>
    attempt((id) => {
      const input = { order_id: id, line_id: line.id, discount_percent: percent };
      return throughDoor(
        () => lineDiscount.run(input),
        () => lineDiscountOver.run(input),
        overCap(percent),
      );
    }, 'sale.pos.lineChangeFailed');

  const setTicketDiscount = (discount: { percent: string; amount: number }) =>
    attempt((id) => {
      const input = { order_id: id, discount_percent: discount.percent, discount_amount: discount.amount };
      return throughDoor(
        () => ticketDiscount.run(input),
        () => ticketDiscountOver.run(input),
        overCap(discount.percent),
      );
    }, 'sale.pos.ticketDiscountFailed');

  const voidLine = (line: OrderLineOut, reason: string) =>
    attempt((id) => voidLineCommand.run({ order_id: id, line_id: line.id, reason }), 'sale.pos.voidLineFailed');

  async function rename(next: string): Promise<void> {
    if (!order.value && !check.id.value) {
      pendingLabel.value = next;
      return;
    }
    await toast(attempt((id) => label.run({ order_id: id, label: next }), 'sale.pos.errorSavingTitle'));
  }

  async function park(next: string): Promise<WriteResult> {
    const done = await attempt((id) => label.run({ order_id: id, label: next }), 'sale.pos.parkCheckFailed');
    if (done.ok) release();
    return done;
  }

  async function voidCheck(): Promise<WriteResult> {
    const done = await attempt((id) => voidOrder.run({ order_id: id }), 'sale.pos.discardCheckFailed');
    if (done.ok) release();
    return done;
  }

  function resume(orderId: string): void {
    order.value = null;
    pendingLabel.value = '';
    check.remember(orderId);
  }

  function follow(next: OrderOut): void {
    if (next.id !== check.id.value) return;
    if (next.status !== 'open') {
      // A write of this screen in flight (a void, a charge) closes it itself: its answer tells.
      if (inFlight.value > 0) return;
      release();
      void toastError(t('sale.pos.checkGone'));
      return;
    }
    accept(next);
  }

  function gone(): void {
    if (!check.id.value) return;
    release();
    void toastError(t('sale.pos.checkGone'));
  }

  return {
    order,
    orderId: check.id,
    busy: computed(() => inFlight.value > 0),
    pendingLabel,
    addProduct,
    addProductLine,
    addOpenLine,
    addService,
    addComboLine,
    sendToKitchen,
    setQuantity,
    toggleGift,
    setNote,
    setLineStaff,
    setLineDiscount,
    setTicketDiscount,
    voidLine,
    rename,
    park,
    voidCheck,
    resume,
    follow,
    gone,
    release,
  };
}
