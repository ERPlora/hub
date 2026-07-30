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

/// Origen de una invocación de [`execute_at`] (hub#131, hub#145).
///
/// Distingue el camino EXTERNO — todo lo que entra por `Runtime::execute_command` (HTTP
/// `POST /api/command`, la API pública `POST /api/v1/{module}/c/{command}` de API keys, el
/// asistente/SDK) — del camino INTERNO: el propio runtime invocándose a sí mismo (el relay del
/// Outbox entregando un listener, el scheduler disparando una scheduled task del mismo módulo).
///
/// Solo el origen EXTERNO se gatea contra los commands marcados `internal` (o con el último
/// segmento del nombre prefijado `_`): un caller externo nunca debe poder invocar directamente lo
/// que un módulo emite como implementación (`module._helper`), saltándose la validación,
/// orquestación y atomicidad del command público que normalmente lo dispara.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Origin {
    External,
    Internal,
}

/// Ejecuta `name(payload)` con el contexto dado. Aplica permiso, ejecuta el SQL **y persiste
/// los eventos emitidos en el outbox dentro de la MISMA transacción** (entrega at-least-once
/// asíncrona; los listeners los corre el relay, ver `outbox.rs`). ARQUITECTURA.md §4/§5.4.
///
/// Es el ÚNICO punto de entrada público del dispatcher de commands — lo llama
/// `Runtime::execute_command`, que a su vez es lo único que exponen las rutas HTTP (`/api/command`,
/// `/api/v1/{module}/c/{command}`). Por eso el origen es SIEMPRE [`Origin::External`] aquí: un
/// caller interno legítimo (outbox, scheduler) usa [`execute_at`] directamente con
/// [`Origin::Internal`], no esta función.
pub async fn execute(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
) -> Result<Json> {
    execute_at(db, registry, name, payload, ctx, 0, &[], Origin::External).await
}

/// Como [`execute`] pero a profundidad `depth` (cascada), con `extra_ops` añadidos a la
/// transacción del command y con el [`Origin`] explícito de la llamada. El relay usa `extra_ops`
/// para insertar el marcador de entrega (`_event_delivery`) atómicamente con los efectos del
/// listener (idempotencia, §5.4).
pub(crate) async fn execute_at(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    extra_ops: &[(String, Params)],
    origin: Origin,
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
        let f = crate::settings::get_all(db, &ctx.hub_id)
            .await
            .unwrap_or(Json::Null);
        let get = |k: &str| f.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
        let has_cert = crate::certificate::status(db, &ctx.hub_id)
            .await
            .ok()
            .and_then(|s| s.get("present").and_then(|v| v.as_bool()))
            .unwrap_or(false);
        enriched_ctx = ctx
            .clone()
            .with_business(
                get("business_tax_id"),
                get("business_legal_name"),
                get("business_address"),
            )
            // IDENTIDAD FISCAL (ADR-0085): el país/región del hub. Es la mitad de la clave con la
            // que el SERVIDOR resuelve el impuesto contra el catálogo — sin ella, ninguna regla
            // casa y el handler se cree el % que le mande el cliente.
            .with_fiscal(get("country_code"), get("region_code"))
            .with_certificate(has_cert);
        &enriched_ctx
    } else {
        ctx
    };

    let cmd = registry
        .get_command(name)
        .ok_or_else(|| RuntimeError::CommandNotFound(name.to_string()))?;

    // Gate de ORIGEN (hub#131, hub#145): un command interno (prefijo `_` en su último segmento,
    // o `internal: true` en el manifest) es invisible para un caller EXTERNO — ni el permiso ni
    // el schema del command importan, se rechaza ANTES de comprobarlos. Solo el propio runtime
    // (relay del Outbox, scheduler) lo invoca, siempre con `Origin::Internal`. Sin esto, un
    // `module._helper` "privado" solo por convención era invocable tal cual desde
    // `POST /api/command`, saltándose la orquestación/atomicidad del command público que lo emite.
    if origin == Origin::External && cmd.def.is_internal(name) {
        return Err(RuntimeError::InternalCommand(name.to_string()));
    }

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
            .map_err(|detail| RuntimeError::InvalidPayload {
                name: name.to_string(),
                detail,
            })?;
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
            // Gate de capabilities (ADR-0079): un handler nativo es donde vive el acceso real a
            // certificado/red (verifactu→AEAT). Default-deny: si el módulo declara capabilities que
            // el usuario no ha concedido → CapabilityDenied y el motor nativo NO corre (el cert no
            // se lee ni se toca la AEAT). Ortogonal al RBAC de usuario ya chequeado arriba.
            crate::capabilities::enforce(db, registry, &cmd.module_id, &ctx.hub_id).await?;
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
        return Err(RuntimeError::NotImplemented(
            "command sin SQL ni handler WASM",
        ));
    }

    let bound = crate::system_params(payload, ctx);

    // SQL del command + INSERT en `_event_outbox` por cada evento emitido + `extra_ops` →
    // UNA transacción. Si commitea, los eventos quedan persistidos; si revierte, no hay evento.
    // (Decisión del humano #3: los commands `transaction:false` también se envuelven en tx para
    // garantizar la escritura atómica del outbox.)
    let mut ops: Vec<(String, Params)> = cmd
        .sql
        .iter()
        .map(|sql| (sql.clone(), bound.clone()))
        .collect();
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

    // El id que este command acaba de crear, igual que en el camino WASM (§5.3): `system_params`
    // ya inyecta `:new_id` en el SQL, pero la respuesta se lo callaba. Sin él, quien crea una fila
    // no puede volver a tocarla — el POS se quedaba sin `line_id` al añadir un artículo y las
    // subidas de cantidad se perdían EN SILENCIO (5 tortillas en pantalla, 1 en la BD).
    let new_id = bound.get("new_id").cloned().unwrap_or(Json::Null);
    Ok(json!({ "ok": true, "new_ids": [new_id] }))
}

