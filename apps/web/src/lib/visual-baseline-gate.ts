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
 * Solo fuera de CI (hub#1240 — un Mac nunca va a igualar el PNG de Linux). Saltar NO crea nada: el
 * `testInfo.skip()` aborta el caso antes de que `updateSnapshots: 'missing'` llegue a escribir. Para
 * tener baselines locales con las que trabajar se piden una vez con `HUB_UPDATE_BASELINES=1`, que
 * escribe las de tu plataforma; las siguientes corridas comparan contra ellas.
 *
 * 🔴 En CI NO se salta NUNCA: una baseline que falta es un FALLO. Hasta hub#1752 había aquí una
 * excepción —si el directorio `<Spec>.spec.ts-snapshots/` no existía, se saltaba también en CI—
 * pensada para el estado transitorio de hub#1250: cinco specs recién escritos y ningún PNG
 * todavía, donde un rojo permanente habría sido ruido. El problema es que ese estado no fue
 * transitorio: `visual-baselines.yml` no llegó a correr NI UNA VEZ, la issue se cerró igual, y
 * durante doce días cada PR del repo enseñó un `playwright (test:e2e)` en verde que parecía decir
 * «el aspecto está comprobado» sin haber mirado una sola pantalla. Con las baselines ya
 * commiteadas, lo único que esa excepción podía seguir tapando era que alguien las borrase
 * enteras — que es exactamente el caso que hay que ver en rojo.
 *
 * El guardia que impide volver al estado sin baselines es `tests/visual-baselines-present.test.ts`,
 * que corre en vitest (sin navegador) y falla en segundos en vez de veinte minutos.
 */
export function shouldSkipMissingBaselineLocally(
  env: VisualBaselineEnv,
  baselineExists: boolean,
): boolean {
  if (env.HUB_UPDATE_BASELINES === '1') return false;
  if (baselineExists) return false;
  return !env.CI;
}
