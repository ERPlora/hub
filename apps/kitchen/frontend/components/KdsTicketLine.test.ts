// One dish on a card of the kitchen display: an Ionic item with the quantity large («2×»), the name, the options in
// bold, the note in italics, «Voided» and its reason, the station with its colour and «Paper only»; at its end an
// icon that says the dish's state, named for a screen reader. The whole row is the target: it answers a tap only when
// the card lets it, and then it is a button.
import { describe, expect, it } from 'vitest';

import { item } from '../__tests__/kitchen';
import { click, mountKitchen, said } from '../__tests__/mount-kitchen';
import type { ItemOut } from '../operations';
import KdsTicketLine from './KdsTicketLine.vue';

async function setup(line: ItemOut, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsTicketLine, { props: { line, showStation: false, tappable: true, inMenu: false, ...props }, locale });
  const row = () => m.find(`kitchen-line-${line.id}`);
  return { ...m, row, emitted: () => m.wrapper.emitted() };
}

describe('KdsTicketLine', () => {
  it('is an Ionic item with the quantity as «2×», the name, its options and its note', async () => {
    const s = await setup(item('i1', { quantity: '2.000', name: 'Burger', modifiers: ['+CHEESE', 'Rare'], notes: 'Allergic to nuts' }));
    expect(s.row().element.tagName.toLowerCase()).toBe('ion-item');
    expect(s.row().find('.ep-order-ticket__qty').text()).toBe('2×');
    expect(s.row().find('.ep-order-ticket__name').text()).toBe('Burger');
    expect(s.find('kitchen-line-i1-modifiers').text()).toBe('+CHEESE, Rare');
    expect(s.row().find('.ep-order-ticket__dish-note').text()).toBe('Allergic to nuts');
    const text = said(s.row().element);
    expect(text.indexOf('+CHEESE')).toBeLessThan(text.indexOf('Allergic to nuts'));
  });

  it('says the state of the dish with an icon at its end, named for a screen reader', async () => {
    const states: Array<[ItemOut['status'], string]> = [
      ['pending', 'To prepare'],
      ['preparing', 'Preparing'],
      ['ready', 'Ready'],
      ['served', 'Served'],
      ['voided', 'Voided'],
      ['cancelled', 'Cancelled'],
    ];
    for (const [status, label] of states) {
      const s = await setup(item(`i-${status}`, { status }));
      const icon = s.find(`kitchen-line-i-${status}-state`);
      expect(icon.attributes('slot'), status).toBe('end');
      expect(icon.attributes('aria-label'), status).toBe(label);
      expect(s.row().attributes('data-status')).toBe(status);
    }
  });

  it('a tap asks to mark it ready or to recall it, and the row is a button only when it answers', async () => {
    const todo = await setup(item('i1'));
    expect(todo.row().attributes('title')).toBe('Tap to mark ready');
    expect((todo.row().element as HTMLElement & { button?: boolean }).button).toBe(true);
    await click(todo.row().element);
    expect(todo.emitted().tap).toHaveLength(1);

    const done = await setup(item('i2', { status: 'ready' }));
    expect(done.row().attributes('title')).toBe('Tap to recall');

    const still = await setup(item('i3'), { tappable: false });
    await click(still.row().element);
    expect(still.emitted().tap).toBeUndefined();
    expect(still.row().attributes('aria-disabled')).toBe('true');
    expect(still.row().attributes('title')).toBeUndefined();
    expect((still.row().element as HTMLElement & { button?: boolean }).button).toBe(false);
  });

  it('a voided dish says «Voided» and why', async () => {
    const s = await setup(item('i1', { status: 'voided', void_reason: 'Cold' }), { tappable: false });
    expect(s.row().find('.ep-order-ticket__void').text()).toContain('Voided');
    expect(s.row().find('.ep-order-ticket__void').text()).toContain('Cold');
  });

  it('shows the station with its colour in «All», and an icon for a paper-only station', async () => {
    const line = item('i1', { station_id: 's1', station_name: 'Bar', station_color: '#228BE6', destination: 'printer' });
    const s = await setup(line, { showStation: true });
    expect(s.find('kitchen-line-i1-station').text()).toBe('Bar');
    expect(s.row().find('.ep-station-dot').attributes('style')).toContain('background');
    expect(s.find('kitchen-line-i1-paper').text()).toBe('Paper only');
    const bare = await setup(item('i2', { station_name: '' }), { showStation: true });
    expect(bare.find('kitchen-line-i2-station').text()).toBe('No station');
    const alone = await setup(item('i3', { station_name: 'Bar' }));
    expect(alone.find('kitchen-line-i3-station').exists()).toBe(false);
  });

  it('hangs from its menu when it is one of its dishes', async () => {
    const s = await setup(item('i1', { menu_line_id: 'm1', menu_name: 'MENU' }), { inMenu: true });
    expect(s.row().classes()).toContain('ep-order-ticket__dish--menu');
    expect(s.row().attributes('data-menu')).toBe('m1');
    const plain = await setup(item('i2'));
    expect(plain.row().attributes('data-menu')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup(item('i1', { status: 'ready', destination: 'printer' }), {}, 'es');
    expect(s.find('kitchen-line-i1-state').attributes('aria-label')).toBe('Listo');
    expect(s.row().attributes('title')).toBe('Toca para recuperar');
    expect(s.find('kitchen-line-i1-paper').text()).toBe('Solo papel');
  });
});
