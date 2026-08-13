//! Ejecución de commands declarativos (mutaciones) + emisión de eventos. ARQUITECTURA.md §4.
//! Tier 0/1 (SQL declarativo), Tier 2 (handler WASM vía `erplora-wasm-host`, §5.3 / §9.2)
//! y plugins **nativos first-party** (ADR-0009, `native.rs`).
use erplora_db::{DatabaseAdapter, Params, TxGatedOutcome};
use erplora_wasm_host::{Operation, Output, WasmHost};
use serde_json::{json, Value as Json};

use crate::elevation::Grants;
use crate::errors::{DemoLock, Result, RuntimeError};
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
///
/// [`Origin::Automation`] is the third door (ADR-0283 D2, hub#661): a **flow** executing one of
/// its steps. It is neither of the other two on purpose. It is not `External`, because there is
/// no caller and no role to check; and it is not `Internal`, because `Internal` means "the runtime
/// invoking itself on behalf of a module it already trusts" and would hand a flow every internal
/// command in the hub. What it has instead is its OWN authorisation — `_flow_grants`,
/// default-deny — and the same ban on internal commands that `External` has.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Origin {
    External,
    Internal,
    Automation,
}

/// **Does this payload satisfy the contract `name` declares?** — asked WITHOUT running anything.
///
/// It is the same question [`execute_at`] asks just before it touches the database, and it is the
/// same code answering it ([`validate_against`]): two implementations of "is this payload valid"
/// would eventually disagree, and the whole point of asking early is that the answer matches what
/// will happen later.
///
/// It exists because of hub#825. A write an `ai` step proposes under `policy: "manual"` becomes a row
/// a person reads hours later, and until now nothing checked the payload before writing that row: the
/// owner pressed «approve», the schema refused it, her decision was spent and the run died on a
/// proposal the hub could have refuted the moment the model made it. Under `policy: "auto"` the same
/// refusal already came back to the model as a tool result and the run survived (flows.md §14.9) —
/// this is what lets `manual` take that same path.
///
/// A command that is not in the registry is [`RuntimeError::CommandNotFound`], because "I cannot
/// judge this" and "this is fine" must not be the same answer. A command with no `schema` declares no
/// contract, so anything satisfies it — same as at execution.
pub fn validate_payload(registry: &Registry, name: &str, payload: &Params) -> Result<()> {
    let cmd = registry
        .get_command(name)
        .ok_or_else(|| RuntimeError::CommandNotFound(name.to_string()))?;
    validate_against(cmd, name, payload)
}

/// The one place the compiled schema of a command judges a payload.
fn validate_against(cmd: &RegisteredCommand, name: &str, payload: &Params) -> Result<()> {
    let Some(schema) = &cmd.schema else {
        return Ok(());
    };
    schema
        .validate(&Json::Object(payload.clone()))
        .map_err(|detail| RuntimeError::InvalidPayload {
            name: name.to_string(),
            detail,
        })
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
    grants: &Grants,
) -> Result<Json> {
    execute_at(
        db,
        registry,
        name,
        payload,
        ctx,
        0,
        &[],
        Origin::External,
        Some(grants),
    )
    .await
}

