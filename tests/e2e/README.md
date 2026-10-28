# e2e del Hub (Playwright)

Las specs (`*.spec.ts`) manejan Chrome contra una pila de desarrollo que ya está arrancada: `runserver` del Hub
(Django + su Vite), el SaaS (el login de todo hub pasa por él) y Postgres de `compose.yaml`. Oculto por
defecto; `E2E_HEADED=1` lo enseña. Los `*.test.ts` de esta carpeta son Vitest (`pnpm test`): prueban la
configuración del e2e, no el producto. Todo `*.test.ts` del Hub que cargue Playwright (directo, por la
configuración o por un helper) empieza por `// @vitest-environment node`: en happy-dom, el entorno por defecto,
Playwright pide sus propios ficheros a `localhost:3000` y deja `ECONNREFUSED` detrás de una ejecución en verde.
`playwright-environment.test.ts` lo exige.

`pnpm typecheck` (y la CI) comprueba los tipos de todos los `.ts` de esta carpeta con su propio
`tsconfig.json`, que lleva los tipos de Node (`process`, `node:fs`) en lugar de los del cliente de Vite, sin
añadirlos al proyecto de la SPA (`tsconfig.app.json`). Un error de tipos en una spec o en un helper rompe la CI;
`typecheck.test.ts` vigila que ningún fichero de aquí se quede fuera.

```bash
CI=1 pnpm e2e                                  # toda la suite
CI=1 pnpm e2e tests/e2e/sale-sales.spec.ts     # una spec: SIN `--` (con él, Playwright ignora el filtro)
```

Antes de la primera spec, `global-setup.ts` comprueba que la BD de la ejecución (`DB_NAME`) no tiene
migraciones pendientes (`migrate --check`, `migrate_hubs --check`) y nunca migra nada; después, que el SaaS de la pila
tiene las cuentas de demo con las que entran las specs (abajo, «Varias ejecuciones a la vez»). Antes aún, rechaza más de un
worker: `--workers=N` pisa el `workers: 1` de `playwright.config.ts`, y dos specs a la vez sobre la misma pila se
borran los datos. Para correr en paralelo, otra pila (abajo, «Varias ejecuciones a la vez»).

## El login

