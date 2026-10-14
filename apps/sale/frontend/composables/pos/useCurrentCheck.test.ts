// The device's current check (SALE-F17 step 5: on reloading the screen each device comes back to the
// check it had open): its id kept in localStorage, remembered when a check opens or is resumed and
// forgotten when it is charged whole, parked or voided.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CURRENT_CHECK_KEY, useCurrentCheck } from './useCurrentCheck';

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
afterEach(() => vi.unstubAllGlobals());

describe('useCurrentCheck', () => {
  it('starts with no check on a device that never had one', () => {
    expect(useCurrentCheck().id.value).toBeNull();
  });

  it('remembers the check across a reload of the screen (a new instance reads it back)', () => {
    useCurrentCheck().remember('o1');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(useCurrentCheck().id.value).toBe('o1');
  });

  it('forgets it: the id goes and so does the stored one', () => {
    const check = useCurrentCheck();
    check.remember('o1');
    check.forget();
    expect(check.id.value).toBeNull();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(useCurrentCheck().id.value).toBeNull();
  });

  it('a device whose storage refuses (private mode, quota) still keeps the check while the screen lives', () => {
    const storage = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
      removeItem: () => {
        throw new Error('denied');
      },
    };
    const check = useCurrentCheck(storage);
    expect(check.id.value).toBeNull();
    check.remember('o2');
    expect(check.id.value).toBe('o2');
    check.forget();
    expect(check.id.value).toBeNull();
  });
});
