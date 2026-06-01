# crates/ — runtime Rust de hub-next

Workspace Cargo. El **runtime es la autoridad** (ARQUITECTURA.md §4): valida permisos,
tenant (`hub_id`) y payload, y ejecuta queries/commands declarados por los módulos. Rust
no tiene lógica de negocio hardcodeada.

> ✅ **`cargo test --workspace` → 62 tests verdes, 0 warnings.** Todo compila. El server
> arranca y responde por HTTP real; el flujo de instalación E2E (Cloud→descarga→runtime) y
> el hot-plug (install/activate/deactivate/uninstall) están probados.

## Estado

| Crate | Qué es | Estado |
|-------|--------|--------|
| `erplora-db` | `DatabaseAdapter` + **SQLite** (rusqlite) + **Postgres** (feature `postgres`, traductor `:n`→`$n`). | ✅ 8 tests |
| `erplora-runtime` | Host genérico: manifest → migraciones → permisos → query/command/eventos (scope `hub_id`) + ciclo de vida (estado en `hub_module`). | ✅ 10 tests + ejemplo |
| `erplora-server` | **Axum**: query/command, navigation, gestión de módulos, `/ws`, `/healthz`. | ✅ 5 tests + binario |
| `erplora-cloud-client` | Cliente del Cloud Portal: auth (X-Hub-Token/JWT/webhook), marketplace, **SHA256**. | ✅ 4 tests |
| `erplora-source` | Descarga `module.zip` (S3, fetcher inyectable) + verifica SHA256 + descomprime (anti zip-slip) + cache. | ✅ 6 tests |
| `erplora-installer` | **Flujo E2E**: grant(Cloud) → descarga/verifica(source) → instala(runtime). | ✅ 3 tests |
| `erplora-vector` | `VectorStore` para RAG local (embeddings en SQLite + coseno). | ✅ 7 tests |
| `erplora-guest-sdk` | Contrato host↔guest WASM (Input/Operation/Event/Output) para autores de plugins. | ✅ 6 tests |
| `erplora-wasm-host` | **Tier 2**: ejecuta handlers WASM en sandbox (Extism), devuelve *intenciones*. | ✅ 6 tests |
| `erplora-sync` | Cliente de eventos en vivo (consume `/ws`) con reconexión + backoff. | ✅ 7 tests |

## Probarlo

```sh
cargo test  --workspace                                   # 62 tests verdes
cargo run   -p erplora-runtime --example walking_skeleton # demo runtime end-to-end
cargo build -p erplora-db --features postgres             # compila el backend Postgres

# server real (HTTP) + hot-plug:
HUB_SQLITE_PATH=/tmp/hub.db HUB_BIND=127.0.0.1:8799 cargo run -p erplora-server &
curl -s localhost:8799/api/modules
curl -s -X POST localhost:8799/api/modules/install -H 'content-type: application/json' -d '{"dir":"modules/notes"}'
curl -s localhost:8799/api/navigation
curl -s -X POST localhost:8799/api/modules/notes/deactivate
# demo visual del grid "Mis módulos":
node demos/hotplug/run.mjs
```

## Pendiente

- **Wire Tier 2 en el runtime**: que `execute_command` invoque `erplora-wasm-host` cuando el
  manifest declare `handler: { type: "wasm", ... }` (hoy el runtime devuelve `NotImplemented`
  para commands sin SQL). El host y el contrato ya existen; falta el cableado + el campo
  `handler` en el manifest y validar las *intenciones* contra commands permitidos.
- **`apps/tauri`**: `invoke` → el mismo `runtime` (modo local).
- **Transportes reales**: inyectar reqwest en `cloud-client`/`source`/`installer`; cliente WS
  real (tungstenite) en `erplora-sync`.
- **Auth server-side real**: validar JWT/`X-Hub-Token` contra el Cloud (hoy lee cabeceras en dev).

## Notas de diseño

- **Parámetros del sistema** inyectados en cada query/command (no falsificables desde la UI):
  `:hub_id`, `:current_user_id`, `:now`, `:new_id` (§2.5, §2.9).
- **Migraciones** idempotentes por módulo/fichero (`_hub_migrations`), por dialecto.
- **Hot-plug**: solo los módulos ACTIVOS exponen menú/queries/commands/listeners.
- **Transportes inyectables** (sin red en tests): `Fetcher`/`Transport`/`EventStream` se
  implementan con reqwest/tungstenite en los binarios; en tests van mocks.
