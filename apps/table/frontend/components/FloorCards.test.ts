import { describe, expect, it } from 'vitest';

import { mountTable } from '../__tests__/mount-table';
import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import FloorCards from './FloorCards.vue';

const HOLD = { label: 'Maximiliana Fernández', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 4, reserving: true };
const ROOM: TableOut[] = [
  tableRow({ id: 't10', number: '10', status: 'reserved', hold: HOLD }),
  occupied({ id: 't2', number: '2', since: '2026-10-14T18:30:00Z' }),
  tableRow({ id: 't1', number: '1' }),
];

async function cards(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(FloorCards, { props: { tables: ROOM, now: NOW, timeZone: 'Europe/Madrid', settings: SETTINGS, ...props }, locale });
  const card = (id: string) => m.wrapper.find(`[data-testid="table-floor-tile-${id}"]`);
  const part = (id: string, name: string) => card(id).find(`[data-part="${name}"]`);
  const selected = () => (m.wrapper.emitted('select') ?? []).map(([table]) => (table as TableOut).id);
  return { ...m, card, part, selected };
}

describe('FloorCards', () => {
  it('lists the tables by number, each a button named in full with its miniature', async () => {
    const c = await cards();
    const list = c.wrapper.find('[data-testid="table-floor-cards"]');
    expect(list.attributes('aria-label')).toBe('Tables by number');
    const ids = c.wrapper.findAll('[data-testid^="table-floor-tile-"]').map((el) => el.attributes('data-testid'));
    expect(ids).toEqual(['table-floor-tile-t1', 'table-floor-tile-t2', 'table-floor-tile-t10']);
    expect(c.card('t2').element.tagName).toBe('BUTTON');
    expect(c.card('t2').attributes('data-status')).toBe('occupied');
    expect(c.card('t2').attributes('aria-label')).toBe('Table 2 · Dining room · 4 pax · Occupied · 3 guests · 70 min · Served by Luis');
    expect(c.card('t2').find('.table-glyph--mini').exists()).toBe(true);
  });

  it('says the number, the guests or the reservation, the status and the time', async () => {
    const c = await cards();
    expect(['number', 'meta', 'status', 'time'].map((name) => c.part('t2', name).text())).toEqual(['2', '3/4 pax', 'Occupied', '1:10']);
    expect(c.part('t2', 'time').attributes('data-tone')).toBe('warning');
    expect(['number', 'meta', 'status'].map((name) => c.part('t1', name).text())).toEqual(['1', '4 pax', 'Available']);
    expect(c.part('t1', 'time').exists()).toBe(false);
    expect(['meta', 'status'].map((name) => c.part('t10', name).text())).toEqual(['Maximiliana Fernández · 8:00 PM', 'Reserved']);
  });

  it('a tap picks a table; while picking, only the tables that may be picked answer', async () => {
    const c = await cards();
    await c.card('t1').trigger('click');
    expect(c.selected()).toEqual(['t1']);
    const picking = await cards({ pick: (table: TableOut) => table.status === 'available' });
    expect(picking.card('t2').attributes('disabled')).toBeDefined();
    expect(picking.card('t2').classes()).toContain('floor-card--dimmed');
    expect(picking.card('t1').classes()).toContain('floor-card--target');
    await picking.card('t2').trigger('click');
    await picking.card('t1').trigger('click');
    expect(picking.selected()).toEqual(['t1']);
  });

  it('speaks Spanish', async () => {
    const c = await cards({}, 'es');
    expect(c.wrapper.find('[data-testid="table-floor-cards"]').attributes('aria-label')).toBe('Mesas por número');
    expect(['meta', 'status', 'time'].map((name) => c.part('t2', name).text())).toEqual(['3/4 pax', 'Ocupada', '1:10']);
    expect(c.part('t10', 'meta').text()).toBe('Maximiliana Fernández · 20:00');
  });
});
