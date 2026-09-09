//! Query/command HTTP handlers and the error-redaction boundary — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

#[derive(Deserialize)]
pub(crate) struct QueryReq {
    name: String,
    #[serde(default)]
    params: Map<String, Value>,
}

#[derive(Deserialize)]
pub(crate) struct CommandReq {
    name: String,
    #[serde(default)]
    payload: Map<String, Value>,
}

/// HTTP status + stable error code of a runtime error.
///
/// Split out of [`err_response`] (hub#343) because the print host's WS channel has to answer with
/// **the same codes** and cannot go through a `Response` to get them. One table, so the code a
/// module or the drain declares cannot mean one thing over HTTP and another over the socket.
pub(crate) fn err_status_and_code(
    e: &erplora_runtime::RuntimeError,
) -> (StatusCode, std::borrow::Cow<'_, str>) {
    use erplora_runtime::RuntimeError as E;
    // `Cow` because `Domain` (hub#139) carries a module-declared dynamic code; every other
    // variant keeps its static stable code.
    match e {
        E::PermissionDenied(_) => (StatusCode::FORBIDDEN, "permission_denied".into()),
        E::QueryNotFound(_) | E::CommandNotFound(_) => (StatusCode::NOT_FOUND, "not_found".into()),
        // hub#131, hub#145: un command interno (prefijo `_`/`internal:true`) invocado desde un
        // origen EXTERNO. `403` (como `permission_denied`): el command EXISTE, pero esta puerta
        // no es la suya — nunca `404`, que sugeriría que ni siquiera está registrado.
        E::InternalCommand(_) => (StatusCode::FORBIDDEN, "internal_command".into()),
        // ADR-0127: `queryOptional` del SDK devuelve `undefined` SOLO con este código; un
        // `not_found` normal (contrato roto contra un módulo presente) sigue siendo un error.
        E::ModuleNotInstalled { .. } => (StatusCode::NOT_FOUND, "module_not_installed".into()),
        E::ModuleInactive { .. } => (StatusCode::NOT_FOUND, "module_inactive".into()),
        E::InvalidPayload { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "invalid_payload".into()),
        E::InvalidField { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "invalid_field".into()),
        E::ManifestRejected { code, .. } => (StatusCode::UNPROCESSABLE_ENTITY, code.clone().into()),
        // hub#1088: `business_tax_id` refused with its own stable code per failure kind — the
        // same `422` as `invalid_payload` (what was sent does not validate) with the code the UI
        // translates (es/en), so "the control letter is wrong" and "this is no NIF at all" are
        // two different answers instead of one generic refusal.
        E::InvalidTaxId { code, .. } => (StatusCode::UNPROCESSABLE_ENTITY, (*code).into()),
        // hub#1086: the payload does not carry a bind the query's own SQL references. `422`
        // like `invalid_payload` (it IS a payload-contract refusal, caught before any read),
        // with its own stable code so the caller can tell "you did not send what the query
        // needs" from "what you sent does not validate".
        E::MissingRequiredParam { .. } => (
            StatusCode::UNPROCESSABLE_ENTITY,
            "missing_required_param".into(),
        ),
        // hub#1173: the twin of the above at the same door — a param the LIST query does not
        // declare. Same `422` (it is a payload-contract refusal, caught before any read) with its
        // own stable code, so the caller can tell "that query has no such filter" from "you did
        // not send what it needs" — and fix the call instead of trusting a page that quietly held
        // the whole list.
        E::UnknownFilter { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "unknown_filter".into()),
        // hub#1542: the third of the same family — a `range` bound the COLUMN cannot read. Same
        // `422` (the request is well-formed but its payload does not hold up), with its own code
        // so an integration can tell "that bound is not a number" from a database outage.
        E::InvalidFilterBound { .. } => (
            StatusCode::UNPROCESSABLE_ENTITY,
            "invalid_filter_bound".into(),
        ),
        // hub#139: a business rejection is NOT a generic WASM failure. The namespaced code
        // travels verbatim so the UI can translate it, and `queryOptional` never swallows it.
        // `409`: the request is well-formed, it conflicts with the current business state.
        E::Domain { code, .. } => (StatusCode::CONFLICT, code.as_str().into()),
        // hub#139/hub#140: the affected-rows gate carries its stable kind code (`not_found` /
        // `conflict`) to the caller instead of collapsing into the generic 400 bucket.
        E::MinAffectedRows { kind, .. } => (StatusCode::CONFLICT, kind.as_str().into()),
        // hub#328 (ADR-0203): the fiscal precondition gate — the hub's state (missing business
        // identity/certificate), not the request, blocks emitting fiscal documents. `409`: the
        // request is well-formed and allowed, it conflicts with the hub's current setup state.
        E::FiscalPrecondition { .. } => (StatusCode::CONFLICT, "fiscal_precondition_failed".into()),
        // hub#376 (ADR-0197 §4): this hub IS an ephemeral demo, so its fiscal environment,
        // certificate and identity are not its own. `409` for the same reason as above — the
        // request is well-formed and allowed, it conflicts with what this deploy IS. The code is
        // the SUBJECT of the lock, never a flat `demo_locked`: the UI has to be able to say WHICH
        // of the three refused, and three guards sharing one answer means two can be deleted with
        // the suite still green.
        E::DemoLocked { lock } => (StatusCode::CONFLICT, lock.as_str().into()),
        // hub#554: this hub already emitted, so its tax id is the anchor of a live chain and of the
        // `BillingProfile` upstream (ADR-0201 decisión 5). `409` for the same reason: the request
        // is well-formed and the caller is allowed, it conflicts with what this hub HAS DONE. Its
        // own code, never the demo one — the demo lock has a way out (create your own hub) and this
        // one does not.
        E::BusinessTaxIdFrozen { .. } => (StatusCode::CONFLICT, "business_tax_id_frozen".into()),
        // hub#69: same 409 as its sibling — the request is well formed, the STATE of the hub is
        // what refuses it (ADR-0273: the country freezes at go-live).
        E::HubCountryFrozen { .. } => (StatusCode::CONFLICT, "hub_country_frozen".into()),
        // hub#360 (paso 2b): a refusal a MANAGER could approve. `403` like `permission_denied` —
        // it IS a refusal and nothing ran — but with its own stable code, so the UI can tell
        // "ask the manager" (offer the PIN dialog, hub#363) from "this is not for you". Falling
        // into the generic `400 {code:"error"}` bucket would have made the whole chain undecidable.
        E::RequiresElevation { .. } => (StatusCode::FORBIDDEN, "requires_elevation".into()),
        // hub#714: the module→host permission the OWNER grants (ADR-0079). `403` with its own
        // stable code — the same one `error_registry::error_code_of` already publishes — because
        // it is a refusal with a remedy nobody could guess from a bare `400 {code:"error"}`: go to
        // Settings → Permissions and grant it. It is NOT `permission_denied` (that is the user's
        // RBAC, another axis entirely) and NOT `requires_elevation` (no manager's PIN opens it).
        E::CapabilityDenied { .. } => (StatusCode::FORBIDDEN, "capability_denied".into()),
        // hub#775: a `protects` guard refused the command because a precondition of the route is
        // unmet (the drawer is closed). `409`: the request is well-formed and the caller is
        // allowed, it conflicts with the hub's current state — same shape as the fiscal
        // precondition and the demo locks. Its own code, never `permission_denied`: the action
        // that resolves it is "open the drawer", not "ask the manager".
        E::ProtectsGuard { .. } => (StatusCode::CONFLICT, "protects_guard".into()),
        // hub#1101: other installed modules declare this one in `depends_on`. `409` for the same
        // reason as its neighbours above — the request is well-formed and the caller is allowed,
        // it conflicts with the SHAPE of what this hub has installed. Its own stable code, never
        // the generic `400 {code:"error"}` bucket: the screen does not merely report this one, it
        // ACTS on it (lists the dependants and offers «remove it anyway»), and it cannot do that
        // against an error it cannot tell apart.
        E::HasDependents { .. } => (StatusCode::CONFLICT, "has_dependents".into()),
        E::NotImplemented(_) => (StatusCode::NOT_IMPLEMENTED, "not_implemented".into()),
        // hub#1074: everything else keeps the `400` it always had, but NOT the flat `"error"` code
        // it used to collapse into. `error_code_of` is the registry of stable codes this hub
        // already publishes upstream (`db`, `read_unavailable`, `certificate`…), so the code a
        // caller reads over HTTP is the same one the error report carries — one table, not two.
        // That flat bucket is what forced the UI to paint `error.message`: with nothing to branch
        // on, the raw sentence was all a screen had (hub#1102).
        _ => (
            StatusCode::BAD_REQUEST,
            erplora_runtime::error_registry::error_code_of(e),
        ),
    }
}

