// El alta, la edición y la baja de una persona se conducen SOLO por `data-testid` (hub#1756).
//
// Este spec no prueba el negocio de la ficha —eso ya lo prueban los tests de `EmployeeFormPage`—:
// prueba que el QA PUEDE conducirla. Es la mitad que faltaba de la issue. `apps/web/src/
// form-testids.test.ts` comprueba que los ganchos están escritos en el fichero; lo que nadie
// comprobaba es que, puestos en la pantalla REAL, sirvan para rellenarla: un `data-testid` sobre un
// `ion-input` no es un `<input>` —el nativo vive en el Shadow DOM del Web Component— y un
// `ion-toggle` no se rellena, se pulsa.
//
// Por eso el recorrido es el ciclo CRUD entero (alta → edición → baja) y NO hay ni un selector por
// texto: si el shell cambia de copy o se traduce, este spec sigue en pie. Ese es exactamente el
// contrato que el checklist de restaurante necesita para desbloquear la plantilla y, con ella, la
// matriz de roles.
//
// Sin mocks: runtime Axum real con BD efímera (ver `e2e/README.md`). La lista `/employees` se lee
// por API a propósito — su tabla es un `<ok-data-table>` cuyo cromo (botón «Añadir», buscador,
// acciones de fila) todavía no lleva ganchos, que es el hueco que queda abierto en OutfitKit.
// 🔴 EL NOMBRE DEL FICHERO ES LOAD-BEARING: tiene que ordenar DESPUÉS de los `*Visual.spec.ts`.
//
// Playwright corre los ficheros en orden alfabético con `workers: 1` (`playwright.config.ts`), y
// este spec da de alta una persona que NO se puede borrar: la baja del core es desactivar, nunca
// borrar (`DELETE /api/hub/users/{id}`, hub#348), y `GET /api/hub/users` devuelve activos E
// inactivos. `EmployeesPage.vue` pinta esa lista entera (`:rows="users"`), así que la fila queda a
// la vista de quien fotografíe `/employees`.
//
// Con el nombre anterior (`EmployeeFormTestids.spec.ts`) este spec corría JUSTO ANTES de
// `EmployeesVisual.spec.ts`, cuyo `toHaveScreenshot` afirma —y su comentario lo dice— que la
// pestaña «Personal» es determinista «solo el usuario Demo del seed». Le habríamos metido una fila
// de más cuyo nombre lleva un `Date.now()`: distinta en cada corrida, o sea una baseline envenenada
// al generarla y un rojo intermitente después. `UsersCrudTestids` ordena tras `ShellVisual`, que es
// el último visual, así que ningún contrato visual ve lo que este spec crea.
//
// El `Date.now()` del nombre se queda a propósito: si algún día alguien añade un visual que ordene
// después de éste, la captura saldrá ROJA en voz alta en vez de hornear la fila de un test dentro
// de un contrato visual sin que nadie se entere.
import { test, expect, request as pwRequest } from '@playwright/test';
import { loggedInSession, loginByPin } from './shell-visual-helpers';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface HubUser {
  id: string;
  name: string;
  is_active?: boolean;
}

/**
 * La lista de personas tal como la ve el runtime, con la sesión de la cajera del seed.
 *
 * El core contesta con el SOBRE del hub —`{ ok, data }`, ver `crates/server/tests/hub_users_api.rs`—,
 * no con el array pelado: desenvolverlo aquí es lo que hace que un cambio de sobre falle con un
 * mensaje que se lee, en vez de con un `find is not a function` a mitad del recorrido.
 */
async function hubUsers(token: string): Promise<HubUser[]> {
  const api = await pwRequest.newContext();
  const res = await api.get(`${RUNTIME}/api/hub/users`, { headers: { 'X-Hub-Session': token } });
  expect(res.ok(), `GET /api/hub/users: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = (await res.json()) as { ok?: boolean; data?: HubUser[] };
  await api.dispose();
  expect(body.ok, `GET /api/hub/users no vino en el sobre del hub: ${JSON.stringify(body)}`).toBe(
    true,
  );
  expect(
    Array.isArray(body.data),
    `GET /api/hub/users: \`data\` no es la lista: ${JSON.stringify(body)}`,
  ).toBeTruthy();
  return body.data as HubUser[];
}

/**
 * Un PIN que este hub acepta, del largo que ESTE hub pide.
 *
 * La longitud es política del hub (4 o 6, `lib/pin-length.ts`), así que el spec la lee del propio
 * control en vez de fijarla: clavar un 4 aquí dejaría el spec rojo el día que el banco arranque
 * con la política de 6. Los dígitos no forman progresión — `isGuessablePin` rechaza 1111 y 1234.
 */
const PIN_DIGITS = '481725';

