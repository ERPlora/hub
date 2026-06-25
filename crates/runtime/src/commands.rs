//! Ejecución de commands declarativos (mutaciones) + emisión de eventos. ARQUITECTURA.md §4.
//! Tier 0/1 (SQL declarativo), Tier 2 (handler WASM vía `erplora-wasm-host`, §5.3 / §9.2)
//! y plugins **nativos first-party** (ADR-0009, `native.rs`).
use erplora_db::{DatabaseAdapter, Params};
use erplora_wasm_host::{Operation, Output, WasmHost};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::events;
use crate::outbox;
use crate::permissions;
use crate::registry::{RegisteredCommand, Registry, RequestContext};

/// Profundidad máxima de cascada de eventos (evita bucles de listeners).
pub(crate) const MAX_EVENT_DEPTH: u32 = 16;

/// Cantidad de UUIDs pre-generados que el host pasa al handler WASM en
/// `context.new_ids`, para correlacionar filas padre→hijo (p.ej. 1 venta + sus
/// líneas). Suficiente para un ticket grande; un handler que necesite más debe
/// dividir la operación. ARQUITECTURA.md §5.3.
pub(crate) const NEW_IDS_BATCH: usize = 256;

/// Ejecuta `name(payload)` con el contexto dado. Aplica permiso, ejecuta el SQL **y persiste
/// los eventos emitidos en el outbox dentro de la MISMA transacción** (entrega at-least-once
/// asíncrona; los listeners los corre el relay, ver `outbox.rs`). ARQUITECTURA.md §4/§5.4.
pub async fn execute(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
) -> Result<Json> {
    execute_at(db, registry, name, payload, ctx, 0, &[]).await
}

