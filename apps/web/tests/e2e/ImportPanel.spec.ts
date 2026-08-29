// Contrato UI del panel «Importar configuración» — pestaña Datos de Ajustes
// (ADR-0113 §4, architecture/hub/export-import.md; decisión del humano 2026-07-12:
// import/export viven JUNTOS en /settings#data, ya no hay página /import).
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
  // The device identifies itself, exactly as the browser of a real till does (hub#330: a PIN login
  // that identifies no device is refused). The bank disarms the trust gate with
  // `HUB_DEVICE_TRUST=off` (see `playwright.config.ts`) because the id a browser mints is random
  // and there is nothing to pre-trust in an ephemeral bank — it used to buy that with `HUB_DEMO=1`,
  // which turned the whole hub into a demo and broke the export round trip (hub#1249).
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
  test('muestra las fuentes como cards: blueprints de la nube + subir desde archivo', async ({
    page,
  }) => {
    await withSession(page, await loginByPin());

    // Deep-link a la pestaña Datos por HASH. Era `?tab=data`; `SettingsPage.vue` resuelve la
    // pestaña desde `route.hash` y reescribe la URL a `#<tab>`, así que la query ya no
    // seleccionaba nada y estos specs llevaban rotos sin que nadie los corriera (hub#1240).
    await page.goto('/settings#data');

    // El hub vacío es quien más necesita importar: navega a /settings sin desvíos.
    await expect(page).toHaveURL(/\/settings#data$/);
    await expect(page.getByTestId('import-lead')).toBeVisible();

    // Rediseño 2026-07-17: la card «subir desde archivo» SIEMPRE está a la vista (ya no un botón).
    await expect(page.getByTestId('import-upload-local')).toBeVisible();

    // El catálogo de la nube (ADR-0121) se carga SOLO al entrar — sin botón que descubrir. En un
    // hub sin blueprints publicados sale la nota honesta de «vacío»; con blueprints, una card por
    // cada uno. En cualquier caso, el spinner de carga termina.
    await expect(page.getByTestId('import-cloud-loading')).toHaveCount(0);
  });

  // Regression test for ERPlora/hub#1249 — el round-trip export→import PERDÍA los usuarios.
  //
  // No era el motor: era el BANCO. Este runtime arrancaba como hub de dev + demo, y en un hub que
  // el core no considera un negocio real el export fuerza `purpose: template` (hub#377, ADR-0195),
  // que excluye las identidades del zip. El manifest llegaba con ajustes y media, sin usuarios, y
  // nadie se enteraba. El banco es ahora un hub real (`playwright.config.ts`), así que esta prueba
  // vuelve a decir lo que dice su nombre: la copia de un hub se puede volver a importar ENTERA.
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
    await page.goto('/settings#data');

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
