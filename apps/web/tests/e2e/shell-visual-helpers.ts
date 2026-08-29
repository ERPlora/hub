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
import { dirname } from 'node:path';
import { shouldSkipMissingBaselineLocally } from '../../src/lib/visual-baseline-gate';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

/** Los tres anchos del contrato de UI del proyecto: escritorio, tablet y móvil. */
export const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
] as const;

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
 * Salta el caso (con motivo, en voz alta) si la baseline de esta plataforma no existe TODAVÍA.
 *
 * Fuera de CI, siempre (hub#1240: un Mac nunca va a igualar el PNG de Linux). En CI, solo si esta
 * pantalla no ha llegado a tener NINGUNA baseline generada todavía (el directorio
 * `<Spec>.spec.ts-snapshots/` no existe) — que es el estado de hub#1250 hasta que
 * `visual-baselines.yml` corra por primera vez. En cuanto exista una sola baseline para esta
 * pantalla, que falte ESTE fichero deja de saltarse y cae a la aserción normal: alguien la borró
 * en una PR, y eso tiene que fallar (`updateSnapshots: 'none'` en `playwright.config.ts`), no
 * saltarse en silencio.
 *
 * `testInfo.skip()` aborta la ejecución del caso en el sitio si corresponde saltar — la llamada
 * es suficiente, no hace falta comprobar un valor de vuelta.
 */
export function skipIfBaselineMissingLocally(testInfo: TestInfo, snapshot: string): void {
  const baseline = testInfo.snapshotPath(snapshot);
  const baselineDirExists = existsSync(dirname(baseline));
  if (shouldSkipMissingBaselineLocally(process.env, existsSync(baseline), baselineDirExists)) {
    const reason = `falta la baseline ${baseline} — genérala con el workflow visual-baselines.yml (workflow_dispatch, en Linux)`;
    // El reporter `list` pinta un guion por caso saltado y el motivo no lo pinta nadie: sin esta
    // línea, el salto solo se descubre leyendo el log entero. En CI va además como anotación de
    // Actions (`::warning::`), que sale en el resumen del run y en la pestaña de checks de la PR.
    console.log(process.env.CI ? `::warning file=${testInfo.file}::${reason}` : `SKIP: ${reason}`);
    testInfo.skip(true, reason);
  }
}
