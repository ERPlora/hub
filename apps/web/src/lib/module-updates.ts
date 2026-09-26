// Actualizaciones de módulo en la pantalla de Apps (hub#516).
//
// La decisión de QUÉ versión toca no vive aquí: la toma el runtime con el mismo resolutor que usa
// el arranque (`GET /api/modules/updates`), que respeta la cuarentena y el pin de soporte y nunca
// va hacia atrás. Aquí solo está la presentación, y su regla es la de ADR-0269 §3.5: **de → a, y
// solo lo que cambió**. Una lista de 24 módulos donde 23 dicen «sin cambios» es ruido, y el ruido
// se deja de leer.

import { hubTooOldFor } from './apps-catalog';

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
  /**
   * The ERPlora the `latest` version needs (hub#2082), `null` when it declares none. Absent from a
   * runtime older than the field — read the same as `null`: nothing to warn about.
   */
  latest_min_erplora_version?: string | null;
}

/**
 * Whether the pending update needs a newer ERPlora than this hub runs (hub#2082).
 *
 * Same comparison as the catalog card ({@link hubTooOldFor}, hub#2054) and the runtime's refusal.
 * Only a floor and a hub version that can BOTH be read say «too old»: otherwise «Update» stays, and
 * the runtime still refuses at update time.
 */
export function updateNeedsNewerHub(update: ModuleUpdateInfo | null, hubVersion: string | null | undefined): boolean {
  return update !== null && hubTooOldFor(update.latest_min_erplora_version ?? null, hubVersion);
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

/** Lo que dice `GET /api/modules/:id/versions`: entre qué puede elegir este hub (hub#675). */
export interface ModuleVersions {
  module_id: string;
  /** Versión que corre hoy, o `null` si el módulo aún no está instalado (caso de instalar). */
  installed: string | null;
  /** La que se ofrece por defecto (= `versions[0]`), o `null` si no hay nada que elegir. */
  latest: string | null;
  /** De la más nueva a la más vieja. Ya vienen sin cuarentena, sin retroceso y sin saltarse el pin. */
  versions: string[];
}

/**
 * La versión que se pide cuando nadie elige otra: **la última**, que es la primera de la lista.
 *
 * Sin lista se cae a `latest`, el centinela que el runtime resuelve por su cuenta. Esa rama no es
 * un detalle: si el Cloud no contesta, instalar tiene que seguir funcionando exactamente igual que
 * antes de que existiera el desplegable — una pantalla que se queda sin lista no puede convertirse
 * en una pantalla que no instala.
 */
export function defaultVersion(versions: readonly string[]): string {
  return versions[0] ?? 'latest';
}

/**
 * ¿Hay algo que preguntar? Solo con **más de una** opción.
 *
 * Con una sola —o con ninguna— el diálogo no aporta una decisión: cobra un clic por confirmar lo
 * único que se podía hacer. El caso común (un módulo con una versión nueva) sigue siendo un clic.
 */
export function shouldPickVersion(versions: readonly string[]): boolean {
  return versions.length > 1;
}
