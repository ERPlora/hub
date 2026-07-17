// Resolución PURA de slots cross-módulo (ADR-0043, `provides_slots`). Separada de la I/O de
// `module-loader` (red + `import()` del ESM) para poder fijar su contrato en un unit test: qué
// aportantes matchean un slot y en qué ORDEN se montan. Es el eslabón que decide si el picker de
// MESA/CLIENTE aparece en el POS; si el orden o el match se rompe, los botones desaparecen en
// silencio (el POS oculta el slot vacío). Genérico en el manifest para no acoplarse a `module-loader`.

type SlotDef = { slot?: string; component?: string; priority?: number };

export interface SlotFiller<M> {
  /** El módulo dueño (para cargar su ESM antes de montar el WC). */
  mod: M;
  /** El custom element a montar en el slot. */
  component: string;
}

/**
 * Filtra los `provides_slots` de todos los manifests que aportan a `slot` y los ordena por
 * `priority` ascendente (default 100; el sort de JS es estable → a igual priority manda el orden de
 * instalación). Descarta entradas sin `component` y manifests sin `provides_slots`. `[]` si nadie
 * aporta al slot.
 */
export function orderSlotFillers<M extends { manifest: unknown }>(
  manifests: M[],
  slot: string,
): SlotFiller<M>[] {
  const entries: Array<{ mod: M; component: string; priority: number }> = [];
  for (const mod of manifests) {
    const slots = (mod.manifest as { provides_slots?: SlotDef[] }).provides_slots ?? [];
    for (const def of slots) {
      if (def && def.slot === slot && def.component) {
        entries.push({ mod, component: def.component, priority: def.priority ?? 100 });
      }
    }
  }
  entries.sort((a, b) => a.priority - b.priority);
  return entries.map(({ mod, component }) => ({ mod, component }));
}
