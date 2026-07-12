// Lógica pura del catálogo de Apps (AppsPage), extraída para poder testearla en el entorno node.

/**
 * ¿Está instalado un módulo del catálogo en ESTE hub?
 *
 * El catálogo Cloud es un proxy al SaaS y su `cloudInstalled` puede ir por detrás de la realidad de
 * este hub (`mark_installed/` es best-effort). El runtime es la fuente de verdad local, así que
 * cruzamos con el conjunto de módulos instalados localmente: si está en cualquiera de los dos,
 * cuenta como instalado. Evita mostrar "Disponible" (y el botón Instalar activo) en un módulo ya
 * instalado (bug del demo 2026-07-12).
 */
export function isModuleInstalled(
  cloudInstalled: boolean,
  id: string,
  localInstalledIds: ReadonlySet<string>,
): boolean {
  return cloudInstalled || localInstalledIds.has(id);
}
