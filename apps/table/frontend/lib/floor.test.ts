// The floor plan's geometry and rules, apart from the screen: how big the plan is, where a dragged table
// may go, what each status looks like (colour, icon, written word: never the colour alone, tables#64),
// whose reservation a table paints and which tables a transfer or a merge may pick.
import { describe, expect, it } from 'vitest';

import type { TableOut } from '../operations';
import { BOX, clampPosition, holdName, keyDelta, paintedStatus, planeSize, STATUS_ICON, STATUS_TONE, targetable } from './floor';

function table(overrides: Partial<TableOut> = {}): TableOut {
  return {
    id: 't1',
    number: '1',
    name: '',
    capacity: 4,
    shape: 'square',
    status: 'available',
    blocked: false,
    is_active: true,
    zone_id: 'z1',
    zone_name: 'Dining room',
    in_service: true,
    position_x: 16,
    position_y: 16,
    width: BOX,
    height: BOX,
    guests: null,
    since: null,
    waiter_name: '',
    checks: [],
    hold: null,
    ...overrides,
  };
}

describe('planeSize', () => {
  it('reaches the far edge of the farthest table and the bottom of the lowest one, painted whole', () => {
    const tables = [table({ position_x: 600, position_y: 16 }), table({ id: 't2', position_x: 16, position_y: 400, height: 144 })];
    expect(planeSize(tables)).toEqual({ w: 600 + BOX + 10, h: 400 + 144 + 10 });
  });

  it('never shrinks below the floor kept while a table is dragged', () => {
    expect(planeSize([table()], { w: 900, h: 700 })).toEqual({ w: 900, h: 700 });
  });
});

describe('clampPosition', () => {
  it('keeps the table whole inside the plan', () => {
    expect(clampPosition(-20, 30, { w: BOX, h: BOX }, { w: 400, h: 300 })).toEqual({ x: 0, y: 30 });
    expect(clampPosition(390, 290, { w: BOX, h: BOX }, { w: 400, h: 300 })).toEqual({ x: 400 - BOX - 10, y: 300 - BOX - 10 });
  });
});

describe('keyDelta', () => {
  it('moves 8 px with an arrow and 32 with Shift, and nothing with another key', () => {
    expect(keyDelta('ArrowLeft', false)).toEqual([-8, 0]);
    expect(keyDelta('ArrowDown', true)).toEqual([0, 32]);
    expect(keyDelta('a', false)).toBeNull();
  });
});

describe('statuses', () => {
  it('give each status its own icon and tone', () => {
    expect(STATUS_ICON).toEqual({
      available: 'ion:checkmark-circle-outline',
      occupied: 'ion:people-outline',
      reserved: 'ion:time-outline',
      blocked: 'ion:ban-outline',
    });
    expect(STATUS_TONE).toEqual({ available: 'success', occupied: 'danger', reserved: 'warning', blocked: 'neutral' });
  });
});

describe('holdName', () => {
  it('is the reservation’s name, or «Deleted customer» once her data was erased', () => {
    const hold = { label: 'Ana', erased: false, held_from: '', held_until: '', party_size: 2, reserving: true };
    expect(holdName(hold, 'Deleted customer')).toBe('Ana');
    expect(holdName({ ...hold, label: '', erased: true }, 'Deleted customer')).toBe('Deleted customer');
    expect(holdName(null, 'Deleted customer')).toBe('');
  });
});

describe('targetable', () => {
  const source = table({ id: 'src', status: 'occupied', checks: [{ id: 's1' } as TableOut['checks'][number]] });
  it('lets a transfer pick a free or reserved table in service, never its own', () => {
    expect(targetable('transfer', source, table({ status: 'available' }))).toBe(true);
    expect(targetable('transfer', source, table({ status: 'reserved' }))).toBe(true);
    expect(targetable('transfer', source, table({ status: 'occupied' }))).toBe(false);
    expect(targetable('transfer', source, table({ status: 'blocked' }))).toBe(false);
    expect(targetable('transfer', source, table({ in_service: false }))).toBe(false);
    expect(targetable('transfer', source, { ...source, status: 'available' })).toBe(false);
  });

  it('lets a merge pick an occupied table, its own only when it holds another check', () => {
    expect(targetable('merge', source, table({ status: 'occupied' }))).toBe(true);
    expect(targetable('merge', source, table({ status: 'reserved' }))).toBe(false);
    expect(targetable('merge', source, source)).toBe(false);
    const split = { ...source, checks: [...source.checks, { id: 's2' } as TableOut['checks'][number]] };
    expect(targetable('merge', split, split)).toBe(true);
  });
});

describe('paintedStatus', () => {
  // A reservation enters its window, or ends, with no event of anybody: the plan repaints it by the clock.
  const hold = { label: 'Ana', erased: false, held_from: '2026-10-14T21:00:00Z', held_until: '2026-10-14T23:00:00Z', party_size: 4, reserving: false };
  const at = (iso: string) => new Date(iso);

  it('paints Reserved from the lead before the reservation until it ends, and Available outside', () => {
    const free = table({ status: 'available', hold });
    expect(paintedStatus(free, at('2026-10-14T19:59:00Z'), 60)).toBe('available');
    expect(paintedStatus(free, at('2026-10-14T20:00:00Z'), 60)).toBe('reserved');
    const reserved = table({ status: 'reserved', hold: { ...hold, reserving: true } });
    expect(paintedStatus(reserved, at('2026-10-14T22:59:00Z'), 60)).toBe('reserved');
    expect(paintedStatus(reserved, at('2026-10-14T23:00:00Z'), 60)).toBe('available');
  });

  it('never repaints an occupied or blocked table, nor one without a reservation shown', () => {
    const now = at('2026-10-14T21:30:00Z');
    expect(paintedStatus(table({ status: 'occupied', hold }), now, 60)).toBe('occupied');
    expect(paintedStatus(table({ status: 'blocked', hold }), now, 60)).toBe('blocked');
    expect(paintedStatus(table({ status: 'reserved' }), now, 60)).toBe('reserved');
  });
});
