import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

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
const RUNTIME_BIND = process.env.HUB_BIND ?? '127.0.0.1:8787';
const RUNTIME_URL = process.env.HUB_RUNTIME_URL ?? `http://${RUNTIME_BIND}`;
const WEB_URL = process.env.HUB_WEB_URL ?? 'http://localhost:5173';

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
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  // Las dos mitades del banco. `reuseExistingServer` fuera de CI respeta el `pnpm dev` que el
  // desarrollador ya tenga levantado; en CI se exige arrancarlas aquí, para que un proceso zombi
  // de otro job no pueda contestar por ellas (el «runtime zombi miente» de los e2e del hub).
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
      reuseExistingServer: !process.env.CI,
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
      // que sincronizar y solo añadiría 24 avisos. `--strictPort` para que un 5173 ocupado falle
      // en voz alta en vez de servir el shell de otra rama en el puerto siguiente.
      command: 'pnpm exec vite --port 5173 --strictPort',
      cwd: WEB_DIR,
      url: WEB_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        // El shell alcanza el runtime por el proxy de Vite (`/api` + `/ws`), que se apunta con el
        // mismo `HUB_BIND` que el runtime de arriba — así los dos hablan del mismo puerto.
        HUB_BIND: RUNTIME_BIND,
      },
    },
  ],
});