/// What a client is told when the failure is the hub's own plumbing (hub#1074).
///
/// Deliberately generic and stable: the `code` beside it is what a caller branches on and what the
/// shell translates (ADR-0055), and the detail belongs in the server log, not in a cashier's
/// dialog.
pub(crate) const REDACTED_MESSAGE: &str =
    "the request could not be completed — the hub recorded the details";

/// Does this sentence carry the database driver's own words?
///
/// Second line of defence behind [`may_reach_the_client`] (hub#1074). Several variants whose
/// message IS authored by us wrap a `DbError` inside it —
/// `Other("reset: la transacción falló, nada se borró: {e}")` is the pattern, and there are ~50
/// `Other` sites — so a per-variant rule alone would keep publishing `sqlx` through the very
/// variants we deliberately let speak. Matching the driver's signature covers those without
/// silencing the half of `Other` that says something a person can act on ("usuario no encontrado").
pub(crate) fn carries_driver_text(message: &str) -> bool {
    const MARKS: [&str; 4] = [
        "sqlx",
        "error returned from database",
        "PoolTimedOut",
        " at line ",
    ];
    MARKS.iter().any(|mark| message.contains(mark))
}

/// May the `Display` of this error travel to the caller as human text? (hub#1074)
///
/// The rule the PUBLIC door already applied (`public_door::domain_detail`), brought to the
/// AUTHENTICATED one — the door the UI, the assistant, the flows and the API all come through. A
/// pool error tells the cashier nothing and tells a stranger too much, and until this gate
/// `/api/command` answered a foreign-key violation with the engine, its driver, the table, the
/// constraint and an internal line number (ERPlora/pricing#29 painted exactly that in red in front
/// of a user).
///
/// The match is **exhaustive on purpose**: a new variant must not inherit either answer by falling
/// into a `_` arm — whoever adds it has to say which side of the door it stands on.
pub(crate) fn may_reach_the_client(e: &erplora_runtime::RuntimeError) -> bool {
    use erplora_runtime::RuntimeError as E;
    match e {
        // ── Plumbing. Each of these is the `Display` of a foreign library (sqlx, serde, wasmtime,
        // jsonschema, std::io) and none of it is anything a caller can act on.
        E::Io(_) | E::Manifest { .. } | E::Db(_) | E::Wasm(_) | E::Native(_) | E::Schema { .. } => {
            false
        }
        // hub#1209: the half-migrated hub the money backfill refuses to guess about. It is raised
        // by an ops subcommand and by the boot path, never inside a request, so it does not travel
        // through this door at all — and if it ever did, its sentence is an inventory of this
        // hub's own table.column names: internal shape a caller can neither act on nor need. Ops
        // reads it in the log and in the error registry, which is where it is aimed.
        E::MoneyUnitAmbiguous { .. } => false,
        // ── Sentences this hub, or a module, wrote ON PURPOSE for whoever reads them: they name
        // the operation, the permission, the app or the business rule that refused, which is what
        // the screen has to be able to say. What they must never do is smuggle driver text in, and
        // `carries_driver_text` is the net underneath them.
        E::ManifestUnknownField { .. }
        | E::CoreVersionTooOld { .. }
        | E::ManifestCoreFloorUnreadable { .. }
        | E::QueryNotFound(_)
        | E::ModuleNotInstalled { .. }
        | E::ModuleInactive { .. }
        | E::CommandNotFound(_)
        | E::InternalCommand(_)
        | E::MinAffectedRows { .. }
        | E::Domain { .. }
        | E::PermissionDenied(_)
        | E::RequiresElevation { .. }
        | E::CapabilityDenied { .. }
        | E::MissingDependency { .. }
        | E::HasDependents { .. }
        | E::DependencyTooOld { .. }
        | E::DependencyFloorUnreadable { .. }
        | E::DependencyCycle { .. }
        | E::EventLoop
        | E::EventNotDeclared { .. }
        | E::InvalidPayload { .. }
        // hub#1070 (#1185): the two shapes the core refuses a CONTRACT with — a field of a
        // payload and a manifest that breaks an installer rule. Both are authored by us for
        // whoever has to fix them (a user, a module author), and both carry their own stable
        // code. hub#1490 retired the third (a certificate whose declared type was not the one
        // served) with the control plane's certificate delivery it belonged to.
        | E::InvalidField { .. }
        | E::ManifestRejected { .. }
        | E::MissingRequiredParam { .. }
        // hub#1173: un filtro que la lista no declara es el descuido de QUIEN LLAMA, en la misma
        // puerta que `MissingRequiredParam` — y `severity_of` ya los clasifica juntos. La frase la
        // escribimos nosotros y es justo la que arregla el fallo: nombra la query, el parámetro
        // rechazado y los aceptados. Redactarla dejaría a quien integra con un 400 y sin saber
        // qué parámetro escribió mal, que es peor que el bug que el error previene.
        | E::UnknownFilter { .. }
        // hub#1542: un extremo de `range` que la columna no sabe leer es la misma familia — el
        // descuido de quien llama, con la frase escrita por nosotros. Y es la frase la que
        // arregla la llamada: nombra la lista, CUÁL de los dos extremos no se entendió y el
        // valor que llegó (que es lo que quien llama acaba de escribir, no un dato del hub).
        // Redactarla devolvería justo el mensaje genérico que esta issue viene a quitar.
        | E::InvalidFilterBound { .. }
        | E::Notify(_)
        | E::Print(_)
        | E::Storage(_)
        | E::Certificate(_)
        | E::ReadUnavailable { .. }
        | E::ProtectsGuard { .. }
        | E::FiscalPrecondition { .. }
        | E::InvalidTaxId { .. }
        | E::DemoLocked { .. }
        | E::BusinessTaxIdFrozen { .. }
        | E::HubCountryFrozen { .. }
        | E::NotImplemented(_)
        | E::Other(_) => true,
    }
}

