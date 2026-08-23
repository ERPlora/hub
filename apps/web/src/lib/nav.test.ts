// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest';

const loadMenu = vi.fn();
const invalidateManifestCache = vi.fn();
vi.mock('./module-loader', () => ({
  loadMenu: () => loadMenu(),
  invalidateManifestCache: () => invalidateManifestCache(),
}));

import {
  bootModuleNavLocale,
  moduleNav,
  moduleNavState,
  refreshModuleNav,
  refreshModuleNavAfterInstall,
} from './nav';

// The list of installed apps feeds two launchers (the topbar grid and the panel's «My apps» card),
// and until hub#770 it could only ever say «here is the list» — there was no way for it to say «I
// have not asked yet» or «I asked and it failed». Both of those came out as an empty list, and an
// empty list is painted as «you have no apps yet».

function entry(moduleId: string) {
  return { moduleId, moduleName: moduleId, nav: { icon: 'cube-outline' }, iconSvg: null };
}

beforeEach(() => {
  loadMenu.mockReset();
  invalidateManifestCache.mockReset();
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

// hub#781 — the names of the installed apps stayed in the language of the FIRST fetch.
//
// The names in this list are localized BY THE RUNTIME (`/api/navigation?locale=`, ADR-0055): they
// come from each module's own `locales/<lang>.json`, so the language is baked into the answer, not
// resolved when it is painted. And the list is fetched exactly once, at boot — before `/api/profile`
// has answered, so with the shell still on its default `es`.
//
// The result: a user whose preference is English got Home, Employees, Settings and every other
// chrome string in English, and their apps as `Clientes`, `Mesas`, `Impuestos`, `Inventario` — in
// the sidebar, in the topbar launcher and on the panel card, which all read this one list.
//
// The shell already announces `erplora:locale-changed` on every change. Nobody in the shell was
// listening: the event existed only to repaint module Web Components.
describe('the app names follow the language', () => {
  it('refetches the navigation when the effective locale changes', async () => {
    loadMenu.mockResolvedValue([entry('customers')]);
    bootModuleNavLocale();

    loadMenu.mockClear();
    window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale: 'en' } }));
    await Promise.resolve();

    expect(loadMenu).toHaveBeenCalledTimes(1);
  });

  it('installs the listener ONCE, however many times it is booted', async () => {
    // Two listeners means two fetches per change and a race over which answer lands last — which is
    // exactly how a list ends up in the wrong language after being right for a moment.
    loadMenu.mockResolvedValue([]);
    bootModuleNavLocale();
    bootModuleNavLocale();
    bootModuleNavLocale();

    loadMenu.mockClear();
    window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale: 'en' } }));
    await Promise.resolve();

    expect(loadMenu).toHaveBeenCalledTimes(1);
  });
});

// ── Instalar un módulo cambia el CONJUNTO, no solo la lista (hub#1099) ───────────────────────────
//
// Los `module.json` se leen una vez por sesión desde hub#1099: con 25 módulos, releerlos en cada
// navegación costaba ~1,6 MB por montaje y el ritmo crecía hasta ~75 req/s con la pestaña quieta.
// El precio de esa caché es que alguien tiene que olvidarla cuando deja de ser verdad, y el único
// momento en que eso pasa sin recargar la página es este: el conjunto instalado acaba de cambiar.
//
// Va JUNTO al refresco y no suelto en quien lo llama porque las dos mitades son un solo hecho: una
// nav nueva con los manifests viejos describe un hub que no existe —widgets, slots, `chrome` y
// `protects` del conjunto anterior—, y esa es la clase de mentira muda que costó hub#935.
describe('refreshModuleNavAfterInstall', () => {
  it('olvida los manifests cacheados ANTES de volver a pedir la nav', async () => {
    loadMenu.mockResolvedValue([entry('sales')]);

    await refreshModuleNavAfterInstall();

    expect(invalidateManifestCache).toHaveBeenCalledTimes(1);
    expect(invalidateManifestCache.mock.invocationCallOrder[0]).toBeLessThan(
      loadMenu.mock.invocationCallOrder[0],
    );
  });

  it('y publica la nav como el refresco de siempre', async () => {
    loadMenu.mockResolvedValue([entry('sales')]);

    await refreshModuleNavAfterInstall();

    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/sales']);
    expect(moduleNavState.value).toBe('ready');
  });

  it('NO se olvida nada en el refresco normal: navegar no cambia el conjunto instalado', async () => {
    // Si `refreshModuleNav` vaciara la caché, cada visita a /apps y cada cambio de idioma volverían
    // a pedir los 25 manifests — la caché quedaría en nada por la puerta de atrás.
    loadMenu.mockResolvedValue([entry('sales')]);

    await refreshModuleNav();

    expect(invalidateManifestCache).not.toHaveBeenCalled();
  });
});
