// TDD (hub#516): qué enseña la pantalla de Apps sobre las actualizaciones de módulo.
//
// La decisión de QUÉ versión toca es del runtime (`GET /api/modules/updates`, mismo resolutor que
// el arranque: respeta cuarentena y pin, nunca va hacia atrás). Aquí solo vive la parte de
// presentación, y su regla es la de ADR-0269 §3.5: **de → a, y solo lo que cambió**. Una lista de
// 24 módulos donde 23 dicen «sin cambios» es ruido, y el ruido se deja de leer.
import { describe, expect, it } from 'vitest';

import { pendingUpdate, updateLabel, type ModuleUpdateInfo } from './module-updates';

const info = (over: Partial<ModuleUpdateInfo> = {}): ModuleUpdateInfo => ({
  module_id: 'inventory',
  installed: '1.1.1',
  latest: '1.1.2',
  update_available: true,
  pinned: null,
  ...over,
});

describe('pendingUpdate', () => {
  it('encuentra la actualización del módulo por su id', () => {
    const found = pendingUpdate('inventory', [info()]);
    expect(found?.latest).toBe('1.1.2');
  });

  it('un módulo sin actualización NO aparece — es la mitad del valor de la lista', () => {
    expect(pendingUpdate('inventory', [info({ update_available: false })])).toBeNull();
  });

  it('un módulo que no está en la respuesta no inventa una actualización', () => {
    expect(pendingUpdate('sales', [info()])).toBeNull();
  });

  it('sin respuesta del runtime no se ofrece nada: «no lo sé» nunca se pinta como «hay novedad»', () => {
    expect(pendingUpdate('inventory', [])).toBeNull();
  });

  it('un módulo CLAVADO por soporte no ofrece actualizarse aunque haya versión más nueva', () => {
    // El pin es una herramienta nuestra, no una opción del dueño: si lo hemos dejado en 1.1.1
    // mientras se arregla la 1.1.2, el botón no puede ser la forma de saltárselo.
    const pinned = info({ pinned: '1.1.1', update_available: false, latest: '1.1.1' });
    expect(pendingUpdate('inventory', [pinned])).toBeNull();
  });
});

describe('updateLabel', () => {
  it('dice DE → A, no solo la versión nueva', () => {
    // «Inventario 1.1.2» no dice nada; «1.1.1 → 1.1.2» sí.
    expect(updateLabel('1.1.1', info())).toBe('1.1.1 → 1.1.2');
  });

  it('sin actualización pendiente enseña solo la versión que corre', () => {
    expect(updateLabel('1.1.1', null)).toBe('1.1.1');
  });

  it('un módulo sin versión conocida no enseña una flecha huérfana', () => {
    expect(updateLabel('', null)).toBe('');
  });
});
