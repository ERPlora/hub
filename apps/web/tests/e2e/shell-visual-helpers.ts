// Helpers compartidos por el contrato visual del shell (hub#1240, hub#1250).
//
// Login, dashboard, apps, ajustes y personal comparten la MISMA sesión (PIN del seed de dev) y
// los MISMOS tres anchos — antes de este fichero, `loginByPin`/`withSession` ya se habían
// duplicado en cuatro specs distintos (Dashboard/Export/Import/NoStrayGetApiQuery); para el
// contrato visual, que crece de una pantalla a cinco en esta misma issue, esa duplicación deja de
// ser tolerable: una divergencia silenciosa entre copias es exactamente el tipo de defecto que un
// contrato visual existe para cazar.

import { expect, request as pwRequest, type Page, type TestInfo } from '@playwright/test';
import { existsSync } from 'node:fs';
import { shouldSkipMissingBaselineLocally } from '../../src/lib/visual-baseline-gate';

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
