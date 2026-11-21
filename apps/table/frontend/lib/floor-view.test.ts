import { describe, expect, it } from 'vitest';

import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import type { Money } from '../lib/format';
import type { TableOut } from '../operations';
import { elapsed, floorView } from './floor-view';

const words: Record<string, string> = {
  'table.tableLabel': 'Table {number}',
  'table.status.available': 'Available',
  'table.status.occupied': 'Occupied',
  'table.status.reserved': 'Reserved',
  'table.status.blocked': 'Blocked',
  'table.pax': '{count} pax',
  'table.floor.paxOf': '{guests}/{capacity} pax',
  'table.guestsCount': '{count} guest | {count} guests',
  'table.minutes': '{minutes} min',
  'table.servedBy': 'Served by {name}',
  'table.reservedFor': 'Reserved for {name}',
  'table.erasedCustomer': 'Deleted customer',
  'table.floor.bill': 'Bill {amount}',
  'table.floor.billRequested': 'Bill requested',
};

const EUR: Money = { currency: 'EUR', decimals: 2 };

function t(key: string, named: Record<string, unknown> = {}): string {
  let text = words[key] ?? key;
  if (key === 'table.guestsCount') text = text.split(' | ')[named.count === 1 ? 0 : 1];
  return Object.entries(named).reduce((result, [name, value]) => result.replace(`{${name}}`, String(value)), text);
}

/** `money` null: the business has not answered yet. */
function view(table = tableRow(), now = NOW, pick: ((table: TableOut) => boolean) | null = null, money: Money | null = EUR) {
  return floorView(table, { now, settings: SETTINGS, locale: 'en', timeZone: 'Europe/Madrid', t, pick, money: money ?? undefined });
}

describe('elapsed', () => {
  it('formats minutes as h:mm', () => {
    expect(elapsed(null)).toBe('');
    expect(elapsed(0)).toBe('0:00');
    expect(elapsed(35)).toBe('0:35');
    expect(elapsed(68)).toBe('1:08');
    expect(elapsed(600)).toBe('10:00');
  });
});

