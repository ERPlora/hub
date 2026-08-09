// Actualizaciones de módulo en la pantalla de Apps (hub#516).
//
// La decisión de QUÉ versión toca no vive aquí: la toma el runtime con el mismo resolutor que usa
// el arranque (`GET /api/modules/updates`), que respeta la cuarentena y el pin de soporte y nunca
// va hacia atrás. Aquí solo está la presentación, y su regla es la de ADR-0269 §3.5: **de → a, y
// solo lo que cambió**. Una lista de 24 módulos donde 23 dicen «sin cambios» es ruido, y el ruido
// se deja de leer.

/** Lo que el runtime dice de un módulo instalado (`GET /api/modules/updates`). */
export interface ModuleUpdateInfo {
  module_id: string;
  /** Versión que corre hoy este hub. */
  installed: string;
  /** Versión a la que iría — igual a `installed` cuando no hay nada más nuevo. */
  latest: string;
  update_available: boolean;
  /** Pin de soporte (`hub_module.pinned_version`). No es una opción de producto. */
  pinned: string | null;
}

/**
 * La actualización pendiente de un módulo, o `null` si no la hay.
 *
 * `null` cubre tres casos que se ven igual y deben verse igual: ya está en la última, el runtime no
 * pudo preguntar al marketplace, y el módulo está **clavado** por soporte. En los tres, **no se
 * ofrece nada**: «no lo sé» nunca se pinta como «hay novedad».
 */
export function pendingUpdate(
  moduleId: string,
  updates: readonly ModuleUpdateInfo[],
): ModuleUpdateInfo | null {
  const found = updates.find((u) => u.module_id === moduleId);
  return found && found.update_available ? found : null;
}

/**
 * Lo que se enseña en la columna de versión: `1.1.1 → 1.1.2` si hay actualización, y solo la
 * versión instalada si no.
 *
 * Va el **de → a** y no solo la nueva porque «Inventario 1.1.2» no dice nada y «1.1.1 → 1.1.2» sí:
 * es la primera pregunta de cualquier incidencia.
 */
export function updateLabel(installed: string, update: ModuleUpdateInfo | null): string {
  if (!installed) return '';
  return update ? `${installed} → ${update.latest}` : installed;
}