/// Status + body of the error envelope every authenticated door answers with.
///
/// Split out of [`err_response`] (hub#1074) so the redaction policy can be exercised variant by
/// variant without an HTTP round trip and without a database: what a client is allowed to read is
/// a security rule, and a rule that can only be tested through a fixture that happens to fail in
/// the right way is a rule with holes in its coverage.
pub(crate) fn error_payload(e: &erplora_runtime::RuntimeError) -> (StatusCode, Value) {
    use erplora_runtime::RuntimeError as E;
    let (status, code) = err_status_and_code(e);
    // hub#1074: the detail is not thrown away, it changes audience. Until here it travelled to the
    // client and left NO trace on the server; now it is the other way round.
    // hub#1074 + #1185: `InvalidField` is the one refusal whose `Display` is built FOR THE LOG —
    // «`hub.users`: field `name` required: the name is required». `name`, `field` and `reason` are
    // the contract, and they already travel as data below; putting them in front of the person
    // filling the form puts backticks and an internal door name on a screen, which is the exact
    // shape hub#1102 took off the till. So the sentence that travels is the authored `detail`, and
    // the structure stays structure.
    let detail = match e {
        E::InvalidField { detail, .. } => detail.clone(),
        _ => e.to_string(),
    };
    let message = if may_reach_the_client(e) && !carries_driver_text(&detail) {
        detail
    } else {
        tracing::error!(code = %code, detail = %detail, "response to the client redacted: the detail stays in this log (hub#1074)");
        REDACTED_MESSAGE.to_string()
    };
    let mut error = json!({ "code": code, "message": message });
    // hub#360: the missing permission travels as a FIELD, never parsed out of the message — it is
    // what the dialog names and what hub#361 re-checks. Only on the elevation branch: a flat
    // refusal must not look like an offer to elevate.
    if let E::RequiresElevation { permission } = e {
        error["permission"] = json!(permission);
    }
    // hub#1101: same rule — the apps that would break travel as a FIELD, never parsed out of the
    // sentence, because that list is what the confirmation dialog enumerates.
    if let E::HasDependents { dependents, .. } = e {
        error["dependents"] = json!(dependents);
    }
    // hub#1070: the field and the reason travel as data, so the UI translates by code and a
    // client never has to read the prose.
    if let E::InvalidField { field, reason, .. } = e {
        error["field"] = json!(field);
        error["reason"] = json!(reason);
    }
    if let E::ManifestRejected { at, .. } = e {
        error["at"] = json!(at);
    }
    // hub#1102: and the same rule again for the read a `required` preload could not resolve. The
    // shell translates the CODE (`read_unavailable`) and names the missing app from this field;
    // before it, the only place that query lived was inside an English sentence the till printed
    // verbatim on the Charge dialog.
    if let E::ReadUnavailable { query } = e {
        error["query"] = json!(query);
    }
    // hub#1102: the APP a refusal is about, for the refusals whose remedy names one — install it,
    // switch it back on, grant it a permission. Same rule as the fields above: the sentence that
    // names it («Falta la app Impuestos») must not be built by pulling backticks out of
    // «módulo no instalado: `taxes` (requerido por `sales.complete_sale`)».
    //
    // On `MissingDependency` the app that is missing is `dep`, NOT `module`: `module` is the one
    // being installed, and sending the owner after that one is sending them nowhere.
    match e {
        E::ModuleNotInstalled { module, .. }
        | E::ModuleInactive { module, .. }
        | E::CapabilityDenied { module, .. } => error["module"] = json!(module),
        E::MissingDependency { dep, .. } => error["module"] = json!(dep),
        _ => {}
    }
    // hub#1094: same rule again — the fields the schema refused. The Settings screen the shell
    // generates for ANY module swallowed this 422 (press «Save», nothing changes) precisely
    // because a sentence is all it got, and it will not parse one. The split happens at the
    // runtime, one function below the `format!` that wrote the detail. The key is ABSENT when the
    // refusal names no field (the ~25 doors that raise `InvalidPayload` by hand write prose): a
    // caller that keys on its presence must not read "this is about fields" into all of them.
    if let E::InvalidPayload { detail, .. } = &e {
        let fields = erplora_runtime::registry::invalid_payload_fields(detail);
        if !fields.is_empty() {
            error["fields"] = json!(fields);
        }
    }
    (status, json!({ "ok": false, "error": error }))
}

