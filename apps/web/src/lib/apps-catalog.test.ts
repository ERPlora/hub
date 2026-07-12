// Estado de instalación de una fila del catálogo (AppsPage). El catálogo Cloud es un PROXY al SaaS
// y su flag `installed` puede no reflejar aún la instalación de ESTE hub (`mark_installed` es
// best-effort). El runtime es la FUENTE DE VERDAD local: si el módulo está en la lista instalada
// local, la fila debe salir "Instalado" (badge + botón deshabilitado), aunque el Cloud diga false.
// (Bug reportado en el demo 2026-07-12: un módulo recién instalado seguía como "Disponible".)
import { describe, expect, it } from 'vitest';

import { isModuleInstalled } from './apps-catalog';

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
