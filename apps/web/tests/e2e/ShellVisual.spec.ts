// Regression test for ERPlora/hub#1240 — contrato VISUAL del shell (geometría, no prosa).
//
// Por qué existe: el hub no tenía UNA sola baseline visual, y las 511 pruebas de componentes
// corren en happy-dom, que no calcula layout. Por eso pudieron pasar en verde con dos componentes
// peor colocados que antes, y por eso las issues de pulido (#1197 #1169 #1166 #1106) son todas de
// geometría: nada las podía ver. `toHaveScreenshot` es lo único de esta casa que mira la pantalla.
//
// Se elige el LOGIN como primera pantalla a propósito: es la única que un hub vacío pinta sin
// sesión, así que su captura no depende del seed, del reloj ni de qué módulos haya — las tres
// fuentes habituales de una baseline que parpadea.
//
// ── Las baselines se generan DONDE CORREN ────────────────────────────────────────────────────
// Un PNG hecho en un Mac no casa jamás con el de un Linux (otra pila de fuentes, otro
// antialiasing), así que las de este repo se generan en el runner y se commitean desde ahí:
//   Actions → «Web tests (typecheck · vitest · e2e)» → Run workflow → update_baselines: true
// Ese run corre con `--update-snapshots` y sube los PNG como artefacto para commitearlos.
//
// Mientras no exista la baseline de la plataforma en la que corres, el caso se SALTA en voz alta
// en vez de fallar: un rojo permanente por un fichero que aún no se ha generado no es una señal,
// es ruido que se aprende a ignorar (que es exactamente cómo hub#1200 aguantó en develop).

import { test, expect } from '@playwright/test';
import { existsSync } from 'node:fs';

/** Los tres anchos del contrato de UI del proyecto: escritorio, tablet y móvil. */
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
];

/** `test:e2e` con `--update-snapshots` lo exporta el workflow: ahí no hay nada que saltarse. */
const UPDATING_BASELINES = process.env.HUB_UPDATE_BASELINES === '1';

test.describe('contrato visual del shell', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`la pantalla de login se pinta igual a ${width}px (hub#1240)`, async ({ page }, testInfo) => {
      const snapshot = `login-${width}.png`;
      // `snapshotPath` resuelve la MISMA ruta que usará `toHaveScreenshot`, con su sufijo de
      // plataforma incluido: preguntar por ella es lo único que no se desincroniza del framework.
      const baseline = testInfo.snapshotPath(snapshot);
      if (!UPDATING_BASELINES && !existsSync(baseline)) {
        const reason = `falta la baseline ${baseline} — genérala donde corre el test (workflow_dispatch → update_baselines: true)`;
        // El reporter `list` pinta un guion por caso saltado y el MOTIVO no lo pinta nadie: sin esta
        // línea, el salto solo se descubre leyendo el log entero. En CI va además como anotación de
        // Actions (`::warning::`), que sale en el resumen del run y en la pestaña de checks de la PR.
        console.log(process.env.CI ? `::warning file=${testInfo.file}::${reason}` : `SKIP: ${reason}`);
        test.skip(true, reason);
      }

      await page.setViewportSize({ width, height });
      await page.goto('/login');

      // Punto de asentamiento: la caja de login ya montada. Antes de eso Ionic aún está hidratando
      // y la captura saldría a medio pintar (y distinta en cada corrida).
      await expect(page.getByTestId('login-box')).toBeVisible();
      // El shell pregunta al runtime si el dispositivo puede usar PIN; hasta que contesta, la
      // tarjeta cambia de forma. Los dos caminos de esa respuesta pintan una de estas dos filas
      // (confiar en el dispositivo / aviso de dispositivo personal), así que esperar a cualquiera
      // de las dos es esperar a que el estado asíncrono se haya asentado.
      //
      // Por clase y no por texto ni por rol: la pantalla está traducida (ADR-0055) y una espera
      // que dependa del idioma activo deja de funcionar en cuanto alguien cambia una cadena.
      await expect(page.locator('.trust-row, .setup-hint').first()).toBeVisible();

      // `fullPage` NO: en Ionic el scroll vive dentro de `ion-content`, así que una captura de
      // página completa sale del alto del viewport igual y encima añade una fuente de ruido.
      await expect(page).toHaveScreenshot(snapshot);
    });
  }
});
