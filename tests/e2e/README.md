# e2e del Hub (Playwright)

Las specs (`*.spec.ts`) manejan Chrome contra una pila de desarrollo que ya está arrancada: `runserver` del Hub
(Django + su Vite), el SaaS (el login de todo hub pasa por él) y Postgres de `compose.yaml`. Oculto por
defecto; `E2E_HEADED=1` lo enseña. Los `*.test.ts` de esta carpeta son Vitest (`pnpm test`): prueban la
configuración del e2e, no el producto.

`pnpm typecheck` (y la CI) comprueba los tipos de todos los `.ts` de esta carpeta con su propio
`tsconfig.json`, que lleva los tipos de Node (`process`, `node:fs`) en lugar de los del cliente de Vite, sin
añadirlos al proyecto de la SPA (`tsconfig.app.json`). Un error de tipos en una spec o en un helper rompe la CI;
`typecheck.test.ts` vigila que ningún fichero de aquí se quede fuera.

```bash
CI=1 pnpm e2e                                  # toda la suite
CI=1 pnpm e2e tests/e2e/sale-sales.spec.ts     # una spec: SIN `--` (con él, Playwright ignora el filtro)
```

Antes de la primera spec, `global-setup.ts` comprueba que la BD de la ejecución (`DB_NAME`) no tiene
migraciones pendientes (`migrate --check`, `migrate_hubs --check`) y nunca migra nada.

## La pila compartida

Sin variables, el e2e va contra la pila compartida: Hub en `:8000` (Vite `:5173`), SaaS en `:8001` y la BD
`hub`. La usan otras sesiones: no se migra ni se borra desde aquí.

## Varias ejecuciones a la vez

Cada ejecución en paralelo es **una pila propia**, con sus puertos, su SaaS y **su BD**. En la fase 1 todo el
negocio de los hubs `a` y `b` vive en la BD de control (`DB_NAME`), así que una BD propia aísla todos los datos
de la ejecución: dos pilas sobre `hub` se pisan (el 16-10-2026, el cobro en efectivo de una cayó en el turno de
caja abierto de la otra y `cash-register-shift.spec.ts` falló).

| Variable | Qué aísla | Quién la lee |
|---|---|---|
| `E2E_HUB_PORT` | puerto del `runserver` del Hub | las specs (`stack.ts`) |
| `VITE_DEV_PORT` | puerto del Vite del Hub | `config/settings.py` (entorno o `.env`; `runserver` se la pasa a su Vite), `vite.config.ts` y specs (solo el entorno) |
| `SAAS_URL` | el SaaS propio, donde va el login | `config/settings.py`, specs |
| `DB_NAME` | la BD de la ejecución (control + negocio de `a`/`b`) | `config/settings.py`, specs (`psql()`) |
| `E2E_MAIL_DIR` | la carpeta de correo del SaaS propio (código de acceso) | specs (`mail.ts`) |

Para el `runserver` basta `VITE_DEV_PORT` en el `.env` del worktree; para la e2e hay que **exportarla** (Vite y
las specs no leen el `.env`). Exportada o en el `.env`, `uv run pytest` sigue en el `5173`
(`config/settings_pytest.py`).

Reglas que el e2e hace cumplir:

- Una pila fuera de `:8000` corre sobre **su propia BD e2e**: un nombre `hub_…` con `e2e` como palabra
  (`hub_e2e_8030`). Sin `DB_NAME`, con `hub` o con otra BD (`saas`, `hub_template`…), `stack.ts` la rechaza antes
  de la primera spec y dice qué exportar.
- `node tests/e2e/database.ts` crea la BD de `DB_NAME` si falta y la migra (control y hubs); es idempotente y
  conserva sus filas, así que se repite tras añadir una migración. Va **antes** de arrancar `runserver`, que no
  arranca sin su BD. `--drop` la borra al terminar, nunca a la fuerza: con el `runserver` vivo, falla y lo dice.
  Solo toca BD e2e.
- Si la BD e2e aún no existe, `global-setup.ts` lo dice con la orden que la crea.

Lo que no puede comprobar el e2e, y lo pide la receta:

- **Un SaaS por pila**, con el retorno a su Hub (`HUB_CALLBACK_TEMPLATE`, `HUB_ADMIN_CALLBACK_URL`) y **su carpeta
  de correo** (`EMAIL_FILE_PATH`, la misma que su `E2E_MAIL_DIR`): con una carpeta compartida, una ejecución
  puede leer el código de acceso que el otro SaaS mandó a la misma cuenta y el login falla.
- **Una pila por checkout**: dos Vite del mismo checkout comparten `node_modules/.vite` y se rompen el uno al
  otro al optimizar dependencias (la página se queda en blanco). Cada pila sale de su worktree.

Receta (pila en `8030`, desde la raíz de `erplora-next`; otra pila: otros puertos y otra BD):

```bash
export COMPOSE_FILE="$PWD/compose.yaml"
# 1. SaaS propio en 8031, desde un worktree del SaaS, con su carpeta de correo
(cd <saas-wt> && VITE_DEV_PORT=5204 HUB_CALLBACK_TEMPLATE='http://{slug}.localhost:8030/auth/callback' \
  HUB_ADMIN_CALLBACK_URL='http://hubs.localhost:8030/auth/callback' EMAIL_FILE_PATH="$PWD/.mail-8031" \
  uv run python manage.py runserver 127.0.0.1:8031)    # su propio Vite en 5204 (saas#38); nunca --novite sobre el Vite de otro árbol
# 2. La pila del Hub, desde su worktree
cd <hub-wt>
export E2E_HUB_PORT=8030 VITE_DEV_PORT=5203 SAAS_URL=http://localhost:8031 DB_NAME=hub_e2e_8030 \
  E2E_MAIL_DIR=<saas-wt>/.mail-8031
node tests/e2e/database.ts                           # crea y migra hub_e2e_8030
uv run python manage.py runserver 127.0.0.1:8030     # con las mismas variables
CI=1 pnpm e2e
# 3. Al terminar: parar ese runserver y su SaaS, y borrar la BD
node tests/e2e/database.ts --drop
```

## La página a la vista y los diálogos

`shown(page)` (`helpers.ts`) es la página que enseña `IonRouterOutlet`, nunca un diálogo abierto encima: Ionic Vue
envuelve el contenido de un `ion-modal` en un `.ion-page` propio y lleva el diálogo presentado a `ion-app`, detrás
de las páginas, así que «el último `.ion-page` visible» era el diálogo. Ahí la lista no tiene filas, y una spec que
contaba 0 filas tras confirmar un diálogo pasaba antes de que se borrara nada (el 17-10-2026, en
`sale-backoffice.spec.ts` y `combo-menus.spec.ts`). `helpers-shown.spec.ts` falla si vuelve a pasar.

- Un diálogo se busca en la página entera: `page.locator('ion-modal[data-testid=…]')`, nunca dentro de `shown(page)`.
- Tras confirmar un diálogo, se espera `await expect(<diálogo>).toBeHidden()` antes de contar filas o afirmar que
  algo ya no está.

## Medir cuándo acaba una petición

En la pila de desarrollo Vite sirve cada módulo de la SPA por separado, y llenan el búfer de Resource Timing de
Chrome (250 entradas) antes del primer clic: `performance.getEntriesByType('resource')` ya no lista lo que llega
después (el 16-10-2026 dio `NaN` en `delete-item.spec.ts`, `null` en `optimistic-add-line.spec.ts` y
`two-tabs-live.spec.ts`, y dejó ciega la comprobación de módulos de `no-outfitkit.spec.ts`). Toda spec que mire las
peticiones de la página usa `resource-timing.ts`: `recordResponses(page)` antes de que cargue la página (un
`PerformanceObserver`, que ve todas las entradas) y después `responseEnd(page, '/api/…')` (el fin de la última
petición fetch/XHR a ese path, con su query exacta) o `resourceUrls(page)` (todo lo que cargó). Sin esa petición o
sin el registro falla diciendo qué falta; nunca devuelve `NaN` ni `null`. `resource-timing-reads.test.ts` (Vitest)
falla si una spec o un helper lee el búfer de recursos por su cuenta; leer `'navigation'` sigue permitido.