/// Como [`execute`] pero a profundidad `depth` (cascada), con `extra_ops` añadidos a la
/// transacción del command y con el [`Origin`] explícito de la llamada. El relay usa `extra_ops`
/// para insertar el marcador de entrega (`_event_delivery`) atómicamente con los efectos del
/// listener (idempotencia, §5.4).
///
/// `grants` are the live step-up approvals (hub#361), and only the EXTERNAL door passes them:
/// [`None`] means «no approval can be spent here, whatever the context carries». The internal
/// callers — the Outbox relay, the scheduler, the embedder's seeding entrypoint — pass `None`,
/// because an approval is a person authorising an action at the counter, never the runtime
/// authorising itself. That is the mechanism, not a second check that could disagree with one.
#[allow(clippy::too_many_arguments)] // mismo trato que persist_handler_output: firma interna del dispatcher
pub(crate) async fn execute_at(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    name: &str,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
    extra_ops: &[(String, Params)],
    origin: Origin,
    grants: Option<&Grants>,
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
    // CONSTRUIDO por el relay (`outbox::listener_ctx`) cuyo business_tax_id está vacío. El caso real: `sale.completed`
    // (depth 1) → `invoice.create_from_sale` (listener, depth 1) generaba facturas con issuer_nif
    // vacío → VeriFactu (`ingest_invoice`) no-op (no encadena, 0 registros, 0 QR). Enriquecemos
    // SIEMPRE que falte la identidad fiscal (la cascada con ctx ya enriquecido salta el get_all).
    let enriched_ctx;
    let ctx = if ctx.business_tax_id.is_empty() {
        let f = crate::settings::get_all(db, &ctx.hub_id)
            .await
            .unwrap_or(Json::Null);
        let get = |k: &str| f.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
        // «Can this hub issue?» — the OWN certificate if the business uploaded one, otherwise the
        // DELEGATED one ERPlora handed down (ADR-0202 §2.1, hub#319). One named function, shared
        // with `queries::execute_page` and with the ⛔ arm of `setup_status`, because a gate and a
        // checklist that disagree about this turn ⛔ into a lie in one direction or the other.
        // Degrading to `false` on error keeps the gate failing CLOSED.
        let has_cert = crate::certificate::can_sign(db, &ctx.hub_id)
            .await
            .unwrap_or(false);
        // What this hub OWES right now (ADR-0273 D2/D4): the mode plus the events the provider
        // taught the core start a fiscal chain. Both come from the core's own tables — never from
        // anything the caller sent. Degrading to `Unconfigured` with no triggers on a read error
        // keeps a failed query from inventing "nothing owed"; the gate below treats a missing mode
        // as unresolved, never as permission.
        let (fiscal_mode, fiscal_triggers, fiscal_providers) =
            match crate::fiscal_profile::ensure(db, &ctx.hub_id).await {
                Ok(p) => (
                    crate::fiscal_profile::determine_fiscal_mode(&p, registry, &ctx.hub_id),
                    p.fiscal_trigger_events.clone(),
                    crate::fiscal_profile::providers_of(registry, &p.country_code, &p.fiscal_system)
                        .iter()
                        .map(|m| m.id.clone())
                        .collect(),
                ),
                Err(_) => (
                    crate::fiscal_profile::FiscalMode::Unconfigured,
                    Vec::new(),
                    Vec::new(),
                ),
            };
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
            .with_certificate(has_cert)
            // What this hub OWES right now (ADR-0273 D2, hub#550): resolved here, from the core's
            // own tables and the registry, next to the identity and the certificate — never from
            // anything the caller sent. Degrading to `Unconfigured` on a read error keeps this
            // side of the enrichment from inventing "nothing owed" out of a failed query; nothing
            // gates on it yet (hub#556 does).
            .with_fiscal_mode(fiscal_mode, fiscal_triggers, fiscal_providers);
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
    //
    // hub#661: `Origin::Automation` is gated here too, and for the same reason. A flow is written
    // in an editor by whoever owns the hub; letting it name `module._helper` would hand it the
    // half of a module that exists precisely so that the public command controls when it runs.
    // Cross-module reactions with transformation are what flows are FOR — but through the public
    // surface, with a grant, not through the back door (ADR-0283 §7).
    if origin != Origin::Internal && cmd.def.is_internal(name) {
        return Err(RuntimeError::InternalCommand(name.to_string()));
    }

    // hub#775 — the AUTHORITATIVE `protects` guard. A module that declares a `protects` block over
    // the module this command belongs to can block it until a precondition holds (cash_register
    // blocks every `sales.*` command while `enable_cash_register` is on and no session is open).
    // This is the half the shell cannot be trusted with: a cosmetic route guard stops a click, but
    // a tampered client or a flow that names `sales.complete_sale` directly would complete a cash
    // sale with the drawer closed and the money would vanish from the reconciliation without an
    // error. The dispatcher is the only funnel every surface (HTTP, public API, assistant, outbox
    // relay, scheduler) goes through, so the check lives HERE.
    //
    // Cross-module by design: `cash_register` does not `depends_on` `sales`, it protects a ROUTE
    // the shell serves with `sales`. The protected module is parsed out of `route_setting`. The
    // guard runs BEFORE the RBAC gate so "the drawer is closed" is the signal a cashier sees, not
    // a permission refusal that masks it; and BEFORE the schema/payload work, because the guard is
    // a property of the command's owner, not of the payload the caller happened to send.
    //
    // `Origin::Internal` is exempt: the relay re-running `record_sale` after a `sale.completed`,
    // the scheduler and a seeding entrypoint are the runtime authorising itself, and a protects
    // guard would deadlock `cash_register.record_sale` (a listener of the very event the guard
    // would have blocked). The PUBLIC door — `commands::execute` — never passes `Internal`.
    if origin != Origin::Internal {
        enforce_protects(db, registry, &cmd.module_id, ctx).await?;
    }

    // El handler corre bajo el permiso del command que lo invoca (no re-eleva).
    //
    // hub#360 (paso 2b, rule 1): the same gate, with a refusal a MANAGER could approve reported as
    // `RequiresElevation` naming the missing permission instead of a flat `403`. It denies exactly
    // what `permissions::check` denied, so no command becomes reachable; what changes is only that
    // the caller can tell "ask the manager" from "this is not for you".
    //
    // hub#361 (rules 2 and 4) is the second half: an approval the manager already gave — the PIN
    // was verified HERE, never by the client — is spent right at the gate that refused. Spent, not
    // consulted: `Grants::spend` removes it, so the approval buys THIS action and not the next
    // one. And it does not add the permission to the context, so it opens this gate and nothing
    // else. Everything downstream (the fiscal precondition, the capability gate, a handler's
    // operations) sees the same cashier it always saw, plus a note of who approved.
    //
    // hub#362 (rule 3) is the third: the two attributions the approval exists to produce —
    // `created_by`, the cashier who was at the till, and `approved_by`, the manager who allowed
    // it — are written to the runtime's own record right here, BEFORE the command runs. Not by
    // the module: a module that never declares an `approved_by` column would lose the trace in
    // silence, and today that is every module in the catalogue.
    //
    // hub#661 (ADR-0283 D2): under `Origin::Automation` this gate is a DIFFERENT question, asked
    // of a different table. There is no user whose role could answer «may you do this», so the RBAC
    // check is replaced — not supplemented — by `_flow_grants`: does THIS flow have a live grant
    // for THIS command? Default-deny, and read **fresh on every step**, which is what makes
    // revoking a grant stop a run that is already in flight at its next step.
    //
    // Three properties come from putting it exactly here and nowhere else:
    //  · a flow inherits ÍNTEGROS the fiscal gates, the schema validation and the transactional
    //    outbox below — the reason the ADR insists automation goes through `execute_at` instead of
    //    getting its own dispatcher;
    //  · no elevation: a flow is `Principal::Machine`, and the executor passes `grants: None`, so
    //    there is no manager's PIN to spend and no `RequiresElevation` to offer nobody;
    //  · no privilege growth: the grant opens THIS command and nothing else. `ctx.permissions` —
    //    what the executor derived from the granted commands — is not consulted here at all; it
    //    only answers the questions asked downstream of this point.
    let elevated_ctx;
    let ctx = if origin == Origin::Automation {
        let Some(automation) = ctx.automation() else {
            // Automation with no flow identity is a bug in a caller, and the safe reading of a bug
            // in an authorisation path is "denied".
            return Err(RuntimeError::Domain {
                code: crate::flows::grants::ERR_GRANT_DENIED.to_string(),
                message: format!(
                    "`{name}` was invoked as automation without a flow identity; refused"
                ),
            });
        };
        crate::flows::grants::check_command_grant(db, &ctx.hub_id, &automation.flow_id, name)
            .await?;
        ctx
    } else {
        match permissions::check_command(registry, ctx, &cmd.def.permission) {
            Ok(()) => ctx,
            Err(RuntimeError::RequiresElevation { permission }) => {
                match spend_approval(grants, ctx, name, payload, &permission) {
                    Some((approved_by, fingerprint)) => {
                        // No receipt, no elevated action: swallowing this would make «break the
                        // audit» a way to run a manager-level command leaving no trace at all.
                        crate::elevation::record_spend(
                            db,
                            &ctx.hub_id,
                            name,
                            &permission,
                            &ctx.user_id,
                            &approved_by,
                            &fingerprint,
                        )
                        .await?;
                        elevated_ctx = ctx.clone().spent_approval_of(approved_by);
                        &elevated_ctx
                    }
                    // No approval, or one granted for another action, another cashier or another
                    // hub: all of them mean the same thing to the caller — ask the manager.
                    None => return Err(RuntimeError::RequiresElevation { permission }),
                }
            }
            Err(e) => return Err(e),
        }
    };

    // hub#632 — PATCH semantics. If this command is the `update` door of a record whose module
    // declares `patch: { read, key }`, a PARTIAL payload is completed BEFORE validation: the
    // dispatcher runs the declared read, keeps of the row only the keys the update's schema
    // accepts (the `get` returns columns the update refuses — `additionalProperties: false`), and
    // overlays the caller's keys on top. Explicit `null` overwrites; omitted preserves. The
    // merged object then goes through the SAME validation and SQL as always — a full payload
    // merges into itself, so nothing changes for today's callers. Without this, 46 updates in 20
    // modules require the whole object and a caller that fills one from memory corrupts a record
    // that carries a tax id.
    let patched;
    let payload = match patch_read_spec(registry, &cmd.module_id, name) {
        Some(patch) if cmd.schema.is_some() => {
            patched = merge_patch_read(db, registry, cmd, patch, payload, ctx).await;
            &patched
        }
        _ => payload,
    };

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
        validate_against(cmd, name, payload)?;
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

    // Fiscal precondition gate (hub#328, ADR-0203): SQL that stamps the business identity
    // does not run while that identity (and the certificate, when required) is missing.
    enforce_fiscal_precondition(registry, ctx, cmd.sql.iter().map(|s| s.as_str()))?;
    // ADR-0273 D4 (hub#556): la tercera rama. Distinto disparador que la de arriba —lo que aquí
    // dispara es que la transacción ABRA una cadena fiscal— y por eso hace falta: ADR-0203 dice en
    // sus propias consecuencias que una venta sin identidad SIGUE cerrándose, y lo que muere es el
    // listener de la factura, en dead-letter. Cobrado y sin factura.
    enforce_fiscal_capacity(
        ctx,
        &cmd.module_id,
        name.starts_with(crate::hub_users::CORE_NAMESPACE),
        &cmd.def.emit,
    )?;

    // Fiscal environment pin (ADR-0197 §4, hub#376): a demo hub never leaves the sandbox.
    enforce_fiscal_environment_pin(registry, cmd.sql.iter().map(|s| (s.as_str(), payload)))?;

    let bound = crate::system_params(payload, ctx);

    // SQL del command + INSERT en `_event_outbox` por cada evento emitido + `extra_ops` →
    // UNA transacción. Si commitea, los eventos quedan persistidos; si revierte, no hay evento.
    // (Decisión del humano #3: los commands `transaction:false` también se envuelven en tx para
    // garantizar la escritura atómica del outbox.)
    let sql_op_count = cmd.sql.len();
    let mut ops: Vec<(String, Params)> = cmd
        .sql
        .iter()
        .map(|sql| (sql.clone(), bound.clone()))
        .collect();
    for event in &cmd.def.emit {
        ops.push(outbox::insert_op(
            ctx,
            &cmd.module_id,
            event,
            &bound,
            depth + 1,
        ));
    }
    ops.extend_from_slice(extra_ops);

    // Gate de filas afectadas (hub#140). `min_affected_rows` es OPT-IN: `None` mantiene el
    // comportamiento de siempre (emite haya o no mutado). `Some(n)` exige que la suma de filas
    // afectadas por las sentencias `sql` del command sea `>= n` — contadas sobre las primeras
    // `sql_op_count` ops, NUNCA sobre los INSERT del outbox (que siempre afectan 1 y harían
    // inútil la gate). Se evalúa DENTRO de la tx vía `execute_tx_gated`: si no se cumple, la tx
    // entera revierte (ni mutación ni outbox) y devolvemos el error estable, SIN notificar al WS.
    //
    // hub#139: `expect_rows` is the translatable flavour of the same gate — same rollback
    // semantics, but the failure surfaces as `RuntimeError::Domain` with the module-declared
    // namespaced code instead of the generic `MinAffectedRows` variant. The installer already
    // guaranteed the two fields do not coexist and that the code lives in the module namespace.
    let expected = cmd.def.expect_rows.as_ref();
    let min = expected.map(|expect| expect.n).or(cmd.def.min_affected_rows);
    match db.execute_tx_gated(&ops, sql_op_count, min).await? {
        TxGatedOutcome::RolledBack { sql_counts } => {
            let min = min.expect("la gate sólo revierte con Some(min)");
            let affected: u64 = sql_counts.iter().sum();
            if let Some(expect) = expected {
                return Err(RuntimeError::Domain {
                    code: expect.error.clone(),
                    message: expect.message.clone().unwrap_or_else(|| {
                        // Generated fallback: states the rejection without leaking internals.
                        format!("the operation `{name}` could not be applied in the current state")
                    }),
                });
            }
            return Err(RuntimeError::MinAffectedRows {
                command: name.to_string(),
                required: min,
                affected,
                kind: crate::errors::affected_kind(affected, min),
            });
        }
        TxGatedOutcome::Committed { .. } => {}
    }

    // ADR-0273 D3 (hub#551): si esta transacción acaba de arrancar una cadena fiscal EN PRODUCCIÓN,
    // el go-live queda cerrado para siempre. Se sella DESPUÉS del commit y solo si commiteó —
    // sellar algo que revirtió cerraría la vuelta atrás por una venta que no existió.
    seal_first_record_if_fiscal(db, ctx, &cmd.def.emit).await;

    // Notificación al WS (UI en vivo), tras commit y solo si commiteó. Efímera; la entrega
    // durable a listeners la hace el relay desde el outbox. El emisor viaja con el evento
    // (hub#529): es lo único que el canal puede creerse para filtrar por módulo.
    for event in &cmd.def.emit {
        events::notify_sink(
            registry,
            crate::registry::EventSource::Module(&cmd.module_id),
            event,
            &bound,
        );
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
/// # Las tres reglas (ADR-0069 §1) + la cuarta (hub#701)
///
/// 1. **Alcance por DEPENDENCIA, no por permiso.** Solo queries del propio módulo o de los que
///    declara en `depends_on`. Un módulo no puede leerle las tablas a otro con el que no tiene
///    contrato — la lista de queries permitidas la fija el manifest, no el caller.
/// 2. **Contexto de SISTEMA.** No se re-gatea por el permiso del usuario: el permiso del *command*
///    ya se comprobó, y las reads son contrato vouched por el autor del módulo. Un empleado de POS
///    sin `taxes.view_tax` igual necesita los tipos para poder cobrar. Se conserva el `hub_id` del
///    caller (el tenant NO es negociable) y se usa el wildcard de permisos.
/// 3. **Fallo GRACEFUL (defecto).** Una read que no resuelve se **omite** (no aborta el command).
///    Cobrar es lo último que puede romperse en un TPV: si `taxes` está raro, el handler degrada
///    a su fallback, pero la venta se cierra.
/// 4. **`required` (hub#701, opt-in).** Una read marcada `required` que no resuelve **aborta**
///    el command con `ReadUnavailable`. Es lo que no admite adivinar: el impuesto. Sin esto, un
///    catálogo vacío (la read falló) es indistinguible de «este hub no tiene reglas», y el handler
///    cobra el porcentaje que propone el navegador — exactamente lo que sales#21 prohíbe.
async fn preload_reads(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    ctx: &RequestContext,
    payload: &erplora_db::Params,
) -> Result<Json> {
    if cmd.def.reads.is_empty() {
        return Ok(Json::Object(Default::default()));
    }

    // Regla 1 — alcance: el propio módulo + sus `depends_on` declarados en el manifest.
    let deps: Vec<String> = registry
        .installed
        .iter()
        .find(|m| m.id == cmd.module_id)
        .map(|m| m.depends_on.iter().map(|d| d.id.clone()).collect())
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

        match crate::queries::execute(db, registry, name, &params, &sys).await {
            Ok(rows) => {
                out.insert(name.to_string(), Json::Array(rows));
            }
            Err(e) => {
                // Regla 4 (hub#701): una read OBLIGATORIA aborta. Sin esto, el handler recibe un
                // catálogo vacío indistinguible de «no hay reglas» y degrada al porcentaje del
                // payload — que es justo lo que no puede admitir adivinar (el impuesto).
                if read.is_required() {
                    return Err(RuntimeError::ReadUnavailable {
                        query: name.to_string(),
                    });
                }
                // Regla 3 — graceful: si la query falla (no existe, SQL roto, tabla ausente),
                // se omite. Cobrar es lo último que puede romperse en un TPV.
                eprintln!("⚠ reads: `{name}` falló ({e}) → se omite; el handler degradará");
            }
        }
    }
    Ok(Json::Object(out))
}

/// hub#775 — the AUTHORITATIVE `protects` guard.
///
/// A module that declares a `protects` block (see [`crate::manifest::ProtectsDef`]) over the module
/// `protected_module_id` can refuse a command while a precondition is unmet. The canonical case is
/// `cash_register`: while `enable_cash_register` is on and `cash_register.current_session` returns
/// no row (no drawer is open), every `sales.*` command is refused — not just the POS click that
/// opened the screen. The shell renders `erp-cashregister-open` instead of mounting the POS; this
/// function is the half the shell cannot be trusted with, because a client that bypasses the route
/// guard (a flow, a tampered SPA, a direct `POST /api/command`) would otherwise complete a cash sale
/// whose movement the `_movement_for_open_session.sql` INSERT…SELECT silently drops.
///
/// # How it resolves
///
/// For each `protects` block declared by an INSTALLED and ACTIVE module:
/// 1. the `settings_query` runs in a SYSTEM context (same `hub_id`, no permission re-check — the
///    guard is a contract vouched by the declaring module, the same rule as `reads`, ADR-0069 §1
///    rule 2);
/// 2. if its first row's `enabled_setting` column is true, the guard is ARMED;
/// 3. if the `route_setting` column does not point at `/m/<protected_module_id>`, the guard does
///    not apply to this command (a future guard could protect a different module's route);
/// 4. the `guard_query` runs in the same system context, and if `expect` is not satisfied (today:
///    `non_empty` with zero rows) the command is refused with [`RuntimeError::ProtectsGuard`].
///
/// # Why it degrades OPEN
///
/// A guard that cannot be evaluated (the declaring module is gone, the settings query fails, the
/// columns are missing) does NOT block the sale: a till that stops ringing over a broken read is a
/// worse failure than one that lets a sale through. The only refusal is a guard that evaluated
/// cleanly and found the precondition unmet — exactly the case `cash_register` ships. Compare with
/// `preload_reads`, which degrades the same way for the same reason.
pub(crate) async fn enforce_protects(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    protected_module_id: &str,
    ctx: &RequestContext,
) -> Result<()> {
    for manifest in &registry.installed {
        if !registry.is_active(&manifest.id) {
            continue;
        }
        for guard in &manifest.protects {
            // System context: same hub (tenant is non-negotiable), wildcard permissions. The
            // guard is a module-authored contract, not a user action — same rule as `reads`.
            let sys = RequestContext::new(&ctx.hub_id, &ctx.user_id, ["*".to_string()]);

            // (1) the settings row. Degrade open on any failure — see "Why it degrades OPEN".
            let settings = match crate::queries::execute(db, registry, &guard.settings_query, &Params::new(), &sys).await {
                Ok(rows) => rows.into_iter().next().unwrap_or(Json::Null),
                Err(e) => {
                    eprintln!(
                        "⚠ protects: `{}` settings_query `{}` failed ({e}) → guard skipped (open)",
                        manifest.id, guard.settings_query
                    );
                    continue;
                }
            };

            // (2) armed? The settings row may be missing entirely (a hub that never configured the
            // declaring module) or the column may be absent on an older schema — both mean OFF.
            //
            // Postgres stores booleans as `INTEGER` (0/1) in several module schemas
            // (`cash_register_settings.enable_cash_register` among them), and the driver surfaces
            // those as a JSON NUMBER, not a JSON BOOL — so `as_bool()` alone misses them. The same
            // `as_bool().unwrap_or_else(|| as_i64() == 1)` shape `hub_users::truthy` uses keeps the
            // reading honest for both representations.
            let armed = settings
                .get(&guard.enabled_setting)
                .map(|v| v.as_bool().unwrap_or_else(|| v.as_i64().unwrap_or(0) != 0))
                .unwrap_or(false);
            if !armed {
                continue;
            }

            // (3) does this guard protect the module the command belongs to? `route_setting`'s
            // value is `/m/<module>`; a guard whose route does not parse or points elsewhere does
            // not apply to THIS command.
            let route_value = settings
                .get(&guard.route_setting)
                .and_then(|v| v.as_str())
                .unwrap_or("");
            if guard.protected_module(route_value) != Some(protected_module_id) {
                continue;
            }

            // (4) is the precondition met? Degrade open on a query failure — the alternative is a
            // till that refuses every sale because a read broke.
            let rows = match crate::queries::execute(db, registry, &guard.guard_query, &Params::new(), &sys).await {
                Ok(rows) => rows,
                Err(e) => {
                    eprintln!(
                        "⚠ protects: `{}` guard_query `{}` failed ({e}) → guard skipped (open)",
                        manifest.id, guard.guard_query
                    );
                    continue;
                }
            };
            let satisfied = match guard.expect {
                crate::manifest::ProtectsExpect::NonEmpty => !rows.is_empty(),
            };
            if satisfied {
                continue;
            }

            return Err(RuntimeError::ProtectsGuard {
                declaring_module: manifest.id.clone(),
                protected_module: protected_module_id.to_string(),
                guard_query: guard.guard_query.clone(),
            });
        }
    }
    Ok(())
}

/// The `patch` contract of `command`, if the module that owns it declares one (hub#632): the
/// record entry whose `update` names this command, carrying `patch: { read, key }`.
fn patch_read_spec<'r>(
    registry: &'r Registry,
    module_id: &str,
    command: &str,
) -> Option<&'r crate::manifest::PatchDef> {
    registry
        .installed
        .iter()
        .find(|m| m.id == module_id)?
        .records
        .values()
        .find(|record| record.update.as_deref() == Some(command))?
        .patch
        .as_ref()
}

