// flow: KITCHEN-F19, KITCHEN-F20 — «Tickets · N» in the head of what the check sent (SALE-F20): it follows the
// check's kitchen tickets live and opens «Order tickets», a card per round as the kitchen answers them (the newest
// round first), with the time in the business's zone. «Mark rush» there rushes the round through the kitchen's
// own operation; a refusal is read on top of the sheet, and a rush whose notice did not print says so.
import { describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, MANAGER, mountSale, settle } from '../../__tests__/mount-sale';
import { deferred, kitchenItem, kitchenTicket, refused } from './__tests__/fixtures';
import KitchenTickets from './KitchenTickets.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const BY_ORDER = 'kitchen.ticket.by_order';
const SETTINGS = 'kitchen.settings.get';
/** Who works the floor: sees the kitchen's tickets and may change them (KITCHEN-F14). */
const WAITER = { ...MANAGER, permissions: [...MANAGER.permissions, 'kitchen.view_ticket', 'kitchen.change_ticket'] };
/** Sees them, may not change them. */
const VIEWER = { ...MANAGER, permissions: [...MANAGER.permissions, 'kitchen.view_ticket'] };

const SECOND = kitchenTicket({ id: 't2', round_no: 2, received_at: '2026-10-14T11:20:00Z', status: 'pending', items: [kitchenItem({ id: 'i2', name: 'Soup' })] });
const FIRST = kitchenTicket({
  id: 't1',
  round_no: 1,
  received_at: '2026-10-14T11:00:00Z',
  status: 'ready',
  items: [kitchenItem({ id: 'i1', name: 'Burger' }), kitchenItem({ id: 'i3', name: 'Fries', status: 'voided', void_reason: 'Wrong table' })],
});

async function setup(options: { session?: typeof WAITER; locale?: 'en' | 'es' } = {}) {
  const m = await mountSale(KitchenTickets, { props: { orderId: 'o1' }, session: options.session ?? WAITER, locale: options.locale ?? 'es' });
  await m.live();
  return m;
}

async function opened(options: Parameters<typeof setup>[0] = {}) {
  const m = await setup(options);
  await m.result(BY_ORDER, { tickets: [SECOND, FIRST] });
  await click(m.find('pos-kitchen-tickets-open').element);
  await settle();
  return m;
}

const rushCalls = (m: Awaited<ReturnType<typeof setup>>) =>
  m.sent().filter((call) => call.path === '/api/kitchen/tickets/set_rush').map((call) => call.body);

describe('KitchenTickets: the chip', () => {
  it('follows the check’s kitchen tickets and the kitchen’s settings (its time zone)', async () => {
    const m = await setup();
    expect(m.params(BY_ORDER)).toEqual([{ order_id: 'o1' }]);
    expect(m.params(SETTINGS)).toHaveLength(1);
  });

  it('shows nothing while they load or while the kitchen has none', async () => {
    const m = await setup();
    expect(m.find('pos-kitchen-tickets-open').exists()).toBe(false);
    await m.result(BY_ORDER, { tickets: [] });
    expect(m.find('pos-kitchen-tickets-open').exists()).toBe(false);
  });

  it('says how many rounds the kitchen has, in Spanish and in English', async () => {
    const m = await setup();
    await m.result(BY_ORDER, { tickets: [SECOND, FIRST] });
    const chip = m.find('pos-kitchen-tickets-open');
    expect(chip.text()).toBe('Comandas · 2');
    expect(chip.attributes('aria-label')).toBe('Comandas de la cuenta');
    const english = await setup({ locale: 'en' });
    await english.result(BY_ORDER, { tickets: [FIRST] });
    expect(english.find('pos-kitchen-tickets-open').text()).toBe('Tickets · 1');
  });
});

