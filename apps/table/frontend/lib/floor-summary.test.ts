import { describe, expect, it } from 'vitest';

import { occupied, tableRow } from '../__tests__/tables';
import { roomSummary, zoneCounts } from './floor-summary';

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
