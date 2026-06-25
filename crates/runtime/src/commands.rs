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
use crate::queries;
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
    let enriched_ctx;
    let ctx = if depth == 0 && ctx.business_tax_id.is_empty() {
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
    if let Some(schema) = &cmd.schema {
        schema
            .validate(&Json::Object(payload.clone()))
            .map_err(|detail| RuntimeError::InvalidPayload { name: name.to_string(), detail })?;
    }

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
    // Reads declaradas (ADR-0069): pre-ejecuta las queries que el command declara en `reads` e
    // inyéctalas en `context.reads` para que el handler —que NO toca la BD— disponga de filas de
    // confianza (p. ej. los tipos de impuesto). Vacío si el command no declara `reads`.
    let reads = preload_reads(db, registry, cmd, ctx).await;
    let input = json!({
        "payload": Json::Object(bound_payload),
        "context": {
            "hub_id": ctx.hub_id,
            "current_user_id": ctx.user_id,
            "now": crate::registry::now_rfc3339(),
            "new_ids": new_ids,
            "reads": reads,
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

    // Mismo input que el WASM: payload con system_params + contexto con lote de ids + reads.
    let bound_payload = crate::system_params(payload, ctx);
    let new_ids: Vec<Json> = (0..NEW_IDS_BATCH)
        .map(|_| Json::String(crate::registry::new_id()))
        .collect();
    // Reads declaradas (ADR-0069): mismo mecanismo que el WASM (el handler nativo tampoco asume
    // qué hay en la BD de otros módulos; consume las filas pre-cargadas vía `context.reads`).
    let reads = preload_reads(db, registry, cmd, ctx).await;
    let input = json!({
        "payload": Json::Object(bound_payload),
        "context": {
            "hub_id": ctx.hub_id,
            "current_user_id": ctx.user_id,
            "now": crate::registry::now_rfc3339(),
            "new_ids": new_ids,
            "reads": reads,
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

/// Pre-ejecuta las queries declaradas en `cmd.def.reads` y devuelve el mapa
/// `{ "<query>": <filas> }` para inyectar en `context.reads` del handler (ADR-0069, el "keystone"
/// del impuesto). El handler corre en un sandbox y **no** puede leer la BD ni otros módulos; este
/// mecanismo le alimenta filas **de confianza** (p. ej. los tipos de impuesto que el módulo `taxes`
/// resuelve) antes de invocarlo.
///
/// Reglas (todas del ADR):
/// - **Alcance por `depends_on`, no por permiso de usuario.** Una read solo se carga si su módulo
///   (resuelto del registry) es el **propio** módulo del command **o** está en su `depends_on`
///   (sacado del manifest instalado). Una read fuera de alcance se **omite** con `warn` (no se
///   carga, no falla el command). Esto **sustituye** el gate por-permiso por el gate por-dependencia:
///   el autor del módulo declaró esa dependencia, así que la lectura es contrato vouched.
/// - **Ejecución como sistema.** El permiso del command ya se comprobó en `execute_at`; las reads no
///   se re-gatean por el permiso de USUARIO de cada query (un empleado de POS sin `taxes.view_tax`
///   igual obtiene los tipos). Lo materializa un **contexto efímero** derivado del `ctx` del llamador
///   (mismo `hub_id`/identidad de negocio) pero con el comodín de permisos `*`. Ese contexto vive
///   **solo** en esta función (el camino de reads declaradas); el gate normal de `queries::execute`
///   no se toca en ningún otro sitio.
/// - **Sin params.** Las reads se corren con el contexto de sistema (`hub_id` inyectado por
///   `system_params` como siempre) y un payload vacío; para `taxes` basta (devuelven los ~15 tipos
///   del hub, por debajo del `page_size`).
/// - **Graceful.** Cada read va envuelta: si falla, se **omite** con `warn` (el guest degrada, ya
///   tiene fallback al `payload`). Una read no se considera crítica.
///
/// Devuelve un `Json::Object` (posiblemente vacío). Nunca falla: un problema con una read concreta
/// no debe tumbar el command.
async fn preload_reads(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    ctx: &RequestContext,
) -> Json {
    let mut out = serde_json::Map::new();
    if cmd.def.reads.is_empty() {
        return Json::Object(out);
    }

    // Contexto de sistema EFÍMERO: misma identidad/tenant que el llamador, pero con el comodín `*`
    // para que el gate por-query de `queries::execute` pase sin re-gatear por el permiso de usuario
    // (ADR-0069: las reads corren como sistema, gateadas por `depends_on`). NO debilita el gate en
    // ningún otro sitio: este contexto solo existe aquí y solo se usa para las reads declaradas.
    let mut system_ctx = ctx.clone();
    system_ctx.permissions = std::iter::once("*".to_string()).collect();

    let no_params = erplora_db::Params::new();

    for query_name in &cmd.def.reads {
        // Alcance: el módulo de la query debe ser el del command o estar en su `depends_on`.
        if !read_in_scope(registry, &cmd.module_id, query_name) {
            eprintln!(
                "⚠ read fuera de alcance: el command del módulo `{}` declara `reads:[{query_name}]` pero esa query no es del propio módulo ni de un `depends_on` — se omite",
                cmd.module_id
            );
            continue;
        }
        // Ejecución interna graceful: una read que falle se omite (el handler degrada).
        match queries::execute(db, registry, query_name, &no_params, &system_ctx).await {
            Ok(rows) => {
                out.insert(query_name.clone(), Json::Array(rows));
            }
            Err(e) => {
                eprintln!("⚠ read `{query_name}` (command del módulo `{}`) falló y se omite: {e}", cmd.module_id);
            }
        }
    }
    Json::Object(out)
}

/// ¿Está la query `query_name` **dentro del alcance** de las reads de un command del módulo
/// `command_module`? (ADR-0069). Alcance = la query pertenece al **propio** módulo del command o a
/// uno de sus `depends_on`. El módulo dueño de la query se resuelve del registry (autoridad); si la
/// query no está registrada (módulo inactivo / nombre erróneo) devuelve `false` → la read se omite.
fn read_in_scope(registry: &Registry, command_module: &str, query_name: &str) -> bool {
    // Módulo que aporta la query (sin filtrar por estado activo: el dueño no cambia por estar
    // inactivo; si lo está, `queries::execute` la rechazará después y la read se omite igualmente).
    let Some(query_module) = registry.queries.get(query_name).map(|q| q.module_id.as_str()) else {
        return false;
    };
    if query_module == command_module {
        return true;
    }
    // ¿Está el módulo de la query en el `depends_on` del módulo del command? (manifest instalado).
    registry
        .installed
        .iter()
        .find(|m| m.id == command_module)
        .map(|m| m.depends_on.iter().any(|dep| dep == query_module))
        .unwrap_or(false)
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
            reads: vec![],
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

    // ── reads (ADR-0069): pre-carga de queries en `context.reads` ────────────────────────────────
    use crate::manifest::QueryDef;
    use crate::registry::RegisteredQuery;
    use crate::Manifest;
    use erplora_db::{DatabaseAdapter, SqliteAdapter};

    /// Registra una query `name` (módulo `module_id`) que ejecuta `sql` y exige `permission`.
    fn add_query(reg: &mut Registry, module_id: &str, name: &str, sql: &str, permission: &str) {
        reg.status.insert(module_id.to_string(), ModuleStatus::Active);
        reg.queries.insert(
            name.to_string(),
            RegisteredQuery {
                module_id: module_id.to_string(),
                def: QueryDef {
                    permission: permission.to_string(),
                    sql: sql.to_string(),
                    schema: None,
                    list: None,
                    ai: None,
                    expose_api: false,
                },
                sql: sql.to_string(),
                schema: None,
            },
        );
    }

    /// Inserta el manifest de `module_id` con un `depends_on` dado (para el scope de las reads).
    fn add_manifest(reg: &mut Registry, module_id: &str, depends_on: &[&str]) {
        let deps: Vec<String> = depends_on.iter().map(|s| s.to_string()).collect();
        let manifest = Manifest {
            id: module_id.to_string(),
            name: module_id.to_string(),
            version: "1.0.0".to_string(),
            depends_on: deps,
            permissions: vec![],
            role_permissions: Default::default(),
            navigation: vec![],
            migrations: Default::default(),
            queries: Default::default(),
            commands: Default::default(),
            widgets: Default::default(),
            events: Default::default(),
            agent: None,
            ai_context: None,
            scheduled_tasks: vec![],
            notify: None,
            network: None,
        };
        reg.installed.push(manifest);
    }

    /// Construye un `RegisteredCommand` del módulo `module_id` que declara `reads`.
    fn cmd_with_reads(module_id: &str, reads: &[&str]) -> RegisteredCommand {
        let mut def = cmd_def();
        def.reads = reads.iter().map(|s| s.to_string()).collect();
        RegisteredCommand {
            module_id: module_id.to_string(),
            def,
            sql: vec![],
            wasm: None,
            schema: None,
        }
    }

    #[test]
    fn read_in_scope_accepts_own_module() {
        let mut reg = Registry::new();
        add_query(&mut reg, "taxes", "taxes.rates.list", "SELECT 1", "taxes.view_tax");
        assert!(read_in_scope(&reg, "taxes", "taxes.rates.list"));
    }

    #[test]
    fn read_in_scope_accepts_declared_dependency() {
        let mut reg = Registry::new();
        // `sales` depende de `taxes` → puede leer una query de `taxes`.
        add_manifest(&mut reg, "sales", &["taxes"]);
        add_query(&mut reg, "taxes", "taxes.rates.list", "SELECT 1", "taxes.view_tax");
        assert!(read_in_scope(&reg, "sales", "taxes.rates.list"));
    }

    #[test]
    fn read_in_scope_rejects_module_not_in_depends_on() {
        let mut reg = Registry::new();
        // `sales` NO declara depender de `inventory` → fuera de alcance.
        add_manifest(&mut reg, "sales", &["taxes"]);
        add_query(&mut reg, "inventory", "inventory.products.list", "SELECT 1", "inventory.read");
        assert!(!read_in_scope(&reg, "sales", "inventory.products.list"));
    }

    #[test]
    fn read_in_scope_rejects_unregistered_query() {
        let reg = Registry::new();
        // Query inexistente en el registry (módulo inactivo / nombre mal) → fuera de alcance.
        assert!(!read_in_scope(&reg, "sales", "taxes.rates.list"));
    }

    /// (a) Un command con `reads:[<query del propio módulo>, <query de una dependencia>]` recibe
    /// `context.reads` poblado con AMBOS resultados — y la query de la dependencia se ejecuta
    /// **como sistema** (el contexto del llamador NO tiene su permiso, pero la read igual carga,
    /// gateada por `depends_on`, ADR-0069).
    #[tokio::test]
    async fn preload_reads_populates_in_scope_queries_as_system() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        // Dos tablas con datos scopeados por hub_id (taxes = dependencia, sales = propio módulo).
        db.execute_batch(
            "CREATE TABLE tax_rate (hub_id TEXT, name TEXT, rate_pct REAL);
             INSERT INTO tax_rate VALUES ('hub-1', 'IVA 21', 21.0);
             INSERT INTO tax_rate VALUES ('other-hub', 'IVA 10', 10.0);
             CREATE TABLE sale_config (hub_id TEXT, currency TEXT);
             INSERT INTO sale_config VALUES ('hub-1', 'EUR');",
        )
        .await
        .unwrap();

        let mut reg = Registry::new();
        add_manifest(&mut reg, "sales", &["taxes"]);
        // Query de la dependencia: filtra por :hub_id (inyectado por system_params).
        add_query(
            &mut reg,
            "taxes",
            "taxes.rates.list",
            "SELECT name, rate_pct FROM tax_rate WHERE hub_id = :hub_id",
            "taxes.view_tax",
        );
        // Query del propio módulo.
        add_query(
            &mut reg,
            "sales",
            "sales.config.get",
            "SELECT currency FROM sale_config WHERE hub_id = :hub_id",
            "sales.read",
        );

        let cmd = cmd_with_reads("sales", &["taxes.rates.list", "sales.config.get"]);
        // El contexto del llamador NO lleva `taxes.view_tax` (un empleado de POS): la read de la
        // dependencia debe cargar igual porque corre como sistema, gateada por `depends_on`.
        let ctx = RequestContext::new("hub-1", "user-1", ["sales.create".to_string()]);

        let reads = preload_reads(&db, &reg, &cmd, &ctx).await;

        // Ambas reads presentes y con las filas del hub correcto (scope de tenant respetado).
        let taxes = &reads["taxes.rates.list"];
        assert_eq!(taxes.as_array().unwrap().len(), 1, "solo la fila de hub-1");
        assert_eq!(taxes[0]["name"], "IVA 21");
        assert_eq!(taxes[0]["rate_pct"], 21.0);

        let config = &reads["sales.config.get"];
        assert_eq!(config.as_array().unwrap().len(), 1);
        assert_eq!(config[0]["currency"], "EUR");
    }

    /// (b) Una read **fuera de alcance** (módulo no declarado en `depends_on`) se **omite**: no
    /// aparece en `context.reads` y el command no falla.
    #[tokio::test]
    async fn preload_reads_omits_out_of_scope_query() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        db.execute_batch(
            "CREATE TABLE product (hub_id TEXT, name TEXT);
             INSERT INTO product VALUES ('hub-1', 'Coffee');",
        )
        .await
        .unwrap();

        let mut reg = Registry::new();
        // `sales` solo depende de `taxes`, NO de `inventory`.
        add_manifest(&mut reg, "sales", &["taxes"]);
        add_query(
            &mut reg,
            "inventory",
            "inventory.products.list",
            "SELECT name FROM product WHERE hub_id = :hub_id",
            "inventory.read",
        );

        let cmd = cmd_with_reads("sales", &["inventory.products.list"]);
        let ctx = RequestContext::new("hub-1", "user-1", ["sales.create".to_string()]);

        let reads = preload_reads(&db, &reg, &cmd, &ctx).await;

        // Omitida (no es del propio módulo ni de un depends_on): el mapa queda vacío, sin error.
        assert!(reads.as_object().unwrap().is_empty(), "la read fuera de alcance no se carga");
    }

    /// Una read **en alcance pero que falla en ejecución** (SQL erróneo) se omite con graceful
    /// degradation: no aparece en `context.reads` y el command no falla.
    #[tokio::test]
    async fn preload_reads_skips_failing_query_gracefully() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        let mut reg = Registry::new();
        add_query(
            &mut reg,
            "sales",
            "sales.broken.query",
            "SELECT * FROM table_that_does_not_exist",
            "sales.read",
        );
        let cmd = cmd_with_reads("sales", &["sales.broken.query"]);
        let ctx = RequestContext::new("hub-1", "user-1", ["sales.create".to_string()]);

        let reads = preload_reads(&db, &reg, &cmd, &ctx).await;
        assert!(reads.as_object().unwrap().is_empty(), "la read que falla se omite, no rompe");
    }

    /// Un command **sin** `reads` produce un `context.reads` vacío (backward-compat: ningún cambio
    /// de comportamiento para los commands existentes).
    #[tokio::test]
    async fn preload_reads_empty_when_command_declares_none() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        let reg = Registry::new();
        let cmd = cmd_with_reads("sales", &[]);
        let ctx = RequestContext::new("hub-1", "user-1", ["sales.create".to_string()]);

        let reads = preload_reads(&db, &reg, &cmd, &ctx).await;
        assert!(reads.as_object().unwrap().is_empty());
    }
}
