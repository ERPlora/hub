// A table on the floor plan (WORKBOOK «Plano de sala»; TABLE-F09): its number, its status written with
// its icon and colour (never the colour alone, tables#64), its seats or — occupied — the guests and
// the minutes they have been there («3 pax · 35 min») and who serves them; with a reservation of today,
// its name and its hour on one line (the name cut with «…», the hour never). Round tables are round.
import { describe, expect, it } from 'vitest';

import { mountTable } from '../__tests__/mount-table';
import { NOW, occupied, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import FloorTile from './FloorTile.vue';

async function tile(table: TableOut, more: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(FloorTile, { props: { table, now: NOW, timeZone: 'Europe/Madrid', ...more }, locale });
  const part = (name: string) => m.wrapper.find(`[data-part="${name}"]`);
  return { ...m, el: m.wrapper.element as HTMLElement, part };
}

describe('FloorTile', () => {
  it('a free table says its number, its seats and «Available», on its box of the plan', async () => {
    const t = await tile(tableRow({ position_x: 100, position_y: 40, width: 120 }));
    expect(t.part('number').text()).toBe('4');
    expect(t.part('line').text()).toBe('4 pax');
    expect(t.part('status').text()).toBe('Available');
    expect(t.el.getAttribute('data-status')).toBe('available');
    expect(t.el.getAttribute('data-testid')).toBe('table-floor-tile-t1');
    expect([t.el.style.left, t.el.style.top, t.el.style.width, t.el.style.height]).toEqual(['100px', '40px', '120px', '72px']);
    expect(t.el.getAttribute('role')).toBe('button');
    expect(t.el.getAttribute('aria-label')).toBe('Table 4 · Dining room · 4 pax · Available');
  });

  it('an occupied table says the guests, the minutes and who serves them', async () => {
    const t = await tile(occupied());
    expect(t.part('line').text()).toBe('3 pax · 35 min');
    expect(t.part('waiter').text()).toBe('Luis');
    expect(t.part('status').text()).toBe('Occupied');
    expect(t.el.getAttribute('aria-label')).toBe('Table 4 · Dining room · 4 pax · Occupied · 3 guests · 35 min · Served by Luis');
  });

  it('one guest is said in the singular, in English and in Spanish (hub#462)', async () => {
    expect((await tile(occupied({ guests: 1 }))).el.getAttribute('aria-label')).toContain('· Occupied · 1 guest · 35 min ·');
    expect((await tile(occupied({ guests: 1 }), {}, 'es')).el.getAttribute('aria-label')).toContain('· 1 comensal · 35 min ·');
  });

  it('a reservation of today paints its name and its hour, and an erased customer says so', async () => {
    const hold = { label: 'Maximiliana Fernández', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 4, reserving: true };
    const t = await tile(tableRow({ status: 'reserved', hold }), {}, 'es');
    expect(t.part('hold-name').text()).toBe('Maximiliana Fernández');
    expect(t.part('hold-time').text()).toBe('· 20:00');
    expect(t.part('status').text()).toBe('Reservada');
    expect(t.el.getAttribute('title')).toContain('Reservada para Maximiliana Fernández');
    const erased = await tile(tableRow({ hold: { ...hold, label: '', erased: true } }), {}, 'es');
    expect(erased.part('hold-name').text()).toBe('Cliente borrado');
  });

  it('a round table is round and a blocked or inactive one is greyed out', async () => {
    expect((await tile(tableRow({ shape: 'round' }))).el.classList.contains('table-tile--round')).toBe(true);
    const blocked = await tile(tableRow({ status: 'blocked', blocked: true }));
    expect(blocked.part('status').text()).toBe('Blocked');
    const idle = await tile(tableRow({ is_active: false, in_service: false }), { editing: true });
    expect(idle.el.classList.contains('table-tile--inactive')).toBe(true);
    expect(idle.part('inactive').text()).toBe('Inactive');
  });

  it('while picking a destination, a table that cannot be picked is dimmed and disabled', async () => {
    const t = await tile(occupied(), { pickable: false });
    expect(t.el.getAttribute('aria-disabled')).toBe('true');
    expect(t.el.classList.contains('table-tile--dimmed')).toBe(true);
    const ok = await tile(tableRow(), { pickable: true });
    expect(ok.el.classList.contains('table-tile--target')).toBe(true);
  });
});