pub(crate) fn err_response(e: erplora_runtime::RuntimeError) -> Response {
    let (status, body) = error_payload(&e);
    (status, Json(body)).into_response()
}

/// Respuesta para un fallo de **enrutado multi-tenant** (ADR-0005, hub#24):
///  - `UnknownOrg` → `403`: el `hub_id` de la petición no pertenece a ninguna org conocida; es un
///    intento de acceso cruzado o un hub no provisionado. **No** se cae a ninguna BD.
///  - `PoolLimit` → `503`: back-pressure (techo de orgs por proceso alcanzado), reintenta luego.
///  - `Connect`   → `502`: la Aurora de la org no responde (failover/credencial).
pub(crate) fn tenant_rejected(e: tenant::TenantError) -> Response {
    use tenant::TenantError as T;
    let (status, code) = match &e {
        T::UnknownOrg(_) => (StatusCode::FORBIDDEN, "unknown_org"),
        T::PoolLimit(_) => (StatusCode::SERVICE_UNAVAILABLE, "pool_limit"),
        T::Connect(_) => (StatusCode::BAD_GATEWAY, "org_db_unavailable"),
    };
    let body = json!({ "ok": false, "error": { "code": code, "message": e.to_string() } });
    (status, Json(body)).into_response()
}

/// Gate del dispatcher (revalidación híbrida del entitlement, ver `crate::entitlement`): si el
/// módulo dueño de la query/command está **bloqueado**, devuelve el error estable
/// `module_entitlement_blocked` (HTTP 402) con su `module_id` para que el front lo distinga y
/// pinte el aviso («funcionará hasta {fecha}»). `None` = no bloqueado → la ejecución sigue.
/// Defensa en profundidad: el enforcement REAL es el proxy del SaaS; aquí NUNCA se desinstala
/// ni se tocan datos. `module_id = None` (op desconocida) no se gatea: `execute_*` devolverá su
/// `not_found` de siempre.
pub(crate) fn entitlement_blocked(st: &AppState, module_id: Option<&str>) -> Option<Response> {
    let module_id = module_id?;
    let blocked = st
        .entitlement
        .read()
        .ok()?
        .is_blocked(module_id, entitlement::now_unix());
    if !blocked {
        return None;
    }
    let body = json!({ "ok": false, "error": {
        "code": "module_entitlement_blocked",
        "module_id": module_id,
        "message": format!("el módulo `{module_id}` no está incluido en el entitlement vigente del hub"),
    }});
    Some((StatusCode::PAYMENT_REQUIRED, Json(body)).into_response())
}

