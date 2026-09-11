import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveUpdateSnapshotsMode } from '../src/lib/visual-baseline-gate';
import { resolveBenchPorts, shouldReuseExistingServer } from './bench-ports';
import { BENCH_APP_VERSION } from './bench-app-version';

// E2E del shell del Hub contra el runtime REAL (Axum :8787) y Vite (:5173). Sin mocks (regla del
// proyecto): el test arranca su propio runtime con BD efímera y un directorio de módulos VACÍO,
// que es exactamente el estado "hub recién creado" que queremos ejercer. Ver `e2e/README.md`.
//
// hub#1240 — hasta aquí ese párrafo describía una intención, no el fichero: el config NO arrancaba
// nada. Levantar las dos mitades era trabajo manual (`pnpm dev` en otra terminal), así que la suite
// solo corría cuando alguien se acordaba — y no se acordó nadie ni una vez en CI. Los dos
// `webServer` de abajo son la pieza que faltaba, y son además el mecanismo aburrido y estándar de
// Playwright para esto, no un orquestador nuestro.

const HUB_ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..', '..');
const WEB_DIR = join(HUB_ROOT, 'apps', 'web');
// hub#1517 — los puertos del banco NO son fijos en CI. `ci-runner-1` sirve SEIS ranuras en la
// misma máquina, así que dos jobs `e2e` se solapan a diario; con `reuseExistingServer: false` (que
// en CI es deliberado) el segundo no reutilizaba el puerto ocupado: MORÍA en él —
// «Error: http://127.0.0.1:8787/readyz is already used» — y el rojo caía en la PR que llegase
// segunda, sin relación con su diff. Ver `bench-ports.ts`.
//
// hub#1812 — fuera de CI pasa lo MISMO, y salía peor: ahí los puertos sí eran fijos (8787/5173) y
// `reuseExistingServer` valía `!CI`, o sea SIEMPRE. La segunda corrida de la máquina no moría en
// el puerto ocupado: adoptaba los servidores de la primera y probaba la rama del VECINO, sin
// decirlo. El síntoma es un rojo que miente («no encuentro el gancho que acabo de añadir»), así
// que el rato se va en el diff y no en el banco — medido el 11/09 en #1756. Ahora reutilizar se
// PIDE (`HUB_E2E_REUSE_SERVER=1`) y, si no se pide, cada corrida reparte su propio banco.
const PORTS = resolveBenchPorts(process.env, process.pid);
const REUSE_EXISTING_SERVER = shouldReuseExistingServer(process.env);
const RUNTIME_BIND = process.env.HUB_BIND ?? `127.0.0.1:${PORTS.runtime}`;
const RUNTIME_URL = process.env.HUB_RUNTIME_URL ?? `http://${RUNTIME_BIND}`;
const WEB_URL = process.env.HUB_WEB_URL ?? `http://localhost:${PORTS.web}`;

// Los specs siguen al banco por el ENTORNO, no por una fixture: ya leen
// `process.env.HUB_RUNTIME_URL` (`ImportPanel`, `DashboardPage`, `ExportPanel`,
// `NoStrayGetApiQuery`, `shell-visual-helpers`) y los workers de Playwright heredan el `process.env`
// del proceso que carga este config. Exportarlo aquí es lo que evita tocar un solo spec.
//
// 🔴 Se exportan los CUATRO, y `HUB_BIND` no sobra: Playwright EVALÚA ESTE FICHERO DOS VECES —una
// en el proceso runner y otra en cada worker, que hereda el env del runner (medido: el worker lee
// el valor que escribió el runner antes de escribir el suyo)—. Con `HUB_BIND` fuera, la segunda
// evaluación se encontraba el runtime sin fijar y volvía a sortear un puerto: un subproceso de
// sonda por worker para un puerto que nadie usa. Con los cuatro puestos, releer el config es un
// no-op — y esa idempotencia es lo que afirma `playwright.config.test.ts`.
process.env.HUB_BIND = RUNTIME_BIND;
process.env.HUB_RUNTIME_URL = RUNTIME_URL;
process.env.HUB_WEB_URL = WEB_URL;
process.env.HUB_E2E_ASSISTANT_PORT = String(PORTS.assistant);

// Postgres del banco de e2e. La BD tiene que EXISTIR (el runtime no la crea): en local es el
// contenedor `erplora-test-pg-5433` del repo (`createdb -h localhost -p 5433 hub_e2e_web`), en CI
// la crea `test-web.yml` sobre su servicio pgvector. Se falla en el arranque del runtime, con su
// mensaje, si no está — no en el primer spec, donde parecería un fallo de UI.
const DATABASE_URL =
  process.env.HUB_E2E_DATABASE_URL ?? 'postgres://postgres:test@localhost:5433/hub_e2e_web';

