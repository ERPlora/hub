import { describe, expect, it } from 'vitest';

import { mountTable } from '../__tests__/mount-table';
import { occupied, tableRow, zoneRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import FloorSummary from './FloorSummary.vue';

const HOLD = { label: 'Ana', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 2, reserving: true };
const ROOM: TableOut[] = [
  tableRow({ id: 't1' }),
  tableRow({ id: 't2' }),
  occupied({ id: 't3', guests: 3 }),
  occupied({ id: 't4', guests: 5 }),
  tableRow({ id: 't5', status: 'reserved', hold: HOLD }),
  tableRow({ id: 't6', status: 'blocked', blocked: true }),
];

async function summary(tables = ROOM, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(FloorSummary, { props: { zone: zoneRow({ name: 'Dining room', color: 'secondary' }), tables }, locale });
  const stat = (key: string) => m.wrapper.find(`[data-stat="${key}"]`);
  return { ...m, stat };
}

describe('FloorSummary', () => {
  it('sums up the zone: its name, how many are occupied, and the free, occupied, reserved tables and guests', async () => {
    const s = await summary();
    const root = s.wrapper.find('[data-testid="table-floor-summary"]');
    expect(root.attributes('aria-label')).toBe('Zone summary');
    expect((root.element as HTMLElement).style.getPropertyValue('--zone-color')).toBe('var(--ion-color-secondary)');
    expect(s.wrapper.find('h2').text()).toBe('Dining room');
    expect(s.wrapper.find('[data-part="occupied-of"]').text()).toBe('2 of 6 tables occupied');
    expect(['available', 'occupied', 'reserved', 'guests'].map((key) => s.stat(key).text())).toEqual([
      '2Available',
      '2Occupied',
      '1Reserved',
      '8Guests',
    ]);
  });

  it('speaks Spanish, with the singular of one table', async () => {
    const s = await summary([occupied({ id: 't3', guests: 1 })], 'es');
    expect(s.wrapper.find('[data-testid="table-floor-summary"]').attributes('aria-label')).toBe('Resumen de la zona');
    expect(s.wrapper.find('[data-part="occupied-of"]').text()).toBe('1 de 1 mesa ocupada');
    expect(['available', 'occupied', 'reserved', 'guests'].map((key) => s.stat(key).text())).toEqual([
      '0Disponibles',
      '1Ocupadas',
      '0Reservadas',
      '1Comensales',
    ]);
  });
});
