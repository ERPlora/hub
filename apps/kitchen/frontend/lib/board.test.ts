// What the display remembers between updates (KITCHEN-F10, F16): which tickets it already showed, to
// ring for a new one or one just rushed (never for what was on the board when it opened), and the station
// this device works at.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { item, ticket } from '../__tests__/kitchen';
import { arrivals, groupMenus, rememberedStation, rememberStation, STATION_KEY } from './board';

/** The browser's localStorage (the test environment has none). */
function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => [...items.keys()][index] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, String(value)),
  };
}

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));

describe('arrivals', () => {
  it('learns the board on its first result without ringing', () => {
    const first = arrivals(undefined, [ticket('a'), ticket('b')]);
    expect(first.ring).toBe(false);
    expect([...first.known.keys()]).toEqual(['a', 'b']);
  });

  it('rings once for any new ticket, and for one that turns rush', () => {
    const known = arrivals(undefined, [ticket('a')]).known;
    expect(arrivals(known, [ticket('a'), ticket('b'), ticket('c')]).ring).toBe(true);
    expect(arrivals(known, [ticket('a', { priority: 'rush' })]).ring).toBe(true);
    expect(arrivals(known, [ticket('a')]).ring).toBe(false);
  });

  it('never rings for a ticket the pass recalls: it was on the board, under «Ready» (KITCHEN-F12, F16)', () => {
    const known = arrivals(undefined, [ticket('a')], [ticket('b', { status: 'ready' })]).known;
    expect(arrivals(known, [ticket('a'), ticket('b', { status: 'preparing' })], []).ring).toBe(false);
    expect(arrivals(known, [ticket('a'), ticket('c')], [ticket('b', { status: 'ready' })]).ring).toBe(true);
  });

  it('never rings when the rush is taken away or a ticket leaves', () => {
    const known = arrivals(undefined, [ticket('a', { priority: 'rush' }), ticket('b')]).known;
    expect(arrivals(known, [ticket('a')]).ring).toBe(false);
  });
});

describe('the station of this device', () => {
  it('is every station until one is chosen, and is remembered', () => {
    expect(rememberedStation()).toBe('');
    rememberStation('st-grill');
    expect(localStorage.getItem(STATION_KEY)).toBe('st-grill');
    expect(rememberedStation()).toBe('st-grill');
    rememberStation('');
    expect(rememberedStation()).toBe('');
  });
});

// KITCHEN-F06 (kitchen#57): a menu is the run of its dishes under its header; a dish ordered on its own is
// itself. Two menus of the same name on one ticket are two menus (two lines of the check).
describe('groupMenus', () => {
  const dish = (id: string, menu: string | null, name = 'MENU') =>
    item(id, { menu_line_id: menu, menu_name: menu ? name : '' });

  it('gathers the dishes of each menu under it, and leaves the dishes on their own as they are', () => {
    const groups = groupMenus([dish('a1', 'm1'), dish('a2', 'm1'), dish('b1', 'm2'), dish('c1', null), dish('c2', null)]);
    expect(groups.map((g) => [g.menu?.lineId ?? null, g.menu?.name ?? '', g.items.map((i) => i.id)])).toEqual([
      ['m1', 'MENU', ['a1', 'a2']],
      ['m2', 'MENU', ['b1']],
      [null, '', ['c1']],
      [null, '', ['c2']],
    ]);
  });

  it('gives nothing for a ticket with no dishes', () => {
    expect(groupMenus([])).toEqual([]);
  });
});
