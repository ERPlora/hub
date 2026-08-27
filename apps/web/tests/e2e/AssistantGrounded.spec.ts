// El asistente ANCLADO al hub (ADR-0282) — e2e de navegador contra el runtime REAL.
//
// El fallo de producción que esto clava: preguntar «¿qué necesito configurar para poder empezar
// a vender?» devolvía una página de consejo fiscal GENÉRICO (modelo 036, IAE, OSS…), porque el
// turno llegaba al Cloud sin `instructions` (system prompt VACÍO) y sin la tool
// `hub.setup.status`. Este spec recorre la cadena entera que nosotros embarcamos:
//
//   navegador → drawer → POST /api/assistant/chat/stream → runtime Axum REAL
//   (assemble_tools + build_instructions) → frontera del Cloud → SSE de vuelta → burbuja pintada.
//
// La ÚNICA pieza sustituida es el LLM del otro lado de la frontera del Cloud: un fixture HTTP
// local que CAPTURA el body que el runtime envía (para afirmar el contrato: identidad ERPlora,
// fecha del turno, tool `hub.setup.status`) y devuelve un SSE enlatado. No es un mock de datos
// de negocio (regla del proyecto): es el proveedor de pago externo, la misma frontera que los
// tests del runtime ya sustituyen con el trait `Embedder`. El LLM real se valida en QA contra
// prod (qa-hub), no en CI.
//
// El runtime se arranca AQUÍ (no el de `pnpm dev`): necesita HUB_CLOUD_API_URL apuntando al
// fixture. Hub VACÍO a propósito — es exactamente el estado del cliente nuevo del caso real.

import { test, expect, request as pwRequest } from '@playwright/test';
import { createServer, type Server } from 'node:http';
import { spawn, type ChildProcess } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';

const HUB_ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..', '..', '..');
const RUNTIME_PORT = 8791; // puerto propio: no pisa el 8787 de `pnpm dev`
const RUNTIME = `http://127.0.0.1:${RUNTIME_PORT}`;
const PG = process.env.E2E_DATABASE_URL ?? 'postgres://postgres:test@localhost:5434/hub_e2e_assistant';

/** Lo que el fixture-cloud capturó del runtime, para las aserciones del contrato. */
let capturedBody: Record<string, unknown> | null = null;
/** Lo que el fixture contesta. Se cambia por test: el turno anclado usa la respuesta de setup;
 *  el turno de hub#1038 usa una que AFIRMA una escritura sin pedir ninguna tool. */
let cannedTokens: string[] = ['Según tu hub: ', 'no hay módulos instalados todavía.'];
let cloud: Server;
let runtime: ChildProcess;

/** El «Cloud» del test: captura el body y contesta el SSE que emitiría el orquestador. */
function startFixtureCloud(): Promise<number> {
  cloud = createServer((req, res) => {
    if (req.method === 'POST' && req.url?.includes('/assistant/chat/stream')) {
      let raw = '';
      req.on('data', (c) => (raw += c));
      req.on('end', () => {
        capturedBody = JSON.parse(raw) as Record<string, unknown>;
        res.writeHead(200, { 'Content-Type': 'text/event-stream' });
        // Dos tokens + terminador — el shape real del proxy del SaaS (§9.3).
        for (const t of cannedTokens) res.write(`data: ${JSON.stringify({ text: t })}\n\n`);
        res.write('data: [DONE]\n\n');
        res.end();
      });
      return;
    }
    // Cualquier otra ruta (p. ej. la clave pública JWT del arranque): 404 y a seguir.
    res.writeHead(404).end();
  });
  return new Promise((ok) => cloud.listen(0, '127.0.0.1', () => ok((cloud.address() as AddressInfo).port)));
}

