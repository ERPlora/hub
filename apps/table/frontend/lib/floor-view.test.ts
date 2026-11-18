import { describe, expect, it } from 'vitest';

import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
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
};

function t(key: string, named: Record<string, unknown> = {}): string {
  let text = words[key] ?? key;
  if (key === 'table.guestsCount') text = text.split(' | ')[named.count === 1 ? 0 : 1];
  return Object.entries(named).reduce((result, [name, value]) => result.replace(`{${name}}`, String(value)), text);
}

function view(table = tableRow(), now = NOW) {
  return floorView(table, { now, settings: SETTINGS, locale: 'en', timeZone: 'Europe/Madrid', t });
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
    expect(model).toMatchObject({ minutes: null, tone: 'normal', progress: 0, short: 'Available', pax: '4 pax', labels: ['4 pax'] });
    expect(model.accessible).toBe('Table 4 · Dining room · 4 pax · Available');
  });

  it('gives an occupied table elapsed time, guests and its server', () => {
    const model = view(occupied());
    expect(model).toMatchObject({ minutes: 35, tone: 'normal', short: '0:35', pax: '3/4 pax', labels: ['Occupied · 3/4 pax'] });
    expect(model.progress).toBeCloseTo((35 / 90) * 100);
    expect(model.accessible).toContain('3 guests · 35 min · Served by Luis');
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
    expect([untimed.short, untimed.labels[0]]).toEqual(['Occupied', '3/4 pax']);
    const blocked = view(tableRow({ status: 'blocked', blocked: true }));
    expect([blocked.short, blocked.labels]).toEqual(['Blocked', ['4 pax']]);
  });

  it('keeps reservation details on a second label line for reserved and free tables', () => {
    const hold = { label: 'Ana', erased: false, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 4, reserving: true };
    const reserved = view(tableRow({ status: 'reserved', hold }));
    expect([reserved.short, reserved.holder]).toEqual(['8:00 PM', 'Ana']);
    expect(reserved.labels).toEqual(['Reserved · 4 pax', 'Ana · 8:00 PM']);
    expect(reserved.accessible).toContain('Reserved for Ana · 8:00 PM');
    expect(view(tableRow({ hold: { ...hold, reserving: false } })).labels).toEqual(['4 pax', 'Ana · 8:00 PM']);
  });

  it('keeps exact guest counts above capacity and names erased customers', () => {
    expect(view(occupied({ guests: 8 })).labels[0]).toBe('Occupied · 8/4 pax');
    const erased = tableRow({ hold: { label: '', erased: true, held_from: '2026-10-14T18:00:00Z', held_until: '2026-10-14T20:00:00Z', party_size: 2, reserving: false } });
    expect(view(erased).labels[1]).toBe('Deleted customer · 8:00 PM');
  });
});
