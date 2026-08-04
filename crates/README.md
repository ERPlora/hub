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
| `erplora-vector` | `VectorStore` para RAG. Hoy `MemoryVectorStore` (in-memory, referencia/test); el store Postgres/pgvector es **follow-up** (hub#204 / pm#29). | 🔶 referencia |
| `erplora-guest-sdk` | Contrato host↔guest WASM (Input/Operation/Event/Output) para autores de plugins. | ✅ implementado |
| `erplora-wasm-host` | **Tier 2**: ejecuta handlers WASM en sandbox (Extism), devuelve *intenciones*. | ✅ implementado |
| `erplora-sync` | Cliente de eventos en vivo (consume `/ws`) con reconexión + backoff. | ✅ implementado |
| `erplora-peripherals` | Hardware POS red-only (ESC/POS, cajón, discovery, cola/reintentos) — ver [`peripherals/README.md`](peripherals/README.md). | ✅ implementado |
| `erplora-verifactu` | Lógica fiscal VeriFactu (encadenado, XML, hashing). | ✅ implementado |
| `tauri-plugin-erplora-android` | Plugin Tauri para Android: permisos de runtime en contexto (`ACCESS_LOCAL_NETWORK`, `POST_NOTIFICATIONS`) y el Kotlin que Rust no alcanza (ADR-0180 §2). | ✅ implementado |

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

- **Transportes reales**: inyectar reqwest en `cloud-client`/`source`/`installer`; cliente WS
  real (tungstenite) en `erplora-sync`.
- **Auth server-side real**: validar JWT/`X-Hub-Token` contra el SaaS (hoy lee cabeceras en dev).

## Notas de diseño

- **Parámetros del sistema** inyectados en cada query/command (no falsificables desde la UI):
  `:hub_id`, `:current_user_id`, `:now`, `:new_id` (§2.5, §2.9).
- **Migraciones** idempotentes por módulo/fichero (`_hub_migrations`), dialecto `postgres`.
- **Hot-plug**: solo los módulos ACTIVOS exponen menú/queries/commands/listeners.
- **Transportes inyectables** (sin red en tests): `Fetcher`/`Transport`/`EventStream` se
  implementan con reqwest/tungstenite en los binarios; en tests van mocks.