test.beforeAll(async () => {
  // El hook hereda el timeout de test (30 s) y más abajo espera al runtime hasta 60 s: esa
  // espera NO podía completarse nunca — el hook moría antes, y el síntoma era un `undefined`
  // en `expect(r?.ok())` que parece un runtime roto en vez de un reloj mal puesto. Con una BD
  // recién creada (migraciones + seed) el arranque pasa de 30 s con facilidad, así que en CI
  // esto era un rojo esperando su turno.
  test.setTimeout(120_000);
  const cloudPort = await startFixtureCloud();

  // Runtime REAL (binario ya compilado por la suite), hub vacío, seed demo (PIN 0000 + device
  // de confianza), sirviendo el dist del web en el MISMO origen (ADR-0050, sin Vite ni CORS).
  runtime = spawn(join(HUB_ROOT, 'target', 'debug', 'erplora-server'), [], {
    env: {
      ...process.env,
      HUB_DATABASE_URL: PG,
      HUB_BIND: `127.0.0.1:${RUNTIME_PORT}`,
      HUB_AUTH: 'dev',
      HUB_DEV_MODE: '1',
      // Trust-on-first-use de un hub de demo (ADR-0197): sin esto el login por PIN de abajo recibe
      // 403 `device_untrusted` desde hub#630, que borró la fila `demo-trusted-device` del seed.
      HUB_DEMO: '1',
      HUB_SEED_SQL_PATH: join(HUB_ROOT, 'crates', 'server', 'seeds', 'demo.sql'),
      HUB_WEB_DIR: join(HUB_ROOT, 'apps', 'web', 'dist'),
      HUB_CLOUD_API_URL: `http://127.0.0.1:${cloudPort}`,
      // Token de máquina (X-Hub-Token): en prod lo inyecta el provisioning; sin él la sesión
      // por PIN no tiene credencial hub-scoped y el proxy contesta 401 (auth.rs).
      HUB_CLOUD_API_TOKEN: 'e2e-machine-token',
      HUB_MODULES_DIR: mkdtempSync(join(tmpdir(), 'e2e-empty-modules-')), // vacío A PROPÓSITO
    },
    stdio: 'pipe',
  });
  runtime.stderr?.on('data', (d) => process.env.E2E_DEBUG && console.error(`[runtime] ${d}`));

  // Espera activa a que el runtime sirva (el arranque migra + siembra).
  const api = await pwRequest.newContext();
  await expect(async () => {
    const r = await api.get(`${RUNTIME}/api/system`, { timeout: 2000 }).catch(() => null);
    expect(r?.ok()).toBeTruthy();
  }).toPass({ timeout: 60_000 });
  await api.dispose();
});

test.afterAll(async () => {
  // SIGKILL y ESPERAR a que muera, no `kill()` a secas.
  //
  // El SIGTERM por defecto no bajaba este runtime: se quedaba vivo reteniendo el :8791, y la
  // siguiente ejecución fallaba con `AddrInUse` — pero no de forma visible. Su runtime moría, los
  // tests hablaban con el ANTERIOR, cuyo fixture-cloud ya estaba cerrado, y el síntoma era
  // «No se pudo contactar con el asistente»: un error de red que manda a investigar el asistente
  // cuando lo que sobra es un proceso. Se ejecutaba dos veces seguidas y fallaba la segunda.
  const dead = new Promise<void>((done) => {
    if (!runtime || runtime.exitCode !== null) return done();
    runtime.once('exit', () => done());
  });
  runtime?.kill('SIGKILL');
  await dead;
  cloud?.close();
});

