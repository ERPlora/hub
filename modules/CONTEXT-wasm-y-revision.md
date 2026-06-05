# Contexto de arranque — Implementación de handlers WASM (Tier 2) + revisión por módulo

> Documento de **handoff** para continuar en un chat nuevo. Es autocontenido: explica el estado,
> la arquitectura mínima, el patrón exacto para implementar un handler y el plan de trabajo.
> Acompaña a [`todo.md`](todo.md) (checklist de los 323 handlers) y a los `*/WASM-TODO.md` por módulo.

---

## Regla de trabajo (VINCULANTE, 2026-06-02)

El **humano** escribe: arquitectura, interfaces/traits, `module.json`, flujo de instalación,
permisos, modelo de comandos, decisiones SQLite/Postgres, naming y estructura. **La IA** escribe:
boilerplate, validaciones, documentación, ejemplos, refactors pequeños, conversión de ideas a
código repetitivo, plumbing de errores/`Result`/`serde`/`sqlx`. **Tests: solo si el humano los pide.**
Si una tarea toca una decisión de la columna del humano → preguntar, no decidir. Excepciones solo
si se piden explícitamente.

## 0. Objetivo de este hilo

1. **Implementar los handlers Rust→WASM (Tier 2)** que cada módulo declara como
   `command.handler = {type:"wasm"}` y documenta en su `WASM-TODO.md` (lógica no-CRUD:
   cálculo fiscal, batch de líneas, contadores atómicos, motores de pricing/descuento,
   integraciones, etc.). Hay **323 pendientes** (ver `todo.md`).
2. **Revisar cada módulo** para verificar que su **Tier 0 (CRUD declarativo)** corre verde
   en el runtime — la migración dejó el contrato + SQL + UI, pero los 94 módulos nuevos
   **nunca se han ejecutado** contra el runtime (solo compilan y siguen el patrón).

---

## 1. Qué es hub-next (lo mínimo para situarse)

Próxima generación del Hub de ERPlora: **runtime en Rust** que ejecuta **módulos declarativos**.
Lee primero `hub-next/ARQUITECTURA.md` (fuente de verdad, en español) y `hub-next/CLAUDE.md`.

**Principio rector:** el **90% de la lógica vive en Rust** (el runtime es la autoridad).
Flujo: **Web Component (Stencil) → SDK (`query`/`command`/`on`) → Rust**. El WC **nunca toca la BD**;
Rust valida permiso + `hub_id` (tenant) + payload y ejecuta. `hasPermission()` de la UI es solo
mostrar/ocultar; Rust revalida.

**Capas de poder (ARQUITECTURA.md §5.3):**
- **Tier 0** — SQL declarativo (CRUD). Lo ejecuta el runtime directamente. **Ya funciona.**
- **Tier 2** — **WASM (Extism)** para lógica real. **El WASM NUNCA toca la BD**: recibe un `Input`
  (payload + filas que el host le pasa) y devuelve un `Output` con **intenciones** (operaciones SQL
  referenciadas por nombre de command + params, y eventos a emitir) que **el host Rust valida y
  persiste en transacción**. ← **esto es lo que falta implementar.**

**Tenancy (§2.5):** BD compartida por **organización**, discriminada por `hub_id` por fila. El
runtime auto-inyecta `hub_id` + contrato de fila (soft-delete `is_deleted`/`deleted_at`, audit
`created_by`/`created_at`/`updated_by`/`updated_at`). El autor del módulo NO filtra `hub_id` a mano.

**Instalación de un módulo** (`crates/runtime/src/installer.rs`): registra estado en la tabla
**`hub_module`**, aplica las migraciones del módulo (crea sus tablas) registrándolas en
**`_hub_migrations`**, y carga capacidades (queries/commands/permisos/nav/bytes WASM) en un
**`Registry` en memoria** leyendo los ficheros. Tests E2E reales: `crates/runtime/tests/*_e2e.rs`.

---

## 2. Estado actual (verificado 2026-06-02)

- **99 módulos** en `hub-next/modules/`. Migración legacy `old_modules/m_*` → hub-next COMPLETA
  (6 oleadas). Fuera quedan `m_products` (cubierto por `inventory`) y `m_pos` (vista de `sales`).
