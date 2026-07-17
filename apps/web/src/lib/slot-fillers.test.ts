// @vitest-environment node
//
// Contrato de resolución de SLOTS cross-módulo (ADR-0043, `provides_slots`). Este es el eslabón que
// pinta el picker de MESA (tables→erp-tables-pos-zones) y de CLIENTE (customers→erp-customers-pos-search)
// dentro del POS de `sales`: si se rompe, los botones desaparecen EN SILENCIO (el POS oculta el slot
// vacío con `:empty { display:none }`). Por eso se fija aquí la parte pura —qué aportantes matchean un
// slot y en qué ORDEN— separada de la I/O (red + `import()` del ESM), que se ejerce por e2e.
//
// `module-loader` arrastra la cadena de iconos `~icons/…?raw` y el registro de ionicons; los mockeamos
// para poder importar el helper puro sin ese transform (mismo motivo por el que dashboard-widgets.test
// aísla su I/O). NO mockeamos datos: los manifests los construye el test con formas reales.
import { describe, it, expect, vi } from 'vitest';

vi.mock('./icons', () => ({ moduleIconRegistry: {} }));
vi.mock('ionicons', () => ({ addIcons: vi.fn() }));

import { orderSlotFillers } from './slot-fillers';
import type { InstalledManifest } from './module-loader';

/** Manifest instalado mínimo con un bloque `provides_slots` real. */
function mod(moduleId: string, provides_slots: unknown[]): InstalledManifest {
  return {
    moduleId,
    manifest: { provides_slots } as unknown as InstalledManifest['manifest'],
    entryUrl: `/modules/${moduleId}/dist/${moduleId}.esm.js`,
  };
}

describe('orderSlotFillers — resolución pura de provides_slots (ADR-0043)', () => {
  it('recoge solo los aportantes que matchean el slot pedido', () => {
    const manifests = [
      mod('tables', [{ slot: 'sales.pos.order_context', component: 'erp-tables-pos-zones', priority: 100 }]),
      mod('customers', [{ slot: 'sales.pos.customer_context', component: 'erp-customers-pos-search', priority: 50 }]),
    ];
    const out = orderSlotFillers(manifests, 'sales.pos.order_context');
    expect(out.map((e) => e.component)).toEqual(['erp-tables-pos-zones']);
  });

  it('ordena por priority ascendente (el menor primero)', () => {
    const manifests = [
      mod('a', [{ slot: 's', component: 'erp-a', priority: 100 }]),
      mod('b', [{ slot: 's', component: 'erp-b', priority: 10 }]),
      mod('c', [{ slot: 's', component: 'erp-c', priority: 50 }]),
    ];
    const out = orderSlotFillers(manifests, 's');
    expect(out.map((e) => e.component)).toEqual(['erp-b', 'erp-c', 'erp-a']);
  });

  it('trata la priority ausente como 100 (default)', () => {
    const manifests = [
      mod('sin', [{ slot: 's', component: 'erp-sin' }]),
      mod('bajo', [{ slot: 's', component: 'erp-bajo', priority: 5 }]),
    ];
    const out = orderSlotFillers(manifests, 's');
    expect(out.map((e) => e.component)).toEqual(['erp-bajo', 'erp-sin']);
  });

  it('descarta entradas sin component y manifests sin provides_slots', () => {
    const manifests = [
      mod('roto', [{ slot: 's' }]),
      mod('vacio', []),
      { moduleId: 'sin-slots', manifest: {} as InstalledManifest['manifest'], entryUrl: '/x' },
      mod('bueno', [{ slot: 's', component: 'erp-bueno' }]),
    ];
    const out = orderSlotFillers(manifests, 's');
    expect(out.map((e) => e.component)).toEqual(['erp-bueno']);
  });

  it('devuelve [] cuando ningún módulo aporta al slot', () => {
    const manifests = [mod('tables', [{ slot: 'otro.slot', component: 'erp-x' }])];
    expect(orderSlotFillers(manifests, 'sales.pos.order_context')).toEqual([]);
  });

  it('conserva el módulo dueño junto al component (para cargar su ESM)', () => {
    const manifests = [mod('tables', [{ slot: 's', component: 'erp-tables-pos-zones' }])];
    const out = orderSlotFillers(manifests, 's');
    expect(out[0].mod.moduleId).toBe('tables');
    expect(out[0].mod.entryUrl).toContain('/modules/tables/');
  });

  // Para el modal de pestañas del POS (sales.pos.assign, ADR-0043 B): cada aportante declara en su
  // manifest `tab_label`/`tab_icon`, y el resolutor debe conservar el def entero para que sales pinte
  // la pestaña sin conocer al módulo. Es genérico (no sabe de "mesa"/"cliente"): pasa lo que venga.
  it('conserva el slot-def completo (tab_label/tab_icon/…) para que el consumidor lea su metadata', () => {
    const manifests = [
      mod('tables', [{ slot: 's', component: 'erp-tables-pos-zones', tab_label: 'Mesa', tab_icon: 'restaurant-outline' }]),
    ];
    const out = orderSlotFillers(manifests, 's');
    expect(out[0].def).toMatchObject({ component: 'erp-tables-pos-zones', tab_label: 'Mesa', tab_icon: 'restaurant-outline' });
  });
});