// `hub_id` del banco: cualquiera MENOS el de dev (`00000000-…-0001`). Es lo que separa «un hub
// recién creado» de «el hub de desarrollo», y el core cambia de comportamiento entre los dos
// (hub#1249): un hub de dev no exporta más que plantillas, así que sus copias no llevan usuarios.
const E2E_HUB_ID = process.env.HUB_ID ?? 'e2e00000-0000-4000-8000-000000000001';

// Directorio de módulos VACÍO a propósito: los specs afirman sobre el hub recién creado, y con el
// workspace de módulos del monorepo delante afirmarían sobre otra cosa distinta en cada máquina.
const EMPTY_MODULES_DIR = mkdtempSync(join(tmpdir(), 'e2e-empty-modules-'));

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  // En CI un `.only` olvidado convierte la suite entera en un verde vacío.
  forbidOnly: !!process.env.CI,
  // hub#1250 — el DEFAULT de Playwright ('missing') crea sola una baseline ausente y pasa en
  // VERDE en cualquier entorno, CI incluido; eso es justo lo que dejaba una PR que borra un PNG
  // pasar sin avisar. `resolveUpdateSnapshotsMode` (con sus tests en
  // `src/lib/visual-baseline-gate.test.ts`) fuerza `'none'` en CI salvo en la corrida dedicada de
  // `visual-baselines.yml`, que sí quiere `'all'`.
  updateSnapshots: resolveUpdateSnapshotsMode(process.env),
  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
  },
  expect: {
    // Las capturas de `toHaveScreenshot` son un contrato de GEOMETRÍA, no de píxel exacto: el
    // antialiasing de una fuente varía entre versiones del navegador sin que la pantalla cambie.
    // Un 0,2 % de píxeles (≈2.600 en 1440×900) absorbe eso y sigue cazando un bloque desplazado.
    toHaveScreenshot: { maxDiffPixelRatio: 0.002, animations: 'disabled', caret: 'hide' },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // hub#1752 — la zona horaria se FIJA, no se hereda de la máquina. El contrato visual
        // fotografía pantallas que pintan la hora (ajustes: «Automática · Europe/Madrid, 08:51»),
        // así que con la zona del runner de por medio reprovisionar ese runner pondría en rojo
        // todas las baselines a la vez, sin que nadie hubiera tocado la UI. El instante lo congela
        // `freezeVisualClock` (`shell-visual-helpers.ts`); esto fija el huso en el que se pinta.
        timezoneId: 'Europe/Madrid',
      },
    },
  ],

  // Las dos mitades del banco. `reuseExistingServer` solo respeta el `pnpm dev` del desarrollador
  // cuando ESTE lo pide (`HUB_E2E_REUSE_SERVER=1`, hub#1812); por defecto —y siempre en CI— se
  // exige arrancarlas aquí, para que ni un proceso zombi de otro job ni el banco de otro worktree
  // puedan contestar por ellas (el «runtime zombi miente» de los e2e del hub).
  webServer: [
    {
      // `cargo run` y no la ruta del binario: compila si hace falta (no-op cuando ya está) y así
      // `pnpm -F @erplora/web test:e2e` funciona en un checkout limpio sin pasos previos. En CI el
      // binario lo construye un paso anterior, así que esto arranca en segundos.
      command: 'cargo run -q -p erplora-server',
      cwd: HUB_ROOT,
      // `/readyz` (ADR-0291) y no `/healthz`: contesta 200 solo cuando la BD responde y las
      // migraciones de sistema están aplicadas, que es lo que los specs necesitan; `/healthz`
      // responde en cuanto el router se ata. El seed ya corrió cuando el puerto contesta algo (se
      // aplica en el arranque, ANTES de atar el listener). Era `/api/system`, que es `auth:session`
      // y en este banco ya no hay puerta de dev que lo abra sin sesión (hub#1249).
      url: `${RUNTIME_URL}/readyz`,
      reuseExistingServer: REUSE_EXISTING_SERVER,
      // En CI el binario ya está: 3 min es holgura de arranque (migraciones + seed), no de build.
      // En local el primer arranque SÍ compila el runtime entero, y 15 min es el techo realista.
      timeout: process.env.CI ? 180_000 : 900_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        HUB_DATABASE_URL: DATABASE_URL,
        HUB_BIND: RUNTIME_BIND,
        // ── El banco es un hub REAL, no el hub de dev ni una demo (hub#1249) ──────────────────
        //
        // Hasta aquí este banco arrancaba con `HUB_AUTH=dev` + el `hub_id` de dev + `HUB_DEMO=1`,
        // y esa combinación no es «un hub recién creado»: es un hub que el core trata como NO
        // REAL, y eso le cambia el negocio a los specs por debajo. Dos consecuencias, las dos
        // mudas:
        //   · `POST /api/hub/export` fuerza `purpose: template` en un hub de dev o de demo
        //     (hub#377, ADR-0195), así que las secciones de identidad NUNCA entraban en el zip y
        //     el round-trip export→import perdía los usuarios — hub#1249;
        //   · en `AuthMode::Dev` el contexto sale de las cabeceras (`x-hub-id`, por defecto
        //     `local`) mientras el seed escribe el usuario Demo bajo el `hub_id` del despliegue,
        //     así que el volcado miraba a OTRO hub y salía vacío aunque la sección viajase.
        //
        // `HUB_AUTH=session` es además la puerta de producción, y la que los specs ya usaban:
        // entran por `/api/auth/pin` e inyectan `X-Hub-Session`, exactamente como el navegador de
        // una cajera. Un `hub_id` propio + el token de máquina hacen `machine_registered()`, que es
        // la otra forma —la real— de pasar la barrera de `require_machine_registration`.
        HUB_AUTH: 'session',
        HUB_ID: E2E_HUB_ID,
        HUB_DEV_MODE: '1',
        // El PIN de una cajera se presenta desde un navegador cuyo `device_id` acuña el propio
        // navegador (`apps/web/src/lib/device.ts`), así que en un banco efímero no hay dispositivo
        // de confianza que valga: la puerta se desarma A PROPÓSITO y en voz alta. Antes esto se
        // compraba con `HUB_DEMO=1` (trust-on-first-use de la demo), que de paso convertía el hub
        // en una demo a todos los efectos — el precio que pagaba hub#1249.
        HUB_DEVICE_TRUST: 'off',
        // Token de máquina (X-Hub-Token): en prod lo inyecta el provisioning; sin él la sesión por
        // PIN no tiene credencial hub-scoped y el proxy del asistente contesta 401.
        HUB_CLOUD_API_TOKEN: 'e2e-machine-token',
        // 🔴 EL BANCO NO LLAMA A PRODUCCIÓN. Sin esto, `cloud_base_url` es `https://erplora.com` y
        // el hub del banco —que allí no existe— recibe **410 `hub_not_found`** del gate de
        // entitlement; el shell lo trata como «este hub fue borrado» (`setOnHubGone`, main.ts),
        // cierra sesión y manda a /login a mitad de spec. Un puerto cerrado convierte eso en un
        // fallo de red, que es lo que un banco sin Cloud tiene que parecer — el mismo truco que
        // usan los tests del server (`cloud_base_url: http://127.0.0.1:1`).
        HUB_CLOUD_API_URL: 'http://127.0.0.1:1',
        // Seed de dev: usuario Demo (PIN 0000). Sin él no hay a quién autenticar y el login por
        // PIN de todos los specs falla antes del primer caso.
        HUB_SEED_SQL_PATH: join(HUB_ROOT, 'crates', 'server', 'seeds', 'demo.sql'),
        HUB_MODULES_DIR: EMPTY_MODULES_DIR,
      },
    },
    {
      // `vite` directo (no `pnpm dev`): salta el `predev` de sync-modules, que aquí no tiene nada
      // que sincronizar y solo añadiría 24 avisos. `--strictPort` para que un puerto ocupado falle
      // en voz alta en vez de servir el shell de otra rama en el puerto siguiente — y el puerto lo
      // reparte `resolveBenchPorts`, así que en CI ya no es el mismo para dos jobs (hub#1517).
      command: `pnpm exec vite --port ${PORTS.web} --strictPort`,
      cwd: WEB_DIR,
      url: WEB_URL,
      reuseExistingServer: REUSE_EXISTING_SERVER,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        // El shell alcanza el runtime por el proxy de Vite (`/api` + `/ws`), que se apunta con el
        // mismo `HUB_BIND` que el runtime de arriba — así los dos hablan del mismo puerto.
        HUB_BIND: RUNTIME_BIND,
        // hub#1752 — el pie del sidebar sale en las CINCO pantallas del contrato visual, y pinta
        // `__APP_VERSION__`. Sin fijarlo, `vite.config.ts` lo resuelve del último tag de git, así
        // que las quince baselines dependerían del estado del checkout que las generó. Ver
        // `bench-app-version.ts`.
        APP_VERSION: BENCH_APP_VERSION,
      },
    },
  ],
});
