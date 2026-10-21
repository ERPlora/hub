// flow: KITCHEN-F19, KITCHEN-F20 — one round of the check in «Order tickets»: «Order N», the time it was sent
// (the business's), its state, «Rush» if it is, its dishes (a voided one struck, with «Voided») and, to whoever
// may change tickets, «Mark rush» / «Remove rush» while it cooks (never on a VIP round). The words are the
// kitchen's own (kitchen#112: the till and the kitchen's list name a state the same way).
import { describe, expect, it } from 'vitest';

import kitchenEn from '../../../../kitchen/frontend/locale/en.json';
import kitchenEs from '../../../../kitchen/frontend/locale/es.json';
import { click, mountSale } from '../../__tests__/mount-sale';
import en from '../../locale/en.json';
import es from '../../locale/es.json';
import { kitchenItem, kitchenTicket } from './__tests__/fixtures';
import KitchenTicketCard from './KitchenTicketCard.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'es') {
  return mountSale(KitchenTicketCard, {
    props: { ticket: kitchenTicket(), canRush: true, busy: false, timeZone: 'Europe/Madrid', ...props },
    locale,
  });
}

describe('KitchenTicketCard', () => {
  it('says «Order N», the time it was sent in the business’s zone and its state', async () => {
    // 11:05 UTC is 13:05 in Madrid on 2026-10-14 (summer time).
    const m = await setup({ ticket: kitchenTicket({ round_no: 2, received_at: '2026-10-14T11:05:00Z', status: 'preparing' }) });
    expect(m.find('pos-kitchen-ticket-t1-round').text()).toBe('Comanda 2');
    expect(m.find('pos-kitchen-ticket-t1-time').text()).toBe('13:05');
    expect(m.find('pos-kitchen-ticket-t1-status').text()).toBe('En preparación');
    expect(m.find('pos-kitchen-ticket-t1-status').attributes('data-status')).toBe('preparing');
    const canary = await setup({ ticket: kitchenTicket({ received_at: '2026-10-14T11:05:00Z' }), timeZone: 'Atlantic/Canary' });
    expect(canary.find('pos-kitchen-ticket-t1-time').text()).toBe('12:05');
  });

  it('names each state as the kitchen does, in English and in Spanish', async () => {
    for (const [locale, kitchen] of [
      ['es', kitchenEs],
      ['en', kitchenEn],
    ] as const) {
      for (const status of ['pending', 'preparing', 'ready', 'served', 'cancelled'] as const) {
        const m = await setup({ ticket: kitchenTicket({ status }) }, locale);
        expect(m.find('pos-kitchen-ticket-t1-status').text()).toBe(kitchen.kitchen.status[status]);
      }
    }
  });

  it('marks a rush round «Rush», and no other', async () => {
    const rush = await setup({ ticket: kitchenTicket({ priority: 'rush' }) });
    expect(rush.find('pos-kitchen-ticket-t1-rush-mark').text()).toBe('Urgente');
    expect(rush.find('pos-kitchen-ticket-t1').classes()).toContain('pos-kticket--rush');
    for (const priority of ['normal', 'vip'] as const) {
      const other = await setup({ ticket: kitchenTicket({ priority }) });
      expect(other.find('pos-kitchen-ticket-t1-rush-mark').exists()).toBe(false);
    }
  });

  it('lists its dishes with their quantity; a voided one is struck and says «Voided»', async () => {
    const ticket = kitchenTicket({
      items: [
        kitchenItem({ id: 'i1', name: 'Burger', quantity: '2.000' }),
        kitchenItem({ id: 'i2', name: 'Fries', quantity: '0.500', status: 'voided', void_reason: 'Wrong table' }),
      ],
    });
    const m = await setup({ ticket });
    expect(m.find('pos-kitchen-dish-i1').text()).toBe('2× Burger');
    expect(m.find('pos-kitchen-dish-i1').attributes('data-status')).toBe('pending');
    expect(m.find('pos-kitchen-dish-i1-voided').exists()).toBe(false);
    expect(m.find('pos-kitchen-dish-i1').classes()).not.toContain('pos-kticket__dish--voided');
    const voided = m.find('pos-kitchen-dish-i2');
    expect(voided.attributes('data-status')).toBe('voided');
    expect(voided.classes()).toContain('pos-kticket__dish--voided');
    expect(voided.find('.pos-kticket__dish-name').text()).toBe('0,5× Fries');
    expect(m.find('pos-kitchen-dish-i2-voided').text()).toBe('Anulado');
  });

  it('offers «Mark rush» on a round that cooks and says which way it goes', async () => {
    for (const status of ['pending', 'preparing'] as const) {
      const m = await setup({ ticket: kitchenTicket({ status }) });
      const button = m.find('pos-kitchen-ticket-t1-rush');
      expect(button.text()).toBe('Marcar urgente');
      await click(button.element);
      expect(m.wrapper.emitted('rush')).toEqual([[true]]);
    }
    const rushed = await setup({ ticket: kitchenTicket({ priority: 'rush' }) });
    expect(rushed.find('pos-kitchen-ticket-t1-rush').text()).toBe('Quitar urgente');
    await click(rushed.find('pos-kitchen-ticket-t1-rush').element);
    expect(rushed.wrapper.emitted('rush')).toEqual([[false]]);
  });

  it('never offers it on a round that no longer cooks, on a VIP one, or to whoever may not change tickets', async () => {
    for (const status of ['ready', 'served', 'cancelled'] as const) {
      const m = await setup({ ticket: kitchenTicket({ status }) });
      expect(m.find('pos-kitchen-ticket-t1-rush').exists()).toBe(false);
    }
    const vip = await setup({ ticket: kitchenTicket({ priority: 'vip' }) });
    expect(vip.find('pos-kitchen-ticket-t1-rush').exists()).toBe(false);
    const viewer = await setup({ canRush: false });
    expect(viewer.find('pos-kitchen-ticket-t1-rush').exists()).toBe(false);
  });

  it('waits while its rush is on its way', async () => {
    const m = await setup({ busy: true });
    expect((m.find('pos-kitchen-ticket-t1-rush').element as HTMLButtonElement).disabled).toBe(true);
  });

  it('the till’s words are the kitchen’s words (kitchen#112), in English and in Spanish', () => {
    for (const [sale, kitchen] of [
      [en, kitchenEn],
      [es, kitchenEs],
    ] as const) {
      const words = sale.sale.pos.kitchen.tickets;
      expect(words.status).toEqual(kitchen.kitchen.status);
      expect(words.rush).toBe(kitchen.kitchen.priority.rush);
      expect(words.voided).toBe(kitchen.kitchen.card.voided);
      expect(words.markRush).toBe(kitchen.kitchen.card.markRush);
      expect(words.clearRush).toBe(kitchen.kitchen.card.clearRush);
      expect(words.rushNoticeFailed).toBe(kitchen.kitchen.display.rushNoticeFailed);
    }
  });
});