/// `401` uniforme para fallos de autenticación (modo Jwt: token ausente/ inválido).
pub(crate) fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// The same refusal, telling **"who are you"** apart from **"not you"** (hub#660): a valid session
/// with an insufficient role answers `403`, because re-authenticating as the same cashier would
/// never help. The body carries a **stable code** (`unauthorized` / `forbidden`) next to the
/// message, the shape of [`tenant_rejected`] and of the dead-letter doors (`outbox_admin`): the UI
/// branches on the code, never on prose (hub#1241). One implementation on purpose — two copies of
/// a refusal is how one ends up being the permissive one.
pub(crate) fn auth_rejected(e: auth::AuthError) -> Response {
    let (status, code) = if e.is_forbidden() {
        (StatusCode::FORBIDDEN, "forbidden")
    } else {
        (StatusCode::UNAUTHORIZED, "unauthorized")
    };
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": e.message() } })),
    )
        .into_response()
}

/// axum's rejection of a body, said in the shape every other answer of these doors uses (hub#1691).
///
/// `Json<T>` refuses a body it cannot read BEFORE the handler runs, and axum answers that on its
/// own: a line of English prose, no JSON, no `{ok, error}`. Every door this is used on is on the
/// module surface, and module code reads answers through `unwrap(env)` in `@erplora/module-sdk`,
/// which looks for `ok` or throws `ErploraError('error', 'unknown error')` — so the sentence
/// naming the bad field is stripped off on the way and the module is left with nothing to say and
/// nothing to branch on.
///
/// The status is the extractor's own and is NOT flattened: `422` means «read as JSON, a field is
/// missing» and `400` means «that is not JSON», which is the difference between a body worth
/// re-sending with a fix and a bug in whatever built the request. The sentence is kept too — it is
/// the half that names the field — while the code is what a caller branches on (ADR-0055).
pub(crate) fn invalid_body(rejection: axum::extract::rejection::JsonRejection) -> Response {
    (
        rejection.status(),
        Json(json!({
            "ok": false,
            "error": { "code": "invalid_body", "message": rejection.body_text() }
        })),
    )
        .into_response()
}

pub(crate) async fn query(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Result<Json<QueryReq>, axum::extract::rejection::JsonRejection>,
) -> Response {
    // Caught rather than left to axum: this is the busiest door a module has, and its rejection
    // reaches module code as a blank `unknown error` (hub#1691, see `invalid_body`).
    let Json(req) = match body {
        Ok(json) => json,
        Err(rejection) => return invalid_body(rejection),
    };
    // Tier cloud compartido (ADR-0005): resuelve el runtime de la ORG dueña del `hub_id` de la
    // petición (un pool por org). En single-tenant devuelve el runtime único. El rechazo cross-org
    // (hub_id de org desconocida) ocurre aquí, ANTES de tocar ninguna BD.
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.hub_id())).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.read().await;
    let mut ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    // Entitlement-blocked module ids (hub#1175), stamped on the context so the runtime's own idea
    // of "available" — `hub.setup.status` reads it right next to `is_active` — cannot promise a
    // route the entitlement gate below is about to refuse for a DIFFERENT query. Same source as
    // `revalidation.blocked_modules` on `GET /api/entitlement` (`proxy_entitlement`): this hub's
    // installed ids against the last verified claims.
    let installed: Vec<String> = rt.modules().into_iter().map(|m| m.id).collect();
    if let Ok(revalidation) = st.entitlement.read() {
        ctx.blocked_modules = revalidation
            .blocked_modules(&installed, entitlement::now_unix())
            .into_iter()
            .collect();
    }
    // Gate de entitlement (defensa en profundidad): módulo dueño bloqueado → 402 estable.
    let owner = rt
        .registry()
        .get_query(&req.name)
        .map(|q| q.module_id.clone());
    if let Some(resp) = entitlement_blocked(&st, owner.as_deref()) {
        return resp;
    }
    // Queries de lista (con bloque `list`) devuelven `{rows,total,limit,offset}` para el pager;
    // el resto devuelve el array de filas tal cual (compat con get/stats/settings).
    if rt.is_list_query(&req.name) {
        match rt.execute_query_page(&req.name, &req.params, &ctx).await {
            Ok(page) => Json(json!({ "ok": true, "data": page })).into_response(),
            Err(e) => err_response(e),
        }
    } else {
        match rt.execute_query(&req.name, &req.params, &ctx).await {
            Ok(rows) => Json(json!({ "ok": true, "data": rows })).into_response(),
            Err(e) => err_response(e),
        }
    }
}

