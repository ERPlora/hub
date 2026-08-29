// Gate del contrato visual del shell (`toHaveScreenshot`, hub#1240 / hub#1250) — decisiones puras,
// sin tocar el sistema de ficheros ni Playwright, para poder testearlas sin navegador.
//
// Por qué hace falta un módulo propio: el valor por defecto de Playwright para `updateSnapshots`
// es `'missing'` (crea el PNG que falte y el caso pasa en VERDE, en cualquier entorno, CI
// incluido — no es un comportamiento nuestro, es el de la librería). Eso es justo lo contrario de
// lo que un contrato visual necesita: si alguien borra una baseline en una PR, `'missing'` la
// regenera sola en el runner y el caso sigue en verde como si nada hubiera pasado.

/** Subconjunto de `process.env` del que dependen estas decisiones. */
export interface VisualBaselineEnv {
  CI?: string;
  HUB_UPDATE_BASELINES?: string;
}

/**
 * Modo `updateSnapshots` de Playwright, derivado del entorno.
 *
 * - En la corrida DEDICADA a regenerar baselines (`HUB_UPDATE_BASELINES=1`, disparada a mano
 *   desde `visual-baselines.yml`) → `'all'`: reescribe cualquier captura, que es justo lo que se
 *   pidió al lanzarla.
 * - En cualquier OTRA corrida de CI → `'none'`: una baseline ausente debe FALLAR, nunca crearse
 *   sola. Es el único modo de Playwright que no la regenera — así una baseline borrada por
 *   accidente (o a propósito, en una PR) tumba el caso en vez de dejarlo pasar en silencio.
 * - Fuera de CI (una máquina de desarrollo) → `'missing'`, el valor por defecto de Playwright:
 *   crea lo que falte sin pisar lo que ya exista. Sirve para desarrollar un caso nuevo; esas
 *   capturas nunca se commitean porque no van a coincidir con las de Linux (hub#1240).
 */
export function resolveUpdateSnapshotsMode(env: VisualBaselineEnv): 'all' | 'none' | 'missing' {
  if (env.HUB_UPDATE_BASELINES === '1') return 'all';
  if (env.CI) return 'none';
  return 'missing';
}

/**
 * Si el caso debe SALTARSE (con motivo) en vez de dejar que la aserción compare contra una
 * baseline ausente.
 *
 * Aplica solo fuera de CI (hub#1250 — antes saltaba en cualquier entorno, y eso es lo que dejaba
 * una baseline borrada en una PR pasar en verde por salto). En CI, una baseline ausente cae
 * siempre a la aserción normal, que falla gracias a `resolveUpdateSnapshotsMode` devolviendo
 * `'none'` — nunca se salta.
 */
export function shouldSkipMissingBaselineLocally(env: VisualBaselineEnv, baselineExists: boolean): boolean {
  if (env.HUB_UPDATE_BASELINES === '1') return false;
  if (env.CI) return false;
  return !baselineExists;
}