- **UI: 99/99 compilan y empaquetan** — `cd packages/module-stencil && node build-all.mjs`
  (Stencil + esbuild → `modules/<id>/dist/<id>.esm.js`). build-all empaqueta **todas** las vistas
  de `navigation[]` (ya arreglado; antes solo la 1ª → nav muerta).
- **Contrato:** 460 queries (todas Tier 0) + 829 commands → **495 SQL Tier 0** (59%) + **334 WASM**.
- **Handlers WASM implementados (Rust real): 11**, en los 5 módulos POS
  (`inventory`, `customers`, `sales`, `invoice`, `cash_register`). **Pendientes: 323.**
- **Sin verificar:** los 94 módulos nuevos **no se han ejecutado** contra el runtime (Tier 0 incluido).

### Estructura de un módulo migrado
```
modules/<id>/
  module.json                 # manifest declarativo (permisos, nav, queries, commands, events, ui.entry)
  migrations/sqlite/001_init.sql
  queries/*.sql               # Tier 0 lectura
  commands/*.sql              # Tier 0 escritura (algunos commands son handler WASM en vez de sql)
  schemas/*.json              # JSON Schema de payloads/params
  ui/components/<tag>/<tag>.tsx  # Web Component Stencil (usa <data-table> + Ionic)
  WASM-TODO.md                # ← spec de los handlers Tier 2 a implementar
  package.json                # @stencil/core
  dist/<id>.esm.js            # build UI (generado)
  handler/                    # ← SOLO en módulos con WASM ya implementado (los 5 POS); falta crearlo en el resto
    Cargo.toml
    src/lib.rs
  dist/handler.wasm           # ← generado al compilar el handler (falta en los 94)
```

---

## 3. Cómo implementar un handler WASM (patrón EXACTO)

**Plantilla viva:** `modules/inventory/handler/` (+ `customers`/`sales`/`invoice`/`cash_register`).
Cópialos como referencia. Contrato host↔guest: `crates/guest-sdk/src/lib.rs`
(`Input`, `Output`, `Operation`, `Event`). Host que invoca: `crates/wasm-host/src/lib.rs`.
Test de referencia Tier 2: `crates/runtime/tests/wasm_tier2.rs`.

**`modules/<id>/handler/Cargo.toml`** (crate cdylib desacoplado del workspace):
```toml
[package]
name = "<id>-handler"
version = "0.1.0"
edition = "2021"
[lib]
crate-type = ["cdylib", "rlib"]
[features]
guest = ["dep:extism-pdk"]
[dependencies]
erplora-guest-sdk = { path = "../../../crates/guest-sdk" }
extism-pdk = { version = "1", optional = true }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
[profile.release]
opt-level = "s"   # sin lto/strip: rompen los wrappers de export de extism-pdk
[workspace]       # vacío: desacopla del workspace raíz
```

**`modules/<id>/handler/src/lib.rs`** (lógica PURA, sin BD; devuelve intenciones):
```rust
use erplora_guest_sdk::{Operation, Output, Input};
use serde_json::{json, Map, Value};
#[cfg(feature = "guest")]
use extism_pdk::*;

#[cfg(feature = "guest")]
#[plugin_fn]
pub fn <function>(input: Json<Input>) -> FnResult<Json<Output>> {
    Ok(Json(<function>_pure(input.into_inner().into_value())))
}

// Función pura testeable en target nativo (sin extism):
fn <function>_pure(v: Value) -> Output {
    // v = { payload, context }. context.new_ids = ids que reparte el host (autoridad de ids).
    // Lógica: validar, calcular (decimal HALF_UP), construir N Operation::sql(<command>, params).
    Output::new()
        .with_operation(Operation::sql("<id>._insert_xxx", { /* Map params */ }))
        // .with_event(Event::new("<id>.xxx", json!({...})))
}
```
Reglas:
- El guest **no** lee la BD: el host pasa en `context` lo que haya leído (filas, contadores) y los
  `new_ids`. El guest reparte ids y emite operaciones por nombre de command **del mismo módulo**.
- **Cross-módulo prohibido**: nada de tocar tablas de otro módulo; usar eventos/contratos públicos.
- **Aritmética decimal de precisión fija, redondeo HALF_UP** (paridad SQLite↔Postgres).
- El **detalle funcional de cada handler está en `modules/<id>/WASM-TODO.md`** — leerlo SIEMPRE antes.

