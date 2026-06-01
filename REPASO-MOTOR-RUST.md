# Repaso del motor Rust de hub-next (tracker de estudio)

Documento vivo para recorrer **todo el Rust de `crates/`** en orden, un fichero a la
vez: un concepto → lo entiendo → lo probamos → siguiente. Lo escribe Ioan; el asistente
explica y marca progreso. Marca `[x]` cuando un fichero queda entendido y probado.

> Estado verificado contra el repo (2026-06-01): workspace compila, **95/95 tests verdes**,
> 0 fallos (2 `ignored` = Extism real). El `README.md`/`CLAUDE.md` de hub-next están
> **desfasados** (dicen "Rust sin compilar" y "Lit"): la fuente de verdad es el código.

---

## Idea clave (no perderse)

**El runtime Rust NO tiene lógica de negocio.** Es un *despachador genérico*: lee
`module.json`, registra capacidades (queries/commands/eventos/menú) y ejecuta **SQL
declarativo** (Tier 0/1) o **WASM** (Tier 2). No hay un solo `if module == "inventory"`
en `crates/`. Toda la lógica de inventory/sales/… vive en `modules/<id>/`, no en el motor.

Consecuencia para el orden de lectura: **contrato de datos → registro → despacho →
transporte HTTP → WASM**. Primero entender *qué es un módulo* y *cómo se guardan datos*,
luego *cómo se registran y despachan* sus capacidades, luego *cómo se exponen por HTTP/WS*,
y al final la *lógica compleja* (WASM).

## Decisiones de contexto (fijadas con Ioan)

- **UI = Stencil** (migrando desde Lit). Razón: escala mejor a módulos grandes.
  **Cada módulo es una mini-aplicación frontend completa**, equivalente a una *app de
  Django*: su propio dominio, sus tablas, sus vistas. Nada se renderiza en backend.
- **DataTable = componente principal y reutilizable del Hub.** Existe ya como componente
  React; es la pieza central de casi toda pantalla de módulo. Debe ser un componente
  compartido (no uno por módulo) y la base de la UI declarativa.
- **Eventos en vivo por defecto.** La mayoría de cosas serán eventos live (WS); solo
  algunas operaciones que de verdad no lo necesiten quedarán fuera. Se decide caso a caso.
- **90% de la lógica en Rust** (runtime = autoridad). WASM (Tier 2) solo para batch con
  line-items (sale_lines, bulk_create, receive_stock) y reglas fiscales.

---

## Checklist de lectura

### Fase A — el suelo (qué es un módulo y cómo se guardan datos)
- [ ] **A1.** `crates/runtime/src/manifest.rs` (115) — forma de `module.json` en Rust:
      `Manifest`, `QueryDef`, `CommandDef`, `Nav`, `WasmHandler`, `Events`. + repasar
      **cada línea** cruzándola con `modules/inventory/module.json`.
- [ ] **A2.** `crates/db/src/lib.rs` (610) — trait `DatabaseAdapter` (`query`/`execute`/
      `execute_tx`), `SqliteAdapter`, binding de `:params`, row contract (hub_id, soft-delete,
      audit). Cruzar con `modules/inventory/migrations/sqlite/001_init.sql`.

### Fase B — el corazón (registro + despacho)
- [ ] **B3.** `crates/runtime/src/registry.rs` (167) — `Registry`, `ModuleStatus`
      (Active/Inactive = hot-plug), `RequestContext`, `EventSink`. `get_query`/`get_command`
      filtran por módulo activo.
- [ ] **B4.** `crates/runtime/src/permissions.rs` (13) — el gate (`*` o permiso exacto).
- [ ] **B5.** `crates/runtime/src/queries.rs` (23) — camino de lectura.
- [ ] **B6.** `crates/runtime/src/commands.rs` (257) — **el más importante**: camino de
      escritura Tier 0/1 (SQL+tx+emit) y Tier 2 (WASM→intenciones→tx), `validate_operation`,
      `MAX_EVENT_DEPTH`, `NEW_IDS_BATCH`.
- [ ] **B7.** `crates/runtime/src/events.rs` (26) — bus en proceso: EventSink (→WS) +
      ejecuta listeners de módulos activos (cadena `sale.completed → …`).
- [ ] **B8.** `crates/runtime/src/lib.rs` (122) — fachada `Runtime` + `system_params`
      (inyecta hub_id/current_user_id/now/new_id, no falsificables).
