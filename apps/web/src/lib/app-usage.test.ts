// @vitest-environment happy-dom
// The order of the launcher (hub#367, PLAN step 10): «the installed apps as a grid, the most used
// one first». The grid is the only widget that works with zero data, so what it must never do is
// reorder itself on a guess: the count is what the user did, and what nobody has opened keeps the
// order the runtime answered.
//
// This module is pure so the rule can be checked without a browser: the card only paints it.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { APP_USAGE_KEY, orderAppsByUsage, readAppUsage, recordAppLaunch } from './app-usage';

interface App {
  path: string;
  label: string;
}

const pos: App = { path: '/m/pos', label: 'Till' };
const stock: App = { path: '/m/inventory', label: 'Stock' };
const agenda: App = { path: '/m/appointments', label: 'Appointments' };

beforeEach(() => {
  localStorage.clear();
});

describe('the most used app comes first', () => {
  it('orders by how many times each one was opened, descending', () => {
    const usage = { '/m/inventory': 2, '/m/appointments': 9 };

    expect(orderAppsByUsage([pos, stock, agenda], usage).map((a) => a.path)).toEqual([
      '/m/appointments',
      '/m/inventory',
      '/m/pos',
    ]);
  });

  it('a tie keeps the order the runtime answered: nothing is reshuffled on a guess', () => {
    const usage = { '/m/pos': 3, '/m/inventory': 3, '/m/appointments': 3 };

    expect(orderAppsByUsage([pos, stock, agenda], usage).map((a) => a.path)).toEqual([
      '/m/pos',
      '/m/inventory',
      '/m/appointments',
    ]);
  });

  it('what nobody has opened goes last, and still goes: an app is never dropped', () => {
    const ordered = orderAppsByUsage([pos, stock, agenda], { '/m/appointments': 1 });

    expect(ordered).toHaveLength(3);
    expect(ordered[0].path).toBe('/m/appointments');
  });

  it('a count for an app that is no longer installed invents no tile', () => {
    const ordered = orderAppsByUsage([pos], { '/m/removed': 50 });

    expect(ordered.map((a) => a.path)).toEqual(['/m/pos']);
  });

  it('does not mutate the list it was given (the shell shares that ref with the topbar)', () => {
    const apps = [pos, stock];
    orderAppsByUsage(apps, { '/m/inventory': 4 });

    expect(apps.map((a) => a.path)).toEqual(['/m/pos', '/m/inventory']);
  });

  it('reads the stored counts when it is not told any', () => {
    localStorage.setItem(APP_USAGE_KEY, JSON.stringify({ '/m/inventory': 7 }));

    expect(orderAppsByUsage([pos, stock]).map((a) => a.path)).toEqual(['/m/inventory', '/m/pos']);
  });
});

describe('opening an app is what counts it', () => {
  it('counts the first open, and adds up the next ones', () => {
    recordAppLaunch('/m/pos');
    expect(readAppUsage()['/m/pos']).toBe(1);

    recordAppLaunch('/m/pos');
    recordAppLaunch('/m/pos');
    expect(readAppUsage()['/m/pos']).toBe(3);
  });

  it('counts each app on its own', () => {
    recordAppLaunch('/m/pos');
    recordAppLaunch('/m/inventory');
    recordAppLaunch('/m/inventory');

    expect(readAppUsage()).toEqual({ '/m/pos': 1, '/m/inventory': 2 });
  });

  it('an empty path is not an open: the store keeps no blank key', () => {
    recordAppLaunch('');

    expect(readAppUsage()).toEqual({});
  });
});

describe('a broken store never takes the panel down with it', () => {
  it('corrupt JSON reads as «nobody has opened anything»', () => {
    localStorage.setItem(APP_USAGE_KEY, '{not json');

    expect(readAppUsage()).toEqual({});
    expect(orderAppsByUsage([pos, stock]).map((a) => a.path)).toEqual(['/m/pos', '/m/inventory']);
  });

  it('a non-numeric count is ignored instead of sorting by NaN', () => {
    localStorage.setItem(APP_USAGE_KEY, JSON.stringify({ '/m/pos': 'many', '/m/inventory': 2 }));

    expect(readAppUsage()).toEqual({ '/m/inventory': 2 });
    expect(orderAppsByUsage([pos, stock]).map((a) => a.path)).toEqual(['/m/inventory', '/m/pos']);
  });

  it('a store that is not an object is not trusted either', () => {
    // An array of NUMBERS is the case that matters: read as a map it yields `{0: 3, 1: 5}`, counts
    // for apps called «0» and «1» that no runtime ever reported.
    localStorage.setItem(APP_USAGE_KEY, JSON.stringify([3, 5]));

    expect(readAppUsage()).toEqual({});
  });

  it('no localStorage (private mode, Tauri webview quirks) neither throws nor loses the grid', () => {
    const denied = {
      getItem: vi.fn(() => {
        throw new Error('denied');
      }),
      setItem: vi.fn(() => {
        throw new Error('denied');
      }),
    };
    vi.stubGlobal('localStorage', denied);

    expect(() => recordAppLaunch('/m/pos')).not.toThrow();
    expect(readAppUsage()).toEqual({});
    expect(orderAppsByUsage([pos, stock]).map((a) => a.path)).toEqual(['/m/pos', '/m/inventory']);

    vi.unstubAllGlobals();
  });
});