test('la pregunta de configuración viaja ANCLADA: identidad, fecha y hub.setup.status', async ({ page }) => {
  test.setTimeout(90_000); // arranque real + SSE: el default de 30 s se queda corto
  // Sesión real por PIN (seed demo) — la misma puerta que una cajera.
  const api = await pwRequest.newContext();
  const login = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000', device_id: 'demo-trusted-device' },
  });
  expect(login.ok(), `login PIN falló: ${login.status()} ${await login.text()}`).toBeTruthy();
  const session = await login.json();
  await api.dispose();

  // Mismas claves que lib/session.ts (y que DashboardPage.spec.ts): token opaco + usuario.
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user],
  );

  await page.goto(RUNTIME);

  // Abre el drawer del asistente (✨ del topbar) y pregunta LO MISMO que el caso real.
  // El sparkles de la topbar. OJO: Ionic HEREDA aria-label al botón interno del shadow DOM y lo
  // retira del host — el selector estable es el `title`, que sí se queda (AppTopbar.vue).
  const sparkles = page.locator('ion-button[title*="sistant" i], ion-button[title*="sistente" i]').first();
  await sparkles.waitFor({ timeout: 15_000 });
  // dispatchEvent y no click(): algún overlay del primer arranque (toast/scrim) intercepta el
  // hit-test; el handler de Vue es el mismo, y lo que valida este spec es la CADENA del turno.
  await sparkles.dispatchEvent('click');
  const input = page.locator('ion-textarea textarea').last();
  await input.waitFor({ timeout: 10_000 });
  await input.fill('¿qué necesito configurar para poder empezar a vender?');
  await input.press('Enter');

  // 1) La respuesta enlatada del fixture llega PINTADA a la burbuja → la cadena SSE completa
  //    (runtime → translate_sse_line → drawer) funciona de navegador a navegador.
  await expect(page.locator('.assistant-drawer')).toContainText('no hay módulos instalados', {
    timeout: 15_000,
  });

  // 2) El CONTRATO del turno que cruzó la frontera del Cloud — lo que ADR-0282 garantiza.
  expect(capturedBody, 'el runtime nunca llamó al Cloud').toBeTruthy();
  const body = capturedBody!;
  const instructions = String(body.instructions ?? '');

  // Identidad: el modelo sabe DÓNDE está. Sin esto → «¿a qué sistema te refieres?».
  expect(instructions).toContain('ERPlora');
  // Fecha del turno: el reloj del modelo se congeló al entrenar; aquí viaja la de HOY.
  expect(instructions).toContain('Current date');
  // Hub vacío: se dice como hecho, no se calla.
  expect(instructions.toLowerCase()).toContain('no business modules');
  // Céntimos (ADR-0123): la regla con su ejemplo — 12,50 € = 1250.
  expect(instructions).toContain('1250');
  // La versión de ESTA instalación (hub#1044). Sin ella el modelo negaba que ERPlora tuviera
  // versión mientras el número estaba impreso en la barra lateral de la misma pantalla. Se
  // compara contra la que el propio runtime reporta en `/readyz`, no contra una cadena clavada
  // que habría que editar en cada release.
  const sys = await (await pwRequest.newContext()).get(`${RUNTIME}/readyz`);
  const runningVersion = String((await sys.json()).version);
  expect(instructions).toContain(runningVersion);

  // La tool que convierte «¿qué falta?» en una LECTURA del hub en vez de consejo genérico.
  const tools = body.tools as Array<{ name: string; kind: string }>;
  const setup = tools.find((t) => t.name === 'hub.setup.status');
  expect(setup, `hub.setup.status ausente; tools: ${tools.map((t) => t.name).join(', ')}`).toBeTruthy();
  expect(setup!.kind).toBe('query');

  // Y los `system` del cliente NUNCA viajan en messages (el Cloud los tira; van en instructions).
  const messages = body.messages as Array<{ role: string }>;
  expect(messages.every((m) => m.role !== 'system')).toBeTruthy();
});

/**
 * hub#1038 — el turno que AFIRMA una escritura que nunca ocurrió.
 *
 * Reproduce la sesión de QA del 19/08: el asistente contestó «✅ Categoría creada con éxito» con
 * un id inventado y CERO llamadas a tools; el panel de red no registró un solo POST /api/command.
 * Aquí el fixture devuelve ese mismo texto sin pedir ninguna tool, así que el turno llega al
 * navegador exactamente como llegó en producción — y lo que se comprueba es que el runtime lo
 * marca en vez de pintarlo como una respuesta más.
 *
 * El aviso lo escribe el RUNTIME (i18n del shell), no el modelo: por eso se busca su texto y no
 * una frase que el fixture pudiera haber emitido.
 */
