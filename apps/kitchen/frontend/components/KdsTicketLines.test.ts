// The dishes of a kitchen card as an Ionic list: each dish a row, and the dishes of a menu under its header, which says
// how many there are. A tap on a dish to do asks to mark it ready, on a done one to recall it; a struck or served dish
// never answers. The menu's header marks its dishes still to do. Without leave, nothing answers.
import { describe, expect, it } from 'vitest';

import { item } from '../__tests__/kitchen';
import { click, mountKitchen } from '../__tests__/mount-kitchen';
import type { ItemOut } from '../operations/tickets';
import KdsTicketLines from './KdsTicketLines.vue';

async function setup(items: ItemOut[], props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsTicketLines, { props: { items, showStation: false, canTap: true, canBumpMenus: true, ...props }, locale });
  return { ...m, emitted: () => m.wrapper.emitted() };
}

const MENU = { menu_name: 'MENU', menu_line_id: 'm1' };

describe('KdsTicketLines', () => {
  it('is an Ionic list; a menu is an Ionic item over its dishes that says how many there are', async () => {
    const s = await setup([item('i1', MENU), item('i2', MENU), item('i3')]);
    expect(s.wrapper.element.tagName.toLowerCase()).toBe('ion-list');
    const head = s.find('kitchen-menu-m1');
    expect(head.element.tagName.toLowerCase()).toBe('ion-item');
    expect(head.element.innerHTML).toContain('MENU');
    expect(head.element.innerHTML).toContain('2 dishes');
    expect(s.find('kitchen-line-i2').classes()).toContain('ep-order-ticket__dish--menu');
    expect(s.find('kitchen-line-i3').classes()).not.toContain('ep-order-ticket__dish--menu');
  });

  it('a tap on a dish to do marks it, on a done one recalls it; struck and served dishes do not answer', async () => {
    const s = await setup([
      item('i1'),
      item('i2', { status: 'ready' }),
      item('i3', { status: 'voided' }),
      item('i4', { status: 'cancelled' }),
      item('i5', { status: 'served' }),
    ]);
    for (const id of ['i1', 'i2', 'i3', 'i4', 'i5']) await click(s.find(`kitchen-line-${id}`).element);
    expect(s.emitted().bump).toEqual([[['i1']]]);
    expect(s.emitted().recall).toEqual([[['i2']]]);
    expect(['i3', 'i4', 'i5'].map((id) => s.find(`kitchen-line-${id}`).attributes('aria-disabled'))).toEqual(['true', 'true', 'true']);
  });

  it('the menu header marks the dishes of that menu still to do, and nothing else', async () => {
    const s = await setup([item('i1', MENU), item('i2', { ...MENU, status: 'ready' }), item('i3', MENU), item('i4')]);
    expect(s.find('kitchen-menu-m1').attributes('title')).toBe("Mark this menu's dishes ready");
    await click(s.find('kitchen-menu-m1').element);
    expect(s.emitted().bump).toEqual([[['i1', 'i3']]]);
  });

  it('the menu header does nothing once its dishes are done, or when the ticket no longer cooks', async () => {
    const done = await setup([item('i1', { ...MENU, status: 'ready' }), item('i2')]);
    await click(done.find('kitchen-menu-m1').element);
    expect(done.emitted().bump).toBeUndefined();
    expect(done.find('kitchen-menu-m1').attributes('aria-disabled')).toBe('true');

    const ready = await setup([item('i1', MENU)], { canBumpMenus: false });
    await click(ready.find('kitchen-menu-m1').element);
    expect(ready.emitted().bump).toBeUndefined();
  });

  it('without leave to change tickets, no dish answers', async () => {
    const s = await setup([item('i1'), item('i2', { status: 'ready' })], { canTap: false, canBumpMenus: false });
    await click(s.find('kitchen-line-i1').element);
    await click(s.find('kitchen-line-i2').element);
    expect(s.emitted().bump).toBeUndefined();
    expect(s.emitted().recall).toBeUndefined();
  });

  it('passes «All» on to the dishes, which then say their station', async () => {
    const s = await setup([item('i1', { station_name: 'Grill' })], { showStation: true });
    expect(s.find('kitchen-line-i1-station').text()).toBe('Grill');
  });

  it('counts the dishes of a menu in Spanish', async () => {
    const s = await setup([item('i1', MENU)], {}, 'es');
    expect(s.find('kitchen-menu-m1').element.innerHTML).toContain('1 plato');
    expect(s.find('kitchen-menu-m1').element.innerHTML).not.toContain('1 platos');
  });
});
