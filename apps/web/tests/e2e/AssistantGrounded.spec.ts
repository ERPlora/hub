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

import {
  bootReloadsOf,
  expect,
  request as pwRequest,
  resendsOf,
  sendThroughNetworkChanges,
  test,
  type Page,
  type Request,
} from '../bench-boot';
import es from '../../src/i18n/locales/es';
import { createServer, type Server } from 'node:http';
import { spawn, type ChildProcess } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';

const HUB_ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..', '..', '..');
// Puerto propio: este spec arranca SU runtime, y no puede pisar el 8787 de `pnpm dev`. En CI lo
// reparte `resolveBenchPorts` y lo exporta el config — sin eso, dos jobs `e2e` a la vez en
// `ci-runner-1` (seis ranuras) chocaban aquí con `AddrInUse` igual que en el banco (hub#1517).
const RUNTIME_PORT = Number(process.env.HUB_E2E_ASSISTANT_PORT) || 8791;
const RUNTIME = `http://127.0.0.1:${RUNTIME_PORT}`;
const PG = process.env.E2E_DATABASE_URL ?? 'postgres://postgres:test@localhost:5434/hub_e2e_assistant';

// The spec's runtime is the page's origin, so the bench's boot recovery (hub#1806/#2270) reads
// ITS requests as the app's own. With the bench's default `baseURL` (the Vite dev server) a
// network change during this spec's `goto` was nobody's to recover (hub#2442).
test.use({ baseURL: RUNTIME });

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

/** The assistant's turn: the one request a send in the drawer makes. */
const isTurn = (req: Request): boolean =>
  req.method() === 'POST' && new URL(req.url()).pathname === '/api/assistant/chat/stream';

/**
 * Real PIN session (demo seed) — the same door as a cashier — and the drawer open on its input.
 * Returns the input the turns are typed into.
 */
async function openAssistant(page: Page) {
  const api = await pwRequest.newContext();
  const login = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '000000', device_id: 'demo-trusted-device' },
  });
  expect(login.ok(), `login PIN falló: ${login.status()} ${await login.text()}`).toBeTruthy();
  const session = await login.json();
  await api.dispose();

  // Same keys as lib/session.ts (and DashboardPage.spec.ts): opaque token + user.
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user],
  );

  await page.goto('/');

  // The topbar's sparkles. Ionic MOVES aria-label to the inner button of its shadow DOM and drops
  // it from the host — the stable selector is the `title`, which stays (AppTopbar.vue).
  const sparkles = page.locator('ion-button[title*="sistant" i], ion-button[title*="sistente" i]').first();
  await sparkles.waitFor({ timeout: 15_000 });
  // dispatchEvent and not click(): some first-boot overlay (toast/scrim) takes the hit-test; the
  // Vue handler is the same, and what this spec validates is the CHAIN of the turn.
  await sparkles.dispatchEvent('click');
  const input = page.locator('ion-textarea textarea').last();
  await input.waitFor({ timeout: 10_000 });
  return input;
}

/**
 * Asks `question` in the drawer. A turn the runner's network change killed on the wire is asked
 * again — what the person would do — and nothing else is (hub#2442): a turn the runtime refused,
 * reset or never answered reaches the assertions as it came.
 */
async function ask(page: Page, input: ReturnType<Page['locator']>, question: string): Promise<void> {
  await sendThroughNetworkChanges(page, isTurn, async () => {
    // `fill` waits for the textarea to be editable again: the drawer disables it while a turn is
    // streaming, the one that just died included.
    await input.fill(question);
    await input.press('Enter');
  });
}