pub(crate) async fn command(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Result<Json<CommandReq>, axum::extract::rejection::JsonRejection>,
) -> Response {
    // Caught rather than left to axum: this is the busiest door a module has, and its rejection
    // reaches module code as a blank `unknown error` (hub#1691, see `invalid_body`).
    let Json(req) = match body {
        Ok(json) => json,
        Err(rejection) => return invalid_body(rejection),
    };
    // Mismo enrutado por org que `query` (ADR-0005): el `PgAdapter` de la org corre server-side.
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.hub_id())).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    // Guard COMPARTIDO (hub#978): N cajas cobrando a la vez ejecutan sus commands en paralelo
    // —la transacción la da Postgres y el gasto de una aprobación lo da el propio store de
    // grants—; solo una instalación/activación (escritor) espera a que estos terminen.
    let rt = arc.read().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    // hub#361: a step-up approval the caller already obtained, presented OUT OF BAND. It is a
    // lookup key into the runtime's own store — an unknown or foreign one is worth exactly as
    // much as no header at all — and it is read here and not in `authenticate` on purpose:
    // `/api/query` never elevates (a PIN that unlocks a report leaves no trace of who approved),
    // and neither does the public API-key surface (nobody is standing at an integration).
    let ctx = match auth::elevation_token(&headers) {
        Some(token) => ctx.with_elevation_token(token),
        None => ctx,
    };
    // Gate de entitlement (defensa en profundidad): módulo dueño bloqueado → 402 estable.
    let owner = rt
        .registry()
        .get_command(&req.name)
        .map(|c| c.module_id.clone());
    if let Some(resp) = entitlement_blocked(&st, owner.as_deref()) {
        return resp;
    }
    match rt.execute_command(&req.name, &req.payload, &ctx).await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Body de `POST /api/error-report` (lo postea el frontend). Forma libre del web app:
/// `{ type, message, stack?, url?, component?, module_id? }`. `type` mapea a `error_code`.
#[derive(Deserialize)]
pub(crate) struct FrontendErrorReq {
    /// Tipo del error JS (p. ej. `"js_error"`); se usa como `error_code` del evento.
    #[serde(default = "default_js_error_type")]
    r#type: String,
    #[serde(default)]
    message: String,
    #[serde(default)]
    stack: Option<String>,
    #[serde(default)]
    url: Option<String>,
    #[serde(default)]
    component: Option<String>,
    /// Si el error vino de un Web Component de módulo, su `module_id` (atribución).
    #[serde(default)]
    module_id: Option<String>,
}

pub(crate) fn default_js_error_type() -> String {
    "js_error".to_string()
}

/// POST /api/error-report — embudo del frontend hacia el registro global de errores.
///
/// Same-origin, **sin auth cloud** (el navegador nunca ve el `cloud_api_token`): el web app postea
/// su error JS y el runtime lo normaliza a un `ErrorEvent{ source:"frontend", … }`, lo manda al
/// registro global (que dedup/throttlea y reenvía al Cloud por el sink) y devuelve `{ "ok": true }`.
/// Severidad fija "unexpected" (un error JS no capturado es un fallo, no una acción de usuario).
pub(crate) async fn frontend_error_report(Json(req): Json<FrontendErrorReq>) -> Response {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};

    let mut event = ErrorEvent::new(
        source::FRONTEND,
        req.r#type,
        req.message,
        severity::UNEXPECTED,
    )
    .with_context(json!({ "url": req.url, "component": req.component }));
    if let Some(stack) = req.stack {
        event = event.with_stack(stack);
    }
    if let Some(module_id) = req.module_id {
        event = event.with_module(module_id);
    }
    ErrorRegistry::global().report(event);

    Json(json!({ "ok": true })).into_response()
}

#[cfg(test)]
mod err_response_tests {
    //! hub#139: HTTP mapping of the domain error channel. The namespaced code must travel to
    //! the caller verbatim (the UI translates by code), on a status the SDK never swallows.
    use super::err_response;
    use axum::http::StatusCode;
    use erplora_runtime::RuntimeError;
    use http_body_util::BodyExt;
    use serde_json::Value;

    async fn shape(e: RuntimeError) -> (StatusCode, Value) {
        let resp = err_response(e);
        let status = resp.status();
        let bytes = resp.into_body().collect().await.unwrap().to_bytes();
        (status, serde_json::from_slice(&bytes).unwrap())
    }

    #[tokio::test]
    async fn domain_error_maps_to_409_with_the_namespaced_code() {
        let (status, body) = shape(RuntimeError::Domain {
            code: "inventory.insufficient_stock".into(),
            message: "Not enough stock".into(),
        })
        .await;
        assert_eq!(status, StatusCode::CONFLICT);
        assert_eq!(body["ok"], Value::Bool(false));
        assert_eq!(body["error"]["code"], "inventory.insufficient_stock");
        assert_eq!(body["error"]["message"], "Not enough stock");
    }

    #[tokio::test]
    async fn min_affected_rows_maps_to_409_with_its_stable_kind_code() {
        // Before hub#139 this fell into the generic 400 `{code:"error"}` bucket, erasing the
        // stable `not_found`/`conflict` code hub#140 introduced at the runtime layer.
        let (status, body) = shape(RuntimeError::MinAffectedRows {
            command: "w140.items.confirm".into(),
            required: 1,
            affected: 0,
            kind: erplora_runtime::errors::AffectedKind::NotFound,
        })
        .await;
        assert_eq!(status, StatusCode::CONFLICT);
        assert_eq!(body["error"]["code"], "not_found");
    }