/// Como [`execute`] pero a profundidad `depth` (cascada) y con `extra_ops` añadidos a la
/// transacción del command. El relay usa `extra_ops` para insertar el marcador de entrega
/// (`_event_delivery`) atómicamente con los efectos del listener (idempotencia, §5.4).
pub(crate) async fn execute_at(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    extra_ops: &[(String, Params)],
) -> Result<Json> {
    if depth > MAX_EVENT_DEPTH {
        return Err(RuntimeError::EventLoop);
    }

    // Identidad de NEGOCIO GLOBAL del hub (fuente única país-agnóstica, `hub_settings` — ADR-0061) →
    // contexto, una sola vez en la raíz (depth 0). Así `system_params` la expone como
    // `:business_tax_id`/`:business_legal_name`/`:business_address` a todo el SQL del comando (p.ej.
    // invoice resuelve el emisor sin que el caller lo pase). En cascadas (depth>0) el ctx ya viene
    // enriquecido. Degrada a vacío si los settings fallan.
    // FIX QA (2026-06-25): la condición original `depth == 0` dejaba SIN enriquecer las commands
    // entregadas por el relay del Outbox (listeners de eventos), que corren a depth>0 con un ctx
    // RECONSTRUIDO (reconstruct_ctx) cuyo business_tax_id está vacío. El caso real: `sale.completed`
    // (depth 1) → `invoice.create_from_sale` (listener, depth 1) generaba facturas con issuer_nif
    // vacío → VeriFactu (`ingest_invoice`) no-op (no encadena, 0 registros, 0 QR). Enriquecemos
    // SIEMPRE que falte la identidad fiscal (la cascada con ctx ya enriquecido salta el get_all).
    let enriched_ctx;
    let ctx = if ctx.business_tax_id.is_empty() {
        let f = crate::settings::get_all(db, &ctx.hub_id).await.unwrap_or(Json::Null);
        let get = |k: &str| f.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
        enriched_ctx = ctx.clone().with_business(
            get("business_tax_id"),
            get("business_legal_name"),
            get("business_address"),
        );
        &enriched_ctx
    } else {
        ctx
    };

    let cmd = registry
        .get_command(name)
        .ok_or_else(|| RuntimeError::CommandNotFound(name.to_string()))?;

    // El handler corre bajo el permiso del command que lo invoca (no re-eleva).
    permissions::check(ctx, &cmd.def.permission)?;

    // Validación del payload contra el JSON Schema declarado (compilado al instalar y
    // cacheado en el Registry): rechaza ANTES de tocar la BD o invocar handlers (hub#27).
    // Tras validar, inyectamos los `default` del schema en las claves AUSENTES (causa raíz,
    // decision-log 2026-06-25): así un campo opcional con `default` omitido por el caller llega
    // bindeado con su valor por defecto y el SQL no peta con `NOT NULL constraint failed` — hace
    // redundante (no obsoleto) el COALESCE por-módulo. Solo claves ausentes; un valor aportado
    // (incl. `null` explícito) nunca se sobreescribe. `payload` pasa a ser el payload "defaulteado"
    // para TODOS los tiers de abajo (SQL declarativo, WASM, nativo), que bindean por nombre.
    let defaulted;
    let payload = if let Some(schema) = &cmd.schema {
        schema
            .validate(&Json::Object(payload.clone()))
            .map_err(|detail| RuntimeError::InvalidPayload { name: name.to_string(), detail })?;
        let mut p = payload.clone();
        schema.apply_defaults(&mut p);
        defaulted = p;
        &defaulted
    } else {
        payload
    };

    // ── Plugin nativo first-party (ADR-0009) ────────────────────────────────
    if let Some(handler) = &cmd.def.handler {
        if handler.kind == "native" {
            return execute_native(db, registry, cmd, payload, ctx, depth, extra_ops).await;
        }
    }

    // ── Tier 2: handler WASM ────────────────────────────────────────────────
    if let Some(bytes) = &cmd.wasm {
        return execute_wasm(db, registry, cmd, payload, ctx, depth, bytes, extra_ops).await;
    }

    // ── Tier 0/1: SQL declarativo ───────────────────────────────────────────
    if cmd.sql.is_empty() {
        // Sin SQL ni WASM: no hay nada que ejecutar.
        return Err(RuntimeError::NotImplemented("command sin SQL ni handler WASM"));
    }

    let bound = crate::system_params(payload, ctx);

    // SQL del command + INSERT en `_event_outbox` por cada evento emitido + `extra_ops` →
    // UNA transacción. Si commitea, los eventos quedan persistidos; si revierte, no hay evento.
    // (Decisión del humano #3: los commands `transaction:false` también se envuelven en tx para
    // garantizar la escritura atómica del outbox.)
    let mut ops: Vec<(String, Params)> =
        cmd.sql.iter().map(|sql| (sql.clone(), bound.clone())).collect();
    for event in &cmd.def.emit {
        ops.push(outbox::insert_op(ctx, event, &bound, depth + 1));
    }
    ops.extend_from_slice(extra_ops);
    db.execute_tx(&ops).await?;

    // Notificación al WS (UI en vivo), tras commit y solo si commiteó. Efímera; la entrega
    // durable a listeners la hace el relay desde el outbox.
    for event in &cmd.def.emit {
        events::notify_sink(registry, event, &bound);
    }

    Ok(json!({ "ok": true }))
}

/// Ejecuta un command Tier 2: invoca el handler WASM, valida cada intención y
/// aplica todas las operaciones + el `emit` del command en una sola transacción.
async fn execute_wasm(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    bytes: &[u8],
    extra_ops: &[(String, Params)],
) -> Result<Json> {
    let handler = cmd
        .def
        .handler
        .as_ref()
        .ok_or_else(|| RuntimeError::Wasm("command con bytes wasm pero sin handler".to_string()))?;

    // Input del guest: { "payload": <params del caller con system_params>, "context": {...} }.
    // Reutilizamos system_params para inyectar hub_id/current_user_id/now/new_id, no falsificables.
    let bound_payload = crate::system_params(payload, ctx);
    // Lote de UUIDs pre-generados por el host para que el handler correlacione filas
    // padre→hijo (p.ej. 1 venta + N líneas que referencian el id de la venta). El guest
    // no puede generar UUIDs (sandbox sin aleatoriedad), así que toma ids de `new_ids`.
    // El host es la única autoridad de ids — el guest solo los reparte (§5.3).
    let new_ids: Vec<Json> = (0..NEW_IDS_BATCH)
        .map(|_| Json::String(crate::registry::new_id()))
        .collect();
    let input = json!({
        "payload": Json::Object(bound_payload),
        "context": {
            "hub_id": ctx.hub_id,
            "current_user_id": ctx.user_id,
            "now": crate::registry::now_rfc3339(),
            "new_ids": new_ids,
        },
    });

    let mut host = WasmHost::from_bytes(bytes).map_err(|e| RuntimeError::Wasm(e.to_string()))?;
    let output = host
        .call(&handler.function, &input)
        .map_err(|e| RuntimeError::Wasm(e.to_string()))?;

    persist_handler_output(db, registry, cmd, payload, ctx, depth, extra_ops, &output).await
}