/// Completes a (possibly partial) update payload from the record's declared read (hub#632).
///
/// Merge rules — the contract of the issue, verbatim:
///  - the read's row is kept ONLY for the keys the update's schema declares (`get` returns
///    columns like `id`/`sku`/`stock` the update refuses under `additionalProperties: false`);
///  - the caller's keys always win, **including an explicit `null`** (null overwrites/clears;
///    omitting preserves — the two are different things again);
///  - the read runs in a system context (same `hub_id`, wildcard permissions), the same rule as
///    `reads` (ADR-0069) and `protects`: it is a module-authored contract, not a user action, and
///    the update's own permission was already checked at the gate.
///
/// Degrades OPEN on a broken read or a missing row: the caller's payload goes to validation as
/// sent, and the schema gives its usual answer (a partial payload of a missing record is refused
/// as incomplete — nothing is invented, nothing is written). Same direction as `preload_reads`.
async fn merge_patch_read(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    cmd: &RegisteredCommand,
    patch: &crate::manifest::PatchDef,
    payload: &Params,
    ctx: &RequestContext,
) -> Params {
    let Some(key_value) = payload.get(&patch.key) else {
        return payload.clone(); // No key, nothing to read: validation will say what is missing.
    };
    let mut read_params = Params::new();
    read_params.insert(patch.key.clone(), key_value.clone());
    let sys = RequestContext::new(&ctx.hub_id, &ctx.user_id, ["*".to_string()]);
    let row = match crate::queries::execute(db, registry, &patch.read, &read_params, &sys).await {
        Ok(rows) => rows.into_iter().next(),
        Err(e) => {
            eprintln!(
                "⚠ patch: `{}` read `{}` failed ({e}) → payload validated as sent",
                cmd.module_id, patch.read
            );
            None
        }
    };
    let Some(Json::Object(row)) = row else {
        return payload.clone();
    };
    let Some(props) = cmd
        .schema
        .as_ref()
        .and_then(|schema| schema.raw.get("properties"))
        .and_then(|p| p.as_object())
    else {
        return payload.clone();
    };
    let mut merged = Params::new();
    for key in props.keys() {
        if let Some(value) = row.get(key) {
            merged.insert(key.clone(), value.clone());
        }
    }
    for (key, value) in payload {
        merged.insert(key.clone(), value.clone());
    }
    merged
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
    let reads = preload_reads(db, registry, cmd, ctx, payload).await?;
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

    let output = call_wasm_off_thread(bytes, &handler.function, input).await?;

    persist_handler_output(
        db, registry, cmd, payload, ctx, depth, extra_ops, &output, &new_ids,
    )
    .await
}

/// Margen (ms) que el host espera POR ENCIMA del timeout interno del guest antes de rendirse.
///
/// El corte real lo da wasmtime (interrupción por epoch dentro de `WasmHost`). Este margen cubre
/// la (de)serialización y el arranque de la llamada, y actúa de red por si la interrupción no
/// llegara: el command devuelve error en vez de esperar para siempre.
const WASM_CALL_GRACE_MS: u64 = 2_000;

/// Invoca el handler WASM **fuera del worker async** y con tope de tiempo (hub#241).
///
/// # Por qué
///
/// `WasmHost::call` es una llamada **bloqueante** a wasmtime. Se hacía directamente dentro del
/// worker de Tokio que atendía la petición: un handler que no terminaba (`while(1){}`, o
/// simplemente lento) se quedaba con ese worker y el runtime del TPV dejaba de responder hasta
/// reiniciar el proceso. Ahora:
///
///  1. compilación y llamada van en `spawn_blocking` (pool de hilos bloqueantes: no tocan los
///     workers async);
///  2. el guest lleva sus propios topes de fuel/memoria/reloj (ver `erplora_wasm_host`);
///  3. y el host además espera la LLAMADA con `timeout` (tope del guest + [`WASM_CALL_GRACE_MS`]),
///     así que el command **siempre** vuelve, con `Ok` o con error.
///
/// # El reloj del host solo corre durante la llamada
///
/// La **compilación** del plugin (fase 1) queda FUERA del `timeout`: es código del host
/// (wasmtime/cranelift), termina por construcción y su duración depende de la carga de la
/// máquina, no del guest. Cuando compartía presupuesto con la llamada, bajo carga (varios
/// commands WASM concurrentes, cada uno recompilando su módulo) la compilación se comía el
/// margen entero y handlers legítimos fallaban con "no respondió" sin haber ejecutado ni una
/// instrucción del guest. El anti-cuelgue de hub#241 no lo necesita: el guest no ejecuta nada
/// durante la compilación (fuel + epoch acotan la fase 2, que es la única que un módulo
/// malicioso puede alargar a voluntad).
async fn call_wasm_off_thread(bytes: &[u8], function: &str, input: Json) -> Result<Output> {
    let limits = erplora_wasm_host::WasmLimits::from_env();
    let wasm = bytes.to_vec();

    // Fase 1 — compilar (sin reloj del guest). `extism::Plugin` es Send: puede cruzar de un
    // hilo bloqueante a otro.
    let mut host = tokio::task::spawn_blocking(move || WasmHost::from_bytes_with_limits(&wasm, limits))
        .await
        .map_err(|join_err| {
            RuntimeError::Wasm(format!("el handler `{function}` abortó al cargar: {join_err}"))
        })?
        .map_err(|e| RuntimeError::Wasm(e.to_string()))?;

    // Fase 2 — llamar, con tope.
    let func = function.to_string();
    let join = tokio::task::spawn_blocking(move || host.call(&func, &input));

    let wait = std::time::Duration::from_millis(limits.timeout_ms.saturating_add(WASM_CALL_GRACE_MS));
    match tokio::time::timeout(wait, join).await {
        Ok(Ok(Ok(output))) => Ok(output),
        Ok(Ok(Err(e))) => Err(RuntimeError::Wasm(e.to_string())),
        // El hilo bloqueante murió (panic del guest host-side): no se propaga el panic al server.
        Ok(Err(join_err)) => Err(RuntimeError::Wasm(format!(
            "el handler `{function}` abortó: {join_err}"
        ))),
        // La interrupción interna no llegó a tiempo: se abandona la espera (el hilo bloqueante
        // acabará solo cuando wasmtime lo interrumpa) y el command falla con un error claro.
        Err(_) => Err(RuntimeError::Wasm(format!(
            "el handler `{function}` no respondió en {} ms: se aborta el command",
            wait.as_millis()
        ))),
    }
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
    // Lote de ids que el host generó y entregó al handler. Al llamante solo se le devuelven los
    // que las operaciones del handler CONSUMIERON (hub#776): un id del lote que ninguna operación
    // referencia no nombra ninguna fila, y devolver los 256 convertía cada toque del TPV en una
    // respuesta de varios KB de UUIDs fantasma. Por convención `new_ids[0]` es la entidad
    // principal (§5.3) — se preserva porque el orden del lote se mantiene al filtrar.
    new_ids: &[Json],
) -> Result<Json> {
    // hub#139: a business rejection is a normal guest output, not a WASM trap. It is checked
    // BEFORE looking at any intention: even a buggy guest that returns `error` together with
    // operations/events cannot persist partial effects. The code is validated against the
    // module's own namespace — an invalid or foreign code is a broken guest contract (`Wasm`),
    // never a `Domain` the UI would translate, so a module cannot spoof another module's ABI.
    if let Some(error) = &output.error {
        if !crate::errors::valid_domain_code(&cmd.module_id, &error.code)
            || error.message.chars().count() > 500
        {
            return Err(RuntimeError::Wasm(format!(
                "handler of module `{}` returned an invalid domain error code `{}`",
                cmd.module_id, error.code
            )));
        }
        return Err(RuntimeError::Domain {
            code: error.code.clone(),
            message: error.message.clone(),
        });
    }

    // Valida + resuelve cada operación a su(s) SQL contra los commands del MISMO módulo.
    let mut tx_ops: Vec<(String, Params)> = Vec::new();
    for op in &output.operations {
        let sqls = validate_operation(registry, &cmd.module_id, op)?;
        let bound = crate::system_params(&op.params, ctx);
        for sql in sqls {
            tx_ops.push((sql, bound.clone()));
        }
    }

    // Fiscal precondition gate (hub#328, ADR-0203) on the SQL the handler RESOLVED to —
    // the handler itself is pure (no DB side effects), so rejecting here still means
    // nothing was written. Same gate as the declarative path in `execute_at`.
    enforce_fiscal_precondition(registry, ctx, tx_ops.iter().map(|(sql, _)| sql.as_str()))?;
    // ADR-0273 D4 (hub#556): el mismo embudo para las operaciones que resuelve un handler
    // WASM/nativo — que es por donde pasan los listeners del relay del Outbox y las tareas
    // programadas. Un gate que solo cubriera el camino declarativo dejaría fuera justo la mitad por
    // la que viaja la cadena fiscal.
    enforce_fiscal_capacity(ctx, &cmd.module_id, false, &cmd.def.emit)?;

    // Fiscal environment pin (ADR-0197 §4, hub#376) on what the handler RESOLVED to: the native
    // VeriFactu engine emits its own operations, so the pin has to see the params it bound — not
    // the ones the caller sent.
    enforce_fiscal_environment_pin(registry, tx_ops.iter().map(|(sql, p)| (sql.as_str(), p)))?;

    // Las intenciones + los INSERT de outbox (eventos declarados por el command + eventos
    // devueltos por el handler) + `extra_ops` (marcador de entrega del relay) → UNA transacción.
    let declared_payload = crate::system_params(payload, ctx);
    for event in &cmd.def.emit {
        tx_ops.push(outbox::insert_op(
            ctx,
            &cmd.module_id,
            event,
            &declared_payload,
            depth + 1,
        ));
    }
    // Los eventos que devuelve el handler se validan contra el `module.json` ANTES de encolarlos
    // (hub#240): un nombre no declarado hace fallar el command entero — no se encola en silencio.
    let mut handler_events: Vec<(String, Params)> = Vec::with_capacity(output.events.len());
    for ev in &output.events {
        validate_handler_event(registry, &cmd.module_id, &ev.name)?;
        // `*.reminder.due` llega al listener-host de `host.notify`: además de declarada, la
        // capability tiene que estar CONCEDIDA por el usuario (default-deny, ADR-0079).
        if ev.name.trim().ends_with(outbox::REMINDER_DUE_SUFFIX) {
            crate::capabilities::require(
                db,
                registry,
                &cmd.module_id,
                &ctx.hub_id,
                crate::manifest::CapabilityKind::Notify,
            )
            .await?;
        }
        let payload = match &ev.payload {
            Json::Object(map) => map.clone(),
            other => {
                let mut m = Params::new();
                m.insert("value".into(), other.clone());
                m
            }
        };
        handler_events.push((ev.name.clone(), payload));
    }
    for (name, payload) in &handler_events {
        tx_ops.push(outbox::insert_op(
            ctx,
            &cmd.module_id,
            name,
            payload,
            depth + 1,
        ));
    }
    tx_ops.extend_from_slice(extra_ops);
    db.execute_tx(&tx_ops).await?;

    // Notificación al WS (UI en vivo) tras commit; entrega durable a listeners = relay. Los
    // eventos del handler salen con el módulo del command (hub#529) — que es también el único
    // namespace en el que hub#240 les deja llamarse.
    let source = crate::registry::EventSource::Module(&cmd.module_id);
    for event in &cmd.def.emit {
        events::notify_sink(registry, source, event, &declared_payload);
    }
    for (name, payload) in &handler_events {
        events::notify_sink(registry, source, name, payload);
    }

    Ok(json!({
        "ok": true,
        "operations": output.operations.len(),
        "new_ids": consumed_new_ids(output, new_ids),
    }))
}

