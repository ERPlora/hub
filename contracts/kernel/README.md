# `contracts/kernel/` — la superficie CONGELADA del hub

Estos ficheros **son el contrato del kernel**: lo que el hub le promete a los módulos publicados.
No se escriben a mano — cada uno lo **genera un test desde el código** y lo compara con la copia
commiteada. Si el código se desvía, el build rompe **nombrando** lo que sobra y lo que falta.

Decisión: ADR **«El Hub se CIERRA como KERNEL»** (2026-08-27) · contrato y mecanismo en
`architecture/hub/kernel-contract.md` §2 · issue [hub#1235].

No es un invento nuestro: es lo que hacen Kotlin (`apiCheck` / binary-compatibility-validator),
.NET (`PublicApiAnalyzers`) y `cargo-semver-checks` — la API pública vive en un fichero y el
`diff` de ese fichero es lo que revisa una persona.

## Qué es cada fichero

| Fichero | Qué congela | Lo genera |
|---|---|---|
| `routes.snapshot` | Cada ruta HTTP/WS de `app()`: método · ruta · clase de auth | `cargo test -p erplora-server --test kernel_contract_routes` |
| `engine.snapshot` | Motor declarativo: params inyectados, `hub.*`, capabilities, orígenes del dispatcher, `kind`s de migración **y los verbos que sacan una migración de `expand`**, guardas de fila | `cargo test -p erplora-runtime --test kernel_contract_engine` |
| `guest.snapshot` | Contrato del guest WASM: campos de `Input`/`Output` y topes de `WasmLimits` | `cargo test -p erplora-runtime --test kernel_contract_guest` |
| `tables.snapshot` | Tablas de sistema (`hub_*`, `_*`) con sus columnas, **reflejadas** de un hub recién arrancado | `cargo test -p erplora-runtime --test kernel_contract_tables` (necesita Postgres, `DATABASE_URL`) |
| `sdk.d.ts` | API pública de `@erplora/module-sdk`, tal cual la emite `tsc` | `pnpm -F @erplora/module-sdk contract:check` (va en `pnpm verify`) |

La sexta superficie —el manifest `module.json`— **ya tenía su snapshot** desde ADR-0286: el propio
`schemas/module.schema.json`, vigilado por `crates/runtime/tests/manifest_fields_match_the_schema.rs`.
Por eso no está aquí.

## Cómo se actualiza

Regenerar es **explícito**, nunca automático: se pone `UPDATE_KERNEL_CONTRACT=1` delante del
comando de la tabla y el fichero se reescribe.

```sh
UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-server  --test kernel_contract_routes
UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_engine
UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_guest
UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_tables
UPDATE_KERNEL_CONTRACT=1 pnpm -F @erplora/module-sdk contract:check
```

**El diff resultante ES la revisión.** Un cambio en cualquiera de estos ficheros:

1. va en una PR con etiqueta **`kind:contract`** — sin ella la PR no mergea;
2. lleva **entrada en el decision-log** de `architecture/` en la misma tanda;
3. necesita **`test-hub-modules.yml` en verde** contra los módulos publicados: el kernel no rompe
   a un módulo instalado, nunca (regla de Linus; si rompe, se revierte el hub y el módulo se
   adapta **después**).

## Cómo se leen

- **`routes.snapshot`** — `MÉTODO RUTA auth:<clase>`. La clase se **deriva**, no se declara: es la
  primitiva de `crate::auth` a la que llega el handler a través de sus propios helpers y macros
  (`admin`, `session`, `api-key`, `any-credential`, `capability`). Varias clases se unen con `+`
  cuando el handler pasa por más de una puerta (`admin+capability`). Una sesión resuelta **a mano**
  (`auth::session_token` + `resolve_session`, como `/api/auth/set-pin`) cuenta como `session`.
  El token de máquina del hub (`hub_scoped_auth`/`machine_auth`) **no es una clase**: autentica al
  hub ante el Cloud, no al que llama al hub — listarlo pintaba de «puerta» rutas abiertas.
  `auth:none` significa literalmente **ninguna primitiva en ese camino**. El número drifta con
  cada PR (recuenta con `grep -c auth:none routes.snapshot`, 16 el 2026-09-16): el login
  (`/api/auth/*` salvo `set-pin`), las sondas (`/healthz`, `/readyz`, `/robots.txt`), los assets de
  módulo (`/modules/**`), el modo del dispositivo que lee la pantalla de login, `/api/hub/context`,
  `/api/error-report`, el reporte de CSP (`POST /csp-report/`) y `/p/:locator` —cuya autorización
  **es el localizador** (hub#963)—. Que una ruta abierta salga como `none` es la función del
  fichero, no un defecto suyo.
  Si aparece una forma nueva de gatear una ruta hay que añadirla a la tabla `PRIMITIVES` del test,
  o todas las rutas que gatee saldrán como `none`.
- **`engine.snapshot`** — por secciones. `[system_params]` sale de una llamada REAL a
  `system_params`, no de una copia de sus claves. `[capabilities]` se cruza con el bloque
  `capabilities` de `schemas/module.schema.json`: lo que el host gatea y lo que el schema deja
  declarar no pueden divergir.
  `[migration_not_expand]` sale de `migration_guard::NOT_EXPAND` (hub#1163): con `start-first` la
  versión ANTERIOR del hub sigue sirviendo contra el esquema ya migrado, así que lo que no es
  aditivo tiene que declararse `contract`. Cada verbo tiene su control positivo en los tests, y
  congelarlo aquí es lo que hace visible en una PR que la puerta se ha ensanchado.
- **`tables.snapshot`** — reflejado de `information_schema` tras `Runtime::ensure_system_tables`,
  no parseado del SQL: un `CREATE TABLE` que Postgres rechazaría no puede colarse aquí.
- **`guest.snapshot`** — obtenido SERIALIZANDO valores reales, así que respeta
  `#[serde(transparent)]` y `skip_serializing_if`. Un `.wasm` publicado no se recompila: renombrar
  un campo de aquí rompe a la vez a todos los handlers Tier 2 instalados.

## Lo que vigila el compilador, no un snapshot

Un snapshot congela una **forma**; los bugs de forma correcta los caza el compilador. Desde
hub#1242 el workspace declara **lints Rust**: `[workspace.lints.clippy] correctness = "deny"`
(más `future_incompatible = "deny"` de rustc) en el `Cargo.toml` raíz, heredados por los 14
miembros con `[lints] workspace = true`, y verificados por el paso `cargo clippy --workspace`
de `.github/workflows/test-hub.yml` — el ratchet para subir el siguiente grupo está documentado
en la propia tabla. El cableado lo vigila `scripts/tests/clippy-lints.test.sh`, que corre en ese
mismo workflow.

## La suite de conformidad del kernel (KCS)

Los snapshots congelan la **forma** de la superficie; la KCS comprueba que esa superficie **hace lo
que promete**. Viven juntas a propósito: un snapshot verde con un motor roto es exactamente el
agujero que Android CTS y la conformance de Kubernetes existen para tapar — el fichero dice que la
API está ahí, y solo ejecutarla dice que funciona.

`crates/runtime/tests/kernel_conformance_*.rs`, un fichero por área:

| Fichero | Qué prueba |
|---|---|
| `kernel_conformance_install.rs` | Instalar registra queries/commands/permisos/listeners; un campo desconocido dentro de un command se **rechaza nombrándolo**; un listener a un command ajeno también |
| `kernel_conformance_migrate.rs` | `expand`/`backfill`/`contract`: el `DROP` traducido a `_deprecated_` (las filas sobreviven), el `backfill` que reescribe las filas de la versión anterior, `kind` que no cuadra con el SQL (un `DROP` en un `expand`, un `ALTER` en un `backfill`) y un `contract` que destruye FILAS — todo bajo el código `hub.module_migration_rejected` |
| `kernel_conformance_query_list_row.rs` | Motor de listas (paginado, `default_sort`, `search`, `filters`) y **el contrato de fila**: `hub_id`/`current_user_id`/`now` los sella el kernel y el payload NO los puede falsificar |
| `kernel_conformance_command_gates.rs` | `expect_rows` (con su código), la transacción que revierte entera, y el command interno (`_`) que no es puerta pública |
| `kernel_conformance_permissions.rs` | El gate, el **techo** de las operaciones de un handler (hub#459) por sus dos mitades —pasa con el permiso, se niega en seco por encima de él— y la elevación DERIVADA de `role_permissions.manager` (hub#351) |
| `kernel_conformance_events.rs` | `emit` → `_event_outbox` → listener; el evento de un handler por el mismo camino; un command que falla no emite; nombre fuera de `events.emits` **rechazado nombrándolo** |
| `kernel_conformance_slots_navigation.rs` | `navigation` (permiso, `chrome`), `provides_slots` y los `locales/` del módulo (`en` canónico, `es` traducido) |
| `kernel_conformance_errors.rs` | El catálogo `errors` (ADR-0398/0412): servido ordenado, `deprecated` marcado, `expect_rows.error` fuera del catálogo rechazado **al instalar**, y un código fuera del catálogo devuelto por un handler es contrato roto (`Wasm`), nunca un `Domain` que la UI intente traducir |
| `kernel_conformance_guest_wasm.rs` | El round-trip Tier 2 contra un `.wasm` **compilado de verdad**; el guest no alcanza ni un command inexistente ni el de un módulo VECINO (un gemelo del fixture bajo otro id) |
| `kernel_conformance_update.rs` | Update en caliente (hub#516): los datos sobreviven, solo corre la migración nueva, y un update que falla deja **corriendo la versión anterior** |

Todas usan el **módulo fixture del propio kernel** —`crates/runtime/tests/fixtures/kernel-fixture/`,
id `kfx`— y nunca `sales`, `kitchen` o `invoice`: lo que hace un módulo es asunto del módulo; lo que
el hub debe es la superficie de debajo. El fixture trae **dos versiones** porque instalar `1.0.0` y
luego `1.1.0` ES el camino de actualización:

```text
crates/runtime/tests/fixtures/kernel-fixture/
├── 1.0.0/            # antes de la retirada: 1 migración `expand`, 1 query, 1 command
├── 1.1.0/            # + migraciones `contract` y `backfill`, handler Tier 2, eventos, navigation, errors, locales
│   ├── handler.wasm         # binario COMPILADO, commiteado
│   └── handler.build.json   # sello: sha256 de las fuentes y del binario
├── handler/          # el guest Rust (cdylib) del que sale ese .wasm
└── build-handler.sh  # lo recompila y reescribe el sello
```

**El `.wasm` va commiteado a propósito.** `guest.snapshot` congela los nombres de campo de
`Input`/`Output`, y un `.wasm` publicado **no se recompila**: la única prueba de que el host sigue
hablando esa forma es un binario que se compiló contra ella. Por eso el round-trip de
`wasm_tier2.rs::real_guest_bulk_create` —`#[ignore]` desde que existe, con la receta en un
comentario— pasa a **obligatorio** aquí.

Tras tocar `handler/`:

```sh
crates/runtime/tests/fixtures/kernel-fixture/build-handler.sh   # necesita el target wasm32-unknown-unknown
```

y se commitean `handler.wasm` **y** `handler.build.json`: `kernel_conformance_guest_wasm.rs`
recalcula los dos sha256 y falla si el binario no sale de las fuentes commiteadas (agujero #7 del
contrato, module-toolkit#93, aplicado al propio fixture).

Correr la suite (necesita Postgres, igual que `tables.snapshot`):

```sh
DATABASE_URL=postgres://postgres:test@localhost:5433/hub_test \
  cargo test -p erplora-runtime --test 'kernel_conformance_*'
```

Cada área lleva además su prueba de que **caza el positivo**: se rompe el contrato en una copia del
fixture (código de error sin declarar, listener a un command ajeno, `DROP` declarado `expand`,
evento fuera de `events.emits`…) y se comprueba que el runtime se niega **nombrando el elemento**.
Un guard que no se ha visto fallar no es un guard.

## Lo que NO va aquí

Superficie declarada que **no existe** se retira, no se congela (`navigation[].actions`,
`render.pdf`/`render.xlsx` — hub#1237). Y una superficie nueva entra marcada `experimental`, fuera
del schema que valida `erplora validate`, hasta que una ADR la fija como `stable`.
