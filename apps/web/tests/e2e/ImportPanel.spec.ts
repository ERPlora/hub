// Contrato UI del panel «Importar configuración» — pestaña Datos de Ajustes
// (ADR-0113 §4, architecture/hub/export-import.md; decisión del humano 2026-07-12:
// import/export viven JUNTOS en /settings?tab=data, ya no hay página /import).
//
// Tres pasos: (1) elegir fuente — zip local; «desde la nube» aún no existe (el registro de
// blueprints del SaaS es una tanda posterior) → botón deshabilitado con nota "próximamente" —,
// (2) resumen del manifest tras `POST /api/hub/import/inspect` con checkboxes de las secciones
// DETECTADAS, (3) `POST /api/hub/import` → informe final por sección (Applied/Skipped/Failed).
//
// Endpoints ya vivos en `crates/server/src/export_import.rs` (contrato congelado). Sin mocks:
// runtime Axum real con BD efímera y `HUB_MODULES_DIR` vacío (`e2e/README.md`); el zip del flujo
// completo se genera con el PROPIO `POST /api/hub/export` del runtime (round-trip real, cero
// fixtures). Un hub vacío es EXACTAMENTE el caso de uso del import y navega a /settings sin desvíos.

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

test.describe('importar configuración (Ajustes → Datos)', () => {
  test('muestra el uploader local y la fuente nube deshabilitada ("próximamente")', async ({ page }) => {
    await withSession(page, await loginByPin());

    await page.goto('/settings?tab=data');

    // El hub vacío es quien más necesita importar: navega a /settings sin desvíos.
    await expect(page).toHaveURL(/\/settings\?tab=data$/);
    await expect(page.getByTestId('import-lead')).toBeVisible();

    // Paso 1: subir un zip local…
    await expect(page.getByTestId('import-pick-file')).toBeVisible();
    // …y «desde la nube» deshabilitado con nota (el registro SaaS de blueprints no existe aún).
    await expect(page.getByTestId('import-cloud')).toHaveJSProperty('disabled', true);
    await expect(page.getByTestId('import-cloud-note')).toBeVisible();
  });

  test('inspeccionar un zip muestra el manifest y al importar sale el informe', async ({ page }) => {
    const session = await loginByPin();

    // Round-trip REAL: el zip se genera con el propio export del runtime (cero fixtures).
    const api = await pwRequest.newContext();
    const res = await api.post(`${RUNTIME}/api/hub/export`, {
      headers: { 'X-Hub-Session': session.token },
      data: {
        name: 'roundtrip',
        locale: 'es',
        selection: {
          users: true,
          settings: true,
          settings_items: null,
          fiscal: false,
          media: true,
          modules: [],
        },
      },
    });
    expect(res.ok(), `export falló: ${res.status()} ${await res.text()}`).toBeTruthy();
    const zip = await res.body();
    await api.dispose();

    await withSession(page, session);
    await page.goto('/settings?tab=data');

    // Paso 2: subir el zip → inspect → resumen del manifest + secciones DETECTADAS. Fiscal no
    // viajó (OFF en el export) → su checkbox NO aparece.
    await page.getByTestId('import-file-input').setInputFiles({
      name: 'roundtrip_es.blueprint.zip',
      mimeType: 'application/zip',
      buffer: zip,
    });
    await expect(page.getByTestId('import-manifest')).toBeVisible();
    await expect(page.getByTestId('import-section-users')).toBeVisible();
    await expect(page.getByTestId('import-section-settings')).toBeVisible();
    await expect(page.getByTestId('import-section-fiscal')).toHaveCount(0);

    // Paso 3: importar → INFORME final por sección (contrato JSON del motor pintado tal cual).
    await page.getByTestId('import-submit').click();
    await expect(page.getByTestId('import-report')).toBeVisible({ timeout: 30_000 });
    // Con la BD efímera el SQL aplica (Applied). La media viaja VACÍA (0 ficheros) → «Saltado»:
    // la UI deriva el estado real de `report.media` (copied/failed), no del `Skipped` que el motor
    // pone siempre. El caso «media copiada → Aplicado» (report.media.copied>0) se cubre en la e2e
    // en vivo con un hub que sí tiene imágenes (informe de review 2026-07-12, hallazgo #1).
    await expect(page.getByTestId('import-report')).toContainText('Aplicado');
  });
});