    /// hub#1094: the generic Settings screen swallowed the 422 — «Save» came back
    /// `invalid_payload` and nothing on screen changed. It cannot mark the offending controls
    /// while the only thing it gets is a sentence, and parsing the sentence is exactly what this
    /// house does not do: the list travels as a FIELD, like `permission` (hub#360) and
    /// `dependents` (hub#1101) already do.
    #[tokio::test]
    async fn invalid_payload_names_the_offending_fields_as_a_field_of_the_envelope() {
        let (status, body) = shape(RuntimeError::InvalidPayload {
            name: "kitchen.settings.update".into(),
            detail: "/auto_bump_delay_seconds: null is not of type \"integer\"; \
                     /default_order_type: \"\" is not one of [\"dine_in\"]"
                .into(),
        })
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(body["error"]["code"], "invalid_payload");
        assert_eq!(
            body["error"]["fields"],
            serde_json::json!(["auto_bump_delay_seconds", "default_order_type"]),
        );
    }

    /// The other refusals must NOT grow the field: a caller that keys on its presence would read
    /// «this one is about fields» into every hand-written rejection in the runtime.
    #[tokio::test]
    async fn a_refusal_that_names_no_field_carries_no_fields_key() {
        let (_, body) = shape(RuntimeError::InvalidPayload {
            name: "hub.device_mode.set".into(),
            detail: "modo de dispositivo desconocido: `kiosko`".into(),
        })
        .await;
        assert!(
            body["error"].get("fields").is_none(),
            "una negativa sin campos no debe inventarse la clave, got {body}"
        );
    }
}

#[cfg(test)]
mod error_redaction_tests {
    //! hub#1074 / hub#1102 — WHAT a client is allowed to read when the hub fails.
    //!
    //! The HTTP end of this lives in `tests/error_redaction_door.rs` (a real foreign-key violation
    //! through `/api/command`). Here the policy is pinned variant by variant, because the door test
    //! can only reach the variants a fixture happens to be able to provoke — and a security rule
    //! whose coverage depends on that has holes exactly where nobody looks.
    use super::{error_payload, REDACTED_MESSAGE};
    use erplora_runtime::RuntimeError;

    fn error_of(e: RuntimeError) -> serde_json::Value {
        error_payload(&e).1["error"].clone()
    }

    /// Plumbing that wraps a foreign library never speaks to a client. (The `Db` variant of the
    /// same family needs a real `sqlx::Error` to build, so it is pinned where it actually happens:
    /// `tests/error_redaction_door.rs` provokes a genuine foreign-key violation over
    /// `/api/command` and asserts the driver's words never come back.)
    #[test]
    fn plumbing_is_redacted_and_keeps_its_stable_code() {
        let e = RuntimeError::Io(std::io::Error::other(
            "/srv/erplora/modules/sales: permission denied",
        ));

        let error = error_of(e);
        assert_eq!(error["message"], REDACTED_MESSAGE);
        assert_eq!(error["code"], "io");
    }

    /// The net under the variants we DO let speak: `Other` is a grab-bag of ~50 sites, half of
    /// which wrap a `DbError` inside an otherwise perfectly readable sentence
    /// (`reset: la transacción falló, nada se borró: {e}`). Per-variant rules alone would keep
    /// publishing the driver through them.
    #[test]
    fn driver_text_smuggled_inside_an_authored_sentence_is_redacted_too() {
        let e = RuntimeError::Other(
            "reset: la transacción falló, nada se borró: sqlx: error returned from database".into(),
        );
        assert_eq!(error_of(e)["message"], REDACTED_MESSAGE);
    }

    /// …and the other half of `Other` still says something a person can act on.
    #[test]
    fn an_authored_sentence_without_driver_text_still_reaches_the_client() {
        let e = RuntimeError::Other("usuario no encontrado".into());
        assert_eq!(error_of(e)["message"], "usuario no encontrado");
    }

    /// ADR-0205 / hub#139: the one channel a module has to say something true about the request.
    /// Redacting this would silence the modules, which is the opposite of the point.
    #[test]
    fn a_module_domain_rejection_is_never_redacted() {
        let e = RuntimeError::Domain {
            code: "inventory.insufficient_stock".into(),
            message: "Not enough stock".into(),
        };
        let error = error_of(e);
        assert_eq!(error["code"], "inventory.insufficient_stock");
        assert_eq!(error["message"], "Not enough stock");
    }

    /// hub#1102: the cashier's dialog printed `required read \`taxes.rules.list\` is unavailable —
    /// the command was aborted (hub#701)`. The code is what the shell translates and the query is
    /// a field it reads; neither the backticks nor the issue number belong on a till.
    #[test]
    fn an_unavailable_required_read_carries_a_code_and_the_query_as_a_field() {
        let error = error_of(RuntimeError::ReadUnavailable {
            query: "taxes.rules.list".into(),
        });

        assert_eq!(error["code"], "read_unavailable");
        assert_eq!(error["query"], "taxes.rules.list");
        assert!(
            !error["message"]
                .as_str()
                .unwrap_or_default()
                .contains("hub#"),
            "an issue number is not something a cashier can act on: {error}"
        );
    }

