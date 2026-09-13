// Helpers compartidos por el contrato visual del shell (hub#1240, hub#1250).
//
// Login, dashboard, apps, ajustes y personal comparten la MISMA sesión (PIN del seed de dev) y
// los MISMOS tres anchos — antes de este fichero, `loginByPin`/`withSession` ya se habían
// duplicado en cuatro specs distintos (Dashboard/Export/Import/NoStrayGetApiQuery); para el
// contrato visual, que crece de una pantalla a cinco en esta misma issue, esa duplicación deja de
// ser tolerable: una divergencia silenciosa entre copias es exactamente el tipo de defecto que un
// contrato visual existe para cazar.

import { expect, request as pwRequest, type Locator, type Page, type TestInfo } from '@playwright/test';
import { existsSync } from 'node:fs';
import { shouldSkipMissingBaselineLocally } from '../../src/lib/visual-baseline-gate';
import { everyOnScreenIconIsPainted, everyScrollerHasStoppedMoving, shellChromeHasSettled } from './visual-settle';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

/** Los tres anchos del contrato de UI del proyecto: escritorio, tablet y móvil. */
export { VIEWPORTS } from './viewports';

/** Sesión REAL del runtime vía `/api/auth/pin` (usuario Demo / PIN 0000 del seed de dev). */
export async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  // The device identifies itself, exactly as the browser of a real till does (hub#330: a PIN login
  // that identifies no device is refused). The bank disarms the trust gate with
  // `HUB_DEVICE_TRUST=off` (see `playwright.config.ts`) because the id a browser mints is random
  // and there is nothing to pre-trust in an ephemeral bank.
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `login PIN falló: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  expect(body.token, 'el runtime no devolvió token de sesión').toBeTruthy();
  await api.dispose();
  return { token: body.token, user: body.user };
}

/** Inyecta la sesión ya emitida por el runtime (mismas claves que `lib/session.ts`). */
export async function withSession(page: Page, s: Session): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [s.token, s.user] as const,
  );
}

/** Atajo: login + sesión inyectada, para specs que no necesitan tocar la respuesta cruda. */
export async function loggedInSession(page: Page): Promise<void> {
  await withSession(page, await loginByPin());
}

/**
 * Instante que ve el navegador en TODA captura del contrato visual.
 *
 * Un lunes, laborable, a media mañana y lejos del cambio de hora: el saludo del dashboard sale
 * «Buenos días» en las dos zonas horarias que este banco usa (UTC en el runner, Europe/Madrid en
 * un Mac), y la fecha no cae ni en fin de semana ni en festivo, que es lo que cambia la forma de
 * una pantalla de agenda el día que una entre en el contrato.
 */
const VISUAL_CLOCK = new Date('2026-01-12T09:30:00.000Z');

/**
 * Congela el reloj del navegador ANTES de navegar. Hay que llamarlo en todo `*Visual.spec.ts`, y
 * lo exige `tests/visual-baselines-present.test.ts`.
 *
 * Por qué: dos de las cinco pantallas del contrato pintan la hora —el dashboard su saludo y su
 * fecha («Buenos días · Hoy, viernes, 11 de septiembre»), ajustes la hora de la zona horaria
 * («Automática · Europe/Madrid, 08:51»)—. Con el reloj vivo, su baseline caduca sola: la de
 * ajustes al minuto siguiente y la del dashboard al día siguiente, y el rojo cae sobre PRs que no
 * han tocado esa pantalla. Es exactamente el fallo que hace que un gate se acabe ignorando.
 *
 * `setFixedTime` y no `install()`: solo fija lo que `Date` contesta. `install()` además PARA los
 * temporizadores, y el shell monta con `setTimeout` de por medio (Ionic hidratando, las
 * transiciones de vista), así que pausarlos deja la captura a medio pintar.
 */
export async function freezeVisualClock(page: Page): Promise<void> {
  await page.clock.setFixedTime(VISUAL_CLOCK);
}

/**
 * Salta el caso (con motivo, en voz alta) si la baseline de esta plataforma no existe TODAVÍA.
 *
 * Fuera de CI, siempre (hub#1240: un Mac nunca va a igualar el PNG de Linux). En CI, NUNCA
 * (hub#1752): allí una baseline que falta cae a la aserción normal y falla nombrando la captura
 * —`updateSnapshots: 'none'` en `playwright.config.ts`—, porque alguien la borró en una PR sobre
 * un contrato que ya funcionaba.
 *
 * `testInfo.skip()` aborta la ejecución del caso en el sitio si corresponde saltar — la llamada
 * es suficiente, no hace falta comprobar un valor de vuelta.
 */
export function skipIfBaselineMissingLocally(testInfo: TestInfo, snapshot: string): void {
  const baseline = testInfo.snapshotPath(snapshot);
  if (shouldSkipMissingBaselineLocally(process.env, existsSync(baseline))) {
    const reason = `falta la baseline ${baseline} — genérala con el workflow visual-baselines.yml (workflow_dispatch, en Linux)`;
    // El reporter `list` pinta un guion por caso saltado y el motivo no lo pinta nadie: sin esta
    // línea, el salto solo se descubre leyendo el log entero. En CI va además como anotación de
    // Actions (`::warning::`), que sale en el resumen del run y en la pestaña de checks de la PR.
    console.log(process.env.CI ? `::warning file=${testInfo.file}::${reason}` : `SKIP: ${reason}`);
    testInfo.skip(true, reason);
  }
}

/**
 * Lo que TODA captura del contrato visual tiene que TAPAR, y por qué solo esto.
 *
 * El QR del sidebar codifica la dirección del hub que está en pantalla — en el banco,
 * `http://localhost:<puerto>` (`lib/install-qr.ts`: `hubUrl(host) ?? origin`). Hasta hub#1812 el
 * banco clavaba 8787/5173 y esa dirección era la misma en cada corrida; desde hub#1812 cada
 * corrida toma su propio puerto (`bench-ports.ts`), así que el símbolo sale DISTINTO cada vez.
 * Medido el 11/09 regenerando en `:8850` y comparando en `:8860`, sin tocar nada más: las cuatro
 * pantallas de 1440px que pintan el sidebar —apps, dashboard, personal y ajustes— en rojo
 * (dashboard: 3.168 px contra el presupuesto de entonces, un ratio de 0,002 = 2.592 px a
 * 1440×900; desde hub#1823 el presupuesto es absoluto, 20 px — `visual-diff-budget.ts`).
 *
 * Se TAPA en vez de fijarse porque lo que codifica es legítimamente propio de cada máquina, y su
 * contenido ya tiene tests propios que no dependen de una foto (`lib/install-qr.test.ts`,
 * `components/sidebar-qr-symbol.test.ts`). Tapar NO saca el QR del contrato: Playwright pinta un
 * rectángulo sólido sobre el locator, así que un código que desaparezca, se mueva o cambie de
 * tamaño sigue poniendo la captura en rojo. Lo único que deja de compararse es el ruido de píxeles
 * de la dirección.
 *
 * `ok-qr` y no el bloque entero (`[data-testid="sidebar-install-qr"]`) a propósito: el título y la
 * pista («Ábrelo en el móvil», «Escanea el código…») son copy traducido que SÍ tiene que seguir en
 * la foto. Tapar el contenedor los sacaría del contrato de paso.
 *
 * Lo exige `tests/visual-baselines-present.test.ts`: un `*Visual.spec.ts` nuevo no puede olvidarlo.
 */
export function visualSnapshotMask(page: Page): Locator[] {
  return [page.locator('ok-qr')];
}

/**
 * Espera a que la pantalla esté REALMENTE terminada antes de fotografiarla (hub#1823).
 *
 * TRES cosas del shell se mueven DESPUÉS de que el punto de asentamiento de cada spec se cumpla, y
 * las tres salían en las capturas a medio hacer; medido el 11/09 contra el banco real:
 *
 *   · El CHROME todavía no ha decidido por dónde se entra al menú. `ion-menu` se registra en
 *     Ionic de forma asíncrona y hasta que lo hace el botón hamburguesa está en `display: none`:
 *     en 8 de 8 cargas de /settings a 390px seguía oculto en el asentamiento y a +200 ms, y
 *     aparecía antes de +1,5 s. La captura caía a un lado u otro del salto según la máquina.
 *   · Los ICONOS todavía no tienen su glifo. `ion-icon` inyecta su `<svg>` tras un
 *     IntersectionObserver: en 7 de 12 cargas de /dashboard a 390px quedaba uno en pantalla sin
 *     pintar en ese instante (pinta ~10 ms después).
 *   · El TABBAR se mueve solo. `ion-segment[scrollable]` empuja su propio scroll para insinuar
 *     que hay más pestañas: medido en /settings a 390px, la pista arranca a 889 ms — 117 ms
 *     DESPUÉS de que los dos predicados anteriores dieran la pantalla por lista—, llega a 28 px,
 *     se queda ahí 300 ms y vuelve a 0 a 1.368 ms. El runner de Linux fotografiaba los 28 px y
 *     este Mac los 0: 5.239 px en una sola pantalla.
 *
 * Con el presupuesto viejo (`maxDiffPixelRatio: 0.002` = 658 px a 390x844) nada de esto se veía;
 * con los 20 px absolutos de hub#1823 son 69 px y el contrato entero salía rojo en 2 de 12
 * corridas. Los predicados viven en `visual-settle.ts`, aparte, porque corren DENTRO del
 * navegador y tienen su propio guardia en vitest (`tests/visual-settle.test.ts`).
 *
 * Los timeouts son cortos A PROPÓSITO: si el chrome no se resuelve en cinco segundos, los glifos
 * no llegan en uno o algo sigue desplazándose pasados otros cinco, lo que hay no es una carrera
 * sino una pantalla rota, y eso tiene que salir como fallo con su mensaje, no como una espera de
 * 30 s que nadie asocia a su causa.
 *
 * Lo exige `tests/visual-baselines-present.test.ts`: un `*Visual.spec.ts` nuevo no puede olvidarlo.
 */
export async function waitForVisualSettle(page: Page): Promise<void> {
  await page.waitForFunction(shellChromeHasSettled, undefined, { timeout: 5_000 });
  await page.waitForFunction(everyOnScreenIconIsPainted, undefined, { timeout: 1_000 });
  await page.waitForFunction(everyScrollerHasStoppedMoving, undefined, { timeout: 5_000 });
}