test('un turno que dice haber creado algo SIN ejecutar nada sale marcado (hub#1038)', async ({ page }) => {
  test.setTimeout(90_000);
  cannedTokens = ['✅ Categoría creada con éxito.\n', '- ID asignado: `cat_9b4e7c1a`\n', '- Estado: `active`'];

  const api = await pwRequest.newContext();
  const login = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000', device_id: 'demo-trusted-device' },
  });
  expect(login.ok(), `login PIN falló: ${login.status()} ${await login.text()}`).toBeTruthy();
  const session = await login.json();
  await api.dispose();

  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user],
  );
  await page.goto(RUNTIME);

  const sparkles = page.locator('ion-button[title*="sistant" i], ion-button[title*="sistente" i]').first();
  await sparkles.waitFor({ timeout: 15_000 });
  await sparkles.dispatchEvent('click');
  const input = page.locator('ion-textarea textarea').last();
  await input.waitFor({ timeout: 10_000 });
  await input.fill('Crea una categoría de servicios llamada Barbería QA');
  await input.press('Enter');

  const drawer = page.locator('.assistant-drawer');
  // La respuesta se pinta (la cadena SSE sigue funcionando)…
  await expect(drawer).toContainText('Categoría creada', { timeout: 15_000 });
  // …y el runtime la marca: ni la afirmación ni el id se dejan pasar como buenos.
  await expect(drawer.locator('.chat-grounding')).toBeVisible({ timeout: 10_000 });
  await expect(drawer).toContainText('no se ejecutó ninguna acción');
  await expect(drawer).toContainText('identificador');
});

/**
 * hub#1043 — la tabla, que era lo ilegible.
 *
 * El drawer pintaba el markdown CRUDO: el usuario leía `**negrita**` y las tablas salían como una
 * sopa de barras verticales, partidas en tres líneas a 390 px. Aquí el fixture devuelve la misma
 * forma de respuesta que da el modelo de verdad —tabla de módulos con código en línea— y se
 * comprueba en el NAVEGADOR que llega pintada: una `<table>` real, sin barras a la vista y sin
 * asteriscos.
 */
test('una respuesta con tabla y negrita llega PINTADA, no en crudo (hub#1043)', async ({ page }) => {
  test.setTimeout(90_000);
  cannedTokens = [
    'Tienes estos **módulos** instalados:\n\n',
    '| Módulo | Para qué | Ruta |\n',
    '|---|---|---|\n',
    '| `staff` | Personal | /m/staff/staff |\n',
    '| `taxes` | Impuestos | /m/taxes/categories |\n',
  ];

  const api = await pwRequest.newContext();
  const login = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000', device_id: 'demo-trusted-device' },
  });
  expect(login.ok(), `login PIN falló: ${login.status()} ${await login.text()}`).toBeTruthy();
  const session = await login.json();
  await api.dispose();

  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user],
  );
  await page.goto(RUNTIME);

  const sparkles = page.locator('ion-button[title*="sistant" i], ion-button[title*="sistente" i]').first();
  await sparkles.waitFor({ timeout: 15_000 });
  await sparkles.dispatchEvent('click');
  const input = page.locator('ion-textarea textarea').last();
  await input.waitFor({ timeout: 10_000 });
  await input.fill('¿Qué módulos tengo instalados?');
  await input.press('Enter');

  const drawer = page.locator('.assistant-drawer');
  // Una tabla DE VERDAD, con sus filas.
  const table = drawer.locator('table.md-table');
  await expect(table).toBeVisible({ timeout: 15_000 });
  await expect(table.locator('tbody tr')).toHaveCount(2);
  await expect(table.locator('thead th').first()).toHaveText('Módulo');

  // Y nada de sintaxis a la vista: ni asteriscos de negrita ni barras de tabla.
  const painted = (await drawer.innerText()).replace('¿Qué módulos tengo instalados?', '');
  expect(painted).not.toContain('**');
  expect(painted).not.toContain('|---|');
  expect(painted).toContain('módulos');
});