    /// A WASM trap is the hub's plumbing, not the module talking: a handler that wants to say
    /// something to the caller returns `Output.error`, which arrives as `Domain`.
    #[test]
    fn a_wasm_trap_is_plumbing() {
        assert_eq!(
            error_of(RuntimeError::Wasm("unreachable executed at 0x4f2".into()))["message"],
            REDACTED_MESSAGE
        );
    }

    /// The variants #1185 added while this branch was open (`InvalidField`, `ManifestRejected`;
    /// the third, `CertificateTypeMismatch`, was retired with its door in hub#1490). The
    /// exhaustive `match` of `may_reach_the_client` made the compiler ask which side of the door
    /// each stands on; this pins the ANSWER, because «it compiles» only proves somebody chose,
    /// not that they chose right. Both are authored by us for whoever has to fix them, and both
    /// carry a code and the offending element as data.
    #[test]
    fn the_contract_refusals_of_1185_reach_the_client_with_their_code_and_their_data() {
        let field = error_of(RuntimeError::InvalidField {
            name: "hub.users".into(),
            field: "name".into(),
            reason: "required".into(),
            detail: "the name is required".into(),
        });
        assert_eq!(field["code"], "invalid_field");
        assert_eq!(field["field"], "name");
        assert_eq!(field["reason"], "required");
        assert_eq!(field["message"], "the name is required");

        let manifest = error_of(RuntimeError::ManifestRejected {
            module: "kitchen".into(),
            at: "roles[0]".into(),
            code: "role_grants_admin".into(),
            detail: "a module never grants administration of the hub".into(),
        });
        assert_eq!(manifest["code"], "role_grants_admin");
        assert_eq!(manifest["at"], "roles[0]");
        assert_ne!(manifest["message"], REDACTED_MESSAGE);
    }

    /// …and the net still runs under them. `InvalidField.detail` is authored today, but the whole
    /// point of `carries_driver_text` is that «authored» is a habit, not a guarantee: the day a
    /// refusal interpolates a `DbError` into its detail, the driver must still not come out.
    #[test]
    fn a_contract_refusal_that_smuggles_driver_text_is_redacted_anyway() {
        let error = error_of(RuntimeError::InvalidField {
            name: "hub.users".into(),
            field: "name".into(),
            reason: "duplicate".into(),
            detail: "could not check: sqlx: error returned from database".into(),
        });
        assert_eq!(error["message"], REDACTED_MESSAGE);
        // The code and the data survive: what is redacted is the PROSE, never the contract.
        assert_eq!(error["code"], "invalid_field");
        assert_eq!(error["field"], "name");
    }

    /// The refusals a screen ACTS on keep their sentence AND their field. Redacting by default and
    /// exempting case by case would have swallowed these the day someone added a variant.
    #[test]
    fn refusals_the_screen_acts_on_keep_their_sentence() {
        let elevation = error_of(RuntimeError::RequiresElevation {
            permission: "sales.refund".into(),
        });
        assert_eq!(elevation["permission"], "sales.refund");
        assert!(
            elevation["message"]
                .as_str()
                .unwrap_or_default()
                .contains("sales.refund"),
            "{elevation}"
        );

        let dependents = error_of(RuntimeError::HasDependents {
            module: "taxes".into(),
            dependents: vec!["sales".into(), "invoicing".into()],
        });
        assert_eq!(dependents["code"], "has_dependents");
        assert_eq!(dependents["dependents"][0], "sales");
        assert!(
            dependents["message"]
                .as_str()
                .unwrap_or_default()
                .contains("sales"),
            "{dependents}"
        );
    }
}

#[cfg(test)]
mod error_field_tests {
    //! hub#1102 — the app an error is ABOUT travels as a field, never inside the sentence.
    //!
    //! Same rule as `permission` (hub#360) and `dependents` (hub#1101), for the same reason: the
    //! screen names the app («Falta la app Impuestos»), and the only way to name it from a message
    //! like «módulo no instalado: `taxes` (requerido por `sales.complete_sale`)» is to parse
    //! backticks out of prose — which is how a screen silently stops naming anything.
    use super::error_payload;
    use erplora_runtime::RuntimeError;

    fn error_of(e: RuntimeError) -> serde_json::Value {
        error_payload(&e).1["error"].clone()
    }

    #[test]
    fn a_missing_module_names_it_as_a_field() {
        let error = error_of(RuntimeError::ModuleNotInstalled {
            module: "taxes".into(),
            operation: "taxes.rules.list".into(),
        });
        assert_eq!(error["code"], "module_not_installed");
        assert_eq!(error["module"], "taxes");
    }

    #[test]
    fn a_switched_off_module_names_it_as_a_field() {
        let error = error_of(RuntimeError::ModuleInactive {
            module: "taxes".into(),
            operation: "taxes.rules.list".into(),
        });
        assert_eq!(error["code"], "module_inactive");
        assert_eq!(error["module"], "taxes");
    }

    /// The install-time twin: the app that is MISSING is `dep`, not the one being installed — that
    /// is the one the sentence has to send the owner after.
    #[test]
    fn an_unsatisfied_dependency_names_the_app_that_is_missing() {
        let error = error_of(RuntimeError::MissingDependency {
            module: "sales".into(),
            dep: "taxes".into(),
        });
        assert_eq!(error["code"], "missing_dependency");
        assert_eq!(error["module"], "taxes");
    }
}
