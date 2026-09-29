// TDD (hub#516): qué enseña la pantalla de Apps sobre las actualizaciones de módulo.
//
// La decisión de QUÉ versión toca es del runtime (`GET /api/modules/updates`, mismo resolutor que
// el arranque: respeta cuarentena y pin, nunca va hacia atrás). Aquí solo vive la parte de
// presentación, y su regla es la de ADR-0269 §3.5: **de → a, y solo lo que cambió**. Una lista de
// 24 módulos donde 23 dicen «sin cambios» es ruido, y el ruido se deja de leer.
import { describe, expect, it } from 'vitest';

import {
  defaultVersion,
  pendingUpdate,
  shouldPickVersion,
  updateAll,
  updateAllTargets,
  updateLabel,
  type ModuleUpdateInfo,
} from './module-updates';

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

// hub#675 — elegir versión. El runtime dice ENTRE QUÉ se puede elegir (`GET
// /api/modules/:id/versions`, ya sin cuarentena, sin retroceso y sin saltarse el pin); aquí solo
// está lo que la pantalla hace con esa lista.
describe('defaultVersion', () => {
  it('offers the latest, which is the first the runtime returns', () => {
    expect(defaultVersion(['2.1.0', '2.0.0', '1.0.0'])).toBe('2.1.0');
  });

  it('falls back to `latest` when the runtime returned nothing', () => {
    // El Cloud no contestó. Instalar NO puede quedarse bloqueado por eso: `latest` es el centinela
    // que el runtime resuelve por su cuenta, exactamente igual que antes de que hubiera desplegable.
    expect(defaultVersion([])).toBe('latest');
  });
});

describe('shouldPickVersion', () => {
  it('asks when there is genuinely something to choose', () => {
    expect(shouldPickVersion(['2.1.0', '2.0.0'])).toBe(true);
  });

  it('does NOT ask when there is a single option — un diálogo de una sola opción es un clic de peaje', () => {
    expect(shouldPickVersion(['2.1.0'])).toBe(false);
  });

  it('does NOT ask when there is nothing to choose', () => {
    expect(shouldPickVersion([])).toBe(false);
  });
});

// hub#2331 — «Update all» in «My apps». It rides the SAME per-app update the row button uses
// (`POST /api/modules/{id}/update`); what lives here is which apps enter the batch and how the batch
// reports. The screen wiring is pinned by `views/AppsPage.update-all.hub2331.test.ts`.
describe('updateAllTargets', () => {
  const installed = [
    { id: 'sales', name: 'Sales' },
    { id: 'inventory', name: 'Inventory' },
    { id: 'pinned', name: 'Pinned' },
    { id: 'current', name: 'Current' },
    { id: 'future', name: 'Future' },
  ];
  const updates = [
    info({ module_id: 'inventory' }),
    info({ module_id: 'sales' }),
    // Pinned by support: the runtime reports no update → nothing offered.
    info({ module_id: 'pinned', update_available: false, pinned: '1.1.1' }),
    info({ module_id: 'current', update_available: false, latest: '1.1.1' }),
    // Needs a newer ERPlora than this hub runs (hub#2082): the owner cannot apply it.
    info({ module_id: 'future', latest_min_erplora_version: '9.0.0' }),
  ];

  it('takes every app the row would offer «Update» for, in the order of the list', () => {
    expect(updateAllTargets(installed, updates, '1.4.0')).toEqual([
      { id: 'sales', name: 'Sales' },
      { id: 'inventory', name: 'Inventory' },
    ]);
  });

  it('leaves out an update this hub is too old for', () => {
    expect(updateAllTargets(installed, updates, '1.4.0').map((t) => t.id)).not.toContain('future');
    // With a hub that meets the floor, it goes in.
    expect(updateAllTargets(installed, updates, '9.0.0').map((t) => t.id)).toContain('future');
  });

  it('is empty when nothing has a new version', () => {
    expect(updateAllTargets(installed, [], '1.4.0')).toEqual([]);
  });
});

describe('updateAll', () => {
  it('update_all_applies_every_offered_update_and_reports_each_result_hub1172', async () => {
    const calls: string[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const boom = new Error('marketplace down');
    const update = async (id: string) => {
      calls.push(id);
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight -= 1;
      if (id === 'inventory') throw boom;
      if (id === 'kitchen') return { updated: false, from: '2.0.0', to: '2.0.0' };
      return { updated: true, from: '1.0.0', to: '1.1.0' };
    };
    const steps: Array<[number, string]> = [];

    const results = await updateAll(
      [
        { id: 'sales', name: 'Sales' },
        { id: 'inventory', name: 'Inventory' },
        { id: 'kitchen', name: 'Kitchen' },
        { id: 'tables', name: 'Tables' },
      ],
      update,
      (index, target) => steps.push([index, target.id]),
    );

    // Every one, one after another — a failure in the middle does not stop the rest.
    expect(calls).toEqual(['sales', 'inventory', 'kitchen', 'tables']);
    expect(maxInFlight).toBe(1);
    expect(steps).toEqual([[0, 'sales'], [1, 'inventory'], [2, 'kitchen'], [3, 'tables']]);
    expect(results).toEqual([
      { id: 'sales', name: 'Sales', status: 'updated', from: '1.0.0', to: '1.1.0' },
      { id: 'inventory', name: 'Inventory', status: 'failed', error: boom },
      { id: 'kitchen', name: 'Kitchen', status: 'up_to_date' },
      { id: 'tables', name: 'Tables', status: 'updated', from: '1.0.0', to: '1.1.0' },
    ]);
  });

  it('with nothing to update, asks nothing', async () => {
    let asked = 0;
    const results = await updateAll([], async () => {
      asked += 1;
      return { updated: true, from: '1', to: '2' };
    });
    expect(results).toEqual([]);
    expect(asked).toBe(0);
  });
});