**Build del handler:**
```
cd modules/<id>/handler
cargo build --target wasm32-unknown-unknown --release --features guest
# copiar target/wasm32-unknown-unknown/release/<id>_handler.wasm → modules/<id>/dist/handler.wasm
```
(El `packages/module-cli/src/build.mjs` automatiza parte de esto; revisar cómo lo hacen los 5 POS.)

---

## 4. Comandos útiles

```bash
# UI de todos los módulos (Stencil + esbuild):
cd hub-next/packages/module-stencil && node build-all.mjs [<id>...]

# Tests del runtime (incluye E2E de install + Tier0 + wasm_tier2):
cd hub-next && cargo test -p erplora-runtime

# Compilar un handler WASM a wasm32:
cd hub-next/modules/<id>/handler && cargo build --target wasm32-unknown-unknown --release --features guest
```

---

## 5. Reglas duras (lecciones de la migración — NO romper)

- **Tags** de custom elements: minúsculas con **guiones**, nunca guion bajo
  (`credit_notes` → tag `erp-credit-notes-list`). El `@Component` tag == carpeta/archivo ==
  `module.json navigation[].component`. El `data-table` compartido vive en
  `modules/_shared/ui/components/data-table/data-table.tsx` (tag `<data-table>`, sin prefijo `erp-`).
- **Cross-módulo prohibido**: un módulo solo lee/escribe **sus** tablas; lo demás vía
  queries/commands públicos o eventos. (`orders` se rehízo por violar esto.)
- Todo `schema` referenciado en `module.json` debe existir; sin entradas de `navigation` muertas.
- Los 5 POS llevan handler Rust real → **no** tienen WASM-TODO.md (es correcto). El resto sí.

---

## 6. Plan de trabajo sugerido para este hilo

**Fase A — Verificar Tier 0 de los 94 nuevos (antes de WASM).**
Montar un smoke-test que, por módulo: cargue `module.json`, aplique `migrations/` a un SQLite en
memoria vía el runtime (`install_from_dir`) y ejecute cada query + cada command **SQL Tier 0**
con params de ejemplo. Devuelve la lista de módulos que corren verdes y los desajustes (binds,
columnas, schema). Patrón: como `crates/runtime/tests/inventory_e2e.rs`. Se puede paralelizar con workers.

**Fase B — Implementar los handlers WASM por dominio** (usar `todo.md` + cada `WASM-TODO.md`):
orden sugerido por valor/uso: Retail/POS (56) → Inventario/Logística (57) → Finanzas/Fiscal (90)
→ CRM (46) → RRHH/Ops (47) → AI/Analítica (27). Por handler: leer su WASM-TODO, escribir la
función pura + export extism, test nativo de la función pura, compilar a wasm, E2E en el runtime.
Ojo módulos críticos de cumplimiento (`verifactu`, `payroll`): valorar plugin nativo Rust estático
en vez de WASM (escape hatch, ARQUITECTURA.md §5.3).

**Fase C — Revisión por módulo**: contrato vs legacy (`old_modules/m_<id>`), permisos, eventos
cruzados, UI, y que migración E2E (install → query → command → evento) pase.

> 2 módulos (`accounting`, `collections`) tienen **todas** sus escrituras en WASM → quedan de
> solo-lectura hasta que se implementen sus handlers; priorizar si se necesitan operativos.

---

## 7. Referencias clave (paths)

- Checklist accionable: `modules/todo.md`
- Spec por módulo: `modules/<id>/WASM-TODO.md`
- Plantilla handler: `modules/inventory/handler/` (+ customers/sales/invoice/cash_register)
- Contrato host↔guest: `crates/guest-sdk/src/lib.rs` · host: `crates/wasm-host/src/lib.rs`
- Runtime + install + tests: `crates/runtime/src/{installer,migrations,registry,commands}.rs`,
  `crates/runtime/tests/*_e2e.rs`, `crates/runtime/tests/wasm_tier2.rs`
- Build UI: `packages/module-stencil/build-all.mjs` · DataTable: `modules/_shared/ui/components/data-table/`
- Arquitectura: `hub-next/ARQUITECTURA.md` (§1, §2.2/§2.5, §4, §5.3, §7.3), `hub-next/CLAUDE.md`
- Workflows guardados (sesión anterior): `migrate-wave-full` (editar const `WAVE`+`ALREADY` por oleada;
  ⚠️ pasar `args` vía `scriptPath` NO se aplica — editar la const).
