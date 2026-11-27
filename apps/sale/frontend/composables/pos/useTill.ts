// `useTill()`: the check on screen and every write to it (SALE-F01, F09, F13–F18, F38; the product's «cart →
// order» mapping, server first).
import type { ComputedRef, Ref } from 'vue';

import type { ComboChoiceIn, OpenLineIn, OrderLineOut, OrderOut, SettingsOut } from '../../operations';
import { useAddLines } from './useAddLines';
import { useCheckActions } from './useCheckActions';
import { useCheckWrites } from './useCheckWrites';
import { useDiscounts } from './useDiscounts';
import { useFollowCheck } from './useFollowCheck';
import { useKitchenSend } from './useKitchenSend';
import { useLineChanges } from './useLineChanges';
import type { useLineNote } from './useLineNote';

/** What a sheet needs to know of its write: done, or the words of the refusal. */
export type WriteResult = { ok: true } | { ok: false; message: string };

export type OpenLine = Pick<OpenLineIn, 'unit_price' | 'department_id' | 'tax_category_key' | 'name'>;

export interface TillOptions {
  /** The till settings (`sale.pos_settings.get`): the discount cap. */
  settings: () => SettingsOut | undefined;
  /** A check was just opened: the page links its customer to it. */
  onOpened?: (orderId: string) => void;
  /** The check on screen was joined with another (SALE-F24): the till now shows that one; the page reads its customer. */
  onJoined?: (orderId: string) => void;
  /** What else a new check opens with: who serves it (SALE-F16), chosen before it existed. */
  opening?: () => { staff_id?: string };
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
  /** Kitchen sends what is pending as a new round, normal or rush (SALE-F20, KITCHEN-F18), naming who serves the check;
   *  the check is read back with its round. `printed` is false when its sheet did not reach the printer (KITCHEN-F08). */
  sendToKitchen(rush: boolean): Promise<WriteResult & { round?: number; printed?: boolean; code?: string }>;
  setQuantity(line: OrderLineOut, quantity: string): Promise<void>;
  toggleGift(line: OrderLineOut): Promise<void>;
  setNote: ReturnType<typeof useLineNote>;
  setLineStaff(line: OrderLineOut, staffId: string | null): Promise<void>;
  setLineDiscount(line: OrderLineOut, percent: string): Promise<WriteResult>;
  setTicketDiscount(discount: { percent: string; amount: number }): Promise<WriteResult>;
  voidLine(line: OrderLineOut, reason: string): Promise<WriteResult>;
  rename(label: string): Promise<void>;
  park(label: string): Promise<WriteResult>;
  voidCheck(): Promise<WriteResult>;
  resume(orderId: string): void;
  /** The live `sale.order.get` of the check on screen; joined with another, the till follows the one that stays. */
  follow(next: OrderOut): void;
  /** The check on screen no longer exists. */
  gone(): void;
  /** Lets the check go (charged whole, parked, voided): the screen starts empty. */
  release(): void;
}

export function useTill(options: TillOptions): Till {
  const writes = useCheckWrites();
  return {
    order: writes.order,
    orderId: writes.check.id,
    busy: writes.busy,
    pendingLabel: writes.pendingLabel,
    ...useAddLines(writes, options),
    sendToKitchen: useKitchenSend(writes),
    ...useLineChanges(writes),
    ...useDiscounts(writes, options),
    ...useCheckActions(writes),
    ...useFollowCheck(writes, options),
    release: writes.release,
  };
}
