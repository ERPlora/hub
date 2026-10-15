// A ticket on the kitchen display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F14): the label (or
// the type), «Waiter: …», the Rush/VIP, «Round N» and «Ready» marks, the clock and «#0012»; each dish with
// its quantity large, its note and, in «All», its station; a voided dish struck with its reason that does
// not answer; the border green, amber or red by the minutes since it was sent. One tap marks a dish ready,
// a tap on a struck one recalls it; the header or «Ready» marks every dish on screen. A viewer gets no
// buttons and taps do nothing.
import { describe, expect, it } from 'vitest';

import { item, NOW, SETTINGS, ticket } from '../__tests__/kitchen';
import { click, mountKitchen } from '../__tests__/mount-kitchen';
import type { TicketOut } from '../operations';
import KdsTicket from './KdsTicket.vue';

async function setup(t: TicketOut, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsTicket, {
    props: { ticket: t, now: NOW, settings: SETTINGS, showStation: false, canChange: true, canServe: true, ...props },
    locale,
  });
  const card = () => m.find(`kitchen-card-${t.id}`);
  return { ...m, card, emitted: () => m.wrapper.emitted() };
}

const MINUTE = 60_000;

describe('KdsTicket', () => {
  it('paints the header and the dishes as the old card', async () => {
    const t = ticket('t1', {
      priority: 'rush',
      round_no: 2,
      received_at: new Date(NOW.getTime() - 65_000).toISOString(),
      items: [item('i1', { quantity: '2.000', name: 'Burger', notes: 'Well done' }), item('i2', { name: 'Fries' })],
    });
    const s = await setup(t);
    expect(s.find('kitchen-card-t1-label').text()).toBe('Table 4');
    expect(s.find('kitchen-card-t1-waiter').text()).toBe('Waiter: luis');
    expect(s.find('kitchen-card-t1-priority').text()).toBe('Rush');
    expect(s.find('kitchen-card-t1-round').text()).toBe('Round 2');
    expect(s.find('kitchen-card-t1-timer').text()).toBe('1:05');
    expect(s.find('kitchen-card-t1-number').text()).toBe('#0012');
    expect(s.find('kitchen-line-i1').text()).toContain('2');
    expect(s.find('kitchen-line-i1').text()).toContain('Well done');
    expect(s.card().attributes('aria-label')).toBe('Ticket 0012');
  });

  it('says the type when there is no label, and no round mark on the first round', async () => {
    const s = await setup(ticket('t1', { label: '', order_type: 'takeaway' }));
    expect(s.find('kitchen-card-t1-label').text()).toBe('Takeaway');
    expect(s.find('kitchen-card-t1-round').exists()).toBe(false);
  });

  it('turns amber and red with the minutes, grey without colours, and hides the clock if asked', async () => {
    const at = (minutes: number) => new Date(NOW.getTime() - minutes * MINUTE).toISOString();
    expect((await setup(ticket('a', { received_at: at(5) }))).card().attributes('data-sem')).toBe('ok');
    expect((await setup(ticket('b', { received_at: at(16) }))).card().attributes('data-sem')).toBe('warning');
    expect((await setup(ticket('c', { received_at: at(31) }))).card().attributes('data-sem')).toBe('critical');
    const off = await setup(ticket('d', { received_at: at(31) }), { settings: { ...SETTINGS, color_coding: false, show_timer: false } });
    expect(off.card().attributes('data-sem')).toBe('off');
    expect(off.find('kitchen-card-d-timer').exists()).toBe(false);
  });

  it('a tap marks a dish ready, a tap on a struck one recalls it; a voided dish does not answer', async () => {
    const t = ticket('t1', {
      status: 'preparing',
      items: [item('i1'), item('i2', { status: 'ready' }), item('i3', { status: 'voided', void_reason: 'Cold' })],
    });
    const s = await setup(t);
    await click(s.find('kitchen-line-i1').element);
    await click(s.find('kitchen-line-i2').element);
    await click(s.find('kitchen-line-i3').element);
    expect(s.emitted().bump).toEqual([[['i1']]]);
    expect(s.emitted().recall).toEqual([[['i2']]]);
    expect(s.find('kitchen-line-i3').text()).toContain('Voided');
    expect(s.find('kitchen-line-i3').text()).toContain('Cold');
    expect(s.find('kitchen-line-i3').attributes('aria-disabled')).toBe('true');
  });

  it('the header and «Ready» mark every dish on screen; rush, recall and served say what they do', async () => {
    const t = ticket('t1', { status: 'preparing', items: [item('i1'), item('i2', { status: 'ready' })] });
    const s = await setup(t);
    await click(s.find('kitchen-card-t1-head').element);
    await click(s.find('kitchen-card-t1-bump').element);
    await click(s.find('kitchen-card-t1-rush').element);
    await click(s.find('kitchen-card-t1-recall').element);
    expect(s.emitted().bump).toEqual([[[]], [[]]]);
    expect(s.emitted().rush).toEqual([[true]]);
    expect(s.emitted().recall).toEqual([[[]]]);
    expect(s.find('kitchen-card-t1-rush').text()).toBe('Mark rush');
    expect(s.find('kitchen-card-t1-served').exists()).toBe(false);
  });

  it('a rush ticket offers «Remove rush»; a VIP one offers neither', async () => {
    const rush = await setup(ticket('r', { priority: 'rush' }));
    expect(rush.find('kitchen-card-r-rush').text()).toBe('Remove rush');
    await click(rush.find('kitchen-card-r-rush').element);
    expect(rush.emitted().rush).toEqual([[false]]);
    const vip = await setup(ticket('v', { priority: 'vip' }));
    expect(vip.find('kitchen-card-v-rush').exists()).toBe(false);
  });

  it('a ready ticket offers «Recall» and «Served»', async () => {
    const s = await setup(ticket('t1', { status: 'ready', items: [item('i1', { status: 'ready' })] }));
    expect(s.find('kitchen-card-t1-status').text()).toBe('Ready');
    expect(s.find('kitchen-card-t1-bump').exists()).toBe(false);
    await click(s.find('kitchen-card-t1-served').element);
    expect(s.emitted().serve).toHaveLength(1);
  });

  it('shows the station in «All» and an icon for paper-only dishes', async () => {
    const t = ticket('t1', {
      items: [item('i1', { station_id: 's1', station_name: 'Bar', station_color: '#228BE6', destination: 'printer' })],
    });
    const s = await setup(t, { showStation: true });
    expect(s.find('kitchen-line-i1-station').text()).toBe('Bar');
    expect(s.find('kitchen-line-i1-paper').exists()).toBe(true);
  });

  it('is only to look at without the permission to change tickets', async () => {
    const s = await setup(ticket('t1'), { canChange: false, canServe: false });
    await click(s.find('kitchen-line-t1-1').element);
    await click(s.find('kitchen-card-t1-head').element);
    expect(s.emitted().bump).toBeUndefined();
    expect(s.find('kitchen-card-t1-foot').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup(ticket('t1', { priority: 'rush', round_no: 3 }), {}, 'es');
    expect(s.find('kitchen-card-t1-waiter').text()).toBe('Camarero: luis');
    expect([s.find('kitchen-card-t1-priority').text(), s.find('kitchen-card-t1-round').text()]).toEqual(['Urgente', 'Ronda 3']);
    expect(s.find('kitchen-card-t1-bump').text()).toBe('Listo');
  });
});