/// Ejecuta un command de **plugin nativo first-party** (ADR-0009): mismo contrato de
/// intenciones que el WASM, pero la función vive en un crate horneado en el runtime
/// (registrado vía [`crate::Runtime::register_native`]) con acceso pleno a red/cripto y
/// lecturas mediadas (`native::NativeHost`, solo SELECT).
async fn execute_native(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    extra_ops: &[(String, Params)],
) -> Result<Json> {
    let handler = cmd.def.handler.as_ref().ok_or_else(|| {
        RuntimeError::Native("command nativo sin bloque handler".to_string())
    })?;
    let engine = registry.native.get(&cmd.module_id).ok_or_else(|| {
        RuntimeError::Native(format!(
            "plugin nativo del módulo `{}` no registrado en este runtime",
            cmd.module_id
        ))
    })?;

    // Mismo input que el WASM: payload con system_params + contexto con lote de ids.
    let bound_payload = crate::system_params(payload, ctx);
    let new_ids: Vec<Json> = (0..NEW_IDS_BATCH)
        .map(|_| Json::String(crate::registry::new_id()))
        .collect();
    let input = json!({
        "payload": Json::Object(bound_payload),
        "context": {
            "hub_id": ctx.hub_id,
            "current_user_id": ctx.user_id,
            "now": crate::registry::now_rfc3339(),
            "new_ids": new_ids,
        },
    });

    let host = crate::native::DbHost { db };
    let output = engine.call(&handler.function, &input, &host).await?;

    persist_handler_output(db, registry, cmd, payload, ctx, depth, extra_ops, &output).await
}

/// Persiste el [`Output`] de un handler (WASM o nativo): valida cada intención contra los
/// commands SQL del MISMO módulo y aplica intenciones + outbox (`emit` declarado + eventos
/// del handler) + `extra_ops` en UNA transacción; notifica al WS tras el commit.
#[allow(clippy::too_many_arguments)]
async fn persist_handler_output(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    extra_ops: &[(String, Params)],
    output: &Output,
) -> Result<Json> {
    // Valida + resuelve cada operación a su(s) SQL contra los commands del MISMO módulo.
    let mut tx_ops: Vec<(String, Params)> = Vec::new();
    for op in &output.operations {
        let sqls = validate_operation(registry, &cmd.module_id, op)?;
        let bound = crate::system_params(&op.params, ctx);
        for sql in sqls {
            tx_ops.push((sql, bound.clone()));
        }
    }

    // Las intenciones + los INSERT de outbox (eventos declarados por el command + eventos
    // devueltos por el handler) + `extra_ops` (marcador de entrega del relay) → UNA transacción.
    let declared_payload = crate::system_params(payload, ctx);
    for event in &cmd.def.emit {
        tx_ops.push(outbox::insert_op(ctx, event, &declared_payload, depth + 1));
    }
    let handler_events: Vec<(String, Params)> = output
        .events
        .iter()
        .map(|ev| {
            let payload = match &ev.payload {
                Json::Object(map) => map.clone(),
                other => {
                    let mut m = Params::new();
                    m.insert("value".into(), other.clone());
                    m
                }
            };
            (ev.name.clone(), payload)
        })
        .collect();
    for (name, payload) in &handler_events {
        tx_ops.push(outbox::insert_op(ctx, name, payload, depth + 1));
    }
    tx_ops.extend_from_slice(extra_ops);
    db.execute_tx(&tx_ops).await?;

    // Notificación al WS (UI en vivo) tras commit; entrega durable a listeners = relay.
    for event in &cmd.def.emit {
        events::notify_sink(registry, event, &declared_payload);
    }
    for (name, payload) in &handler_events {
        events::notify_sink(registry, name, payload);
    }

    Ok(json!({ "ok": true, "operations": output.operations.len() }))
}