/// The batch ids the handler's operations actually CONSUMED, in batch order (hub#776).
///
/// The host is the only id authority (§5.3): the guest cannot mint UUIDs, it can only take them
/// from `context.new_ids`. So an id of the batch names a materialised row **iff** some operation's
/// params reference it — anywhere, including nested structures (order lines carry theirs inside
/// arrays of objects). Scanning the params is therefore a complete and safe derivation: it needs
/// no guest-sdk change and no republish of the 21 modules with handlers.
///
/// Properties the callers rely on:
///  - **batch order is preserved**, so `new_ids[0]` keeps being the main entity for every caller
///    that already reads it (handlers take ids from the front of the batch by convention);
///  - an id referenced by two operations is reported **once** (it names one row);
///  - a handler that consumed nothing answers with an empty list — no phantom ids.
fn consumed_new_ids(output: &Output, new_ids: &[Json]) -> Vec<Json> {
    use std::collections::HashSet;

    fn scan<'v>(value: &'v Json, batch: &HashSet<&'v str>, used: &mut HashSet<&'v str>) {
        match value {
            Json::String(s) => {
                if let Some(&id) = batch.get(s.as_str()) {
                    used.insert(id);
                }
            }
            Json::Array(items) => {
                for item in items {
                    scan(item, batch, used);
                }
            }
            Json::Object(map) => {
                for item in map.values() {
                    scan(item, batch, used);
                }
            }
            _ => {}
        }
    }

    let batch: HashSet<&str> = new_ids.iter().filter_map(Json::as_str).collect();
    let mut used: HashSet<&str> = HashSet::new();
    for op in &output.operations {
        for value in op.params.values() {
            scan(value, &batch, &mut used);
        }
    }
    new_ids
        .iter()
        .filter(|id| id.as_str().is_some_and(|s| used.contains(s)))
        .cloned()
        .collect()
}

/// Valida el **nombre de un evento devuelto por un handler** contra lo declarado en el
/// `module.json` del módulo, ANTES de encolarlo en el outbox (hub#240).
///
/// # Por qué existe
///
/// Los eventos del `Output` de un handler se encolaban tal cual: el handler ponía el nombre y el
/// relay se lo entregaba a los listeners de **otros** módulos y —si acababa en `.reminder.due`— al
/// **listener-host de `host.notify`**, que envía email/SMS/WhatsApp. Es decir: un módulo alcanzaba
/// un primitivo de envío externo (coste real, datos del cliente saliendo del hub) sin declarar la
/// capability ni pasar por `capabilities::enforce`, que es justo lo que `module-capabilities.md`
/// dice que nunca puede ocurrir: *una capability solo significa algo si se comprueba en Rust*.
///
/// # Reglas
///
/// 1. **Declarado** en `events.emits` del manifest o en el `emit` de cualquier command del propio
///    módulo → permitido.
/// 2. **`*.reminder.due`** (el disparador de `host.notify`) → el módulo DEBE declarar la capability
///    `notify`. El *grant* del usuario se comprueba aparte, contra la BD
///    ([`crate::capabilities::require`]), tanto al encolar como al entregar.
/// 3. **Namespace ajeno**: el primer segmento no puede ser el id de OTRO módulo instalado — un
///    módulo del marketplace no emite `verifactu.record.transmitted` en nombre de nadie.
/// 4. Si el módulo **declara** `events.emits`, queda en **modo estricto**: cualquier nombre fuera de
///    la lista se rechaza. Si no la declara (todos los manifests publicados hoy), se tolera su
///    propio namespace y los namespaces de nadie, con un aviso — la migración a estricto es una
///    decisión del humano, no un corte silencioso del TPV.
pub(crate) fn validate_handler_event(
    registry: &Registry,
    handler_module_id: &str,
    event: &str,
) -> Result<()> {
    let name = event.trim();
    if name.is_empty() {
        return Err(RuntimeError::EventNotDeclared {
            module: handler_module_id.to_string(),
            event: event.to_string(),
        });
    }
    let denied = || RuntimeError::EventNotDeclared {
        module: handler_module_id.to_string(),
        event: name.to_string(),
    };

    let manifest = registry
        .installed
        .iter()
        .find(|m| m.id == handler_module_id);

    // Regla 2 — el disparador de `host.notify` exige la capability declarada, pase lo que pase.
    if name.ends_with(crate::outbox::REMINDER_DUE_SUFFIX) {
        let declares_notify = manifest
            .map(|m| m.requests_capability(crate::manifest::CapabilityKind::Notify))
            .unwrap_or(false);
        if !declares_notify {
            return Err(RuntimeError::CapabilityDenied {
                module: handler_module_id.to_string(),
                capability: crate::manifest::CapabilityKind::Notify.as_str().to_string(),
            });
        }
    }

    // Regla 1 — declarado (manifest `events.emits` o `emit` de un command del módulo).
    let declared_in_manifest = manifest
        .map(|m| m.events.emits.iter().any(|e| e == name))
        .unwrap_or(false);
    let declared_in_commands = registry
        .commands
        .values()
        .filter(|c| c.module_id == handler_module_id)
        .any(|c| c.def.emit.iter().any(|e| e == name));
    if declared_in_manifest || declared_in_commands {
        return Ok(());
    }

    // Regla 3 — no suplantar el namespace de otro módulo instalado.
    let namespace = name.split('.').next().unwrap_or_default();
    let owned_by_other = registry
        .installed
        .iter()
        .any(|m| m.id == namespace && m.id != handler_module_id);
    if owned_by_other {
        return Err(denied());
    }

    // Regla 4 — modo estricto si el módulo declaró sus eventos; si no, compat + aviso.
    let strict = manifest.map(|m| !m.events.emits.is_empty()).unwrap_or(false);
    if strict {
        return Err(denied());
    }
    if namespace != handler_module_id {
        eprintln!(
            "⚠ eventos: el módulo `{handler_module_id}` emite `{name}` fuera de su namespace y \
             sin declararlo en `events.emits` — decláralo (hub#240)"
        );
    }
    Ok(())
}

/// Spends the step-up approval that authorises `command(payload)` for this context, if there is
/// one, returning the `hub_user.id` that approved and the **fingerprint** the grant was matched
/// against (hub#361, hub#362).
///
/// Everything the answer depends on is server-side: the token is a **lookup key** into the
/// runtime's own store and the binding is rebuilt here from the context, the command name and the
/// payload as sent. The client contributes the key and nothing else — it cannot state the
/// permission, the cashier, the hub or what was approved.
fn spend_approval(
    grants: Option<&Grants>,
    ctx: &RequestContext,
    command: &str,
    payload: &Params,
    permission: &str,
) -> Option<(String, String)> {
    // The token comes from the CONTEXT and from nowhere else — the HTTP layer put it there from
    // `X-Elevation-Token`. Reading it from `payload` instead would be the whole vulnerability:
    // the body of a command is caller-controlled data that already gets validated, defaulted and
    // bound into SQL, and it must never carry authority (`a_real_token_smuggled_in_the_payload_
    // grants_nothing` pins that).
    //
    // ⚠️ Mutation note: turning this `?` into `.unwrap_or("")` is an EQUIVALENT mutant and no
    // test can kill it. An empty string is not a token any path can produce — `new_token` always
    // emits 64 hex chars and `auth::elevation_token` drops an empty header — so the lookup would
    // simply miss and return `None`, exactly as the short circuit does. It is kept as `?` because
    // "no token, no question asked" is cheaper and says what it means.
    let token = ctx.elevation_token.as_deref()?;
    let grants = grants?;
    // The fingerprint of the payload the manager was shown is computed ONCE and handed back with
    // the approver, so the receipt hub#362 writes names the very same action the grant was
    // matched against. Recomputing it at the call site would let the two drift apart — the record
    // would then describe an action nobody actually approved.
    let fingerprint = crate::elevation::fingerprint(payload);
    let approved_by = grants.spend(
        token,
        &crate::elevation::Binding {
            hub_id: ctx.hub_id.clone(),
            requester: ctx.user_id.clone(),
            command: command.to_string(),
            fingerprint: fingerprint.clone(),
            permission: permission.to_string(),
        },
    )?;
    Some((approved_by, fingerprint))
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

// ─── Fiscal precondition gate (hub#328, ADR-0203) ────────────────────────────

/// The `system_params` params that stamp the hub's BUSINESS identity into a document
/// (ADR-0061). SQL that references any of them is, by definition, resolving the fiscal
/// issuer of a document — the structural marker the fiscal precondition gate keys on.
/// (`:business_address` is deliberately out: the decision requires name ∧ tax id.)
const FISCAL_IDENTITY_PARAMS: [&str; 2] = ["business_tax_id", "business_legal_name"];

/// Does `sql` reference the named parameter `:{param}` as a whole token? Boundary-checked
/// on both sides so `:business_tax_id_verified` (another param) and `x::business_tax_id`
/// (a Postgres cast, outside the ERPlora SQL subset anyway) do not count.
fn references_param(sql: &str, param: &str) -> bool {
    let needle = format!(":{param}");
    let bytes = sql.as_bytes();
    let mut start = 0;
    while let Some(pos) = sql[start..].find(&needle) {
        let abs = start + pos;
        let end = abs + needle.len();
        let next_is_ident = sql[end..]
            .chars()
            .next()
            .is_some_and(|c| c.is_ascii_alphanumeric() || c == '_');
        let prev_is_colon = abs > 0 && bytes[abs - 1] == b':';
        if !next_is_ident && !prev_is_colon {
            return true;
        }
        start = end;
    }
    false
}

/// Fiscal precondition gate (hub#328, ADR-0203): a transaction whose SQL stamps the hub's
/// business identity (any statement referencing [`FISCAL_IDENTITY_PARAMS`]) only runs when
/// that identity exists. Otherwise `COALESCE(NULLIF(:issuer_nif,''), :business_tax_id)`
/// (invoice) resolves empty + empty to an issued document with a BLANK issuer — and
/// VeriFactu chains from it (ADR-0189: an accepted record is never re-sent). Preconditions:
///
/// 1. `business_legal_name` ∧ `business_tax_id` set in `hub_settings` (ADR-0061 source);
/// 2. the business certificate loaded, while any INSTALLED module declares the
///    `certificate` capability (today: verifactu) — installed even if inactive: emitting
///    without it would strand documents outside the fiscal chain.
///
/// Structural and default-deny: no manifest flag a module could forget, no hardcoded
/// module ids — the trigger is the SQL using the injected identity itself, so the runtime
/// stays business-free. Both dispatch paths funnel through it (declarative Tier 0/1 in
/// [`execute_at`], handler-resolved operations in [`persist_handler_output`]) BEFORE
/// anything touches the DB. No modes, no toggles.
fn enforce_fiscal_precondition<'a>(
    registry: &Registry,
    ctx: &RequestContext,
    mut sqls: impl Iterator<Item = &'a str>,
) -> Result<()> {
    let stamps_identity =
        sqls.any(|sql| FISCAL_IDENTITY_PARAMS.iter().any(|p| references_param(sql, p)));
    if !stamps_identity {
        return Ok(());
    }
    let mut missing: Vec<&'static str> = Vec::new();
    if ctx.business_legal_name.trim().is_empty() {
        missing.push("business_legal_name");
    }
    if ctx.business_tax_id.trim().is_empty() {
        missing.push("business_tax_id");
    }
    if !ctx.has_certificate
        && registry
            .installed
            .iter()
            .any(|m| m.capabilities.certificate.is_some())
    {
        missing.push("certificate");
    }
    if missing.is_empty() {
        Ok(())
    } else {
        Err(RuntimeError::FiscalPrecondition { missing })
    }
}