describe('KitchenTickets: «Order tickets» (KITCHEN-F19)', () => {
  it('opens a card per round, in the kitchen’s order: the newest first', async () => {
    const m = await opened();
    expect(m.find('pos-kitchen-tickets-title').text()).toBe('Comandas de la cuenta');
    const cards = m.wrapper.findAll('[data-testid^="pos-kitchen-ticket-"][data-round]');
    expect(cards.map((card) => card.attributes('data-round'))).toEqual(['2', '1']);
    expect(m.find('pos-kitchen-ticket-t1-status').text()).toBe('Lista');
    expect(m.find('pos-kitchen-dish-i3-voided').text()).toBe('Anulado');
  });

  it('paints the time in the business’s zone once the kitchen says it', async () => {
    const m = await opened();
    expect(m.find('pos-kitchen-ticket-t2-time').text()).toBe('13:20');
    await m.result(SETTINGS, { timezone: 'Atlantic/Canary' });
    expect(m.find('pos-kitchen-ticket-t2-time').text()).toBe('12:20');
  });

  it('changes by itself, open, when the kitchen moves a round or the till voids a dish', async () => {
    const m = await opened();
    const moved = { ...SECOND, status: 'preparing' as const, items: [kitchenItem({ id: 'i2', name: 'Soup', status: 'voided' })] };
    await m.result(BY_ORDER, { tickets: [moved, FIRST] }, {}, 2);
    expect(m.find('pos-kitchen-ticket-t2-status').text()).toBe('En preparación');
    expect(m.find('pos-kitchen-dish-i2-voided').text()).toBe('Anulado');
    expect(m.find('pos-kitchen-tickets-title').exists()).toBe(true);
  });

  it('says so when they cannot be read, and «Retry» asks again', async () => {
    const m = await opened();
    m.net.lastStream().push(errorFrame(m.subId(BY_ORDER), 'internal_error'));
    await flush();
    expect(m.find('pos-kitchen-tickets-load-error').text()).toContain('No se pudieron cargar las comandas de la cuenta.');
    const streams = m.net.streams.length;
    await click(m.find('pos-kitchen-tickets-retry').element);
    await m.reopen();
    expect(m.net.streams.length).toBeGreaterThan(streams);
  });

  it('✕ closes it', async () => {
    const m = await opened();
    await click(m.find('pos-kitchen-tickets-close').element);
    expect(m.find('pos-kitchen-tickets-title').exists()).toBe(false);
  });
});

describe('KitchenTickets: «Mark rush» from the till (KITCHEN-F20)', () => {
  it('rushes the round through the kitchen and takes the rush away the same way', async () => {
    const m = await opened();
    m.answer(200, { ...SECOND, priority: 'rush', print_error: null });
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect(rushCalls(m)).toEqual([{ ticket_id: 't2', rush: true }]);
    await m.result(BY_ORDER, { tickets: [{ ...SECOND, priority: 'rush' }, FIRST] }, {}, 2);
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect(rushCalls(m)).toEqual([
      { ticket_id: 't2', rush: true },
      { ticket_id: 't2', rush: false },
    ]);
    expect(m.find('pos-kitchen-tickets-error').exists()).toBe(false);
  });

  it('waits while the rush is on its way', async () => {
    const m = await opened();
    const answer = deferred();
    m.net.onApi(() => answer.promise);
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect((m.find('pos-kitchen-ticket-t2-rush').element as HTMLButtonElement).disabled).toBe(true);
    answer.resolve(Response.json({ ...SECOND, priority: 'rush', print_error: null }));
    await settle();
    expect((m.find('pos-kitchen-ticket-t2-rush').element as HTMLButtonElement).disabled).toBe(false);
  });

  it('a refusal is read on top of the sheet, in the server’s words', async () => {
    const m = await opened();
    m.net.onApi(() => refused('kitchen.ticket_not_cooking', 'Esa comanda ya no se cocina.'));
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    const error = m.find('pos-kitchen-tickets-error');
    expect(error.text()).toBe('Esa comanda ya no se cocina.');
    expect(error.attributes('role')).toBe('alert');
  });

  it('a failure nobody worded says the till’s own sentence', async () => {
    const m = await opened();
    m.net.onApi(() => refused('internal_error', 'Internal error', 500));
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect(m.find('pos-kitchen-tickets-error').text()).toBe('No se pudo actualizar la comanda');
  });

  it('a rush whose notice did not print says so, until a later rush prints', async () => {
    const m = await opened();
    m.answer(200, { ...SECOND, priority: 'rush', print_error: 'No printer' });
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect(m.find('pos-kitchen-tickets-print-warning').text()).toBe(
      'No se ha podido imprimir el aviso de urgencia. Avisa a cocina de viva voz y revisa su impresora.',
    );
    await m.result(BY_ORDER, { tickets: [{ ...SECOND, priority: 'rush' }, FIRST] }, {}, 2);
    m.answer(200, { ...SECOND, priority: 'normal', print_error: null });
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect(m.find('pos-kitchen-tickets-print-warning').exists()).toBe(true);
    await m.result(BY_ORDER, { tickets: [SECOND, FIRST] }, {}, 3);
    m.answer(200, { ...SECOND, priority: 'rush', print_error: null });
    await click(m.find('pos-kitchen-ticket-t2-rush').element);
    expect(m.find('pos-kitchen-tickets-print-warning').exists()).toBe(false);
  });

  it('whoever may not change tickets sees the rounds, without the button', async () => {
    const m = await opened({ session: VIEWER });
    expect(m.find('pos-kitchen-ticket-t2').exists()).toBe(true);
    expect(m.find('pos-kitchen-ticket-t2-rush').exists()).toBe(false);
  });
});
