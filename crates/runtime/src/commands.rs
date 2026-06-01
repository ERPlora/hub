//! Ejecución de commands declarativos (mutaciones) + emisión de eventos. ARQUITECTURA.md §4.
//! Tier 0/1 (SQL declarativo) y Tier 2 (handler WASM vía `erplora-wasm-host`, §5.3 / §9.2).
use erplora_db::{DatabaseAdapter, Params};
use erplora_wasm_host::{Operation, WasmHost};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::events;
use crate::permissions;
use crate::registry::{RegisteredCommand, Registry, RequestContext};

/// Profundidad máxima de cascada de eventos (evita bucles de listeners).
pub(crate) const MAX_EVENT_DEPTH: u32 = 16;

/// Cantidad de UUIDs pre-generados que el host pasa al handler WASM en
/// `context.new_ids`, para correlacionar filas padre→hijo (p.ej. 1 venta + sus
/// líneas). Suficiente para un ticket grande; un handler que necesite más debe
/// dividir la operación. ARQUITECTURA.md §5.3.
pub(crate) const NEW_IDS_BATCH: usize = 256;

/// Ejecuta `name(payload)` con el contexto dado. Aplica permiso, ejecuta SQL (en transacción
/// si está declarada) y emite los eventos resultantes.
pub fn execute(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
) -> Result<Json> {
    execute_at(db, registry, name, payload, ctx, 0)
}

pub(crate) fn execute_at(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
) -> Result<Json> {
    if depth > MAX_EVENT_DEPTH {
        return Err(RuntimeError::EventLoop);
    }

    let cmd = registry
        .get_command(name)
        .ok_or_else(|| RuntimeError::CommandNotFound(name.to_string()))?;

    // El handler corre bajo el permiso del command que lo invoca (no re-eleva).
    permissions::check(ctx, &cmd.def.permission)?;

    // ── Tier 2: handler WASM ────────────────────────────────────────────────
    if let Some(bytes) = &cmd.wasm {
        return execute_wasm(db, registry, cmd, payload, ctx, depth, bytes);
    }

    // ── Tier 0/1: SQL declarativo ───────────────────────────────────────────
    if cmd.sql.is_empty() {
        // Sin SQL ni WASM: no hay nada que ejecutar.
        return Err(RuntimeError::NotImplemented("command sin SQL ni handler WASM"));
    }

    let bound = crate::system_params(payload, ctx);

    if cmd.def.transaction {
        let ops: Vec<(String, Params)> =
            cmd.sql.iter().map(|sql| (sql.clone(), bound.clone())).collect();
        db.execute_tx(&ops)?;
    } else {
        for sql in &cmd.sql {
            db.execute(sql, &bound)?;
        }
    }

    // Emite eventos declarados; los payloads de evento llevan los params del command.
    for event in &cmd.def.emit {
        events::dispatch(db, registry, event, &bound, ctx, depth + 1)?;
    }

    Ok(json!({ "ok": true }))
}

/// Ejecuta un command Tier 2: invoca el handler WASM, valida cada intención y
/// aplica todas las operaciones + el `emit` del command en una sola transacción.
fn execute_wasm(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    bytes: &[u8],
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

    // Valida + resuelve cada operación a su(s) SQL contra los commands del MISMO módulo.
    let mut tx_ops: Vec<(String, Params)> = Vec::new();
    for op in &output.operations {
        let sqls = validate_operation(registry, &cmd.module_id, op)?;
        let bound = crate::system_params(&op.params, ctx);
        for sql in sqls {
            tx_ops.push((sql, bound.clone()));
        }
    }

    // Todas las intenciones + el emit del command original van en UNA transacción.
    db.execute_tx(&tx_ops)?;

    // Eventos declarados por el command + eventos devueltos por el handler.
    let declared_payload = crate::system_params(payload, ctx);
    for event in &cmd.def.emit {
        events::dispatch(db, registry, event, &declared_payload, ctx, depth + 1)?;
    }
    for ev in &output.events {
        let payload = match &ev.payload {
            Json::Object(map) => map.clone(),
            other => {
                let mut m = Params::new();
                m.insert("value".into(), other.clone());
                m
            }
        };
        events::dispatch(db, registry, &ev.name, &payload, ctx, depth + 1)?;
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