/// Seals `first_record_at` when a transaction that STARTS a fiscal chain has just committed while
/// the hub files for real (ADR-0273 D3, hub#551).
///
/// This is what makes the go-live one-way **without asking any module anything**. The alternative
/// —the provider reporting back that it filed— would put the irreversible half of a fiscal system
/// in the hands of a module remembering to speak: one that forgets leaves the toggle reversible for
/// ever, which is the hole this whole ADR exists to close.
///
/// The core does not need to be told. It already knows two things by itself: that the profile is in
/// `production`, and that the events this command emits are among the ones the provider taught it
/// start a fiscal chain while it was healthy ([`crate::fiscal_profile::FiscalProfile::fiscal_trigger_events`]).
///
/// **Best-effort on the read, strict on the meaning.** A failure here is logged and never turns a
/// committed sale into an error — the money is already taken and the record is already on its way;
/// refusing afterwards would help nobody. The seal is idempotent, so the next fiscal transaction
/// catches up.
async fn seal_first_record_if_fiscal(db: &dyn DatabaseAdapter, ctx: &RequestContext, emitted: &[String]) {
    if emitted.is_empty() || ctx.fiscal_mode != Some(crate::fiscal_profile::FiscalMode::Active) {
        return; // Nothing emitted, or this hub is not filing for real: nothing to seal.
    }
    let profile = match crate::fiscal_profile::load(db, &ctx.hub_id).await {
        Ok(Some(p)) => p,
        _ => return,
    };
    if profile.environment != crate::fiscal_profile::ENV_PRODUCTION
        || !emitted
            .iter()
            .any(|e| profile.fiscal_trigger_events.iter().any(|t| t == e))
    {
        return;
    }
    if let Err(e) = crate::fiscal_profile::stamp_first_record(db, &ctx.hub_id).await {
        eprintln!("⚠ fiscal: no se pudo sellar el primer registro en producción (ADR-0273): {e}");
    }
}

/// **The third branch of the fiscal gate: the core REFUSES** (ADR-0273 D4, hub#556).
///
/// The two branches that already existed key on the hub's *identity* being stamped (ADR-0203).
/// This one keys on something else, and it has to, because ADR-0203 says so in its own
/// consequences: **a sale without identity still closes** — what gets rejected is the
/// `invoice.create_from_sale` listener, which retries and dies in dead-letter. Money taken, invoice
/// dead in a queue. So a second trigger is needed, and this is it.
///
/// **The trigger is an event the CORE learnt, not a flag a module declares.** While a provider of
/// the hub's regime was healthy, the core wrote down the events it listened to (hub#550); here it
/// asks whether this transaction would enqueue one of them. That is what makes it fail-closed:
/// derive it live from the registry and an uninstalled provider means no listener, no trigger, and
/// a till that sells happily. Opt-in flags in the manifest were rejected for the same reason
/// (ADR-0203): a module that "forgets" would emit without a gate.
///
/// Two hardnesses, deliberately different:
///
/// - **`BLOCKED`** (recoverable) rejects only the **fiscal chain** — the transactions that would
///   start one. The rest of the till keeps working. Killing the whole hub because a module failed
///   to mount is disproportionate and pushes the user to work around us.
/// - **`CLOSED`** (the owner's decision, irreversible) is **default-deny on writes**, with two
///   exceptions the core can classify by itself without naming anybody: commands of the reserved
///   `hub.*` namespace (so the hub can still be operated) and commands of **any module that
///   fulfils the active regime** (so pending work can be drained and consulted).
///
/// **Queries are never gated** — that is where "✅ consult · ✅ export · ✅ accounting" comes from,
/// free of charge.
fn enforce_fiscal_capacity(
    ctx: &RequestContext,
    module_id: &str,
    is_core_command: bool,
    emitted: &[String],
) -> Result<()> {
    // `None` means UNRESOLVED, never "nothing owed": a path that did not stamp the mode must not
    // read as compliant. Nothing can be decided here, so nothing is allowed through on its word —
    // but neither is a hub blocked for a field that a caller cannot set. Resolving it is the
    // dispatcher's job and it always does; this arm exists so the meaning is written down.
    let Some(mode) = ctx.fiscal_mode else {
        return Ok(());
    };
    match mode {
        crate::fiscal_profile::FiscalMode::Closed => {
            if is_core_command || ctx.fiscal_providers.iter().any(|id| id == module_id) {
                return Ok(());
            }
            Err(RuntimeError::Domain {
                code: crate::fiscal_profile::HUB_CLOSED.to_string(),
                message: "this hub has closed its fiscal period: it can still be consulted and \
                          exported, but it does not issue any more"
                    .to_string(),
            })
        }
        crate::fiscal_profile::FiscalMode::Blocked(reason) => {
            // Only what would OPEN a fiscal chain is refused. Everything else keeps working.
            if !emitted
                .iter()
                .any(|e| ctx.fiscal_triggers.iter().any(|t| t == e))
            {
                return Ok(());
            }
            Err(RuntimeError::Domain {
                code: reason.code().to_string(),
                message: match reason {
                    crate::fiscal_profile::BlockedReason::ProviderMissing =>
                        "this hub files for real and no installed module fulfils its fiscal \
                         regime: nobody would generate the record for this sale. Reinstall the \
                         fiscal module to carry on".to_string(),
                    crate::fiscal_profile::BlockedReason::InstallationMismatch =>
                        "these records were filed by a DIFFERENT installation of this hub: \
                         carrying on would mix two chains. Adopt the installation explicitly \
                         before issuing again".to_string(),
                },
            })
        }
        _ => Ok(()),
    }
}

// ─── Fiscal environment policy (ADR-0197 §4 · hub#376) ───────────────────────

/// The `system_params`/payload param that names the tax authority environment a fiscal record is
/// transmitted to. SQL that binds it is, by definition, deciding which AEAT this hub talks to —
/// the structural marker the pin keys on, exactly like [`FISCAL_IDENTITY_PARAMS`] above.
const FISCAL_ENVIRONMENT_PARAM: &str = "environment";

/// The only environment an ephemeral demo hub may ever use.
const SANDBOX_ENVIRONMENT: &str = "testing";

/// Which fiscal environment this hub is PINNED to, if any — the core's answer to «may this hub
/// change where its fiscal records go?».
///
/// This is the seam that hub#485 lands on. Ioan's rule of 2026-08-08: *a tax obligation may never
/// depend on a module being installed, enabled, licensed or available — the module implements HOW
/// to comply, the CORE decides THAT you must*. So the authority over the fiscal environment is
/// here, in the dispatcher, and not in `verifactu/commands/config_save.sql`.
///
/// Two cases, one policy, and today only the first is enforced:
///  - **demo hub → `Some("testing")`.** Pinned, both ways, for its whole life. It is anonymous,
///    unregistered, disposable and (ADR-0202 phase 2) can receive a *delegated* certificate by
///    the normal distribution: environment + a certificate is all it takes to file real records
///    for a business that never asked. This is R5 of ADR-0202 §5 (hub#315) resolved in the core.
///  - **real hub → `None`.** No pin *today*. hub#485 tightens exactly this arm into a **one-way**
///    switch: `testing → production` free (the go-live), `production → testing` refused once a
///    record has been accepted in production. When it lands it replaces this `None`, and the
///    demo arm above stays untouched — a pin is the degenerate case of a one-way switch.
fn fiscal_environment_pin(demo_hub: bool) -> Option<&'static str> {
    demo_hub.then_some(SANDBOX_ENVIRONMENT)
}

