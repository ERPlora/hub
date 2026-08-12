import { beforeEach, describe, expect, it, vi } from 'vitest';

const loadMenu = vi.fn();
vi.mock('./module-loader', () => ({ loadMenu: () => loadMenu() }));

import { moduleNav, moduleNavState, refreshModuleNav } from './nav';

// The list of installed apps feeds two launchers (the topbar grid and the panel's «My apps» card),
// and until hub#770 it could only ever say «here is the list» — there was no way for it to say «I
// have not asked yet» or «I asked and it failed». Both of those came out as an empty list, and an
// empty list is painted as «you have no apps yet».

function entry(moduleId: string) {
  return { moduleId, moduleName: moduleId, nav: { icon: 'cube-outline' }, iconSvg: null };
}

beforeEach(() => {
  loadMenu.mockReset();
  moduleNav.value = [];
  moduleNavState.value = 'loading';
});

describe('refreshModuleNav', () => {
  it('starts out NOT knowing — «loading» is the boot value, never «ready and empty»', () => {
    // Asserted as the module's own initial state, because the first paint of the panel happens
    // before any request finishes. Booting as `ready` would say «no apps» to every cold load.
    expect(moduleNavState.value).toBe('loading');
  });

  it('publishes the apps and says it knows', async () => {
    loadMenu.mockResolvedValue([entry('sales'), entry('sales'), entry('inventory')]);
    await refreshModuleNav();
    // One entry per MODULE, not per navigation item: `sales` declares two tabs and is one app.
    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/sales', '/m/inventory']);
    expect(moduleNavState.value).toBe('ready');
  });

  it('an empty hub is «ready» and empty — that is a real answer', async () => {
    loadMenu.mockResolvedValue([]);
    await refreshModuleNav();
    expect(moduleNavState.value).toBe('ready');
  });

  it('a failure says «error» and KEEPS the apps it already had', async () => {
    loadMenu.mockResolvedValue([entry('sales')]);
    await refreshModuleNav();

    loadMenu.mockRejectedValue(new Error('401'));
    await refreshModuleNav();

    // The case from the field: a second device signs in on the Free plan and displaces this
    // session. The runtime answers 401, and the launcher used to go blank — «somebody uninstalled
    // everything» — while the till in the next tab was still selling.
    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/sales']);
    expect(moduleNavState.value).toBe('error');
  });

  it('never throws: the shell paints even when the runtime does not answer', async () => {
    loadMenu.mockRejectedValue(new Error('boom'));
    await expect(refreshModuleNav()).resolves.toBeUndefined();
  });
});
