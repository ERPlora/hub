// The words, tones and icons a card of the kitchen display wears: the wait by the semaphore, the ticket's status and
// priority as pills, the type of order and the state of each dish as icons. Every table covers every value the server
// sends, and every icon is one the shell bakes (an unknown one paints nothing).
import { resolveIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import type { ItemStatus, OrderType, Priority, TicketStatus } from '../operations/fields';
import { ITEM_STATUS_ICONS, ORDER_TYPE_ICONS, PRIORITY_TONES, STATUS_TONES, waitOf } from './card';

const ORDER_TYPES: OrderType[] = ['dine_in', 'takeaway', 'delivery'];
const ITEM_STATUSES: ItemStatus[] = ['pending', 'preparing', 'ready', 'served', 'cancelled', 'voided'];
const STATUSES: TicketStatus[] = ['pending', 'preparing', 'ready', 'served', 'cancelled'];
const PRIORITIES: Exclude<Priority, 'normal'>[] = ['rush', 'vip'];

describe('the kitchen card tables', () => {
  it('say the wait in words and with an icon, from the semaphore, and nothing without colours', () => {
    expect(waitOf('ok')).toEqual({ key: 'kitchen.card.wait.ok', icon: 'ion:time-outline' });
    expect(waitOf('warning')).toEqual({ key: 'kitchen.card.wait.warning', icon: 'ion:warning-outline' });
    expect(waitOf('critical')).toEqual({ key: 'kitchen.card.wait.critical', icon: 'ion:alert-circle-outline' });
    expect(waitOf('off')).toBeNull();
  });

  it('give each status and priority a tone: ready is success, cancelled and rush are danger', () => {
    expect(STATUSES.map((status) => STATUS_TONES[status])).toEqual(['neutral', 'info', 'success', 'neutral', 'danger']);
    expect(PRIORITIES.map((priority) => PRIORITY_TONES[priority])).toEqual(['danger', 'info']);
  });

  it('give every type of order and every state of a dish an icon the shell bakes', () => {
    for (const type of ORDER_TYPES) expect(resolveIcon(ORDER_TYPE_ICONS[type]), type).toBeTruthy();
    for (const status of ITEM_STATUSES) expect(resolveIcon(ITEM_STATUS_ICONS[status]), status).toBeTruthy();
    for (const sem of ['ok', 'warning', 'critical'] as const) expect(resolveIcon(waitOf(sem)!.icon), sem).toBeTruthy();
  });

  it('tell a dish done from one to do, and one struck out from both', () => {
    expect(new Set(ITEM_STATUSES.map((status) => ITEM_STATUS_ICONS[status])).size).toBeGreaterThanOrEqual(4);
    expect(ITEM_STATUS_ICONS.ready).not.toBe(ITEM_STATUS_ICONS.pending);
    expect(ITEM_STATUS_ICONS.voided).not.toBe(ITEM_STATUS_ICONS.ready);
  });
});
