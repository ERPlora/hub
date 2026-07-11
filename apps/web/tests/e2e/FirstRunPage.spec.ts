// Contrato del "empujón" de primer arranque (cierra el hueco de ADR-0087).
//
// Un hub recién provisionado se despliega VACÍO: sin módulos, sin sector, sin país. Hoy aterriza en
// `/dashboard`, que está en blanco, y nada le dice al usuario cuál es su siguiente paso. El shell
// debe empujarle a ponerse en marcha.
//
// El módulo `setup` se RETIRÓ (ADR-0113): la puesta en marcha ahora es importar una plantilla
// (pestaña Datos de Ajustes, /settings?tab=data) o elegir módulos del marketplace. En cuanto hay
// un módulo instalado, el shell se aparta.
//
// Sin mocks: se ejerce contra el runtime Axum real, con una BD efímera y `HUB_MODULES_DIR` vacío.
// Arranque documentado en `e2e/README.md`.

import { test, expect, request as pwRequest, type Page } from '@playwright/test';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
/** Módulo real que se instala para comprobar que el empujón DESAPARECE. Origen: modules-workspace. */
const REAL_MODULE_DIR = process.env.HUB_TEST_MODULE_DIR ?? '';

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

test.describe('primer arranque de un hub vacío', () => {
  test('sin módulos instalados, el shell desvía a la pantalla de puesta en marcha', async ({ page }) => {
    await withSession(page, await loginByPin());

    await page.goto('/');

    await expect(page).toHaveURL(/\/first-run$/);
    await expect(page.getByTestId('first-run-title')).toBeVisible();
    await expect(page.getByTestId('first-run-install')).toBeVisible();
  });

  test('el CTA de puesta en marcha lleva a importar una plantilla (Ajustes → Datos)', async ({ page }) => {
    await withSession(page, await loginByPin());

    await page.goto('/first-run');
    await page.getByTestId('first-run-install').click();

    // El módulo `setup` ya no existe (ADR-0113): el botón navega a la pestaña Datos de Ajustes,
    // donde vive el import (decisión del humano 2026-07-12: ya no hay página /import).
    await expect(page).toHaveURL(/\/settings\?tab=data$/);
    await expect(page.getByTestId('import-lead')).toBeVisible();
  });

  test('la pantalla no es una trampa: se puede salir al marketplace', async ({ page }) => {
    await withSession(page, await loginByPin());

    await page.goto('/first-run');
    await page.getByTestId('first-run-marketplace').click();

    await expect(page).toHaveURL(/\/marketplace$/);
  });

  test('en cuanto hay un módulo instalado, el shell deja de empujar', async ({ page }) => {
    test.skip(!REAL_MODULE_DIR, 'define HUB_TEST_MODULE_DIR con la carpeta de un módulo real');
    const session = await loginByPin();

    // Instalación REAL desde carpeta (`POST /api/modules/install {dir}`), no un stub del endpoint.
    const api = await pwRequest.newContext();
    const res = await api.post(`${RUNTIME}/api/modules/install`, { data: { dir: REAL_MODULE_DIR } });
    expect(res.ok(), `instalación falló: ${res.status()} ${await res.text()}`).toBeTruthy();
    await api.dispose();

    await withSession(page, session);
    await page.goto('/');

    await expect(page).toHaveURL(/\/dashboard$/);
  });
});