/// Valida una intención del handler y la resuelve a su(s) SQL.
///
/// Reglas (ARQUITECTURA.md §5.3): el `command` referenciado debe (1) ser de tipo
/// `"sql"`, (2) existir en el registry, (3) pertenecer al **mismo módulo** que el
/// handler (`handler_module_id`). En otro caso se rechaza y la transacción no se aplica.
pub(crate) fn validate_operation(
    registry: &Registry,
    handler_module_id: &str,
    op: &Operation,
) -> Result<Vec<String>> {
    if op.kind != "sql" {
        return Err(RuntimeError::Wasm(format!(
            "operación de tipo no soportado: `{}`",
            op.kind
        )));
    }
    // Busca el command destino directamente en el registry (sin filtrar por estado activo:
    // el handler corre dentro de un command ya activo y solo puede llamar a su propio módulo).
    let target = registry
        .commands
        .get(&op.command)
        .ok_or_else(|| RuntimeError::CommandNotFound(op.command.clone()))?;

    if target.module_id != handler_module_id {
        // Un handler no puede invocar commands de otros módulos (aislamiento).
        return Err(RuntimeError::PermissionDenied(format!(
            "el handler del módulo `{handler_module_id}` no puede invocar `{}` (módulo `{}`)",
            op.command, target.module_id
        )));
    }

    Ok(target.sql.clone())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::CommandDef;
    use crate::registry::ModuleStatus;
    use serde_json::Map;

    fn cmd_def() -> CommandDef {
        CommandDef {
            permission: String::new(),
            transaction: true,
            sql: vec!["INSERT INTO x VALUES (1);".to_string()],
            emit: vec![],
            handler: None,
            ai: None,
            schema: None,
            expose_api: false,
        }
    }

    fn registry_with_command(module_id: &str, name: &str) -> Registry {
        let mut reg = Registry::new();
        reg.status.insert(module_id.to_string(), ModuleStatus::Active);
        reg.commands.insert(
            name.to_string(),
            RegisteredCommand {
                module_id: module_id.to_string(),
                def: cmd_def(),
                sql: vec!["INSERT INTO x VALUES (1);".to_string()],
                wasm: None,
                schema: None,
            },
        );
        reg
    }

    fn op(command: &str) -> Operation {
        Operation { kind: "sql".to_string(), command: command.to_string(), params: Map::new() }
    }

    #[test]
    fn validate_operation_resolves_same_module_command_to_sql() {
        let reg = registry_with_command("notes", "notes.create");
        let sql = validate_operation(&reg, "notes", &op("notes.create")).unwrap();
        assert_eq!(sql, vec!["INSERT INTO x VALUES (1);".to_string()]);
    }

    #[test]
    fn validate_operation_rejects_other_module_command() {
        let reg = registry_with_command("inventory", "inventory.products.create");
        let err = validate_operation(&reg, "notes", &op("inventory.products.create")).unwrap_err();
        assert!(matches!(err, RuntimeError::PermissionDenied(_)), "got {err:?}");
    }

    #[test]
    fn validate_operation_rejects_unknown_command() {
        let reg = registry_with_command("notes", "notes.create");
        let err = validate_operation(&reg, "notes", &op("notes.nope")).unwrap_err();
        assert!(matches!(err, RuntimeError::CommandNotFound(_)), "got {err:?}");
    }

    #[test]
    fn validate_operation_rejects_non_sql_kind() {
        let reg = registry_with_command("notes", "notes.create");
        let mut o = op("notes.create");
        o.kind = "http".to_string();
        let err = validate_operation(&reg, "notes", &o).unwrap_err();
        assert!(matches!(err, RuntimeError::Wasm(_)), "got {err:?}");
    }
}
