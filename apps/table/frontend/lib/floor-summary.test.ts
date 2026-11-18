import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { occupied, tableRow, zoneRow } from '../__tests__/tables';
import type { Translate } from '../composables/useT';
import en from '../locale/en.json';
import es from '../locale/es.json';
import { roomSummary, zoneCounts, zoneSummary, zoneTabs } from './floor-summary';

function translator(locale: 'en' | 'es'): Translate {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return (key, named) => (named ? i18n.global.t(key, named) : i18n.global.t(key));
}

const HOLD = { label: 'Ana', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 2, reserving: true };

describe('zoneCounts', () => {
  it('counts occupied tables over tables in service among the painted rows', () => {
    const rows = [
      tableRow({ id: 'free' }),
      occupied({ id: 'busy' }),
      occupied({ id: 'inactive', in_service: false }),
      tableRow({ id: 'blocked', status: 'blocked', in_service: false }),
    ];
    expect(zoneCounts(rows)).toEqual({ occupied: 1, total: 2 });
  });

  it('is zero without tables', () => {
    expect(zoneCounts([])).toEqual({ occupied: 0, total: 0 });
  });
});

describe('roomSummary', () => {
  it('counts each visible state and only seated guests', () => {
    const rows = [
      tableRow({ id: 'a' }),
      tableRow({ id: 'b' }),
      occupied({ id: 'c', guests: 3 }),
      occupied({ id: 'd', guests: 2 }),
      tableRow({ id: 'e', status: 'reserved' }),
      tableRow({ id: 'f', status: 'blocked' }),
    ];
    expect(roomSummary(rows)).toEqual({ available: 2, occupied: 2, reserved: 1, guests: 5 });
  });
});

describe('zoneTabs', () => {
  const zones = [zoneRow({ id: 'z1', name: 'Dining room', color: 'primary' }), zoneRow({ id: 'z2', name: 'Terrace', color: 'tertiary' })];
  const tables = [tableRow({ id: 't1' }), occupied({ id: 't4' }), tableRow({ id: 't9', is_active: false, in_service: false }), tableRow({ id: 't7', zone_id: 'z2' })];

  it('gives each zone its colour and its occupied tables over those in service, also in words', () => {
    expect(zoneTabs(zones, tables, translator('en'))).toEqual([
      { id: 'z1', name: 'Dining room', color: 'primary', occupied: 1, total: 2, said: '1 of 2 tables occupied', testid: 'table-floor-zone-tab-z1' },
      { id: 'z2', name: 'Terrace', color: 'tertiary', occupied: 0, total: 1, said: '0 of 1 table occupied', testid: 'table-floor-zone-tab-z2' },
    ]);
  });

  it('speaks Spanish', () => {
    expect(zoneTabs(zones, tables, translator('es')).map((tab) => tab.said)).toEqual(['1 de 2 mesas ocupadas', '0 de 1 mesa ocupada']);
  });
});

describe('zoneSummary', () => {
  const room = [
    tableRow({ id: 't1' }),
    tableRow({ id: 't2' }),
    occupied({ id: 't3', guests: 3 }),
    occupied({ id: 't4', guests: 5 }),
    tableRow({ id: 't5', status: 'reserved', hold: HOLD }),
    tableRow({ id: 't6', status: 'blocked', blocked: true }),
  ];

  it('names the zone in its colour, how many are occupied, and the free, occupied, reserved tables and guests', () => {
    expect(zoneSummary(zoneRow({ name: 'Dining room', color: 'secondary' }), room, translator('en'))).toEqual({
      title: 'Dining room',
      subtitle: '2 of 6 tables occupied',
      color: 'secondary',
      stats: [
        { key: 'available', value: 2, label: 'Available' },
        { key: 'occupied', value: 2, label: 'Occupied' },
        { key: 'reserved', value: 1, label: 'Reserved' },
        { key: 'guests', value: 8, label: 'Guests' },
      ],
    });
  });

  it('speaks Spanish, with the singular of one table', () => {
    const summary = zoneSummary(zoneRow(), [occupied({ id: 't3', guests: 1 })], translator('es'));
    expect(summary.subtitle).toBe('1 de 1 mesa ocupada');
    expect(summary.stats.map((stat) => `${stat.value}${stat.label}`)).toEqual(['0Disponibles', '1Ocupadas', '0Reservadas', '1Comensales']);
  });

  it('without a zone has no name nor colour of its own', () => {
    expect(zoneSummary(null, [], translator('en'))).toMatchObject({ title: '', color: null, subtitle: '0 of 0 tables occupied' });
  });
});