/// Ejecuta un command Tier 2: invoca el handler WASM, valida cada intención y
/// aplica todas las operaciones + el `emit` del command en una sola transacción.
/// Ejecuta las **lecturas pre-cargadas** que el command declara (`reads`) y las devuelve como
/// `{ "<query>": [ …filas… ] }` para inyectarlas en `context.reads` del handler (ADR-0069 §1).
///
/// # Por qué existe
///
/// El handler WASM corre en un **sandbox**: no puede tocar la BD. Sin este mecanismo, un handler
/// solo sabe lo que le cuenta el cliente — y así es como el navegador acababa decidiendo **el IVA
/// que se le declara a la AEAT**: `sales.complete_sale` recibía el `tax_rate` de cada línea en el
/// payload y se lo creía. Con `reads`, el handler resuelve el % contra `taxes.rules.list` (el
/// catálogo del hub) y la pista del cliente queda como mero fallback.
///
/// # Las tres reglas (ADR-0069 §1)
///
/// 1. **Alcance por DEPENDENCIA, no por permiso.** Solo queries del propio módulo o de los que
///    declara en `depends_on`. Un módulo no puede leerle las tablas a otro con el que no tiene
///    contrato — la lista de queries permitidas la fija el manifest, no el caller.
/// 2. **Contexto de SISTEMA.** No se re-gatea por el permiso del usuario: el permiso del *command*
///    ya se comprobó, y las reads son contrato vouched por el autor del módulo. Un empleado de POS
///    sin `taxes.view_tax` igual necesita los tipos para poder cobrar. Se conserva el `hub_id` del
///    caller (el tenant NO es negociable) y se usa el wildcard de permisos.
/// 3. **Fallo GRACEFUL.** Una read que no resuelve se **omite** (no aborta el command). Cobrar es
///    lo último que puede romperse en un TPV: si `taxes` está raro, el handler degrada a su
///    fallback, pero la venta se cierra.
async fn preload_reads(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    ctx: &RequestContext,
    payload: &erplora_db::Params,
) -> Json {
    if cmd.def.reads.is_empty() {
        return Json::Object(Default::default());
    }

    // Regla 1 — alcance: el propio módulo + sus `depends_on` declarados en el manifest.
    let deps: Vec<String> = registry
        .installed
        .iter()
        .find(|m| m.id == cmd.module_id)
        .map(|m| m.depends_on.clone())
        .unwrap_or_default();
    let allowed: Vec<&str> = std::iter::once(cmd.module_id.as_str())
        .chain(deps.iter().map(|s| s.as_str()))
        .collect();

    // Regla 2 — contexto de sistema: mismo `hub_id` (el tenant NO se negocia), permisos wildcard.
    let sys = RequestContext::new(&ctx.hub_id, &ctx.user_id, ["*".to_string()]);

    let mut out = serde_json::Map::new();
    for read in &cmd.def.reads {
        let name = read.query();
        let owner = name.split('.').next().unwrap_or("");
        if !allowed.contains(&owner) {
            // No es un error del caller: es un manifest mal declarado. Se avisa y se omite —
            // el módulo no puede leer lo que no declaró como dependencia.
            eprintln!(
                "⚠ reads: `{}` declara `{name}`, pero `{owner}` no está en su depends_on → omitida",
                cmd.module_id
            );
            continue;
        }
        // Regla 4 — parámetros desde el PAYLOAD (ADR-0069 fase 2). Sin esto, un handler podía
        // pedir «todas las reglas de IVA» pero no «la unidad de ESTE producto», y toda validación
        // contra la fila concreta se quedaba sin sitio donde vivir.
        let params = read.resolve_params_from_map(payload);

        // Regla 3 — graceful: si la query falla (no existe, SQL roto, tabla ausente), se omite.
        match crate::queries::execute(db, registry, name, &params, &sys).await {
            Ok(rows) => {
                out.insert(name.to_string(), Json::Array(rows));
            }
            Err(e) => {
                eprintln!("⚠ reads: `{name}` falló ({e}) → se omite; el handler degradará");
            }
        }
    }
    Json::Object(out)
}

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
    let handler =
        cmd.def.handler.as_ref().ok_or_else(|| {
            RuntimeError::Wasm("command con bytes wasm pero sin handler".to_string())
        })?;

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
    // LECTURAS PRE-CARGADAS (ADR-0069). El handler corre en un sandbox y NO puede leer la BD, así
    // que sin esto solo sabe lo que le cuenta el cliente. Aquí el host le entrega el **catálogo de
    // confianza del hub**.
    let reads = preload_reads(db, registry, cmd, ctx, payload).await;
    let input = json!({
        "payload": Json::Object(bound_payload),
        "context": {
            "hub_id": ctx.hub_id,
            "current_user_id": ctx.user_id,
            "now": crate::registry::now_rfc3339(),
            "new_ids": new_ids.clone(),
            // Identidad fiscal del hub: con esto + `reads`, el handler resuelve el impuesto contra
            // el catálogo de confianza en vez de fiarse del payload (ADR-0085/0069).
            "country_code": ctx.country_code,
            "region_code": ctx.region_code,
            "reads": reads,
        },
    });

    let mut host = WasmHost::from_bytes(bytes).map_err(|e| RuntimeError::Wasm(e.to_string()))?;
    let output = host
        .call(&handler.function, &input)
        .map_err(|e| RuntimeError::Wasm(e.to_string()))?;

    persist_handler_output(
        db, registry, cmd, payload, ctx, depth, extra_ops, &output, &new_ids,
    )
    .await
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
    let handler = cmd
        .def
        .handler
        .as_ref()
        .ok_or_else(|| RuntimeError::Native("command nativo sin bloque handler".to_string()))?;
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
            "new_ids": new_ids.clone(),
        },
    });

    let static_folder = registry
        .installed
        .iter()
        .find(|module| module.id == cmd.module_id)
        .and_then(|module| module.static_files.as_ref())
        .map(|decl| decl.folder.as_str());
    let host = crate::native::DbHost {
        db,
        storage: registry.module_storage.as_deref(),
        hub_id: &ctx.hub_id,
        module_id: &cmd.module_id,
        static_folder,
    };
    let output = engine.call(&handler.function, &input, &host).await?;

    persist_handler_output(
        db, registry, cmd, payload, ctx, depth, extra_ops, &output, &new_ids,
    )
    .await
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
    // Lote de ids que el host generó y entregó al handler. Se devuelven al llamante para que la
    // UI pueda correlacionar lo que acaba de crear (el POS abre un pedido y necesita su `order_id`
    // para añadirle líneas). Por convención `new_ids[0]` es la entidad principal (§5.3).
    new_ids: &[Json],
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

    Ok(json!({ "ok": true, "operations": output.operations.len(), "new_ids": new_ids }))
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

    if target.sql.is_empty() {
        // Un comando sin sentencias declarativas (p.ej. WASM) NO es un destino válido de una
        // intención: devolver una lista vacía convertía la op en un no-op SILENCIOSO (así se
        // perdió el descuento de stock por evento en ADR-0147). §5.3: se rechaza con ruido.
        return Err(RuntimeError::Wasm(format!(
            "la operación `{}` no resuelve a SQL declarativo (¿comando WASM?): una intención \
             solo puede referenciar comandos SQL del propio módulo (§5.3)",
            op.command
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
            reads: Vec::new(),
            transaction: true,
            sql: vec!["INSERT INTO x VALUES (1);".to_string()],
            emit: vec![],
            handler: None,
            ai: None,
            schema: None,
            expose_api: false,
            internal: false,
        }
    }

    fn registry_with_command(module_id: &str, name: &str) -> Registry {
        let mut reg = Registry::new();
        reg.status
            .insert(module_id.to_string(), ModuleStatus::Active);
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
        Operation {
            kind: "sql".to_string(),
            command: command.to_string(),
            params: Map::new(),
        }
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
        assert!(
            matches!(err, RuntimeError::PermissionDenied(_)),
            "got {err:?}"
        );
    }

    #[test]
    fn validate_operation_rejects_unknown_command() {
        let reg = registry_with_command("notes", "notes.create");
        let err = validate_operation(&reg, "notes", &op("notes.nope")).unwrap_err();
        assert!(
            matches!(err, RuntimeError::CommandNotFound(_)),
            "got {err:?}"
        );
    }

    #[test]
    fn validate_operation_rejects_non_sql_kind() {
        let reg = registry_with_command("notes", "notes.create");
        let mut o = op("notes.create");
        o.kind = "http".to_string();
        let err = validate_operation(&reg, "notes", &o).unwrap_err();
        assert!(matches!(err, RuntimeError::Wasm(_)), "got {err:?}");
    }

    #[test]
    fn validate_operation_rejects_command_without_sql() {
        // Encontrado con ADR-0147: el listener de inventory apuntaba una op a su comando WASM
        // `inventory.stock.decrease` y esto resolvía a una lista VACÍA de sentencias — la op se
        // "aplicaba" sin hacer nada y el descuento de stock no ocurría, en silencio. §5.3 dice
        // que una intención debe resolver a un comando SQL del propio módulo; lo que no cumpla
        // eso se RECHAZA con ruido, no se convierte en un no-op.
        let mut reg = Registry::new();
        reg.status
            .insert("inventory".to_string(), ModuleStatus::Active);
        let mut def = cmd_def();
        def.sql = vec![]; // comando WASM: sin sentencias declarativas
        reg.commands.insert(
            "inventory.stock.decrease".to_string(),
            RegisteredCommand {
                module_id: "inventory".to_string(),
                def,
                sql: vec![],
                wasm: None,
                schema: None,
            },
        );
        let err =
            validate_operation(&reg, "inventory", &op("inventory.stock.decrease")).unwrap_err();
        assert!(
            matches!(err, RuntimeError::Wasm(_)),
            "debe rechazar, no aplicar 0 sentencias: {err:?}"
        );
    }

    // ── Gate de origen: comandos internos (hub#131, hub#145) ────────────────────────────────

    /// Como [`registry_with_command`] pero permite marcar el command `internal: true` en el
    /// manifest (independiente del prefijo `_` en `name`).
    fn registry_with_command_flagged(module_id: &str, name: &str, internal: bool) -> Registry {
        let mut reg = Registry::new();
        reg.status
            .insert(module_id.to_string(), ModuleStatus::Active);
        let mut def = cmd_def();
        def.internal = internal;
        reg.commands.insert(
            name.to_string(),
            RegisteredCommand {
                module_id: module_id.to_string(),
                def,
                sql: vec!["INSERT INTO x VALUES (1);".to_string()],
                wasm: None,
                schema: None,
            },
        );
        reg
    }

    /// Contexto admin con la identidad de negocio ya rellena: evita que `execute_at` dispare
    /// `settings::get_all` (lectura de `hub_settings`) antes de llegar al gate de origen, así los
    /// tests de este bloque pueden usar un `DatabaseAdapter` que PANIC-ea ante cualquier consulta
    /// y probar de verdad que el rechazo ocurre "ANTES DE TOCAR LA BD".
    fn ctx_admin() -> RequestContext {
        RequestContext::new("h1", "u1", ["*".to_string()]).with_business(
            "B00000000",
            "ACME Test",
            "Calle Falsa 123",
        )
    }

    /// Doble de test que PANIC-ea ante cualquier operación de BD. Sirve para demostrar que el
    /// gate de origen corta ANTES de tocar la base de datos (no solo que devuelve el error
    /// correcto, sino que ni siquiera llega a `db.execute_tx`/`db.query`).
    struct DenyDb;

    #[async_trait::async_trait]
    impl DatabaseAdapter for DenyDb {
        async fn execute(
            &self,
            _sql: &str,
            _params: &Params,
        ) -> std::result::Result<erplora_db::CommandResult, erplora_db::DbError> {
            panic!("DenyDb::execute no debía llamarse — el gate de origen debe cortar antes");
        }
        async fn execute_tx(
            &self,
            _ops: &[(String, Params)],
        ) -> std::result::Result<erplora_db::CommandResult, erplora_db::DbError> {
            panic!("DenyDb::execute_tx no debía llamarse — el gate de origen debe cortar antes");
        }
        async fn query(
            &self,
            _sql: &str,
            _params: &Params,
        ) -> std::result::Result<erplora_db::QueryResult, erplora_db::DbError> {
            panic!("DenyDb::query no debía llamarse — el gate de origen debe cortar antes");
        }
        async fn execute_batch(&self, _sql: &str) -> std::result::Result<(), erplora_db::DbError> {
            panic!("DenyDb::execute_batch no debía llamarse");
        }
    }

    /// Doble de test que ACEPTA trivialmente cualquier operación de BD (sin Postgres real). Sirve
    /// para probar que una invocación INTERNA (Origin::Internal) sí atraviesa el gate y llega a
    /// ejecutar el SQL del command.
    struct FakeDb;

    #[async_trait::async_trait]
    impl DatabaseAdapter for FakeDb {
        async fn execute(
            &self,
            _sql: &str,
            _params: &Params,
        ) -> std::result::Result<erplora_db::CommandResult, erplora_db::DbError> {
            Ok(erplora_db::CommandResult::affected(0))
        }
        async fn execute_tx(
            &self,
            ops: &[(String, Params)],
        ) -> std::result::Result<erplora_db::CommandResult, erplora_db::DbError> {
            Ok(erplora_db::CommandResult::affected(ops.len() as u64))
        }
        async fn query(
            &self,
            _sql: &str,
            _params: &Params,
        ) -> std::result::Result<erplora_db::QueryResult, erplora_db::DbError> {
            Ok(erplora_db::QueryResult::new(Vec::new()))
        }
        async fn execute_batch(&self, _sql: &str) -> std::result::Result<(), erplora_db::DbError> {
            Ok(())
        }
    }

    /// (a) hub#131/#145 — el camino EXTERNO real (`execute`, lo único que llaman las rutas HTTP
    /// vía `Runtime::execute_command`) rechaza un command "privado por convención"
    /// (`cash_register._reverse_sale`-style: último segmento con `_`) con `InternalCommand`, SIN
    /// tocar la BD (`DenyDb` habría hecho panic si se hubiera llegado a `execute_tx`/`query`).
    #[tokio::test]
    async fn execute_rejects_underscore_command_from_the_public_entrypoint() {
        let reg = registry_with_command("cash_register", "cash_register._reverse_sale");
        let ctx = ctx_admin();
        let err = execute(
            &DenyDb,
            &reg,
            "cash_register._reverse_sale",
            &Params::new(),
            &ctx,
        )
        .await
        .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InternalCommand(ref n) if n == "cash_register._reverse_sale"),
            "got {err:?}"
        );
    }

    /// (a bis) Mismo rechazo a nivel de `execute_at` con `Origin::External` explícito — la doble
    /// puerta de la API pública (`api_keys::data_command`) llega aquí por el mismo camino.
    #[tokio::test]
    async fn execute_at_external_rejects_underscore_command_before_touching_db() {
        let reg = registry_with_command("inventory", "inventory._restock_on_void");
        let ctx = ctx_admin();
        let err = execute_at(
            &DenyDb,
            &reg,
            "inventory._restock_on_void",
            &Params::new(),
            &ctx,
            0,
            &[],
            Origin::External,
        )
        .await
        .unwrap_err();
        assert!(matches!(err, RuntimeError::InternalCommand(_)), "got {err:?}");
    }

    /// (b) Una invocación INTERNA legítima (el relay del Outbox entregando un listener, o el
    /// scheduler) del MISMO command `_` SÍ se ejecuta: llega hasta `db.execute_tx` (con `FakeDb`,
    /// sin necesitar Postgres real) y devuelve `{ok: true, ...}`.
    #[tokio::test]
    async fn execute_at_internal_origin_runs_the_underscore_command() {
        let reg = registry_with_command("cash_register", "cash_register._reverse_sale");
        let ctx = ctx_admin();
        let out = execute_at(
            &FakeDb,
            &reg,
            "cash_register._reverse_sale",
            &Params::new(),
            &ctx,
            0,
            &[],
            Origin::Internal,
        )
        .await
        .expect("una invocación INTERNA sí debe ejecutar el comando `_`");
        assert_eq!(out["ok"], serde_json::json!(true));
    }

    /// (c) `internal: true` explícito en el manifest, SIN prefijo `_` en el nombre, también se
    /// bloquea desde el origen EXTERNO — el flag es aditivo al convenio del prefijo, no un
    /// sustituto.
    #[tokio::test]
    async fn execute_at_external_rejects_manifest_flagged_internal_without_underscore() {
        let reg =
            registry_with_command_flagged("pricing", "pricing.insert_special_price_list", true);
        let ctx = ctx_admin();
        let err = execute_at(
            &DenyDb,
            &reg,
            "pricing.insert_special_price_list",
            &Params::new(),
            &ctx,
            0,
            &[],
            Origin::External,
        )
        .await
        .unwrap_err();
        assert!(matches!(err, RuntimeError::InternalCommand(_)), "got {err:?}");
    }

    /// Control: un command PÚBLICO normal (sin `_`, sin `internal: true`) sigue funcionando desde
    /// el origen EXTERNO — el gate no bloquea de más.
    #[tokio::test]
    async fn execute_at_external_allows_a_public_command() {
        let reg = registry_with_command("inventory", "inventory.products.create");
        let ctx = ctx_admin();
        let out = execute_at(
            &FakeDb,
            &reg,
            "inventory.products.create",
            &Params::new(),
            &ctx,
            0,
            &[],
            Origin::External,
        )
        .await
        .unwrap();
        assert_eq!(out["ok"], serde_json::json!(true));
    }
}
