// Estado de instalación de una fila del catálogo (AppsPage). El catálogo Cloud es un PROXY al SaaS
// y su flag `installed` puede no reflejar aún la instalación de ESTE hub (`mark_installed` es
// best-effort). El runtime es la FUENTE DE VERDAD local: si el módulo está en la lista instalada
// local, la fila debe salir "Instalado" (badge + botón deshabilitado), aunque el Cloud diga false.
// (Bug reportado en el demo 2026-07-12: un módulo recién instalado seguía como "Disponible".)
import { describe, expect, it } from 'vitest';

import { alsoInstalledNames, catalogActionFor, catalogRowState, isModuleInstalled } from './apps-catalog';

describe('isModuleInstalled', () => {
  it('el Cloud manda cuando dice instalado', () => {
    expect(isModuleInstalled(true, 'taxes', new Set())).toBe(true);
  });

  it('la verdad LOCAL rescata el caso del bug: Cloud=false pero instalado localmente → instalado', () => {
    expect(isModuleInstalled(false, 'taxes', new Set(['taxes']))).toBe(true);
  });

  it('ni Cloud ni local → disponible', () => {
    expect(isModuleInstalled(false, 'inventory', new Set(['taxes']))).toBe(false);
  });
});

// hub#795 — the catalog said «Update to 1.2.22» in the status column and the only button on the row
// was still called «Install». With icon-only actions the label IS the accessible name, so a keyboard
// or a screen reader was told the wrong operation; and `installModule` decided install-or-update
// afterwards, from the CLOUD's `installed` flag, which is best-effort and can lag behind this hub.
//
// The row's state already knew the answer. These two turn it into the one thing the screen needs:
// which action a row offers, so the button can be labelled BEFORE anyone presses it.
describe('catalogRowState', () => {
  const base = { cloudInstalled: false, id: 'sales', localInstalledIds: new Set<string>(), hasUpdate: false, available: true, busy: false };

  it('is available when neither side has it', () => {
    expect(catalogRowState(base)).toBe('available');
  });

  it('is installed when the CLOUD knows, and equally when only the runtime does', () => {
    expect(catalogRowState({ ...base, cloudInstalled: true })).toBe('installed');
    expect(catalogRowState({ ...base, localInstalledIds: new Set(['sales']) })).toBe('installed');
  });

  it('is updatable — and that survives the Cloud not having caught up yet', () => {
    // The case of the issue: the runtime has the module, the Cloud still answers `installed: false`.
    // Reading the Cloud flag alone sends this row down the INSTALL branch.
    expect(catalogRowState({ ...base, localInstalledIds: new Set(['sales']), hasUpdate: true })).toBe('updatable');
  });

  it('offers no update for something that is not installed here', () => {
    // A newer version in the marketplace is not an update if this hub never had the module.
    expect(catalogRowState({ ...base, hasUpdate: true })).toBe('available');
  });

  it('is unavailable when the marketplace does not offer it to this hub', () => {
    expect(catalogRowState({ ...base, available: false })).toBe('unavailable');
  });

  it('busy wins over everything: a row already working says so and nothing else', () => {
    expect(catalogRowState({ ...base, busy: true })).toBe('installing');
    expect(catalogRowState({ ...base, busy: true, localInstalledIds: new Set(['sales']), hasUpdate: true })).toBe('installing');
  });
});

describe('catalogActionFor', () => {
  it('names the operation the row will actually run', () => {
    expect(catalogActionFor('available')).toBe('install');
    expect(catalogActionFor('updatable')).toBe('update');
  });

  it('offers nothing where there is nothing to do', () => {
    expect(catalogActionFor('installed')).toBe(null);
    expect(catalogActionFor('unavailable')).toBe(null);
    expect(catalogActionFor('installing')).toBe(null);
  });
});

// hub#1130: `request-install` now reports `also_installed` (dependency ids) alongside the module
// the owner actually asked for. The screen must name them by their catalogue NAME — the owner
// asked to install "Verifactu", not "invoice"/"sales"/"inventory".
describe('alsoInstalledNames', () => {
  const catalog = [
    { id: 'invoice', name: 'Facturas' },
    { id: 'sales', name: 'Ventas' },
  ];

  it('resolves each dragged-in id to its catalogue name, in the given order', () => {
    expect(alsoInstalledNames(['invoice', 'sales'], catalog)).toEqual(['Facturas', 'Ventas']);
  });

  it('falls back to the raw id for a module the catalogue does not know', () => {
    expect(alsoInstalledNames(['inventory'], catalog)).toEqual(['inventory']);
  });

  it('nothing dragged in → empty list, never dropped silently', () => {
    expect(alsoInstalledNames([], catalog)).toEqual([]);
  });
});
