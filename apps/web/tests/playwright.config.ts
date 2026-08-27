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
      // `/api/system` y no `/healthz`: contesta 200 solo cuando el runtime ya migró y sembró,
      // que es lo que los specs necesitan. `/healthz` responde en cuanto el router se ata.
      url: `${RUNTIME_URL}/api/system`,
      reuseExistingServer: !process.env.CI,
      // En CI el binario ya está: 3 min es holgura de arranque (migraciones + seed), no de build.
      // En local el primer arranque SÍ compila el runtime entero, y 15 min es el techo realista.
      timeout: process.env.CI ? 180_000 : 900_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        HUB_DATABASE_URL: DATABASE_URL,
        HUB_BIND: RUNTIME_BIND,
        // Mismo trío que el runtime que `AssistantGrounded.spec.ts` ya arranca — se copia porque
        // funciona, no por parecido. `HUB_AUTH=dev` + el `hub_id` de dev hacen `is_dev_hub()`, que
        // es la ÚNICA excepción al registro de máquina (`crates/server/src/lib.rs`): sin ella el
        // runtime contesta 428 `machine_registration_required` a TODA la superficie de negocio y
        // el banco se cae entero antes del primer spec. Los specs siguen entrando por
        // `/api/auth/pin`, la misma puerta que una cajera.
        HUB_AUTH: 'dev',
        HUB_DEV_MODE: '1',
        // `HUB_DEMO` (ADR-0197) es lo que hace que el PIN se pueda usar en este banco. El seed
        // sembraba una fila `hub_trusted_device` llamada `demo-trusted-device` y hub#630 la BORRÓ:
        // el `device_id` se lo acuña el navegador, así que nadie iba a presentar jamás ese nombre.
        // Lo que la sustituyó es el trust-on-first-use de un hub de demo — el PRIMER dispositivo
        // que se presenta queda adoptado (`device_mode::demo_would_adopt`) — y sin esta variable
        // los specs que entran por `/api/auth/pin` reciben 403 `device_untrusted`. Llevaban rotos
        // desde hub#630 sin que nadie lo viera, que es exactamente lo que hub#1240 arregla.
        HUB_DEMO: '1',
        // Token de máquina (X-Hub-Token): en prod lo inyecta el provisioning; sin él la sesión por
        // PIN no tiene credencial hub-scoped y el proxy del asistente contesta 401.
        HUB_CLOUD_API_TOKEN: 'e2e-machine-token',
        // Seed de dev: usuario Demo (PIN 0000) + `demo-trusted-device`. Sin él el device-trust
        // (armado por defecto desde hub#330) rechaza el login por PIN de todos los specs.
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
