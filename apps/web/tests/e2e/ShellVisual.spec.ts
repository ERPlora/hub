// Regression test for ERPlora/hub#1240 — contrato VISUAL del shell (geometría, no prosa).
//
// Por qué existe: el hub no tenía UNA sola baseline visual, y las 511 pruebas de componentes
// corren en happy-dom, que no calcula layout. Por eso pudieron pasar en verde con dos componentes
// peor colocados que antes, y por eso las issues de pulido (#1197 #1169 #1166 #1106) son todas de
// geometría: nada las podía ver. `toHaveScreenshot` es lo único de esta casa que mira la pantalla.
//
// Se elige el LOGIN como primera pantalla a propósito: es la única que un hub vacío pinta sin
// sesión, así que su captura no depende del seed, del reloj ni de qué módulos haya — las tres
// fuentes habituales de una baseline que parpadea. Las otras cuatro pantallas del shell
// (dashboard, apps, ajustes, personal) viven en sus propios specs `*Visual.spec.ts` (hub#1250) y
// comparten con este los helpers de `shell-visual-helpers.ts`.
//
// ── Las baselines se generan DONDE CORREN ────────────────────────────────────────────────────
// Un PNG hecho en un Mac no casa jamás con el de un Linux (otra pila de fuentes, otro
// antialiasing), así que las de este repo se generan en el runner y se commitean desde ahí:
//   Actions → «Regenerar baselines visuales (Linux)» (visual-baselines.yml) → Run workflow
// Ese run corre con `--update-snapshots=all` y sube los PNG como artefacto para commitearlos.
//
// Mientras no exista la baseline de la plataforma en la que corres, el caso se SALTA en voz alta
// en vez de fallar — pero SOLO fuera de CI (hub#1250: en CI una baseline ausente tiene que FALLAR,
// no saltarse, o borrar un PNG en una PR volvería el caso verde por salto en lugar de rojo; ese
// fallo lo produce `updateSnapshots: 'none'` en `playwright.config.ts`). Ver
// `src/lib/visual-baseline-gate.ts` para la lógica y sus tests.

import { test, expect } from '@playwright/test';
import { VIEWPORTS, skipIfBaselineMissingLocally } from './shell-visual-helpers';

test.describe('contrato visual del shell — login', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`la pantalla de login se pinta igual a ${width}px (hub#1240)`, async ({ page }, testInfo) => {
      const snapshot = `login-${width}.png`;
      skipIfBaselineMissingLocally(testInfo, snapshot);

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