- [ ] **B8b.** `crates/runtime/src/errors.rs` (28) — `RuntimeError` (mapeo a códigos HTTP).

### Fase C — instalación / ciclo de vida (hot-plug)
- [ ] **C9.** `crates/runtime/src/installer.rs` (138) — install / set_status / uninstall.
- [ ] **C10.** `crates/runtime/src/migrations.rs` (63) — aplicar migraciones por dialecto.
- [ ] **C11.** `crates/runtime/src/loader.rs` (10) — carga de SQL de disco.
- [ ] **C11b.** `crates/runtime/src/ui.rs` (3) + `wasm.rs` (11) — stubs/punteros.

### Fase D — el transporte (lo que arrancas y llamas)
- [ ] **D12.** `crates/server/src/main.rs` (35) — binario + env vars + auto-install.
- [ ] **D13.** `crates/server/src/state.rs` (44) — `AppState`, `Mutex<Runtime>`,
      `BroadcastSink` → WS.
- [ ] **D14.** `crates/server/src/auth.rs` (23) — `RequestContext` desde headers.
- [ ] **D15.** `crates/server/src/lib.rs` (172) — router Axum + handlers.

### Fase E — Tier 2 y puente con el Cloud (más adelante)
- [ ] **E16.** `crates/wasm-host/src/lib.rs` (245) — Extism: `WasmHost`, `Operation`, `Output`.
- [ ] **E17.** `crates/guest-sdk/src/lib.rs` (258) — contrato guest (lo que usa el handler).
- [ ] **E18.** `crates/source/src/lib.rs` (405) — descarga/extracción del zip de módulo.
- [ ] **E19.** `crates/installer/src/lib.rs` (426) — verify SHA256, topo-sort deps, instala.
- [ ] **E20.** `crates/cloud-client/src/lib.rs` (158) + `integrity.rs` (38) — handshake Cloud.
- [ ] **E21.** `crates/sync/src/lib.rs` (472) — sincronización.
- [ ] **E22.** `crates/vector/src/lib.rs` (385) — base vectorial / RAG (degradación local).

---

## Cómo arrancar y probar (referencia)

```bash
cd /Users/ioan.beilic/workspace/code/ERPlora/hub-next
rm -f /tmp/erplora-dev.db
HUB_SQLITE_PATH=/tmp/erplora-dev.db \
HUB_MODULES_DIR=$PWD/modules \
HUB_BIND=127.0.0.1:8787 \
cargo run -p erplora-server
```

```bash
curl -s localhost:8787/api/modules | jq
curl -s -X POST localhost:8787/api/command -H 'content-type: application/json' \
  -H 'x-hub-id: demo' -H 'x-user-id: ioan' \
  -d '{"name":"inventory.products.create","payload":{"name":"Café 1kg","price":12.5,"sku":"CAF-1","stock":20}}' | jq
curl -s -X POST localhost:8787/api/query -H 'content-type: application/json' -H 'x-hub-id: demo' \
  -d '{"name":"inventory.products.list","params":{}}' | jq
# eventos en vivo:  websocat ws://localhost:8787/ws
```

Tests: `cargo test --workspace`.

---

## Flujo de una request (verificado en código)

```
POST /api/command {name, payload}
  └─ server/lib.rs:145 command()
       ├─ auth::context_from_headers → RequestContext{hub_id,user_id,perms}  (auth.rs:12)
       ├─ st.runtime.lock()                                                  (state.rs)
       └─ Runtime::execute_command                                          (lib.rs:97)
            └─ commands::execute_at                                         (commands.rs:33)
                 ├─ registry.get_command → ¿módulo ACTIVO? si no → 404      (registry.rs:83)
                 ├─ permissions::check                                       (permissions.rs:7)
                 ├─ system_params → inyecta hub_id/now/new_id                (lib.rs:115)
                 ├─ SQL: db.execute_tx  ── O ──  Tier 2 WASM → validate → tx (commands.rs)
                 └─ por cada emit: events::dispatch                          (events.rs:10)
                       ├─ event_sink.emit → broadcast → WS /ws               (state.rs:22)
                       └─ listeners_for → execute_at (recursivo, depth+1)
```

---

## Notas por fichero (se rellenan al repasar)

### A1 · manifest.rs — (en curso)
_Ver explicación en el chat; resumen al cerrar el repaso._
</content>
</invoke>
