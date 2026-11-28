// What a card of the kitchen display wears besides its data: the wait in words and with an icon (never colour
// alone), the tones of its status and priority pills, and the icons of the type of order and of each dish's state.
import type { StatusPillTone } from '@erplora/ui/components';

import type { ItemStatus, OrderType, Priority, TicketStatus } from '../operations/fields';
import type { Semaphore } from './format';

export interface Wait {
  key: string;
  icon: string;
}

const WAITS: Readonly<Record<Exclude<Semaphore, 'off'>, Wait>> = {
  ok: { key: 'kitchen.card.wait.ok', icon: 'ion:time-outline' },
  warning: { key: 'kitchen.card.wait.warning', icon: 'ion:warning-outline' },
  critical: { key: 'kitchen.card.wait.critical', icon: 'ion:alert-circle-outline' },
};

/** The wait a semaphore says; none when the kitchen turned the colours off. */
export function waitOf(sem: Semaphore): Wait | null {
  return sem === 'off' ? null : WAITS[sem];
}

export const STATUS_TONES: Readonly<Record<TicketStatus, StatusPillTone>> = {
  pending: 'neutral',
  preparing: 'info',
  ready: 'success',
  served: 'neutral',
  cancelled: 'danger',
};

export const PRIORITY_TONES: Readonly<Record<Exclude<Priority, 'normal'>, StatusPillTone>> = {
  rush: 'danger',
  vip: 'info',
};

export const ORDER_TYPE_ICONS: Readonly<Record<OrderType, string>> = {
  dine_in: 'ion:storefront-outline',
  takeaway: 'lucide:shopping-bag',
  delivery: 'ion:cube-outline',
};

export const ITEM_STATUS_ICONS: Readonly<Record<ItemStatus, string>> = {
  pending: 'ion:time-outline',
  preparing: 'ion:play-circle-outline',
  ready: 'ion:checkmark-circle',
  served: 'ion:checkmark-done-outline',
  cancelled: 'ion:close-circle-outline',
  voided: 'ion:close-circle-outline',
};
