// Contrato UI del panel «Exportar configuración» — pestaña Datos de Ajustes
// (ADR-0113 §4, architecture/hub/export-import.md; decisión del humano 2026-07-12:
// import/export viven JUNTOS en /settings?tab=data, ya no hay página /export).
//
// El panel empaqueta la configuración del hub (y opcionalmente sus datos) en un
// `<nombre>_<idioma>.blueprint.zip` descargable (`POST /api/hub/export`, contrato congelado;
// endpoints ya vivos en `crates/server/src/export_import.rs`).
//
// Sin mocks: runtime Axum real con BD efímera y `HUB_MODULES_DIR` vacío (mismo arranque que
// FirstRunPage.spec.ts, ver `e2e/README.md`). Un hub vacío PUEDE exportar (usuarios/ajustes):
// /settings es un escape del guard de first-run.

import { test, expect, request as pwRequest, type Page } from '@playwright/test';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

/** Sesión REAL del runtime vía `/api/auth/pin` (usuario Demo / PIN 0000 del seed de dev). */
async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}/api/auth/pin`, { data: { name: 'Demo', pin: '0000' } });
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

    // Deep-link a la pestaña Datos: ?tab=data selecciona la pestaña al montar.
    await page.goto('/settings?tab=data');

    // El guard de first-run NO desvía: /settings es un escape (un hub vacío puede exportar).
    await expect(page).toHaveURL(/\/settings\?tab=data$/);
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

    await page.goto('/settings?tab=data');
    await page.getByTestId('export-name').locator('input').fill('barberia');

    // El zip llega como blob → link download: el filename sale del Content-Disposition del server
    // (o del default `<nombre>_<idioma>.blueprint.zip`). El locale del shell arranca en 'es'.
    const download = page.waitForEvent('download');
    await page.getByTestId('export-submit').click();
    expect((await download).suggestedFilename()).toBe('barberia_es.blueprint.zip');
  });
});
