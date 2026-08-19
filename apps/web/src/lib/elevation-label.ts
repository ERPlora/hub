// Qué se está aprobando, dicho en las palabras del negocio (hub#579).
//
// El diálogo de aprobación no imprimía NADA: ni la acción, ni siquiera de qué app venía. El
// encargado tecleaba su PIN a ciegas, y un recibo (`approved_by`) que no dice qué se aprobó es un
// sello de goma.
//
// Lo que **no** se hace, y sigue siendo la decisión de hub#363: imprimir la clave de permiso o el
// nombre del command. `sales.void` es vocabulario nuestro, no del mostrador — y enseñarlo en la
// pantalla que mira el cliente sería resolver el problema rompiendo la razón por la que existía.
//
// La escalera, de mejor a peor: la traducción que el MÓDULO da a ese command → el nombre localizado
// del módulo → una frase genérica. Nunca el command crudo.
import { ref } from 'vue';

import type { InstalledManifest } from './module-loader';

/** Lo que un módulo aporta para poder nombrar sus acciones. */
export interface ElevationCatalogueEntry {
  moduleId: string;
  /** Nombre del módulo YA localizado (el mismo que pinta la navegación). */
  moduleName: string;
  /** `commands["<módulo>.<acción>"].label` de su `locales/<lang>.json`. */
  commands: Record<string, { label?: string }>;
}

/** Lo que el diálogo pinta. Cadenas vacías = «no se sabe», y la UI cae a su copia genérica. */
export interface ElevationDescription {
  /** La acción en palabras del negocio («Anular una venta»). */
  action: string;
  /** De qué app viene, localizado («Ventas / TPV»). */
  moduleName: string;
}

/** El módulo de un command namespaced: lo de delante del PRIMER punto (`sales.orders.void`). */
export function moduleOfCommand(command: string): string {
  const dot = command.indexOf('.');
  return dot > 0 ? command.slice(0, dot) : '';
}

/**
 * Describe la acción que espera aprobación. `ask` se acepta parcial a propósito: aquí solo se usa
 * `command`, y aceptar el `ElevationAsk` entero ataría esta función —y sus tests— al transporte.
 */
export function describeElevation(
  ask: { command: string; permission?: string },
  catalogue: readonly ElevationCatalogueEntry[],
): ElevationDescription {
  const moduleId = moduleOfCommand(ask.command);
  const entry = catalogue.find((c) => c.moduleId === moduleId);
  if (!entry) return { action: '', moduleName: '' };
  return {
    action: entry.commands[ask.command]?.label?.trim() || '',
    moduleName: entry.moduleName.trim(),
  };
}

/** El catálogo vigente. Vacío = todavía no se sabe, y la escalera degrada al mensaje genérico. */
export const elevationCatalogue = ref<ElevationCatalogueEntry[]>([]);

/**
 * Lo llena desde lo que el shell ya carga. El `import()` es DINÁMICO a propósito: `module-loader`
 * arrastra el registro de iconos, y meterlo en el grafo estático de un diálogo que vive montado
 * siempre convierte una pantalla de aprobación en un motivo para cargar medio shell.
 */
export async function loadElevationCatalogue(): Promise<void> {
  try {
    const { loadInstalledManifests } = await import('./module-loader');
    elevationCatalogue.value = catalogueFromManifests(await loadInstalledManifests());
  } catch {
    elevationCatalogue.value = [];
  }
}

/** Construye el catálogo desde lo que ya carga el shell (manifests instalados + su locale). */
export function catalogueFromManifests(
  installed: readonly InstalledManifest[],
): ElevationCatalogueEntry[] {
  return installed.map((m) => ({
    moduleId: m.moduleId,
    // El `name` del manifest es el inglés canónico (ADR-0055); el locale del módulo lo traduce.
    moduleName: m.locale?.name?.trim() || m.manifest.name,
    commands: m.locale?.commands ?? {},
  }));
}
