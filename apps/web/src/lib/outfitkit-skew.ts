// Aviso de DERIVA de OutfitKit entre el shell y un módulo (hub#1024).
//
// **El defecto que hace visible.** Un módulo publicado hornea SU copia de OutfitKit: `erplora build`
// la resuelve desde los `node_modules` del toolkit —el checkout local de quien construyó— y la mete
// en `dist/<id>.esm.js`. En un hub real esa copia casi nunca manda: el shell define sus `ok-*` al
// arrancar (`main.ts` importa 20) y el `define()` horneado está GUARDADO
// (`if (!customElements.get(tag))`), así que pierde **en silencio**. La imagen, además, instala
// `@erplora/outfitkit@latest` en CADA build.
//
// O sea: la página corre **dos OutfitKit repartidos elemento por elemento** — el del shell para lo
// que él importa (`ok-data-table`…), el del módulo para lo que no (`ok-scheduler`, `ok-receipt`…) —
// y hasta hoy **nadie comparaba esas dos versiones**. Un cambio de contrato rompe módulos publicados
// sin que ningún test lo vea, y en `pnpm dev` no reproduce porque ahí las dos copias son el mismo
// checkout: por eso hub#754 y hub#804 se cerraron con un «no reproducible en develop».
//
// Esto **no arregla** la deriva: la hace visible. Una línea, con las dos versiones, para que el
// siguiente que mire la consola no tenga que deducirlo.

/** Módulos ya avisados en esta sesión. El aviso es por MÓDULO, no por carga. */
const warned = new Set<string>();

/** Para los tests: olvida lo avisado. */
export function resetOutfitkitSkewWarnings(): void {
  warned.clear();
}

/**
 * Avisa si la OutfitKit horneada en el módulo no es la del shell.
 *
 * Se calla en tres casos, y los tres a propósito:
 * - **misma versión** — no hay nada que contar;
 * - **el módulo no trae sello** — son los 25 publicados de hoy (el sello lo añade module-toolkit
 *   ahora): avisar de todos ellos en cada arranque enterraría el aviso que sí importa;
 * - **el shell no sabe la suya** — comparar contra un hueco no dice nada de nadie.
 *
 * Y avisa **una vez por módulo**: el shell carga el bundle varias veces por sesión (menú, widgets,
 * slots cross-módulo) y un aviso por carga es ruido, que se ignora igual que el silencio.
 */
export function warnOnOutfitkitSkew(
  moduleId: string,
  bakedVersion: string | undefined,
  shellVersion: string,
): void {
  if (!bakedVersion || !shellVersion || bakedVersion === shellVersion) return;
  if (warned.has(moduleId)) return;
  warned.add(moduleId);
  console.warn(
    `[erplora] «${moduleId}» se construyó con OutfitKit ${bakedVersion} y este hub trae la ` +
      `${shellVersion}. Los ok-* que el shell ya define ganan, así que la copia del módulo se ` +
      `descarta: si algo de su interfaz no responde, esta diferencia es el primer sitio donde mirar.`,
  );
}
