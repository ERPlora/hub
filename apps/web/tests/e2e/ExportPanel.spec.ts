// Contrato UI del panel «Exportar configuración» — pestaña Datos de Ajustes
// (ADR-0113 §4, architecture/hub/export-import.md; decisión del humano 2026-07-12:
// import/export viven JUNTOS en /settings#data, ya no hay página /export).
//
// El panel empaqueta la configuración del hub (y opcionalmente sus datos) en un
// `<nombre>_<idioma>.blueprint.zip` descargable (`POST /api/hub/export`, contrato congelado;
// endpoints ya vivos en `crates/server/src/export_import.rs`).
//
// Sin mocks: runtime Axum real con BD efímera y `HUB_MODULES_DIR` vacío (ver `e2e/README.md`).
// Un hub vacío PUEDE exportar (usuarios/ajustes) y navega a /settings sin desvíos.

import { test, expect, request as pwRequest, type Page } from '../bench-boot';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

/** REAL runtime session via `/api/auth/pin` (Demo user / PIN 000000 from the dev seed, hub#1929). */
async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  // The device identifies itself, exactly as the browser of a real till does (hub#330: a PIN login
  // that identifies no device is refused). The bank disarms the trust gate with
  // `HUB_DEVICE_TRUST=off` (see `playwright.config.ts`) because the id a browser mints is random
  // and there is nothing to pre-trust in an ephemeral bank — it used to buy that with `HUB_DEMO=1`,
  // which turned the whole hub into a demo and broke the export round trip (hub#1249).
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '000000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `login PIN falló: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  expect(body.token, 'el runtime no devolvió token de sesión').toBeTruthy();
  await api.dispose();
  return { token: body.token, user: body.user };
}

/** Inyecta la sesión ya emitida por el runtime (mismas claves que `lib/session.ts`). */
async function withSession(page: Page, s: Session): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [s.token, s.user] as const,
  );
}

test.describe('exportar configuración (Ajustes → Datos)', () => {
  test('renderiza nombre, idioma, secciones y la tabla de módulos', async ({ page }) => {
    await withSession(page, await loginByPin());

    // Deep-link a exportar. DOS cosas cambiaron bajo este spec mientras nadie lo corría
    // (hub#1240): la pestaña se elige por HASH (`SettingsPage.vue` lee `route.hash`, el
    // `?tab=data` de antes no seleccionaba nada) y dentro de Datos hay un sub-segment
    // importar/exportar/restablecer cuyo valor inicial sale de `?data=` — sin él aterrizas en
    // «Importar» y el panel de exportar ni siquiera está montado.
    await page.goto('/settings?data=export#data');

    // Un hub vacío navega a /settings sin desvíos (puede exportar usuarios/ajustes).
    await expect(page).toHaveURL(/\/settings\?data=export#data$/);
    await expect(page.getByTestId('export-lead')).toBeVisible();

    // Nombre con default "hub" (el fichero final será `<nombre>_<idioma>.blueprint.zip`) + idioma.
    await expect(page.getByTestId('export-name').locator('input')).toHaveValue('hub');
    await expect(page.getByTestId('export-locale')).toBeVisible();

    // Secciones: usuarios/ajustes/media ON por defecto; fiscal OFF + advertencia (el .p12 viaja
    // tal cual y conserva su contraseña — decisión (d) del doc).
    await expect(page.getByTestId('export-section-users')).toHaveJSProperty('checked', true);
    await expect(page.getByTestId('export-section-settings')).toHaveJSProperty('checked', true);
    await expect(page.getByTestId('export-section-media')).toHaveJSProperty('checked', true);
    await expect(page.getByTestId('export-section-fiscal')).toHaveJSProperty('checked', false);
    await expect(page.getByTestId('export-fiscal-note')).toBeVisible();

    // Tabla de módulos instalados (ok-data-table: checkbox módulo + checkbox datos por fila),
    // botón «Seleccionar todo» y botón de exportar.
    await expect(page.getByTestId('export-select-all')).toBeVisible();
    await expect(page.getByTestId('export-modules-table')).toBeVisible();
    await expect(page.getByTestId('export-submit')).toBeVisible();
  });

  test('exportar descarga <nombre>_<idioma>.blueprint.zip', async ({ page }) => {
    await withSession(page, await loginByPin());

    await page.goto('/settings?data=export#data');
    await page.getByTestId('export-name').locator('input').fill('barberia');

    // El zip llega como blob → link download: el filename sale del Content-Disposition del server
    // (o del default `<nombre>_<idioma>.blueprint.zip`). El locale del shell arranca en 'es'.
    const download = page.waitForEvent('download');
    await page.getByTestId('export-submit').click();
    expect((await download).suggestedFilename()).toBe('barberia_es.blueprint.zip');
  });
});