/** Prefijo del nombre de la persona que este spec da de alta. También es su etiqueta de limpieza. */
const QA_PREFIX = 'QA Testid ';

/**
 * Deja el banco sin personas ACTIVAS de corridas anteriores, y por una razón concreta: la BD del
 * banco (`hub_e2e_web`) **no es efímera entre corridas**, y un PIN solo puede abrir la sesión de
 * un usuario activo (`hub.users.pin_in_use`, `identity::pin_is_taken`). Una corrida que muera a
 * mitad —antes de la baja, que es el último paso— deja su persona activa con este PIN puesto, y
 * la siguiente ya no falla por lo que se está probando: falla porque el PIN está cogido. Eso es
 * un rojo que miente, que es peor que no tener el test.
 *
 * Dar de baja NO borra la fila (hub#348): sigue en la lista, inactiva, y su PIN queda libre.
 */
async function deactivateLeftovers(token: string): Promise<void> {
  const stale = (await hubUsers(token)).filter(
    (u) => u.name.startsWith(QA_PREFIX) && u.is_active !== false,
  );
  if (stale.length === 0) return;
  const api = await pwRequest.newContext();
  for (const user of stale) {
    const res = await api.delete(`${RUNTIME}/api/hub/users/${user.id}`, {
      headers: { 'X-Hub-Session': token },
    });
    expect(
      res.ok(),
      `no se pudo dar de baja el resto de una corrida anterior (${user.name}): ${res.status()} ${await res.text()}`,
    ).toBeTruthy();
  }
  await api.dispose();
}

test.describe('la ficha de una persona se conduce por data-testid (hub#1756)', () => {
  test('alta, edición y baja sin un solo selector por texto', async ({ page }) => {
    const session = await loginByPin();
    await deactivateLeftovers(session.token);
    const before = await hubUsers(session.token);
    const name = `${QA_PREFIX}${Date.now()}`;

    // ── Alta ──────────────────────────────────────────────────────────────────────────────────
    await loggedInSession(page);
    await page.goto('/employees/new');
    await expect(page.getByTestId('employee-form')).toBeVisible();

    await page.getByTestId('employee-name').locator('input').fill(name);

    // Persona LOCAL: nombre y PIN, sin cuenta en el SaaS — el alta que un salón hace en el
    // mostrador. Marcarlo esconde el email (`v-if="!isLocal"`), así que el gancho del email deja
    // de existir en el DOM: es la comprobación de que el toggle hizo algo.
    await page.getByTestId('employee-local').click();
    await expect(page.getByTestId('employee-email')).toHaveCount(0);

    const pin = page.getByTestId('employee-pin').locator('input');
    const pinLength = await pin.evaluate((el) => (el as HTMLInputElement).maxLength);
    expect(pinLength, 'el PIN del hub es de 4 o 6 dígitos').toBeGreaterThan(0);
    await pin.fill(PIN_DIGITS.slice(0, pinLength));

    await page.getByTestId('employee-submit').click();

    // El formulario vuelve a la lista cuando el runtime acepta (`router.replace('/employees')`).
    await expect(page).toHaveURL(/\/employees$/);
    const afterCreate = await hubUsers(session.token);
    const created = afterCreate.find((u) => u.name === name);
    expect(created, `el alta no llegó al runtime: ${afterCreate.map((u) => u.name).join(', ')}`)
      .toBeDefined();
    expect(afterCreate.length).toBe(before.length + 1);

    // ── Edición ───────────────────────────────────────────────────────────────────────────────
    await page.goto(`/employees/${created!.id}`);
    await expect(page.getByTestId('employee-form')).toBeVisible();
    await expect(page.getByTestId('employee-name').locator('input')).toHaveValue(name);

    const renamed = `${name} bis`;
    await page.getByTestId('employee-name').locator('input').fill(renamed);
    await page.getByTestId('employee-submit').click();
    await expect(page).toHaveURL(/\/employees$/);
    expect((await hubUsers(session.token)).find((u) => u.id === created!.id)?.name).toBe(renamed);

    // ── Baja ──────────────────────────────────────────────────────────────────────────────────
    // Dar de baja es apagar «usuario activo»: la fila se queda (una persona = una fila, hub#348).
    await page.goto(`/employees/${created!.id}`);
    await expect(page.getByTestId('employee-active')).toHaveJSProperty('checked', true);
    await page.getByTestId('employee-active').click();
    await expect(page.getByTestId('employee-active')).toHaveJSProperty('checked', false);
    await page.getByTestId('employee-submit').click();
    await expect(page).toHaveURL(/\/employees$/);

    const afterDeactivate = (await hubUsers(session.token)).find((u) => u.id === created!.id);
    expect(afterDeactivate, 'la baja NO borra la fila').toBeDefined();
    expect(afterDeactivate!.is_active, 'la persona quedó dada de baja').toBeFalsy();
  });
});
