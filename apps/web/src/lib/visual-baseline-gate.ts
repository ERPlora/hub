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
 * Fuera de CI siempre se salta lo que falte (hub#1240 — un Mac nunca va a igualar el PNG de
 * Linux). En CI la respuesta depende de si esta pantalla ha llegado a tener ALGUNA baseline
 * generada (`baselineDirExists`, el directorio `<Spec>.spec.ts-snapshots/`):
 *
 * - Directorio inexistente → la pantalla nunca se ha regenerado todavía (es justo el estado de
 *   este PR: cinco specs nuevos, cero PNG en el repo, y `visual-baselines.yml` no se puede
 *   disparar hasta llegar a `main`). Saltar en voz alta aquí es la MISMA razón por la que
 *   saltábamos en cualquier entorno antes de hub#1250: un rojo por un fichero que aún no existe
 *   no es una señal, es ruido — y sin este caso, fusionar este PR pondría en rojo permanente el
 *   job `e2e` de `test-web.yml` para cualquier PR que toque `apps/web/**`, mucho antes de que
 *   nadie haya podido generar nada.
 * - Directorio existente pero falta ESTE fichero → alguien la borró (a propósito o no) en una PR
 *   sobre un contrato que ya funcionaba. Ahí no se salta: cae a la aserción normal, que falla
 *   gracias a `resolveUpdateSnapshotsMode` devolviendo `'none'` — es el hueco que señaló Ioan en
 *   el comentario del 27/08 (hub#1250).
 */
export function shouldSkipMissingBaselineLocally(
  env: VisualBaselineEnv,
  baselineExists: boolean,
  baselineDirExists: boolean,
): boolean {
  if (env.HUB_UPDATE_BASELINES === '1') return false;
  if (baselineExists) return false;
  if (!env.CI) return true;
  return !baselineDirExists;
}
