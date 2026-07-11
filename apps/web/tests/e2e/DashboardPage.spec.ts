// Widget CORE de export/import en la home (ADR-0113 §4, architecture/hub/export-import.md).
//
// La home anuncia que el export/import existe (restaurar un backup, importar una plantilla,
// exportar el hub). DECISIÓN del humano (2026-07-12): es un widget DEL BOARD, igual que los de
// módulo — entra en el catálogo de <ok-widget-board> y en todos los presets (activo por defecto
// sin estado guardado), y el picker permite ocultarlo como a cualquier otro. Sus CTAs llevan a
// la pestaña «Datos» de Ajustes (/settings?tab=data), donde viven importar y exportar juntos.
//
// Llegar a /dashboard exige que el hub NO esté vacío (el guard de first-run desvía) → mismo
// patrón HUB_TEST_MODULE_DIR que FirstRunPage.spec.ts para instalar un módulo real primero.

import { test, expect, request as pwRequest, type Page } from '@playwright/test';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
/** Módulo real a instalar para que el guard de first-run deje entrar al dashboard. */
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

test.describe('widget core de export/import en la home', () => {
  test('el widget vive DENTRO del board y lleva a Ajustes → Datos', async ({ page }) => {
    test.skip(!REAL_MODULE_DIR, 'define HUB_TEST_MODULE_DIR con la carpeta de un módulo real');
    const session = await loginByPin();

    // Instalación REAL desde carpeta para que el guard de first-run deje entrar al dashboard.
    const api = await pwRequest.newContext();
    const res = await api.post(`${RUNTIME}/api/modules/install`, { data: { dir: REAL_MODULE_DIR } });
    expect(res.ok(), `instalación falló: ${res.status()} ${await res.text()}`).toBeTruthy();
    await api.dispose();

    await withSession(page, session);
    // localStorage FRESCO (sin `okwb:dashboard-hub`): el board activa el primer preset, y el
    // widget core debe formar parte de TODOS los presets para ser visible por defecto.
    await page.goto('/dashboard');

    // El widget está DENTRO de <ok-widget-board> (no una tarjeta fija encima).
    const board = page.locator('ok-widget-board');
    await expect(board.getByTestId('dashboard-blueprint-widget')).toBeVisible();
    await expect(board.getByTestId('dashboard-blueprint-import')).toBeVisible();
    await expect(board.getByTestId('dashboard-blueprint-export')).toBeVisible();

    // CTA «importar» → pestaña Datos de Ajustes, con la sección de import visible.
    await board.getByTestId('dashboard-blueprint-import').click();
    await expect(page).toHaveURL(/\/settings\?tab=data$/);
    await expect(page.getByTestId('import-lead')).toBeVisible();

    // CTA «exportar» → misma pestaña (import y export viven juntos), sección de export visible.
    await page.goBack();
    await board.getByTestId('dashboard-blueprint-export').click();
    await expect(page).toHaveURL(/\/settings\?tab=data$/);
    await expect(page.getByTestId('export-lead')).toBeVisible();
  });
});