test.beforeAll(async () => {
  // El hook hereda el timeout de test (30 s) y más abajo espera al runtime hasta 60 s: esa
  // espera NO podía completarse nunca — el hook moría antes, y el síntoma era un `undefined`
  // en `expect(r?.ok())` que parece un runtime roto en vez de un reloj mal puesto. Con una BD
  // recién creada (migraciones + seed) el arranque pasa de 30 s con facilidad, así que en CI
  // esto era un rojo esperando su turno.
  test.setTimeout(120_000);
  const cloudPort = await startFixtureCloud();

  // REAL runtime (binary already built by the suite), empty hub, demo seed (PIN 000000, six
  // digits — hub#1929), serving the web dist on the SAME origin (ADR-0050, no Vite, no CORS).
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
  // El SIGTERM por defecto no bajaba este runtime: se quedaba vivo reteniendo el puerto, y la
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
  // Pregunta LO MISMO que el caso real, con el drawer abierto desde el ✨ del topbar.
  const input = await openAssistant(page);
  await ask(page, input, '¿qué necesito configurar para poder empezar a vender?');

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

  const input = await openAssistant(page);
  await ask(page, input, 'Crea una categoría de servicios llamada Barbería QA');

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

  const input = await openAssistant(page);
  await ask(page, input, '¿Qué módulos tengo instalados?');

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

// Regression tests for ERPlora/hub#2442 — the turn that died under a network change of the runner.
//
// Measured on run 36798035754 (attempt 1, PR hub#2441, which only touches the footer tabs) and on
// develop's run 37203596535: in both traces `POST /api/assistant/chat/stream` died with
// `net::ERR_NETWORK_CHANGED` inside a storm that killed every request in flight at once, and the
// drawer said «No se pudo contactar con el asistente». Neither the runtime nor the fixture-cloud was
// involved, and the rerun of the same commit was green. `route.abort('internetdisconnected')` is
// the injectable twin of that code (`route.abort()` has none for a network change; Chromium derives
// both from the machine's network moving, and the bench's `NETWORK_CHANGE_ERRORS` holds both).
test('a network change that kills the turn costs a resend, not a red build (hub#2442)', async ({ page }) => {
  test.setTimeout(90_000);
  cannedTokens = ['Según tu hub: ', 'no hay módulos instalados todavía.'];
  let turns = 0;
  // Killed ONCE: a network that stays down is an outage, and has to end red.
  await page.route('**/api/assistant/chat/stream', async (route) => {
    turns += 1;
    if (turns === 1) return route.abort('internetdisconnected');
    return route.continue();
  });

  const input = await openAssistant(page);
  await ask(page, input, '¿qué necesito configurar para poder empezar a vender?');

  // Before the fix this is where it went red, with the CI's very text: the error bubble instead of
  // the canned answer.
  await expect(page.locator('.assistant-drawer')).toContainText('no hay módulos instalados', {
    timeout: 15_000,
  });
  expect(turns, 'the bench did not ask the turn again').toBe(2);
  expect(resendsOf(page)).toEqual(['net::ERR_INTERNET_DISCONNECTED']);
});

test('a turn that dies of anything else is NOT asked again (hub#2442)', async ({ page }) => {
  // The other half, and the reason this is not a retry: a reset is something a crashing runtime
  // causes too, so re-asking would re-roll the very defect this spec exists to catch.
  test.setTimeout(90_000);
  cannedTokens = ['Según tu hub: ', 'no hay módulos instalados todavía.'];
  let turns = 0;
  await page.route('**/api/assistant/chat/stream', async (route) => {
    turns += 1;
    if (turns === 1) return route.abort('connectionreset');
    return route.continue();
  });

  const input = await openAssistant(page);
  await ask(page, input, '¿qué necesito configurar para poder empezar a vender?');

  const drawer = page.locator('.assistant-drawer');
  await expect(drawer).toContainText(es.assistant.error, { timeout: 15_000 });
  expect(turns, 'the bench asked again a turn the network did not kill').toBe(1);
  expect(resendsOf(page)).toEqual([]);
  await expect(drawer).not.toContainText('no hay módulos instalados');
});

test("a network change during this spec's own boot is recovered by the bench (hub#2442)", async ({
  page,
}) => {
  // The second hole of the same issue. This spec boots the shell from ITS runtime, not from the
  // bench's dev server, and the boot recovery only treats the `baseURL` origin as the app's own: a
  // storm during this `goto` left a blank shell and the spec failed waiting for the ✨ button.
  test.setTimeout(90_000);
  let entries = 0;
  await page.route('**/assets/index-*.js', async (route) => {
    entries += 1;
    if (entries === 1) return route.abort('internetdisconnected');
    return route.continue();
  });

  await openAssistant(page);

  expect(entries, 'the bench did not fetch the lost entry module again').toBeGreaterThan(1);
  expect(bootReloadsOf(page).length).toBeGreaterThan(0);
});
