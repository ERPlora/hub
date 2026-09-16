# crates/ — runtime Rust de hub

Workspace Cargo. El **runtime es la autoridad** (ARQUITECTURA.md §4): valida permisos,
tenant (`hub_id`) y payload, y ejecuta queries/commands declarados por los módulos. Rust
no tiene lógica de negocio hardcodeada.

> ✅ **`cargo test --workspace` en verde** (todo compila; el número exacto de tests cambia
> con cada commit — corre el comando, o `/test-hub`, en vez de fiarte de una cifra congelada
> aquí). El server arranca y responde por HTTP real; el flujo de instalación E2E
> (SaaS→descarga→runtime) y el hot-plug (install/activate/deactivate/uninstall) están probados.

## Estado

Todos con código real (ninguno es un esqueleto). El recuento vigente es `ls -d crates/*/`;
para el de tests, `cargo test -p <crate>`. Tabla orientativa:

| Crate | Qué es | Estado |
|-------|--------|--------|
| `erplora-db` | `DatabaseAdapter` + **Postgres** (`PgAdapter`, traductor `:n`→`$n`). Postgres-only (SQLite/`rusqlite` retirados, ADR-0154). | ✅ implementado |
| `erplora-runtime` | Host genérico: manifest → migraciones → permisos → query/command/eventos (scope `hub_id`) + ciclo de vida (estado en `hub_module`). | ✅ implementado + varias suites e2e |
| `erplora-server` | **Axum**: query/command, navigation, gestión de módulos, `/ws`, `/healthz`. | ✅ implementado + binario |
| `erplora-cloud-client` | Cliente del SaaS: auth (X-Hub-Token/JWT/webhook), marketplace, **SHA256**. | ✅ implementado |
| `erplora-source` | Descarga `module.zip` (S3, fetcher inyectable) + verifica SHA256 + descomprime (anti zip-slip) + cache. | ✅ implementado |
| `erplora-installer` | **Flujo E2E**: grant(SaaS) → descarga/verifica(source) → instala(runtime). | ✅ implementado |
| `erplora-vector` | `VectorStore` para RAG. `PgVectorStore` (Postgres/pgvector) es la implementación de producción, instanciada en `crates/server/src/boot.rs`; si la BD del hub no tiene `pgvector` el arranque no aborta — degrada a `None` (todas las tools). `MemoryVectorStore` sigue siendo solo referencia/test. | ✅ implementado |
| `erplora-guest-sdk` | Contrato host↔guest WASM (Input/Operation/Event/Output) para autores de plugins. | ✅ implementado |
| `erplora-wasm-host` | **Tier 2**: ejecuta handlers WASM en sandbox (Extism), devuelve *intenciones*. | ✅ implementado |
| `erplora-sync` | Cliente de eventos en vivo (consume `/ws`) con reconexión + backoff. | ✅ implementado |
| `erplora-peripherals` | Hardware POS, tres transportes — red (ESC/POS), USB (cola RAW del SO, hub#1083) y Bluetooth SPP en Android (ADR-0204) — cajón, discovery, cola/reintentos. Ver [`peripherals/README.md`](peripherals/README.md). | ✅ implementado |
| `erplora-verifactu` | Lógica fiscal VeriFactu (encadenado, XML, hashing). Vive en **`crates/plugins/`** (convención de abajo). | ✅ implementado |
| `tauri-plugin-erplora-android` | Plugin Tauri para Android: permisos de runtime en contexto (`ACCESS_LOCAL_NETWORK`, `POST_NOTIFICATIONS`) y el Kotlin que Rust no alcanza (ADR-0180 §2). Lleva además el `AndroidManifest.xml` que los DECLARA fuera del proyecto generado, para que regenerar `gen/android` no se los lleve (ADR-0241). | ✅ implementado |

## Convención: `crates/*` vs `crates/plugins/*` (hub#1405)

- **`crates/*`** = el **core país-agnóstico** («el hub es la base de LEGO»): nada aquí puede
  nombrar un país ni un régimen fiscal concreto.
- **`crates/plugins/*`** = motores de **régimen fiscal first-party** (hoy `verifactu`; futuro:
  `ticketbai`, `nf525`, `facturx`…). La frontera base↔pieza se LEE en el árbol del workspace, y
  el gate la vigila (guard «el core no nombra países», hub#1407).
- Es un **estado intermedio a propósito**: el ADR-0424 fija como destino que cada motor migre al
  WASM de su módulo y este directorio acabe desapareciendo. No invertir aquí más de lo mecánico.

## Probarlo

```sh
cargo test  --workspace                                   # ver conteo real al ejecutar (no lo congeles)
cargo run   -p erplora-runtime --example walking_skeleton # demo runtime end-to-end

# server real (HTTP) + hot-plug (requiere Postgres — HUB_DATABASE_URL).
# `HUB_DEV_MODE=1` + `HUB_MODULES_DIR`: instalar desde CARPETA es una vía de desarrollo,
# confinada a ese staging y APAGADA en producción (allí: marketplace + SHA256, hub#239).
HUB_DATABASE_URL=postgres://localhost/erplora_hub_dev HUB_BIND=127.0.0.1:8799 \
  HUB_DEV_MODE=1 HUB_MODULES_DIR="$PWD/modules" cargo run -p erplora-server &
curl -s localhost:8799/api/modules
curl -s -X POST localhost:8799/api/modules/install -H 'content-type: application/json' -d '{"dir":"modules/notes"}'
curl -s localhost:8799/api/navigation
curl -s -X POST localhost:8799/api/modules/notes/deactivate
# demo visual del grid "Mis módulos":
node demos/hotplug/run.mjs
```

## Hecho

- **Tier 2 en el runtime**: `execute_command` (`crates/runtime/src/commands.rs::execute_wasm`)
  ya invoca `erplora-wasm-host` (`WasmHost::from_bytes` + `call`) para commands con
  `handler: { type: "wasm", ... }`.

## Pendiente

- **`erplora-sync` sigue huérfano**: su feature `ws` (cliente tungstenite real) existe pero
  ningún binario del workspace depende de este crate — `crates/server` no lo lista como
  dependencia. Las descargas reales de `module.zip` **ya están resueltas**: `crates/server` trae
  su **propia** dependencia `reqwest` (no la de `cloud-client`/`source`/`installer`, que siguen
  con su transporte real detrás de la feature opcional `reqwest-transport`, sin habilitar en el
  workspace) y `crates/server/src/install.rs` la usa directamente.
- **Auth de sesión es la ruta real de producción**: el JWT de usuario cloud se verifica RS256 de
  verdad (`cloud_client::verify_user_jwt`) y abre una `hub_session` server-side (`crates/server/src/auth.rs`).
  El modo que «lee cabeceras sin validar» (`HubConfig::auth_mode == Dev`) es un **modo aparte,
  explícito y confinado a desarrollo local** (`HUB_DEV_MODE`), nunca lo que sirve el provisioning.

## Notas de diseño

- **Parámetros del sistema** inyectados en cada query/command (no falsificables desde la UI):
  `:hub_id`, `:current_user_id`, `:now`, `:new_id` (§2.5, §2.9).
- **Migraciones** idempotentes por módulo/fichero (`_hub_migrations`), dialecto `postgres`.
- **Hot-plug**: solo los módulos ACTIVOS exponen menú/queries/commands/listeners.
- **Transportes inyectables** (sin red en tests): `Fetcher`/`Transport`/`EventStream` se
  implementan con reqwest/tungstenite en los binarios; en tests van mocks.