`login()` de `helpers.ts` hace el login de verdad: el hub manda al SaaS, el SaaS pide la cuenta y el código que
envía por correo (leído de `E2E_MAIL_DIR`) y devuelve al hub con su código de un solo uso. Cada cuenta inicia
sesión en el SaaS **una vez por worker**: los logins siguientes, en contextos nuevos, empiezan con esa sesión del
SaaS, como quien ya entró en erplora.com, y solo hacen la vuelta al hub. Antes cada login dejaba otra sesión
abierta de la cuenta, y el SaaS las recorre todas en cada inicio de sesión (`allauth.usersessions`): con 1680 de
`owner@example.com` en la BD `saas` compartida, el SaaS tardó 30 y 37 s en contestar el código con la máquina
cargada (hub#107). Si una spec cierra la sesión del SaaS, el siguiente login vuelve a pedir la cuenta y guarda la
sesión nueva (`helpers-login.spec.ts`).

Lo mismo con el hub: la sesión que abre un salto se guarda **por cuenta y por hub**, y un contexto nuevo empieza con
ella y aterriza en `next` sin pasar por el SaaS, como quien vuelve a su negocio. Así una spec salta **una vez por
cuenta y hub** mientras esa sesión viva. Cada salto cuenta para el freno del SaaS (`HUB_LOGIN_RATELIMIT`, 20 por
cuenta cada 5 minutos, ACCOUNTS-F28): antes cada login saltaba, y una spec de más de 20 tests caía en el 21.º con
«429 · Too many attempts» (`staff-flows.spec.ts`, de 23 saltos a 2). Si la sesión del hub ya no vale (una spec salió
del hub), el hub manda al SaaS como siempre y se guarda la nueva; solo se guarda la que el SaaS abrió para esa cuenta.
La spec que prueba el salto mismo lo pide: `login(page, origin, next, cuenta, { fresh: true })` (o `hostPage(…, {
fresh: true })`). Lo cubre `helpers-login-hub-session.spec.ts`.

Esa sesión es **una sola** en el servidor para todos los contextos que la reutilizan, también los de specs
distintas: salir del hub en uno la termina en todos (el siguiente login salta otra vez), y lo que una spec deje
guardado en ella lo hereda la siguiente. Una spec con dos dispositivos de la misma cuenta, o la del cambio de
empleado por PIN cuando llegue (fase 2) si no rota la clave de sesión, pide `fresh: true` para tener la suya.

Cada paso espera una sexta parte del tiempo del test (30 s con los 180 s de `playwright.config.ts`; más con
`test.slow()` o `test.setTimeout`) y, si no llega, falla diciendo cuál y cuánto esperó. «code rejected» solo
sale cuando el SaaS dice que el código no vale; si aún no ha contestado, el error dice «the SaaS did not answer
the code within … ms».

## La pila compartida

Sin variables, el e2e va contra la pila compartida: Hub en `:8000` (Vite `:5173`), SaaS en `:8001` y las BD
`hub` y `saas` (la del SaaS, con sus cuentas de demo). La usan otras sesiones: no se migra ni se borra desde aquí.

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
| `E2E_SAAS_DB` | la BD del SaaS propio, si no es `saas_e2e_<Hub+1>` (con el Hub en `:8000`, `saas`) | `global-setup.ts` y las specs que la leen (`stack.ts`) |

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
- Ese mismo paso deja en el `.env` del checkout las dos claves Fernet con las que cifra el Hub: la
  `FISCAL_CERTIFICATE_KEY` de los certificados de prueba (sin ella, «Mi certificado» de `verifactu-config.spec.ts`
  recibe un 409) y la `FLOW_SECRETS_KEY` de los secretos de las automatizaciones (sin ella, la caja «Secretos» de
  «Llamar a otro sistema» dice que el servidor no puede guardar secretos y `flow-steps.spec.ts` se queda esperando en
  FLOW-F26). Genera cada una para ese checkout si falta o está vacía, respeta la que ya haya en el `.env` o en el
  entorno, dice en una línea qué hizo con cada una (nunca su valor) y, si alguna no es una clave, falla sin escribir
  nada (`fernet-keys.ts`).
- Si la BD e2e aún no existe, `global-setup.ts` lo dice con la orden que la crea.
- Las specs entran con las cuentas de demo del SaaS (`owner@example.com` y `employee@example.com`, con acceso a `a` y
  `b`), que solo crea `manage.py demo_seed` del SaaS. `global-setup.ts` las busca en la BD del SaaS de la pila (`E2E_SAAS_DB`,
  por defecto `saas_e2e_<Hub+1>`; con un solo `select`, sin escribir nada) y, si faltan, para antes de la primera spec con
  la orden que las siembra; si esa BD no existe, con la que la crea. Sin ellas, cada login esperaba 30 s para caer con «The
  email address and/or password you specified are not correct.».

Lo que no puede comprobar el e2e, y lo pide la receta:

- **Un SaaS por pila**, con el retorno a su Hub (`HUB_CALLBACK_TEMPLATE`, `HUB_ADMIN_CALLBACK_URL`) y **su carpeta
  de correo** (`EMAIL_FILE_PATH`, la misma que su `E2E_MAIL_DIR`): con una carpeta compartida, una ejecución
  puede leer el código de acceso que el otro SaaS mandó a la misma cuenta y el login falla.
- **Su propia BD del SaaS** (`saas_e2e_<Hub+1>`, la crea y la migra `tests/e2e/database.ts` del SaaS con
  `E2E_SAAS_PORT=<Hub+1>`), con `env -u DB_NAME` al crearla y `DB_NAME=saas_e2e_<Hub+1>` en su `runserver`: la `saas` del
  `.env` es de la pila compartida y puede ir atrasada de migraciones (su login cae con un 500), y con el `DB_NAME` del Hub
  exportado el SaaS abre la BD del Hub (su login cae con `relation "django_site" does not exist`).
- **Sus límites por dirección subidos** (`E2E_RELAX_LOGIN_RATE_LIMIT=True` en su `runserver`; `config/settings.py` del
  SaaS, solo con `DEBUG`): todas las specs entran y se dan de alta desde `127.0.0.1`, y sin la marca una pasada entera
  cae con «429 · Too many attempts» en el login o en la 11.ª alta de la hora (10 por hora y dirección). Cada cuenta
  conserva su propio límite, y el freno de saltos al hub (`HUB_LOGIN_RATELIMIT`, arriba) no cambia. El e2e no lo puede
  comprobar: la marca vive en el entorno del proceso del SaaS, el SaaS no la dice por ninguna ruta y probarla gastaría
  los intentos que protege.
- **Una pila por checkout**: dos Vite del mismo checkout comparten `node_modules/.vite` y se rompen el uno al
  otro al optimizar dependencias (la página se queda en blanco). Cada pila sale de su worktree.

Receta (pila en `8030`, desde la raíz de `erplora-next`; otra pila: otros puertos y otra BD):

```bash
export COMPOSE_FILE="$PWD/compose.yaml"
# 1. SaaS propio en 8031, desde un worktree del SaaS, sobre su BD saas_e2e_8031 y con su carpeta de correo
cd <saas-wt>
env -u DB_NAME E2E_SAAS_PORT=8031 node tests/e2e/database.ts        # crea y migra saas_e2e_8031
env DB_NAME=saas_e2e_8031 uv run python manage.py demo_seed         # las cuentas de demo con las que entran las specs
env DB_NAME=saas_e2e_8031 VITE_DEV_PORT=5204 HUB_CALLBACK_TEMPLATE='http://{slug}.localhost:8030/auth/callback' \
  HUB_ADMIN_CALLBACK_URL='http://hubs.localhost:8030/auth/callback' HUB_INTERNAL_URL=http://localhost:8030 \
  EMAIL_FILE_PATH="$PWD/.mail-8031" E2E_RELAX_LOGIN_RATE_LIMIT=True \
  uv run python manage.py runserver 127.0.0.1:8031   # su propio Vite en 5204 (saas#38); nunca --novite sobre el Vite de otro árbol
# 2. La pila del Hub, desde su worktree (en otra terminal)
cd <hub-wt>
export E2E_HUB_PORT=8030 VITE_DEV_PORT=5203 SAAS_URL=http://localhost:8031 DB_NAME=hub_e2e_8030 \
  E2E_MAIL_DIR=<saas-wt>/.mail-8031
node tests/e2e/database.ts                           # crea y migra hub_e2e_8030
uv run python manage.py runserver 127.0.0.1:8030     # con las mismas variables
CI=1 pnpm e2e
# 3. Al terminar: parar ese runserver y su SaaS, y borrar las dos BD
node tests/e2e/database.ts --drop
(cd <saas-wt> && env -u DB_NAME E2E_SAAS_PORT=8031 node tests/e2e/database.ts --drop)
```

## La demo (`demo.spec.ts`)

Recorre la demo de punta a punta (plan `docs/plans/2026-10-17-demo-hubs-fase-1.md` §3, README del Hub «Demo»):
`/demo/` del SaaS → «Try the demo» → `demo-<hex>.localhost:<puerto>` con la shell y la sesión «Demo» → crea un ítem
→ `manage.py demo_expire <slug>` (por `execFileSync`, desde este checkout y con el `DB_NAME` de la ejecución) → 410
«This demo has ended» → su enlace → `/demo/?state=expired` del SaaS → otra demo. Pide dos cosas que el resto de
specs no piden:

- **El SaaS con la puerta de la demo** (`ERPlora/saas` con `/demo/?state=expired`, en `main` desde el 2026-10-17) y
  su `HUB_INTERNAL_URL` en el Hub de esta pila (la receta de arriba la lleva): el SaaS crea la demo
  llamando él mismo a `/internal/demos`; apuntado a otro puerto, la crea en otro Hub y esta ejecución no la ve.
- El mismo `INTERNAL_SHARED_SECRET` en los dos (en local, el valor por defecto de ambos).

```bash
CI=1 pnpm e2e tests/e2e/demo.spec.ts   # con las variables de la receta exportadas
```

Cada ejecución crea dos demos en la BD de la pila y las deja purgadas (lápidas `DEMO_TOMBSTONE_DAYS`); no gasta el
tope de demos vivas (`MAX_CONCURRENT_DEMOS`).

## El asistente (`base-assistant.spec.ts`)

Prueba el asistente del Hub (BASE-F92…F106) con sus dependencias de verdad: el Hub de la pila, la pasarela del SaaS de
la pila (`/internal/assistant/*` y `/internal/speech/transcribe`) y, detrás, el proveedor falso
`tests/e2e/assistant-provider.ts`, un servidor HTTP en 127.0.0.1 que habla la API de OpenAI y que la propia spec
arranca en `E2E_AI_PROVIDER_PORT` (por defecto, el puerto del Hub + 2). Ningún test llega a un proveedor real ni
escribe una clave real. Pide tres cosas al SaaS de la pila:

- **La BD del SaaS sembrada con ese proveedor**, desde su worktree y antes de la primera ejecución:
  `env DB_NAME=saas_e2e_<Hub+1> uv run python tests/e2e/panel/assistant_seed.py gateway http://127.0.0.1:<Hub+2>/v1`
  (además del `demo_seed` de la receta de arriba, como el resto de specs). La spec lo comprueba al arrancar y, si falta,
  cae con «not seeded with this provider».
- **`ASSISTANT_SERVICE_PROVIDER=e2e-local`** en el `runserver` del SaaS (con el resto de variables de la receta de
  arriba, también `E2E_RELAX_LOGIN_RATE_LIMIT=True`): sin ella el dictado responde 503.
- **`E2E_SAAS_DB`** (la de la tabla de arriba), si la BD del SaaS no es `saas_e2e_<Hub+1>` (con el Hub en :8000, `saas`):
  la spec fija en ella los mensajes del mes del negocio `a` antes de cada test, así que nunca gasta el cupo del plan.

```bash
# El SaaS de la pila (8871), desde su worktree:
env DB_NAME=saas_e2e_8871 VITE_DEV_PORT=6071 ASSISTANT_SERVICE_PROVIDER=e2e-local \
  HUB_CALLBACK_TEMPLATE='http://{slug}.localhost:8870/auth/callback' \
  HUB_ADMIN_CALLBACK_URL='http://hubs.localhost:8870/auth/callback' HUB_INTERNAL_URL=http://localhost:8870 \
  EMAIL_FILE_PATH="$PWD/.mail-8871" E2E_RELAX_LOGIN_RATE_LIMIT=True uv run python manage.py runserver 127.0.0.1:8871
# La spec, con las variables de «Varias ejecuciones a la vez» exportadas (Hub en 8870):
CI=1 pnpm e2e tests/e2e/base-assistant.spec.ts --workers=1
```

La cuenta del e2e está en inglés: la spec comprueba las cadenas `en`.

## La QA maestra (`base-qa-master.spec.ts`)

La QA maestra del Hub (BASE-F107, la del contrato `qa-hub` del hub viejo): un dueño nuevo se da de alta en las pantallas
del SaaS de la pila, crea por su API un restaurante (con su tipo de negocio) y el Hub lo recibe con su vertical; carga la
plantilla de ese vertical y recorre la plataforma entera (Inicio, Apps, Ajustes y Datos, Empleados, Sistema, Archivos, Mi
perfil, la página de una dirección que no existe y el asistente) en 390, 834 y 1440, en español y en inglés. Cada
pantalla carga sin error y sin un texto del otro idioma ni una clave a la vista: lo compara con los catálogos del propio
Hub (`translations.ts`, los `en`/`es` de la SPA y los `.po`). Pide al SaaS de la pila lo mismo que el asistente (arriba)
y, además, **su taxonomía**, que en cada despliegue siembra `saas-migrate`:

```bash
# Desde el worktree del SaaS, sobre su BD de la pila (8871 en el ejemplo de arriba):
env DB_NAME=saas_e2e_8871 uv run python manage.py seed_taxonomy
```

Sin ella la spec cae al empezar con «no business type of the restaurant vertical». Da de alta una cuenta por ejecución:
con `E2E_RELAX_LOGIN_RATE_LIMIT=True` en el SaaS (la receta) las altas no tienen tope práctico; sin la marca, el SaaS deja
10 por hora y dirección, y tras varias ejecuciones seguidas hay que reiniciar su `runserver` (la caché local es de
memoria). Deja `APP-BASE-10-BASE-G152-<idioma>-<pantalla>-<ancho>.png` en `.artifacts/`.

## La página a la vista y los diálogos

`shown(page)` (`helpers.ts`) es la página que enseña `IonRouterOutlet`, nunca un diálogo abierto encima: Ionic Vue
envuelve el contenido de un `ion-modal` en un `.ion-page` propio y lleva el diálogo presentado a `ion-app`, detrás
de las páginas, así que «el último `.ion-page` visible» era el diálogo. Ahí la lista no tiene filas, y una spec que
contaba 0 filas tras confirmar un diálogo pasaba antes de que se borrara nada (el 17-10-2026, en
`sale-backoffice.spec.ts` y `combo-menus.spec.ts`). `helpers-shown.spec.ts` falla si vuelve a pasar.

- Un diálogo se busca en la página entera: `page.locator('ion-modal[data-testid=…]')`, nunca dentro de `shown(page)`.
- Tras confirmar un diálogo, se espera `await expect(<diálogo>).toBeHidden()` antes de contar filas o afirmar que
  algo ya no está.

## Las capturas

Una captura justo después de `setViewportSize` puede salir antes de que el navegador pinte la página a su nuevo tamaño:
la zona que destapa el cambio de tamaño aún tiene lo de arriba de la página, y la captura repite la barra superior en su
parte de abajo (87 filas; en `main`, 5 de 24 capturas de la lista de la demo sin espera y 2 de 24 tras `settled`). Esa
captura es la prueba de una pantalla que nadie vio. Toda captura de la e2e pasa por `capture(page, name)` (`helpers.ts`):
espera a un fotograma pintado, repite la captura mientras repite la franja de arriba (`repeatedTop`, la del SaaS) y, si
no deja de hacerlo, falla diciéndolo y no escribe nada; si no, la deja en `.artifacts/<name>.png` y la devuelve. Lo que
tiene que estar en pantalla antes (datos, un diálogo, nada moviéndose: `settled` o `untilStill`) lo espera la spec.
`helpers-capture.spec.ts` falla si vuelve a pasar.

`settled(page)` (`helpers.ts`; `service-helpers.ts` y `schedule-helpers.ts` reparten el mismo, sin copias) espera a que
nada se mueva (`untilStill`) y a un fotograma pintado. «Nada se mueve» se lee en el documento **y en cada shadow root
abierto, a cualquier profundidad** (`movingInPage`): `document.getAnimations()` no ve los shadow roots, y Ionic anima ahí
sus avisos, diálogos y popovers (con el `settled` de antes, un `ion-toast` aún entrando daba 0 animaciones en el
documento y 1 en su shadow root). Las infinitas (spinners, un brillo de carga) no cuentan; si algo sigue moviéndose a los
10 s, la spec falla diciendo qué; y si la página navega a mitad de espera, mira la página nueva. Lo cubre
`settled.spec.ts` (la misma corrección que la e2e del SaaS, saas#147).

`raw-screenshots.test.ts` (Vitest) es el trinquete: ningún fichero de `tests/e2e` hace más `.screenshot(` crudos de los
que lista `raw-screenshots.json` (los que quedaban al llegar `capture`), y una spec nueva no hace ninguno. Al pasar
capturas de un fichero a `capture`, baja su número en el JSON (o quita su línea): la lista solo encoge.

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
