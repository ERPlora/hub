import { describe, expect, it } from 'vitest';

import { mountTable } from '../__tests__/mount-table';
import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import FloorTile from './FloorTile.vue';

async function tile(table: TableOut, more: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(FloorTile, { props: { table, now: NOW, timeZone: 'Europe/Madrid', settings: SETTINGS, ...more }, locale });
  const part = (name: string) => m.wrapper.find(`[data-part="${name}"]`);
  return { ...m, el: m.wrapper.element as HTMLElement, part, button: () => m.wrapper.find('button') };
}

describe('FloorTile', () => {
  it('positions the slot, centres its table and keeps logical coordinates', async () => {
    const fit = { spread: 2, box: 1.3, plane: { w: 800, h: 600 } };
    const t = await tile(tableRow({ position_x: 100, position_y: 40, width: 120 }), { fit });
    expect(t.part('number').text()).toBe('4');
    expect(t.part('line').text()).toBe('Available');
    expect(t.part('status').text()).toBe('Available · 4 pax');
    expect(t.el.getAttribute('data-status')).toBe('available');
    expect(t.el.getAttribute('data-testid')).toBe('table-floor-tile-t1');
    expect([t.el.dataset.x, t.el.dataset.y]).toEqual(['100', '40']);
    expect([t.el.style.left, t.el.style.top, t.el.style.width, t.el.style.height]).toEqual(['242px', '105.2px', '156px', '93.6px']);
    expect(t.el.getAttribute('role')).toBeNull();
    expect(t.button().attributes('aria-label')).toBe('Table 4 · Dining room · 4 pax · Available');
  });

  it('an occupied table shows elapsed time and guests, with its server only accessible', async () => {
    const t = await tile(occupied());
    expect(t.part('line').text()).toBe('0:35');
    expect(t.part('waiter').exists()).toBe(false);
    expect(t.part('status').text()).toBe('Occupied · 3/4 pax');
    expect(t.button().attributes('aria-label')).toBe('Table 4 · Dining room · 4 pax · Occupied · 3 guests · 35 min · Served by Luis');
    expect(t.wrapper.findComponent({ name: 'TableGlyph' }).exists()).toBe(true);
  });

  it('one guest is said in the singular, in English and in Spanish', async () => {
    expect((await tile(occupied({ guests: 1 }))).button().attributes('aria-label')).toContain('· Occupied · 1 guest · 35 min ·');
    expect((await tile(occupied({ guests: 1 }), {}, 'es')).button().attributes('aria-label')).toContain('· 1 comensal · 35 min ·');
  });

  it('a reservation paints its full name and hour on the label, including an erased customer', async () => {
    const hold = { label: 'Maximiliana Fernández', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 4, reserving: true };
    const t = await tile(tableRow({ status: 'reserved', hold }), {}, 'es');
    expect(t.part('hold-name').text()).toBe('Maximiliana Fernández');
    expect(t.part('hold-time').text()).toBe('· 20:00');
    expect(t.part('line').text()).toBe('20:00');
    expect(t.part('status').text()).toBe('Reservada · 4 pax');
    expect(t.button().attributes('title')).toContain('Reservada para Maximiliana Fernández');
    const erased = await tile(tableRow({ hold: { ...hold, label: '', erased: true } }), {}, 'es');
    expect(erased.part('hold-name').text()).toBe('Cliente borrado');
  });

  it('keeps a later reservation visible on an available table', async () => {
    const hold = { label: 'Ana', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 2, reserving: false };
    const t = await tile(tableRow({ hold }));
    expect(t.part('line').text()).toBe('Available');
    expect(t.part('hold-name').text()).toBe('Ana');
    expect(t.part('hold-time').text()).toBe('· 8:00 PM');
  });

  it('marks shape, inactivity, timer tone and destination state without losing written status', async () => {
    expect((await tile(tableRow({ shape: 'round' }))).el.classList.contains('table-tile--round')).toBe(true);
    expect((await tile(tableRow({ shape: 'rectangle' }))).el.classList.contains('table-tile--rectangle')).toBe(true);
    const blocked = await tile(tableRow({ status: 'blocked', blocked: true }));
    expect(blocked.part('status').text()).toBe('Blocked · 4 pax');
    const idle = await tile(tableRow({ is_active: false, in_service: false }), { editing: true });
    expect(idle.el.classList.contains('table-tile--inactive')).toBe(true);
    expect(idle.part('inactive').text()).toBe('Inactive');
    const critical = await tile(occupied({ since: '2026-10-14T18:00:00Z' }));
    expect(critical.el.getAttribute('data-timer')).toBe('critical');
    expect(critical.el.getAttribute('data-status')).toBe('occupied');
  });

  it('while picking a destination, an invalid table is dimmed and its button disabled', async () => {
    const t = await tile(occupied(), { pickable: false });
    expect(t.button().attributes('aria-disabled')).toBe('true');
    expect(t.button().attributes('tabindex')).toBe('-1');
    expect(t.el.classList.contains('table-tile--dimmed')).toBe(true);
    const ok = await tile(tableRow(), { pickable: true });
    expect(ok.el.classList.contains('table-tile--target')).toBe(true);
  });
});
