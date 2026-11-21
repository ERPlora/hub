// A ticket on the kitchen display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F14), an Ionic card: the label (or
// the type), «Waiter: …», the status, Rush/VIP and «Round N» pills, the clock with the wait in words and «#0012»; each
// dish with its quantity large, its note and, in «All», its station; a voided dish struck with its reason that does
// not answer; the stripe on top green, amber or red by the minutes since it was sent. One tap marks a dish ready, a
// tap on a struck one recalls it; the header or «Ready» marks every dish on screen; «⋮» holds rush and recall. A
// viewer gets no buttons and taps do nothing.
import { describe, expect, it } from 'vitest';

import { item, NOW, SETTINGS, ticket } from '../__tests__/kitchen';
import { click, mountKitchen, PopoverStub, said } from '../__tests__/mount-kitchen';
import type { TicketOut } from '../operations';
import KdsTicket from './KdsTicket.vue';

async function setup(t: TicketOut, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsTicket, {
    props: { ticket: t, now: NOW, settings: SETTINGS, showStation: false, canChange: true, canServe: true, ...props },
    stubs: { IonPopover: PopoverStub },
    locale,
  });
  const card = () => m.find(`kitchen-card-${t.id}`);
  const more = () => click(m.find(`kitchen-card-${t.id}-more`).element);
  return { ...m, card, more, emitted: () => m.wrapper.emitted() };
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
    expect(said(s.find('kitchen-line-i1').element)).toContain('2×');
    expect(said(s.find('kitchen-line-i1').element)).toContain('Well done');
    expect(s.card().attributes('aria-label')).toBe('Ticket 0012');
    expect(s.card().find('ion-card').exists()).toBe(true);
    expect(s.card().classes()).toContain('ep-order-ticket');
    expect(s.card().find('ion-card').classes()).toEqual(expect.arrayContaining(['ep-order-ticket__card', 'ep-surface']));
  });

  it('says the type when there is no label, and no round mark on the first round', async () => {
    const s = await setup(ticket('t1', { label: '', order_type: 'takeaway' }));
    expect(s.find('kitchen-card-t1-label').text()).toBe('Takeaway');
    expect(s.find('kitchen-card-t1-round').exists()).toBe(false);
  });

  it('turns amber and red with the minutes and says so in words, grey and silent without colours, and hides the clock if asked', async () => {
    const at = (minutes: number) => new Date(NOW.getTime() - minutes * MINUTE).toISOString();
    const ok = await setup(ticket('a', { received_at: at(5) }));
    expect([ok.card().attributes('data-sem'), ok.find('kitchen-card-a-wait').text()]).toEqual(['ok', 'On time']);
    const amber = await setup(ticket('b', { received_at: at(16) }));
    expect([amber.card().attributes('data-sem'), amber.find('kitchen-card-b-wait').text()]).toEqual(['warning', 'Warning']);
    const red = await setup(ticket('c', { received_at: at(31) }));
    expect([red.card().attributes('data-sem'), red.find('kitchen-card-c-wait').text()]).toEqual(['critical', 'Late']);
    const off = await setup(ticket('d', { received_at: at(31) }), { settings: { ...SETTINGS, color_coding: false, show_timer: false } });
    expect(off.card().attributes('data-sem')).toBe('off');
    expect(off.find('kitchen-card-d-wait').exists()).toBe(false);
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
    expect(said(s.find('kitchen-line-i3').element)).toContain('Voided');
    expect(said(s.find('kitchen-line-i3').element)).toContain('Cold');
    expect(s.find('kitchen-line-i3').attributes('aria-disabled')).toBe('true');
  });

  it('the header and «Ready» mark every dish on screen; rush and recall wait in «⋮» and say what they do', async () => {
    const t = ticket('t1', { status: 'preparing', items: [item('i1'), item('i2', { status: 'ready' })] });
    const s = await setup(t);
    await click(s.find('kitchen-card-t1-head').element);
    await click(s.find('kitchen-card-t1-bump').element);
    expect(s.find('kitchen-card-t1-rush').exists()).toBe(false);
    await s.more();
    expect(said(s.find('kitchen-card-t1-rush').element)).toBe('Mark rush');
    await click(s.find('kitchen-card-t1-rush').element);
    await s.more();
    await click(s.find('kitchen-card-t1-recall').element);
    expect(s.emitted().bump).toEqual([[[]], [[]]]);
    expect(s.emitted().rush).toEqual([[true]]);
    expect(s.emitted().recall).toEqual([[[]]]);
    expect(s.find('kitchen-card-t1-served').exists()).toBe(false);
  });

  it('a rush ticket offers «Remove rush»; a VIP one offers neither', async () => {
    const rush = await setup(ticket('r', { priority: 'rush' }));
    await rush.more();
    expect(said(rush.find('kitchen-card-r-rush').element)).toBe('Remove rush');
    await click(rush.find('kitchen-card-r-rush').element);
    expect(rush.emitted().rush).toEqual([[false]]);
    const vip = await setup(ticket('v', { priority: 'vip' }));
    expect(vip.find('kitchen-card-v-more').exists()).toBe(false);
    expect(vip.find('kitchen-card-v-rush').exists()).toBe(false);
  });

  it('a ready ticket offers «Served» and, in «⋮», «Recall»', async () => {
    const s = await setup(ticket('t1', { status: 'ready', items: [item('i1', { status: 'ready' })] }));
    expect(s.find('kitchen-card-t1-status').text()).toBe('Ready');
    expect(s.find('kitchen-card-t1-bump').exists()).toBe(false);
    await click(s.find('kitchen-card-t1-served').element);
    expect(s.emitted().serve).toHaveLength(1);
    await s.more();
    await click(s.find('kitchen-card-t1-recall').element);
    expect(s.emitted().recall).toEqual([[[]]]);
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

  it('shows the options chosen under the dish, before its note (KITCHEN-F07)', async () => {
    const t = ticket('t1', {
      items: [
        item('i1', { name: 'Burger', modifiers: ['+CHEESE', '-ONION', 'Rare'], notes: 'Allergic to nuts' }),
        item('i2', { name: 'Fries' }),
      ],
    });
    const s = await setup(t);
    expect(s.find('kitchen-line-i1-modifiers').text()).toBe('+CHEESE, -ONION, Rare');
    const text = said(s.find('kitchen-line-i1').element);
    expect(text.indexOf('+CHEESE')).toBeLessThan(text.indexOf('Allergic to nuts'));
    expect(s.find('kitchen-line-i2-modifiers').exists()).toBe(false);
  });

  it('puts the dishes of a menu under its header, with how many there are (KITCHEN-F06)', async () => {
    const t = ticket('t1', {
      items: [
        item('i1', { name: 'Lentils', menu_name: 'MENU', menu_line_id: 'm1' }),
        item('i2', { name: 'Steak', menu_name: 'MENU', menu_line_id: 'm1', modifiers: ['Rare'] }),
        item('i3', { name: 'Salad', menu_name: 'MENU', menu_line_id: 'm2' }),
        item('i4', { name: 'Burger' }),
      ],
    });
    const s = await setup(t);
    const head = said(s.find('kitchen-menu-m1').element);
    expect(head).toContain('MENU');
    expect(head).toContain('2 dishes');
    // One dish is «1 dish», never «1 dishes».
    expect(said(s.find('kitchen-menu-m2').element)).toContain('1 dish');
    expect(said(s.find('kitchen-menu-m2').element)).not.toContain('1 dishes');
    // The header carries the menu, never a dish's options; the dishes follow it in order, inside the menu.
    expect(head).not.toContain('Rare');
    const order = s.wrapper.findAll('[data-testid^="kitchen-menu-"], [data-testid^="kitchen-line-"]')
      .map((node) => node.attributes('data-testid'))
      .filter((id) => !id?.endsWith('-modifiers') && !id?.endsWith('-state'));
    expect(order).toEqual(['kitchen-menu-m1', 'kitchen-line-i1', 'kitchen-line-i2', 'kitchen-menu-m2', 'kitchen-line-i3', 'kitchen-line-i4']);
    expect(s.find('kitchen-line-i2').attributes('data-menu')).toBe('m1');
    expect(s.find('kitchen-line-i4').attributes('data-menu')).toBeUndefined();
  });

  it('keeps the allergy on every dish of a menu with only that dish’s matches', async () => {
    const t = ticket('t1', {
      items: [
        item('i1', {
          name: 'Lentils',
          menu_name: 'MENU',
          menu_line_id: 'm1',
          allergy: ['milk'],
          allergy_in_dish: [],
        }),
        item('i2', {
          name: 'Flan',
          menu_name: 'MENU',
          menu_line_id: 'm1',
          allergy: ['milk'],
          allergy_in_dish: ['milk'],
        }),
      ],
    });
    const s = await setup(t);
    expect(s.find('kitchen-line-i1-allergy').text()).toContain('Allergy: Milk');
    expect(s.find('kitchen-line-i1-allergy-contains').exists()).toBe(false);
    expect(s.find('kitchen-line-i2-allergy').text()).toContain('Allergy: Milk');
    expect(s.find('kitchen-line-i2-allergy-contains').text()).toBe('The dish contains Milk');
  });

  it('a tap on the menu header marks ready the dishes of that menu still to do, and nothing else', async () => {
    const t = ticket('t1', {
      status: 'preparing',
      items: [
        item('i1', { menu_name: 'MENU', menu_line_id: 'm1' }),
        item('i2', { menu_name: 'MENU', menu_line_id: 'm1', status: 'ready' }),
        item('i3', { menu_name: 'MENU', menu_line_id: 'm1' }),
        item('i4'),
      ],
    });
    const s = await setup(t);
    await click(s.find('kitchen-menu-m1').element);
    expect(s.emitted().bump).toEqual([[['i1', 'i3']]]);
  });

  it('the menu header does nothing once its dishes are done, or for who may not change tickets', async () => {
    const done = ticket('t1', {
      status: 'preparing',
      items: [item('i1', { menu_name: 'MENU', menu_line_id: 'm1', status: 'ready' }), item('i2')],
    });
    const s = await setup(done);
    await click(s.find('kitchen-menu-m1').element);
    expect(s.emitted().bump).toBeUndefined();
    expect(s.find('kitchen-menu-m1').attributes('aria-disabled')).toBe('true');

    const viewer = await setup(ticket('t2', { items: [item('j1', { menu_name: 'MENU', menu_line_id: 'm9' })] }), { canChange: false });
    await click(viewer.find('kitchen-menu-m9').element);
    expect(viewer.emitted().bump).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup(ticket('t1', { priority: 'rush', round_no: 3 }), {}, 'es');
    expect(s.find('kitchen-card-t1-waiter').text()).toBe('Camarero: luis');
    expect([s.find('kitchen-card-t1-priority').text(), s.find('kitchen-card-t1-round').text()]).toEqual(['Urgente', 'Ronda 3']);
    expect(s.find('kitchen-card-t1-bump').text()).toBe('Listo');
  });

  it('counts the dishes of a menu in Spanish', async () => {
    const t = ticket('t1', {
      items: [
        item('i1', { menu_name: 'MENÚ', menu_line_id: 'm1' }),
        item('i2', { menu_name: 'MENÚ', menu_line_id: 'm2' }),
        item('i3', { menu_name: 'MENÚ', menu_line_id: 'm2' }),
      ],
    });
    const s = await setup(t, {}, 'es');
    expect(said(s.find('kitchen-menu-m1').element)).toContain('1 plato');
    expect(said(s.find('kitchen-menu-m1').element)).not.toContain('1 platos');
    expect(said(s.find('kitchen-menu-m2').element)).toContain('2 platos');
  });
});