/// Fiscal environment lock (ADR-0197 §4, hub#376): in a demo hub, a transaction may not bind the
/// fiscal `:environment` to anything but the sandbox.
///
/// Structural and business-free, same shape as [`enforce_fiscal_precondition`]: the trigger is the
/// SQL binding the param, not a module id, so a second fiscal module (or a renamed VeriFactu
/// command) is covered the day it exists without touching the runtime.
///
/// An **absent or empty** value is allowed on purpose: `verifactu/_insert_record.sql` binds
/// `COALESCE(:environment, (SELECT environment FROM verifactu_config …))`, so «not stated» resolves
/// to the hub's configuration — which this very gate keeps pinned to the sandbox. Refusing it would
/// break record insertion in the demo instead of pinning it.
fn enforce_fiscal_environment_pin<'a>(
    registry: &Registry,
    pairs: impl Iterator<Item = (&'a str, &'a Params)>,
) -> Result<()> {
    let Some(pinned) = fiscal_environment_pin(registry.demo_hub) else {
        return Ok(());
    };
    for (sql, params) in pairs {
        if !references_param(sql, FISCAL_ENVIRONMENT_PARAM) {
            continue;
        }
        let requested = params
            .get(FISCAL_ENVIRONMENT_PARAM)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim();
        if !requested.is_empty() && !requested.eq_ignore_ascii_case(pinned) {
            return Err(RuntimeError::DemoLocked {
                lock: DemoLock::FiscalEnvironment,
            });
        }
    }
    Ok(())
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
            min_affected_rows: None,
            expect_rows: None,
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

    // ─────────────────────────────────────────────────────────────────────
    // Eventos devueltos por un handler (hub#240).
    //
    // Los eventos del `Output` de un handler se encolaban en el outbox SIN mirar el
    // `module.json`: el handler elegía el nombre y el relay se lo entregaba a los listeners
    // de otros módulos… y, si acababa en `.reminder.due`, al **listener-host de
    // `host.notify`** (email/SMS/WhatsApp). O sea: un módulo con un handler alcanzaba un
    // primitivo de envío externo sin declarar ni que le concedieran la capability.
    // ─────────────────────────────────────────────────────────────────────

    /// Registry con un módulo instalado (manifest) y un command suyo.
    fn registry_with_module(manifest_json: &str, command: &str) -> Registry {
        let m: crate::manifest::Manifest = serde_json::from_str(manifest_json).unwrap();
        let module_id = m.id.clone();
        let mut reg = registry_with_command(&module_id, command);
        reg.installed.push(m);
        reg
    }

    // ── D4 (hub#556): el gate RECHAZA ─────────────────────────────────────────────────────────

    use crate::fiscal_profile::{BlockedReason, FiscalMode};

    /// Un ctx con el modo fiscal ya resuelto, sus disparadores y sus proveedores.
    fn fiscal_ctx(mode: FiscalMode, triggers: &[&str], providers: &[&str]) -> RequestContext {
        RequestContext::new("h1", "u1", ["*".to_string()]).with_fiscal_mode(
            mode,
            triggers.iter().map(|s| (*s).to_string()).collect(),
            providers.iter().map(|s| (*s).to_string()).collect(),
        )
    }

    fn code_of(err: &RuntimeError) -> String {
        match err {
            RuntimeError::Domain { code, .. } => code.clone(),
            other => other.to_string(),
        }
    }

    /// 🔴 **La venta que abriría una cadena fiscal se RECHAZA cuando no queda nadie que la cierre.**
    /// Éste es el agujero entero de la ADR en un test: hub vivo, proveedor desaparecido, y hasta
    /// ahora la venta se cobraba igual y la factura moría en dead-letter.
    #[test]
    fn a_sale_that_would_open_a_fiscal_chain_is_refused_when_nobody_can_close_it() {
        let ctx = fiscal_ctx(
            FiscalMode::Blocked(BlockedReason::ProviderMissing),
            &["invoice.created"],
            &[],
        );
        let err = enforce_fiscal_capacity(&ctx, "sales", false, &["invoice.created".to_string()])
            .expect_err("sin proveedor no se abre una cadena fiscal");
        assert_eq!(code_of(&err), "fiscal.provider_missing");
    }

    /// **`BLOCKED` no tira el hub entero.** Solo cae la cadena fiscal; el resto del TPV sigue
    /// funcionando. Tirarlo todo porque un módulo no montó es desproporcionado y empuja al usuario
    /// a buscarse la vida por fuera.
    #[test]
    fn blocked_does_not_stop_the_rest_of_the_till() {
        let ctx = fiscal_ctx(
            FiscalMode::Blocked(BlockedReason::ProviderMissing),
            &["invoice.created"],
            &[],
        );
        assert!(
            enforce_fiscal_capacity(&ctx, "inventory", false, &["inventory.stock.moved".to_string()])
                .is_ok(),
            "mover stock no abre ninguna cadena fiscal"
        );
        assert!(enforce_fiscal_capacity(&ctx, "inventory", false, &[]).is_ok());
    }

    /// La otra rama: estos registros los emitió OTRA instalación. Seguir mezclaría dos cadenas.
    #[test]
    fn a_chain_from_another_installation_refuses_with_its_own_code() {
        let ctx = fiscal_ctx(
            FiscalMode::Blocked(BlockedReason::InstallationMismatch),
            &["invoice.created"],
            &["verifactu"],
        );
        let err = enforce_fiscal_capacity(&ctx, "sales", false, &["invoice.created".to_string()])
            .expect_err("una cadena ajena no se continúa");
        assert_eq!(code_of(&err), "fiscal.installation_mismatch");
    }

    /// Con el hub sano no se rechaza nada, por más eventos fiscales que emita.
    #[test]
    fn an_active_hub_with_its_provider_mounted_is_not_gated() {
        let ctx = fiscal_ctx(FiscalMode::Active, &["invoice.created"], &["verifactu"]);
        assert!(
            enforce_fiscal_capacity(&ctx, "sales", false, &["invoice.created".to_string()]).is_ok()
        );
    }

    /// `CLOSED` es **default-deny de escrituras**: cesó la actividad, no se emite más.
    #[test]
    fn a_closed_hub_refuses_writes() {
        let ctx = fiscal_ctx(FiscalMode::Closed, &["invoice.created"], &["verifactu"]);
        let err = enforce_fiscal_capacity(&ctx, "inventory", false, &[])
            .expect_err("un hub cerrado no escribe");
        assert_eq!(code_of(&err), "fiscal.hub_closed");
    }

    /// Con dos excepciones que el core clasifica **sin nombrar a nadie**: el namespace reservado
    /// `hub.*` (para poder operar el hub) y cualquier módulo que cumpla el régimen activo (para
    /// drenar lo que aún deba y consultarlo).
    #[test]
    fn a_closed_hub_still_lets_the_core_and_its_provider_work() {
        let ctx = fiscal_ctx(FiscalMode::Closed, &["invoice.created"], &["verifactu"]);
        assert!(
            enforce_fiscal_capacity(&ctx, "hub", true, &[]).is_ok(),
            "el hub se tiene que poder seguir operando"
        );
        assert!(
            enforce_fiscal_capacity(&ctx, "verifactu", false, &[]).is_ok(),
            "el proveedor tiene que poder drenar lo que aún deba"
        );
    }

    /// **`None` = SIN RESOLVER, nunca «no debe nada».** No se bloquea por un campo que el caller no
    /// puede poner, pero tampoco se toma su ausencia como permiso: el dispatcher siempre lo
    /// resuelve, y este test fija qué significa la ausencia.
    #[test]
    fn an_unresolved_mode_is_not_read_as_permission_to_emit() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        assert_eq!(ctx.fiscal_mode, None);
        assert!(enforce_fiscal_capacity(&ctx, "sales", false, &["invoice.created".to_string()]).is_ok());
    }

    /// Un evento declarado en el `emit` de un command del módulo se acepta (comportamiento
    /// de siempre: es el contrato que otros módulos escuchan).
    #[test]
    fn handler_event_declared_in_command_emit_is_allowed() {
        let mut reg = registry_with_module(
            r#"{"id":"notes","name":"Notes","version":"1.0.0"}"#,
            "notes.create",
        );
        reg.commands.get_mut("notes.create").unwrap().def.emit = vec!["notes.note.created".into()];
        validate_handler_event(&reg, "notes", "notes.note.created").unwrap();
    }

    /// Un módulo puede declarar en `events.emits` los eventos que emiten sus **handlers**
    /// (los que no salen de un `emit` de command).
    #[test]
    fn handler_event_declared_in_events_emits_is_allowed() {
        let reg = registry_with_module(
            r#"{"id":"sales","name":"Sales","version":"1.0.0",
                "events":{"emits":["sale.completed"]}}"#,
            "sales.complete_sale",
        );
        validate_handler_event(&reg, "sales", "sale.completed").unwrap();
    }

    /// **El test de regresión de hub#240.** Un módulo que SÍ declara sus eventos queda en
    /// modo estricto: cualquier otro nombre se rechaza y el command falla (no se encola nada
    /// en silencio).
    #[test]
    fn handler_event_not_declared_is_rejected_when_module_declares_its_events() {
        let reg = registry_with_module(
            r#"{"id":"sales","name":"Sales","version":"1.0.0",
                "events":{"emits":["sale.completed"]}}"#,
            "sales.complete_sale",
        );
        let err = validate_handler_event(&reg, "sales", "sales.order.opened").unwrap_err();
        assert!(
            matches!(err, RuntimeError::EventNotDeclared { .. }),
            "got {err:?}"
        );
    }

    /// **Suplantación cross-módulo.** Ni siquiera en modo compatible (manifest sin
    /// `events.emits`) un handler puede emitir en el namespace de OTRO módulo instalado:
    /// así un módulo del marketplace no dispara `verifactu.record.transmitted` ni
    /// `invoice.created` en nombre ajeno.
    #[test]
    fn handler_event_in_another_installed_modules_namespace_is_rejected() {
        let mut reg = registry_with_module(
            r#"{"id":"notes","name":"Notes","version":"1.0.0"}"#,
            "notes.create",
        );
        reg.installed.push(
            serde_json::from_str(r#"{"id":"verifactu","name":"VeriFactu","version":"1.0.0"}"#)
                .unwrap(),
        );
        let err =
            validate_handler_event(&reg, "notes", "verifactu.record.transmitted").unwrap_err();
        assert!(
            matches!(err, RuntimeError::EventNotDeclared { .. }),
            "got {err:?}"
        );
    }

    /// **El vector de hub#240.** `*.reminder.due` es lo que dispara el listener-host de
    /// `host.notify` (email/SMS/WhatsApp): un módulo que no declara la capability `notify`
    /// no puede emitirlo, ni siquiera dentro de su propio namespace.
    #[test]
    fn reminder_due_event_requires_the_notify_capability_to_be_declared() {
        let reg = registry_with_module(
            r#"{"id":"appt","name":"Appointments","version":"1.0.0"}"#,
            "appt.remind",
        );
        let err = validate_handler_event(&reg, "appt", "appt.reminder.due").unwrap_err();
        assert!(
            matches!(&err, RuntimeError::CapabilityDenied { capability, .. } if capability == "notify"),
            "got {err:?}"
        );
    }

    /// Declarando la capability, el evento de recordatorio es legítimo (el **grant** del
    /// usuario se comprueba aparte, contra la BD, antes de encolar y antes de enviar).
    #[test]
    fn reminder_due_event_is_allowed_when_notify_is_declared() {
        let reg = registry_with_module(
            r#"{"id":"appt","name":"Appointments","version":"1.0.0",
                "capabilities":{"notify":{"channels":["email"]}}}"#,
            "appt.remind",
        );
        validate_handler_event(&reg, "appt", "appt.reminder.due").unwrap();
    }

    /// Modo compatible: un manifest sin `events.emits` (todos los publicados hoy) sigue
    /// pudiendo emitir en su propio namespace y en namespaces de nadie — pero se avisa.
    #[test]
    fn legacy_manifest_without_declared_events_still_emits_its_own_namespace() {
        let reg = registry_with_module(
            r#"{"id":"tasks","name":"Tasks","version":"1.0.0"}"#,
            "tasks.create",
        );
        validate_handler_event(&reg, "tasks", "tasks.task.created").unwrap();
        // `sale.*` no es de nadie (no hay módulo `sale` instalado) → tolerado.
        validate_handler_event(&reg, "tasks", "sale.completed").unwrap();
    }

    /// Un nombre de evento vacío o con forma rara no se encola.
    #[test]
    fn empty_event_name_is_rejected() {
        let reg = registry_with_module(
            r#"{"id":"notes","name":"Notes","version":"1.0.0"}"#,
            "notes.create",
        );
        assert!(validate_handler_event(&reg, "notes", "").is_err());
        assert!(validate_handler_event(&reg, "notes", "   ").is_err());
    }

    // ── Regresión END-TO-END (hub#240) ────────────────────────────────────────────────────
    //
    // No basta con probar el validador: hay que probar que el CAMINO REAL
    // (handler → persist_handler_output → outbox) rechaza y no encola. Se usa un handler
    // **nativo** porque comparte exactamente ese camino con el WASM (`persist_handler_output`)
    // y no necesita un `.wasm` compilado.

    /// Handler de prueba que devuelve el evento que se le diga, sin operaciones.
    #[derive(Debug)]
    struct EmittingHandler(&'static str);

    #[async_trait::async_trait]
    impl crate::native::NativeHandler for EmittingHandler {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn crate::native::NativeHost,
        ) -> Result<Output> {
            Ok(Output {
                operations: vec![],
                events: vec![erplora_wasm_host::Event {
                    name: self.0.to_string(),
                    payload: json!({}),
                }],
                ..Output::default()
            })
        }
    }

    /// Registry con un módulo `sales` que **declara** sus eventos y un command con handler nativo.
    fn registry_with_native_handler(emitted: &'static str) -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.installed.push(
            serde_json::from_str(
                r#"{"id":"sales","name":"Sales","version":"1.0.0",
                    "events":{"emits":["sale.completed"]}}"#,
            )
            .unwrap(),
        );
        let mut def = cmd_def();
        def.sql = vec![];
        def.handler = Some(crate::manifest::HandlerRef {
            kind: "native".to_string(),
            file: None,
            function: "handle".to_string(),
        });
        reg.commands.insert(
            "sales.complete_sale".into(),
            RegisteredCommand {
                module_id: "sales".into(),
                def,
                sql: vec![],
                wasm: None,
                schema: None,
            },
        );
        reg.native
            .insert("sales".into(), std::sync::Arc::new(EmittingHandler(emitted)));
        reg
    }

    /// **La regresión de hub#240.** Un handler que devuelve un evento NO declarado hace fallar el
    /// command entero: el evento **no** llega al outbox (antes se encolaba en silencio y el relay
    /// se lo entregaba a los listeners de otros módulos… y a `host.notify`).
    #[tokio::test]
    async fn handler_emitting_an_undeclared_event_fails_the_command_and_queues_nothing() {
        let db = erplora_db::testutil::fresh_db().await;
        crate::outbox::ensure_tables(&db).await.unwrap();
        let reg = registry_with_native_handler("sales.exfiltrate");

        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        let err = execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(err, RuntimeError::EventNotDeclared { .. }),
            "got {err:?}"
        );

        let rows = db
            .query("SELECT COUNT(*) AS c FROM _event_outbox", &Params::new())
            .await
            .unwrap();
        let c = rows.rows[0]["c"].as_i64().unwrap_or(-1);
        assert_eq!(c, 0, "un evento no declarado NO puede quedar encolado");
    }

    /// El camino feliz sigue funcionando: un evento declarado se encola como siempre.
    #[tokio::test]
    async fn handler_emitting_a_declared_event_still_reaches_the_outbox() {
        let db = erplora_db::testutil::fresh_db().await;
        crate::outbox::ensure_tables(&db).await.unwrap();
        let reg = registry_with_native_handler("sale.completed");

        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();

        let rows = db
            .query(
                "SELECT event_name, module_id FROM _event_outbox",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1);
        assert_eq!(rows.rows[0]["event_name"], json!("sale.completed"));
        // La fila guarda el módulo emisor: es lo que permite exigirle la capability al entregar.
        assert_eq!(rows.rows[0]["module_id"], json!("sales"));
    }

    // ── hub#139: domain error channel from a handler ─────────────────────────────────────────
    //
    // Same rationale as the hub#240 regression above: the validator alone is not enough, the
    // REAL path (handler → persist_handler_output) must abort. A native handler shares that
    // path with WASM and needs no compiled `.wasm`.

    /// Test handler that returns a business rejection, alongside a declared event that must
    /// never be enqueued (a rejecting guest cannot persist partial effects).
    #[derive(Debug)]
    struct RejectingHandler(&'static str);

    #[async_trait::async_trait]
    impl crate::native::NativeHandler for RejectingHandler {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn crate::native::NativeHost,
        ) -> Result<Output> {
            Ok(Output::new()
                .with_event(erplora_wasm_host::Event {
                    name: "sale.completed".to_string(),
                    payload: json!({}),
                })
                .with_error(erplora_wasm_host::guest_sdk::DomainError::new(
                    self.0,
                    "Rejected by a business rule",
                )))
        }
    }

    /// Registry with the same `sales` module as the hub#240 harness, but a rejecting handler.
    fn registry_with_rejecting_handler(code: &'static str) -> Registry {
        let mut reg = registry_with_native_handler("sale.completed");
        reg.native
            .insert("sales".into(), std::sync::Arc::new(RejectingHandler(code)));
        reg
    }

    /// hub#139: a handler that returns `error` aborts the whole command with a stable,
    /// namespaced `Domain` code — and NOTHING it returned (events, operations) is persisted.
    #[tokio::test]
    async fn handler_domain_error_aborts_with_a_stable_code_and_persists_nothing() {
        let db = erplora_db::testutil::fresh_db().await;
        crate::outbox::ensure_tables(&db).await.unwrap();
        let reg = registry_with_rejecting_handler("sales.rejected");

        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        let err = execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::Domain { ref code, ref message }
                    if code == "sales.rejected" && message == "Rejected by a business rule"
            ),
            "expected Domain with the guest-declared code, got {err:?}"
        );

        let rows = db
            .query("SELECT COUNT(*) AS c FROM _event_outbox", &Params::new())
            .await
            .unwrap();
        assert_eq!(
            rows.rows[0]["c"].as_i64().unwrap_or(-1),
            0,
            "a rejecting handler must not persist any of its effects"
        );
    }

    /// hub#139: a handler cannot mint codes in a namespace it does not own. An invalid code is
    /// a broken guest contract (`Wasm` error, severity unexpected), NOT a `Domain` rejection —
    /// otherwise a module could spoof another module's error ABI towards the UI.
    #[tokio::test]
    async fn handler_domain_error_with_a_foreign_namespace_is_a_contract_violation() {
        let db = erplora_db::testutil::fresh_db().await;
        crate::outbox::ensure_tables(&db).await.unwrap();
        let reg = registry_with_rejecting_handler("inventory.not_owned");

        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        let err = execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(err, RuntimeError::Wasm(_)),
            "a foreign-namespace code must surface as a broken guest contract, got {err:?}"
        );

        let rows = db
            .query("SELECT COUNT(*) AS c FROM _event_outbox", &Params::new())
            .await
            .unwrap();
        assert_eq!(rows.rows[0]["c"].as_i64().unwrap_or(-1), 0);
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
        async fn execute_tx_gated(
            &self,
            _ops: &[(String, Params)],
            _sql_op_count: usize,
            _min_affected_rows: Option<u64>,
        ) -> std::result::Result<erplora_db::TxGatedOutcome, erplora_db::DbError> {
            panic!("DenyDb::execute_tx_gated no debía llamarse — el gate de origen debe cortar antes");
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
        async fn execute_tx_gated(
            &self,
            ops: &[(String, Params)],
            sql_op_count: usize,
            min_affected_rows: Option<u64>,
        ) -> std::result::Result<erplora_db::TxGatedOutcome, erplora_db::DbError> {
            // Por defecto cada op "muta" 1 fila: simula un INSERT/UPDATE que casa. Si el caller
            // exige un mínimo y la suma de las `sql_op_count` primeras lo cubre, commitea; si no,
            // revierte. Los tests de hub#140 construyen su propio doble cuando necesitan 0 filas.
            let counts = vec![1u64; ops.len()];
            let n = sql_op_count.min(counts.len());
            let sql_counts: Vec<u64> = counts[..n].to_vec();
            let affected: u64 = sql_counts.iter().sum();
            let ok = min_affected_rows.map_or(true, |min| affected >= min);
            if ok {
                Ok(erplora_db::TxGatedOutcome::Committed { per_op: counts })
            } else {
                Ok(erplora_db::TxGatedOutcome::RolledBack { sql_counts })
            }
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
            &Grants::new(),
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
            None,
        )
        .await
        .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InternalCommand(_)),
            "got {err:?}"
        );
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
            None,
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
            None,
        )
        .await
        .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InternalCommand(_)),
            "got {err:?}"
        );
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
            None,
        )
        .await
        .unwrap();
        assert_eq!(out["ok"], serde_json::json!(true));
    }

    // ─────────────────────────────────────────────────────────────────────
    // Fiscal precondition gate (hub#328, ADR-0203).
    //
    // `system_params` injects `:business_tax_id` / `:business_legal_name` into every
    // command's SQL so modules resolve the fiscal issuer without the caller passing it
    // (ADR-0061) — but nothing validated that identity. `invoice/_insert_invoice.sql`
    // does `COALESCE(NULLIF(:issuer_nif,''), :business_tax_id)`, so empty + empty =
    // an issued invoice with a BLANK issuer, and VeriFactu chains from it (ADR-0189:
    // an accepted record is never re-sent). The gate: SQL that stamps the business
    // identity does not run until `business_legal_name` AND `business_tax_id` are set
    // (AND the certificate is loaded, while an installed module declares the
    // `certificate` capability). No modes, no toggles.
    // ─────────────────────────────────────────────────────────────────────

    /// SQL in the shape of `invoice._insert_invoice`: stamps the hub's business identity
    /// as the document issuer. Referencing the injected identity params is the marker
    /// the gate keys on.
    const FISCAL_INSERT: &str = "INSERT INTO fiscal_doc (id, issuer_nif, issuer_name) VALUES \
         (:new_id, COALESCE(NULLIF(:issuer_nif, ''), :business_tax_id), \
         COALESCE(NULLIF(:issuer_name, ''), :business_legal_name));";

    /// Registry with an active `invoice`-like module whose public command stamps the
    /// business identity (declarative Tier 0/1 path).
    fn registry_with_fiscal_command() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("invoice".into(), ModuleStatus::Active);
        reg.commands.insert(
            "invoice.create".into(),
            RegisteredCommand {
                module_id: "invoice".into(),
                def: cmd_def(),
                sql: vec![FISCAL_INSERT.to_string()],
                wasm: None,
                schema: None,
            },
        );
        reg
    }

    /// Caller-side issuer fields empty, like a POS sale: the issuer falls back to the
    /// injected business identity.
    fn fiscal_payload() -> Params {
        let mut p = Params::new();
        p.insert("issuer_nif".into(), json!(""));
        p.insert("issuer_name".into(), json!(""));
        p
    }

    /// Real test DB with the fiscal table and `hub_settings` (system migration v4 DDL).
    async fn db_with_fiscal_tables() -> erplora_db::PgAdapter {
        let db = erplora_db::testutil::fresh_db().await;
        db.execute_batch(
            "CREATE TABLE fiscal_doc (id TEXT, issuer_nif TEXT, issuer_name TEXT);\
             CREATE TABLE hub_settings (\
               hub_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, \
               updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
               PRIMARY KEY (hub_id, key));",
        )
        .await
        .unwrap();
        db
    }

    /// Sets the hub's business identity in `hub_settings` (the single source, ADR-0061).
    async fn set_business_identity(db: &dyn DatabaseAdapter, hub_id: &str) {
        let mut updates = serde_json::Map::new();
        updates.insert("business_tax_id".into(), json!("B12345678"));
        updates.insert("business_legal_name".into(), json!("ACME SL"));
        crate::settings::set_many(db, hub_id, &updates, "hub_user:1", false)
            .await
            .unwrap();
    }

    /// **The red test of hub#328.** Without `business_legal_name` ∧ `business_tax_id` in
    /// `hub_settings`, a command that stamps the business identity is rejected with the
    /// domain error and NOTHING is written — no blank-issuer invoice ever reaches the DB.
    #[tokio::test]
    async fn fiscal_document_without_business_identity_is_rejected() {
        let db = db_with_fiscal_tables().await;
        let reg = registry_with_fiscal_command();
        // No `hub_settings` rows → the enriched context carries an EMPTY business identity.
        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);

        let err = execute(
            &db,
            &reg,
            "invoice.create",
            &fiscal_payload(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::FiscalPrecondition { missing }
                if missing.contains(&"business_tax_id") && missing.contains(&"business_legal_name")),
            "got {err:?}"
        );

        let rows = db
            .query("SELECT COUNT(*) AS c FROM fiscal_doc", &Params::new())
            .await
            .unwrap();
        assert_eq!(
            rows.rows[0]["c"].as_i64().unwrap_or(-1),
            0,
            "a fiscal document with a blank issuer must never be written"
        );
    }

    /// With the identity configured, the same command runs and the document carries the
    /// hub's business identity as issuer (the ADR-0061 fallback keeps working).
    #[tokio::test]
    async fn fiscal_document_with_business_identity_set_is_emitted() {
        let db = db_with_fiscal_tables().await;
        set_business_identity(&db, "h1").await;
        let reg = registry_with_fiscal_command();
        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);

        let out = execute(&db, &reg, "invoice.create", &fiscal_payload(), &ctx, &Grants::new())
            .await
            .expect("with the business identity set, the fiscal document must be emitted");
        assert_eq!(out["ok"], json!(true));

        let rows = db
            .query(
                "SELECT issuer_nif, issuer_name FROM fiscal_doc",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1);
        assert_eq!(rows.rows[0]["issuer_nif"], json!("B12345678"));
        assert_eq!(rows.rows[0]["issuer_name"], json!("ACME SL"));
    }

    /// While an INSTALLED module declares the `certificate` capability (today: verifactu),
    /// the loaded certificate becomes part of the precondition: identity alone is not
    /// enough — emitting without it would strand documents outside the VeriFactu chain.
    #[tokio::test]
    async fn fiscal_document_requires_certificate_when_an_installed_module_declares_it() {
        let db = db_with_fiscal_tables().await;
        set_business_identity(&db, "h1").await;
        let mut reg = registry_with_fiscal_command();
        reg.installed.push(
            serde_json::from_str(
                r#"{"id":"verifactu","name":"VeriFactu","version":"1.0.0",
                    "capabilities":{"certificate":{"purpose":"fiscal-sign"}}}"#,
            )
            .unwrap(),
        );
        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);

        let err = execute(
            &db,
            &reg,
            "invoice.create",
            &fiscal_payload(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::FiscalPrecondition { missing }
                if *missing == vec!["certificate"]),
            "got {err:?}"
        );
    }

    /// Native handler op that resolves to the fiscal SQL of its own module — the exact
    /// path the real `invoice` WASM handler takes (`persist_handler_output`).
    #[derive(Debug)]
    struct FiscalOpHandler;

    #[async_trait::async_trait]
    impl crate::native::NativeHandler for FiscalOpHandler {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn crate::native::NativeHost,
        ) -> Result<Output> {
            Ok(Output {
                operations: vec![Operation::sql("invoice._insert", fiscal_payload())],
                events: vec![],
                ..Output::default()
            })
        }
    }

    /// The handler path is gated too: an operation resolved from a handler that stamps
    /// the business identity is rejected before anything touches the DB.
    #[tokio::test]
    async fn handler_operation_stamping_business_identity_is_gated_too() {
        let db = db_with_fiscal_tables().await;
        let mut reg = Registry::new();
        reg.status.insert("invoice".into(), ModuleStatus::Active);
        let mut def = cmd_def();
        def.sql = vec![];
        def.handler = Some(crate::manifest::HandlerRef {
            kind: "native".to_string(),
            file: None,
            function: "handle".to_string(),
        });
        reg.commands.insert(
            "invoice.create".into(),
            RegisteredCommand {
                module_id: "invoice".into(),
                def,
                sql: vec![],
                wasm: None,
                schema: None,
            },
        );
        reg.commands.insert(
            "invoice._insert".into(),
            RegisteredCommand {
                module_id: "invoice".into(),
                def: cmd_def(),
                sql: vec![FISCAL_INSERT.to_string()],
                wasm: None,
                schema: None,
            },
        );
        reg.native
            .insert("invoice".into(), std::sync::Arc::new(FiscalOpHandler));

        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        let err = execute(
            &db,
            &reg,
            "invoice.create",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(err, RuntimeError::FiscalPrecondition { .. }),
            "got {err:?}"
        );

        let rows = db
            .query("SELECT COUNT(*) AS c FROM fiscal_doc", &Params::new())
            .await
            .unwrap();
        assert_eq!(rows.rows[0]["c"].as_i64().unwrap_or(-1), 0);
    }

    /// Control: a command that does NOT stamp the business identity runs untouched with an
    /// empty identity — the gate keys on the SQL, not on global hub state. Otherwise a
    /// fresh hub could not even save its settings.
    #[tokio::test]
    async fn command_not_stamping_business_identity_runs_without_it() {
        let reg = registry_with_command("notes", "notes.create");
        // Empty business identity (FakeDb returns no settings rows).
        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        let out = execute(&FakeDb, &reg, "notes.create", &Params::new(), &ctx, &Grants::new())
            .await
            .unwrap();
        assert_eq!(out["ok"], json!(true));
    }

    /// Token boundary: a module param that merely STARTS with an identity param name
    /// (`:business_tax_id_verified`) is not the injected identity param and must not
    /// trigger the gate.
    #[tokio::test]
    async fn param_with_identity_prefix_does_not_trigger_the_gate() {
        let mut reg = Registry::new();
        reg.status.insert("crm".into(), ModuleStatus::Active);
        reg.commands.insert(
            "crm.flag".into(),
            RegisteredCommand {
                module_id: "crm".into(),
                def: cmd_def(),
                sql: vec!["INSERT INTO x VALUES (:business_tax_id_verified);".to_string()],
                wasm: None,
                schema: None,
            },
        );
        let mut payload = Params::new();
        payload.insert("business_tax_id_verified".into(), json!(1));
        let ctx = crate::registry::RequestContext::new("h1", "u1", ["*".to_string()]);
        let out = execute(&FakeDb, &reg, "crm.flag", &payload, &ctx, &Grants::new())
            .await
            .unwrap();
        assert_eq!(out["ok"], json!(true));
    }

    // ── Fiscal environment pin in a DEMO hub (ADR-0197 §4 · hub#376) ───────────────────────
    //
    // A demo hub is a REAL hub handed to an anonymous visitor for an hour. What it must never do
    // is file records with the real tax authority. The environment is the switch that decides
    // which AEAT it talks to, so in a demo it is pinned — and the pin is the CORE's, not the
    // module's (Ioan, 2026-08-08: a tax obligation may never depend on a module being installed).

    /// The shape of `verifactu.config.save`: declarative SQL that binds `:environment`.
    fn registry_saving_the_fiscal_environment(demo_hub: bool) -> Registry {
        let mut reg = Registry::new();
        reg.demo_hub = demo_hub;
        reg.status.insert("verifactu".into(), ModuleStatus::Active);
        reg.commands.insert(
            "verifactu.config.save".into(),
            RegisteredCommand {
                module_id: "verifactu".into(),
                def: cmd_def(),
                sql: vec![
                    "INSERT INTO verifactu_config (hub_id, environment) \
                     VALUES (:hub_id, :environment);"
                        .to_string(),
                ],
                wasm: None,
                schema: None,
            },
        );
        reg
    }

    fn environment_payload(value: &str) -> Params {
        let mut p = Params::new();
        p.insert("environment".into(), json!(value));
        p
    }

    /// 🔴 The one that matters: a DEMO hub trying to go live. `DenyDb` panics on any DB call, so
    /// this also proves the refusal lands BEFORE anything is written.
    #[tokio::test]
    async fn a_demo_hub_cannot_point_its_fiscal_environment_at_production() {
        let reg = registry_saving_the_fiscal_environment(true);
        let err = execute(
            &DenyDb,
            &reg,
            "verifactu.config.save",
            &environment_payload("production"),
            &ctx_admin(),
            &Grants::new(),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::FiscalEnvironment
                }
            ),
            "got {err:?}"
        );
    }

    /// Casing is not a bypass: `PRODUCTION` is the same switch.
    #[tokio::test]
    async fn the_pin_is_not_case_sensitive() {
        let reg = registry_saving_the_fiscal_environment(true);
        for spelling in ["PRODUCTION", "Production", " production "] {
            let err = execute(
                &DenyDb,
                &reg,
                "verifactu.config.save",
                &environment_payload(spelling),
                &ctx_admin(),
                &Grants::new(),
            )
            .await
            .unwrap_err();
            assert!(
                matches!(err, RuntimeError::DemoLocked { .. }),
                "`{spelling}` must not go live: {err:?}"
            );
        }
    }

    /// The demo still WORKS: saving the sandbox environment is the normal path, not a refusal.
    #[tokio::test]
    async fn a_demo_hub_can_still_save_the_sandbox_environment() {
        let reg = registry_saving_the_fiscal_environment(true);
        let out = execute(
            &FakeDb,
            &reg,
            "verifactu.config.save",
            &environment_payload("testing"),
            &ctx_admin(),
            &Grants::new(),
        )
        .await
        .expect("a demo hub configures VeriFactu against preproduction like any other");
        assert_eq!(out["ok"], json!(true));
    }

    /// Not stating the environment is not a bypass either — and it must NOT be refused:
    /// `verifactu/_insert_record.sql` binds `COALESCE(:environment, <the config>)`, so «absent»
    /// resolves to the configuration this very gate keeps pinned. Refusing it would stop the demo
    /// from writing records at all.
    #[tokio::test]
    async fn an_absent_environment_falls_back_to_the_pinned_config_instead_of_failing() {
        let reg = registry_saving_the_fiscal_environment(true);
        let out = execute(
            &FakeDb,
            &reg,
            "verifactu.config.save",
            &Params::new(),
            &ctx_admin(),
            &Grants::new(),
        )
        .await
        .expect("no environment stated → the pinned config decides");
        assert_eq!(out["ok"], json!(true));
    }

    /// 🔴 The OTHER direction, and the one that would be a silent disaster: a REAL hub is not
    /// affected. Going live is how a paying business complies — a pin leaking onto a real hub
    /// would stop its sales reaching the AEAT, which is exactly the hole hub#485 is about.
    #[tokio::test]
    async fn a_real_hub_goes_live_untouched() {
        let reg = registry_saving_the_fiscal_environment(false);
        let out = execute(
            &FakeDb,
            &reg,
            "verifactu.config.save",
            &environment_payload("production"),
            &ctx_admin(),
            &Grants::new(),
        )
        .await
        .expect("a real hub must be able to go live");
        assert_eq!(out["ok"], json!(true));
    }

    /// 🔴 A REAL hub cannot DECLARE ITSELF a demo. The marker is the deployment's
    /// (`Registry::demo_hub`, sealed at boot from `HUB_DEMO`), so a caller that ships `demo` /
    /// `is_demo` in the payload changes nothing — otherwise the browser would own the switch that
    /// makes real sales stop counting.
    #[tokio::test]
    async fn the_payload_cannot_turn_a_real_hub_into_a_demo() {
        let reg = registry_saving_the_fiscal_environment(false);
        let mut payload = environment_payload("production");
        payload.insert("demo".into(), json!(true));
        payload.insert("is_demo".into(), json!(true));
        payload.insert("demo_hub".into(), json!(true));
        let out = execute(
            &FakeDb,
            &reg,
            "verifactu.config.save",
            &payload,
            &ctx_admin(),
            &Grants::new(),
        )
        .await
        .expect("only the deployment decides what a demo is");
        assert_eq!(out["ok"], json!(true));
    }

    /// Token boundary, same rule as the identity gate: `:environment_label` is another param.
    #[tokio::test]
    async fn a_param_that_merely_starts_with_environment_is_not_the_fiscal_switch() {
        let mut reg = Registry::new();
        reg.demo_hub = true;
        reg.status.insert("crm".into(), ModuleStatus::Active);
        reg.commands.insert(
            "crm.tag".into(),
            RegisteredCommand {
                module_id: "crm".into(),
                def: cmd_def(),
                sql: vec!["INSERT INTO x VALUES (:environment_label);".to_string()],
                wasm: None,
                schema: None,
            },
        );
        let mut payload = Params::new();
        payload.insert("environment_label".into(), json!("production"));
        let out = execute(&FakeDb, &reg, "crm.tag", &payload, &ctx_admin(), &Grants::new())
            .await
            .expect("an unrelated param must not be read as the fiscal environment");
        assert_eq!(out["ok"], json!(true));
    }

    /// And a demo hub that never mentions the environment runs its normal business untouched:
    /// the gate is structural (it keys on the SQL binding the param), not a global mode.
    #[tokio::test]
    async fn a_demo_hub_runs_commands_that_do_not_bind_the_environment() {
        let mut reg = registry_with_command("inventory", "inventory.stock.set");
        reg.demo_hub = true;
        let out = execute(
            &FakeDb,
            &reg,
            "inventory.stock.set",
            &environment_payload("production"),
            &ctx_admin(),
            &Grants::new(),
        )
        .await
        .expect("no :environment in the SQL → nothing to pin");
        assert_eq!(out["ok"], json!(true));
    }

    /// The pin also covers what a NATIVE/WASM handler resolves to. The VeriFactu engine emits its
    /// own `_insert_record` operation with its own params: a gate that only looked at the caller's
    /// payload would be blind to exactly the path that transmits.
    #[tokio::test]
    async fn the_pin_covers_the_operations_a_handler_resolves_to() {
        let pairs = vec![(
            "INSERT INTO verifactu_record (environment) VALUES (:environment);".to_string(),
            environment_payload("production"),
        )];
        let mut reg = Registry::new();
        reg.demo_hub = true;
        let err = enforce_fiscal_environment_pin(
            &reg,
            pairs.iter().map(|(sql, p)| (sql.as_str(), p)),
        )
        .unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::FiscalEnvironment
                }
            ),
            "got {err:?}"
        );
    }

    /// The policy itself, spelled out — this is the seam hub#485 lands on.
    #[test]
    fn only_a_demo_hub_is_pinned_today() {
        assert_eq!(fiscal_environment_pin(true), Some("testing"));
        assert_eq!(
            fiscal_environment_pin(false),
            None,
            "a real hub has no pin YET: hub#485 turns this arm into a one-way switch"
        );
    }
}