describe('floorView', () => {
  it('gives a free table its status inside and its capacity on the label, without inventing a timer', () => {
    const model = view();
    expect(model).toMatchObject({ timed: false, tone: 'normal', progress: 0, short: 'Available', statusLabel: 'Available', pax: '4 pax', caption: '4 pax', holder: '' });
    expect(model.accessible).toBe('Table 4 · Dining room · 4 pax · Available');
  });

  it('carries what the plan draws of the table: its number, status, shape, places, guests and test id', () => {
    expect(view(occupied())).toMatchObject({ id: 't1', number: '4', status: 'occupied', shape: 'square', capacity: 4, guests: 3, ratio: 1, testid: 'table-floor-tile-t1' });
    expect(view(tableRow({ shape: 'rectangle' })).ratio).toBeCloseTo(1 / 0.68);
  });

  it('gives an occupied table elapsed time, guests and its server', () => {
    const model = view(occupied());
    expect(model).toMatchObject({ timed: true, tone: 'normal', short: '0:35', statusLabel: 'Occupied', pax: '3/4 pax', caption: 'Occupied · 3/4 pax' });
    expect(model.progress).toBeCloseTo((35 / 90) * 100);
    expect(model.accessible).toContain('3 guests · 35 min · Bill €42.50 · Served by Luis');
  });

  it('uses the configured warning and critical thresholds only for an occupied timer', () => {
    const at = (minutes: number) => occupied({ since: new Date(NOW.getTime() - minutes * 60_000).toISOString() });
    expect(view(at(60)).tone).toBe('warning');
    expect(view(at(90)).tone).toBe('critical');
    expect(view(at(120)).progress).toBe(100);
    expect(view(tableRow({ status: 'reserved' })).tone).toBe('normal');
  });

  it('writes the status once: on the label only when the table does not show it inside', () => {
    const untimed = view(occupied({ since: null }));
    expect([untimed.short, untimed.caption, untimed.timed]).toEqual(['Occupied', '3/4 pax', false]);
    const blocked = view(tableRow({ status: 'blocked', blocked: true }));
    expect([blocked.short, blocked.caption]).toEqual(['Blocked', '4 pax']);
  });

  it('keeps who holds a reservation and from what hour, for reserved and free tables', () => {
    const hold = { label: 'Ana', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 4, reserving: true };
    const reserved = view(tableRow({ status: 'reserved', hold }));
    expect([reserved.short, reserved.holder, reserved.holdTime, reserved.caption]).toEqual(['8:00 PM', 'Ana', '8:00 PM', 'Reserved · 4 pax']);
    expect(reserved.accessible).toContain('Reserved for Ana · 8:00 PM');
    const later = view(tableRow({ hold: { ...hold, reserving: false } }));
    expect([later.caption, later.holder, later.holdTime]).toEqual(['4 pax', 'Ana', '8:00 PM']);
  });

  it('keeps exact guest counts above capacity and names erased customers', () => {
    expect(view(occupied({ guests: 8 })).caption).toBe('Occupied · 8/4 pax');
    const erased = tableRow({ hold: { label: '', erased: true, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 2, reserving: false } });
    expect([view(erased).holder, view(erased).holdTime]).toEqual(['Deleted customer', '8:00 PM']);
  });

  it('writes the bill of an occupied table in the business money, also for the screen reader', () => {
    const model = view(occupied());
    expect(model.amount).toBe('€42.50');
    expect(model.accessible).toBe('Table 4 · Dining room · 4 pax · Occupied · 3 guests · 35 min · Bill €42.50 · Served by Luis');
    expect(view(occupied({ amount: 0 })).amount).toBe('€0.00');
    expect(view(occupied({ amount: 125000 }), NOW, null, { currency: 'JPY', decimals: 0 }).amount).toBe('¥125,000');
  });

  it('gives no bill to a table nobody sits at, nor before the business money is known', () => {
    for (const status of ['available', 'reserved', 'blocked'] as const) {
      const model = view(tableRow({ status, amount: 4250 }));
      expect(model.amount, status).toBeUndefined();
      expect(model.accessible, status).not.toContain('Bill');
    }
    const unknown = view(occupied(), NOW, null, null);
    expect(unknown.amount).toBeUndefined();
    expect(unknown.accessible).not.toContain('Bill');
  });

  it('marks an occupied table whose bill was asked for, and says so wherever it says its status', () => {
    const model = view(occupied({ bill_requested: true }));
    expect(model).toMatchObject({ status: 'occupied', billRequested: true, statusLabel: 'Bill requested', caption: 'Bill requested · 3/4 pax', short: '0:35', pax: '3/4 pax', amount: '€42.50' });
    expect(model.accessible).toBe('Table 4 · Dining room · 4 pax · Bill requested · 3 guests · 35 min · Bill €42.50 · Served by Luis');
    expect(view(occupied({ since: null, bill_requested: true })).short).toBe('Bill requested');
  });

  it('leaves an occupied table without its bill asked for, and every other table, as they were', () => {
    const plain = view(occupied());
    expect([plain.billRequested, plain.statusLabel, plain.caption]).toEqual([false, 'Occupied', 'Occupied · 3/4 pax']);
    for (const status of ['available', 'reserved', 'blocked'] as const) {
      const model = view(tableRow({ status, bill_requested: true }));
      expect(model.billRequested, status).toBe(false);
      expect(model.statusLabel, status).toBe(words[`table.status.${status}`]);
      expect(model.accessible, status).not.toContain('Bill requested');
    }
  });

  it('says whether a table may be picked only while a destination is picked', () => {
    const free = (table: TableOut) => table.status === 'available';
    expect(view(tableRow(), NOW, free).pickable).toBe(true);
    expect(view(occupied(), NOW, free).pickable).toBe(false);
    expect(view(tableRow()).pickable).toBeUndefined();
  });
});
