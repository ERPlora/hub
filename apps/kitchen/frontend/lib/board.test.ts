// What the display remembers between updates (KITCHEN-F10, F16): which tickets it already showed, to
// ring for a new one or one just rushed (never for what was on the board when it opened), and the station
// this device works at.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ticket } from '../__tests__/kitchen';
import { arrivals, rememberedStation, rememberStation, STATION_KEY } from './board';

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
