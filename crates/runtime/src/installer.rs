//! Ciclo de vida de módulos desde una carpeta ya extraída (ARQUITECTURA.md §4):
//! validar manifest → comprobar dependencias → migrar → registrar capacidades → estado.
//! El estado por hub se persiste en la tabla `hub_module` (§2.5). La descarga/verificación
//! SHA256 del zip es responsabilidad de `erplora-source`.
use std::path::Path;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::loader;
use crate::manifest::Manifest;
use crate::migrations;
use crate::registry::{
    CompiledSchema, ModuleStatus, NavEntry, RegisteredCommand, RegisteredQuery, Registry,
};

// Baseline (v0) de `hub_module`: PK simple `module_id`. La migración de sistema v1 (hub#31 /
// ADR-0005) la recompone a PK `(hub_id, module_id)` para BD compartida por org. Las BD nuevas
// nacen con este baseline y la v1 lo migra al arrancar (ver `system_migrations.rs`); las viejas
// que ya tienen la tabla reciben el cambio por la misma v1. No editar este baseline para añadir
// hub_id aquí: el cambio de esquema va SIEMPRE por migración versionada para que llegue a BD
// existentes (un `CREATE IF NOT EXISTS` no altera una tabla ya creada).
const ENSURE_HUB_MODULE: &str = "CREATE TABLE IF NOT EXISTS hub_module (\
    module_id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL, \
    installed_at TEXT NOT NULL, updated_at TEXT NOT NULL);";

/// Seed suplementario de IVA España (hub#107): completa la baseline IVA ES (21/10/4) que la
/// semilla del módulo `taxes` deja a medias. Versionado en `crates/server/seeds/es_iva.sql` y
/// embebido aquí para no depender del FS en el arranque (igual que `seed.rs` con `demo.sql`).
/// Ver `es_iva.sql` para el porqué.
const ES_IVA_SEED: &str = include_str!("../../server/seeds/es_iva.sql");

/// Asegura el baseline (v0) de `hub_module` (idempotente). Lo llama `ensure_system_tables` antes
/// de aplicar las migraciones de sistema, para que la migración v1 (que recrea/altera la tabla)
/// tenga sobre qué operar también en un hub vacío.
pub async fn ensure_hub_module_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_HUB_MODULE).await?;
    Ok(())
}

/// Instala el módulo de `dir` en el registro, aplica migraciones y lo deja **activo**.
/// Persiste el estado en `hub_module` **scoped por `hub_id`** (§2.5). Devuelve el id del módulo.
pub async fn install(
    db: &dyn DatabaseAdapter,
    registry: &mut Registry,
    hub_id: &str,
    dir: &Path,
) -> Result<String> {
    let manifest = Manifest::load(dir)?;
    // hub#139: id-dependent contract checks (domain error namespaces, exclusive row gates)
    // run BEFORE any side effect — a broken contract never reaches migrations or the registry.
    validate_command_contracts(&manifest)?;
    // hub#351 (paso 2b): same door for the roles the module declares. A manifest may add roles to
    // the hub's catalogue, but it can neither redefine a base role nor hand out administration.
    validate_role_declarations(&manifest)?;
    // ADR-0273 D6 (hub#555): same door for the regime a module claims to implement. What it
    // declares here is what the core will COUNT as a provider, so a malformed block must not be
    // stored — it would read as "no provider installed", which blocks a till.
    validate_fiscal_regime(&manifest)?;
    // ADR-0273 D7 (hub#559): and if what it declares is THIS hub's regime, it may not be sold.
    // Defensive: no published module is in that position today (see the function).
    validate_fiscal_provider_is_free(db, hub_id, &manifest).await?;

    // `hub` es el namespace RESERVADO del core (ADR-0192): el dispatcher resuelve `hub.*` antes de
    // mirar el registry, así que un módulo con ese id tendría capacidades inalcanzables y aparentaría
    // servir la identidad del propio Hub. Se rechaza en la frontera hostil (el zip de terceros).
    if manifest.id == crate::hub_users::CORE_NAMESPACE.trim_end_matches('.') {
        return Err(RuntimeError::Storage(format!(
            "`{}` es un id reservado del core: ningún módulo puede ocupar el namespace `{}`",
            manifest.id,
            crate::hub_users::CORE_NAMESPACE
        )));
    }

    // `static_files.folder` es un nombre, nunca una ruta. Se vuelve a validar en runtime aunque el
    // toolkit ya lo haga: un ZIP descargado es una frontera hostil. Si el host ha inyectado el
    // backend, materializamos la carpeta ANTES de activar el módulo.
    if let Some(static_files) = &manifest.static_files {
        if !static_files.is_valid_folder() {
            return Err(RuntimeError::Storage(format!(
                "carpeta inválida en `static_files.folder`: `{}`",
                static_files.folder
            )));
        }
        if let Some(storage) = registry.module_storage.clone() {
            storage
                .ensure_module_folder(hub_id, &static_files.folder)
                .await?;
        }
    }

    // Tablas de sistema del runtime (outbox de eventos): necesarias en cuanto un command emita.
    crate::outbox::ensure_tables(db).await?;

    if registry.is_installed(&manifest.id) {
        // Reinstalar = volver a registrar capacidades (p. ej. tras update). Limpiamos antes.
        registry.remove_module(&manifest.id);
    }

    // Dependencias declaradas deben estar ya instaladas (orden topológico = del llamador).
    for dep in &manifest.depends_on {
        if !registry.is_installed(dep) {
            return Err(RuntimeError::MissingDependency {
                module: manifest.id.clone(),
                dep: dep.clone(),
            });
        }
    }

    migrations::apply(db, dir, &manifest).await?;

    // Datos de REFERENCIA del módulo (ADR-0147): unidades de medida, categorías fiscales… lo que
    // todo hub necesita y el usuario no puede aportar. Va DESPUÉS de migrar porque escribe en las
    // tablas que las migraciones acaban de crear, y es idempotente por contrato (`WHERE NOT
    // EXISTS`), así que reinstalar no duplica.
    //
    // Esto llevaba declarado en `taxes` desde ADR-0085 sin que lo ejecutara nadie: el bloque no
    // estaba en `module.schema.json` ni había una línea de Rust que lo leyera, así que las
    // categorías fiscales canónicas y las reglas de IVA de España NO se sembraban al instalar.
    // Hub Cloud es Postgres-only (ADR-0154): siempre el seed del dialecto `postgres`.
    let seed_files = &manifest.seed.postgres;
    if !seed_files.is_empty() {
        let now = crate::registry::now_rfc3339();
        for file in seed_files {
            let sql = loader::read_text(dir, file.file())?;
            crate::seed::apply_module_seed(db, &sql, hub_id, &now).await?;
        }
    }

    // Seed suplementario de IVA España para hubs ES (hub#107): la semilla propia del módulo
    // `taxes` cubre 21% (genéricos/alcohol) y 10% (restauración), pero NO el tipo superreducido
    // del 4% ni deja baseline útil para categorías genéricas al alta de producto. Sin esto, un
    // hub de hostelería ES no puede vender correctamente tras instalar `taxes` sin configurar el
    // IVA a mano. El SQL es idempotente (`WHERE NOT EXISTS` por la clave natural) y compone con
    // la semilla del módulo (mismas claves); re-instalar no duplica. Sólo para hubs cuyo
    // `country_code` = ES (default ES, ADR-0085): un hub de otro país no recibe reglas ES.
    if manifest.id == "taxes" {
        if crate::settings::country_code_of(db, hub_id).await? == "ES" {
            let now = crate::registry::now_rfc3339();
            crate::seed::apply_module_seed(db, ES_IVA_SEED, hub_id, &now).await?;
        }
    }

    for perm in &manifest.permissions {
        registry.permissions.insert(perm.clone());
    }
    for (name, def) in &manifest.queries {
        let sql = loader::read_text(dir, &def.sql)?;
        let schema = load_schema(dir, name, def.schema.as_deref())?;
        registry.queries.insert(
            name.clone(),
            RegisteredQuery {
                module_id: manifest.id.clone(),
                def: def.clone(),
                sql,
                schema,
            },
        );
    }
    for (name, def) in &manifest.commands {
        let mut sql = Vec::with_capacity(def.sql.len());
        for rel in &def.sql {
            sql.push(loader::read_text(dir, rel)?);
        }
        // Tier 2: si el command declara un handler WASM, lee sus bytes del disco.
        // (Los handlers `native` no llevan fichero: el plugin va horneado en el runtime,
        // registrado vía `Runtime::register_native` — ADR-0009.)
        let wasm = match &def.handler {
            Some(handler) if handler.kind == "wasm" => {
                let file = handler.file.as_deref().ok_or_else(|| {
                    RuntimeError::Wasm(format!(
                        "command `{name}`: handler wasm sin `file` en el manifest"
                    ))
                })?;
                let path = dir.join(file);
                let bytes = std::fs::read(&path).map_err(|e| {
                    RuntimeError::Io(std::io::Error::new(
                        e.kind(),
                        format!("no se pudo leer wasm `{}`: {e}", path.display()),
                    ))
                })?;
                Some(bytes)
            }
            _ => None,
        };
        let schema = load_schema(dir, name, def.schema.as_deref())?;
        registry.commands.insert(
            name.clone(),
            RegisteredCommand {
                module_id: manifest.id.clone(),
                def: def.clone(),
                sql,
                wasm,
                schema,
            },
        );
    }
    for (event, listener) in &manifest.events.listen {
        registry
            .listeners
            .entry(event.clone())
            .or_default()
            .push(listener.command.clone());
    }
    for nav in &manifest.navigation {
        registry.navigation.push(NavEntry {
            module_id: manifest.id.clone(),
            nav: nav.clone(),
        });
    }
    // Traducciones del módulo (ADR-0055): `locales/*.json` del paquete → registry. Best-effort;
    // si el módulo no trae i18n, el runtime sirve los valores del manifest (inglés canónico).
    registry.set_locales(&manifest.id, Manifest::load_locales(dir));

    // Vuelca las scheduled tasks del manifest a `_scheduled_tasks` (ADR-0011). Idempotente:
    // preserva el reloj (next_run/last_run) de las tareas ya existentes en una reinstalación y
    // borra las retiradas del manifest. El `command` de cada tarea debe ser del propio módulo.
    crate::scheduler::seed_module_tasks(db, &manifest.id, &manifest.scheduled_tasks).await?;

    let id = manifest.id.clone();
    let version = manifest.version.clone();
    registry.installed.push(manifest);
    registry.status.insert(id.clone(), ModuleStatus::Active);

    persist_status(db, hub_id, &id, &version, ModuleStatus::Active).await?;
    Ok(id)
}

/// Validations that depend on the module id and therefore cannot be expressed by the JSON
/// Schema alone (hub#139): the error namespace must be the module's own, and the legacy gate
/// (`min_affected_rows`) is mutually exclusive with the translatable one (`expect_rows`).
fn validate_command_contracts(manifest: &Manifest) -> Result<()> {
    for (name, command) in &manifest.commands {
        if command.min_affected_rows.is_some() && command.expect_rows.is_some() {
            return Err(RuntimeError::Other(format!(
                "manifest `{}`: command `{name}` cannot combine `min_affected_rows` and `expect_rows`",
                manifest.id
            )));
        }
        if let Some(expect) = &command.expect_rows {
            if !crate::errors::valid_domain_code(&manifest.id, &expect.error) {
                return Err(RuntimeError::Other(format!(
                    "manifest `{}`: command `{name}` declares the invalid domain code `{}`; expected `{}.<snake_case>`",
                    manifest.id, expect.error, manifest.id
                )));
            }
            if expect
                .message
                .as_ref()
                .is_some_and(|message| message.chars().count() > 500)
            {
                return Err(RuntimeError::Other(format!(
                    "manifest `{}`: command `{name}` exceeds 500 characters in `expect_rows.message`",
                    manifest.id
                )));
            }
        }
    }
    Ok(())
}

/// Longest accepted `roles[].key`. It is stored in `hub_user.role` and used as a
/// `role_permissions` key, so it is an identifier with a bounded size, not free text.
const MAX_ROLE_KEY_LEN: usize = 32;

/// Validates the `roles[]` block of a manifest (paso 2b, hub#351) — the roles a module declares
/// for its vertical (`waiter`, `kitchen`, `accountant`) on top of the frozen base catalogue.
///
/// Runs at INSTALL time, before any side effect, for the same reason as the command contracts
/// (hub#139): a `module.zip` is third-party input, and by the time migrations have run it is too
/// late to say no.
///
/// Four things are checked, and the last one is the one that matters:
///
/// 1. **The key is an identifier.** It is what `role_permissions` grants against and what lands in
///    `hub_user.role`, so free text would leak into a data column and into the permission union.
/// 2. **It does not redefine a base role.** `admin`/`manager`/`employee` (and the legacy `owner`)
///    mean the same in the 24 published modules; a module extends that catalogue, it does not get
///    to reassign one of its keys.
/// 3. **`extends` resolves to a base role**, never to another declared role. That is what keeps
///    every role in the hub reducible to the frozen three-key contract, so the core gate and the
///    published modules keep working with no republish and no migration.
/// 4. **🔴 `extends` is never the administrative role.** A manifest cannot mint an administrator.
///    Administering the hub comes from the hub itself (`HUB_OWNER_EMAIL`, ADR-0157) and from the
///    floor the account role imposes at login (hub#347) — never from a declaration a third party
///    ships in a zip. The gate ([`crate::hub_users::is_admin_role`]) refuses a declared role on
///    its own, so this is the second lock on the same door: the manifest is rejected outright
///    instead of being silently downgraded, which would leave the author believing the role
///    administers when it does not.
///
/// What is deliberately NOT checked: that every key in `role_permissions` is declared here. A
/// role's permissions are the union of what the INSTALLED modules grant to that key, so `sales`
/// may grant `waiter` (declared by `tables`) `add_sale` without `take_payment`. Requiring the
/// declaration would force every module to know roles it did not invent — the opposite of the
/// design — and would break manifests that already grant to keys of their own.
/// Validates the optional `fiscal_regime` block of a manifest (ADR-0273 D6, hub#555).
///
/// The block is what makes a module count as a **provider** of the regime a hub owes, so it is
/// checked at the hostile border (a third-party zip) and not only by the JSON Schema: a malformed
/// declaration would join against nothing and read exactly like "nobody is complying" — which, once
/// hub#556 lands, stops a till. Better to refuse the module than to install a provider that
/// silently is not one.
///
/// Two checks and no more, because only two things are joined on:
///
/// 1. `country` is ISO-3166-1 alpha-2 — the shape of `hub_settings.country_code` and of
///    `_hub_fiscal_regime_registry.country_code`. Free text never matches.
/// 2. `regime` is non-empty — an empty key declares nothing while looking like a declaration.
///
/// What is deliberately NOT checked: that the regime exists in the core's registry. A module may
/// legitimately ship before the country is seeded (the registry is data, and adding a country is a
/// row), and refusing it here would make installing the provider depend on the very row the
/// provider exists to serve.
fn validate_fiscal_regime(manifest: &Manifest) -> Result<()> {
    let Some(fiscal) = manifest.fiscal_regime.as_ref() else {
        return Ok(()); // Not a fiscal provider — the shape of the 24 published manifests.
    };
    let reject = |detail: String| {
        Err(RuntimeError::Other(format!(
            "manifest `{}`: `fiscal_regime` {detail}",
            manifest.id
        )))
    };
    let country = fiscal.country.trim();
    if country.len() != 2 || !country.bytes().all(|b| b.is_ascii_alphabetic()) {
        return reject(format!(
            "declares `country: {}`, which is not an ISO-3166-1 alpha-2 code (two ASCII letters, \
             e.g. `ES`): it is joined against the hub's `country_code` and the core's regime \
             registry, so anything else matches nothing",
            fiscal.country
        ));
    }
    if fiscal.regime.trim().is_empty() {
        return reject(
            "declares an empty `regime`: the key is what the core counts providers of, and an \
             empty one declares nothing while looking like a declaration"
                .to_string(),
        );
    }
    Ok(())
}

/// The stable rejection code of the rule below. ABI público: the UI and the marketplace program
/// against the code, never against the message.
pub const PROVIDER_NOT_FREE: &str = "fiscal.provider_not_free";

/// **A module that fulfils the hub's own fiscal regime may not be SOLD** (ADR-0273 D7, hub#559).
///
/// ⚠️ **This fixes nothing that is broken.** VeriFactu is free (decisión de Ioan, 2026-08-08), so
/// the path *«the entitlement expired → VeriFactu off → the till keeps selling»* — one of the five
/// that motivated the ADR — does not exist: there is nothing to expire. Not paying costs the
/// customer **access to the hub**, which is a platform matter and not a fiscal one. Selling this as
/// a security fix would be a lie.
///
/// What it buys is that nothing brings it back **without anybody noticing**. A future price change,
/// or a third party implementing the same regime and charging for it, would reopen it — and the
/// mechanism that breaks the hub already exists: `module-system.md` §2bis, *«blocking = the
/// dispatcher refuses that module's queries and commands»*. Pointed at the fiscal provider, an
/// unpaid invoice leaves a hub that can neither transmit nor read its own queue. That turns a
/// billing incident into a fiscal fire, which is exactly the shape of failure ADR-0273 exists to
/// forbid: **a fiscal obligation may never depend on a module being licensed or available.**
///
/// Three things it deliberately does NOT do:
///
/// 1. **It does not judge commerce.** Only a module fulfilling the regime THIS hub owes is looked
///    at. A paid module that is not a fiscal provider (`whatsapp_inbox`), or one that provides
///    another country's regime, installs untouched — refusing those would be the runtime having an
///    opinion about somebody else's business model.
/// 2. **It does not break a dependency the hub already has.** Every restart re-registers the
///    installed modules through this very function ([`crate::Runtime::rehydrate_installed`], and
///    `install_all_from_dir` in dev), so a rule that only asked "is this sold?" would answer a price
///    change by refusing to mount the provider at the next boot — `BLOCKED`, till stopped, caused by
///    the guard itself. Same for a hub re-downloading its modules after a redeploy (Hub Cloud is
///    stateless: `installed_but_unregistered` → `install_from_cloud`). The door is at the moment the
///    hub TAKES the dependency; from then on the provider lock
///    ([`crate::fiscal_profile::ensure_provider_remains`]) is what governs it, and stopping a free
///    module from turning paid belongs in the SaaS, at publish time, where no till is open.
/// 3. **It does not read the marketplace's price.** It reads what the manifest DECLARES
///    ([`Manifest::sold_under`]), which is also what the SaaS's git sync writes into
///    `Module.tier`/`price` for a module of ours. A third party stripping the block from its zip
///    walks past this — which is why this is the second lock and not the only one: the first is the
///    SaaS refusing to publish it at all (ADR-0105 phase 1 already bars a third-party paid module).
///    What this door adds is the half the SaaS cannot have: it is the only place that knows which
///    regime **this** hub owes.
async fn validate_fiscal_provider_is_free(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    manifest: &Manifest,
) -> Result<()> {
    // Not a fiscal provider at all — the shape of 23 of the 24 published manifests. Cheapest check
    // first, and it keeps the install path from touching the database for almost every module.
    if manifest.fiscal_regime.is_none() {
        return Ok(());
    }
    let Some(term) = manifest.sold_under() else {
        return Ok(()); // Free, which is what a fiscal provider has to be.
    };
    // What this hub owes. `load` is tolerant of the table not being there (a runtime built straight
    // over an empty database), and a hub whose country has no regime owes nothing.
    let Some(profile) = crate::fiscal_profile::load(db, hub_id).await? else {
        return Ok(());
    };
    if profile.fiscal_system.trim().is_empty()
        || !manifest.fulfils_regime(&profile.country_code, &profile.fiscal_system)
    {
        return Ok(());
    }
    if already_installed(db, hub_id, &manifest.id).await {
        return Ok(()); // Point 2 above: never break a dependency the hub already has.
    }
    Err(RuntimeError::Domain {
        code: PROVIDER_NOT_FREE.to_string(),
        message: format!(
            "`{}` fulfils the fiscal regime this hub owes (`{}`) and declares {term}: complying \
             with the law cannot depend on a subscription staying paid, because the day it lapses \
             the hub can neither file nor read its own queue. A module that implements the active \
             regime has to be free",
            manifest.id, profile.fiscal_system
        ),
    })
}

/// Is `module_id` already recorded as installed for `hub_id`?
///
/// Read straight from `hub_module` instead of through [`installed_status`] because that one applies
/// the system migrations as a side effect, and this is called from inside `install`.
///
/// **An unreadable answer counts as "already installed"**, i.e. it makes the caller's guard step
/// aside. The guard above is defensive and has no live case; a false negative costs nothing, while
/// a false positive stops a till. The direction is chosen accordingly.
async fn already_installed(db: &dyn DatabaseAdapter, hub_id: &str, module_id: &str) -> bool {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    db.query(
        "SELECT module_id FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
        &p,
    )
    .await
    .map_or(true, |res| !res.rows.is_empty())
}

fn validate_role_declarations(manifest: &Manifest) -> Result<()> {
    let mut seen: std::collections::BTreeSet<&str> = std::collections::BTreeSet::new();
    for role in &manifest.roles {
        let key = role.key.as_str();
        let reject = |detail: String| {
            Err(RuntimeError::Other(format!(
                "manifest `{}`: role `{key}` {detail}",
                manifest.id
            )))
        };

        if !is_valid_role_key(key) {
            return reject(format!(
                "has an invalid key: expected snake_case ASCII (`^[a-z][a-z0-9_]*$`, up to \
                 {MAX_ROLE_KEY_LEN} chars), because the key is what `role_permissions` grants \
                 against and what `hub_user.role` stores"
            ));
        }
        if crate::hub_users::is_base_role(key) {
            return reject(format!(
                "collides with a base role of the hub ({}): a module EXTENDS the base catalogue, \
                 it never redefines an entry of it",
                crate::hub_users::BASE_ROLES.join(", ")
            ));
        }
        if !seen.insert(key) {
            return reject("is declared twice: a key names exactly one role".to_string());
        }
        if role.label.trim().is_empty() {
            return reject(
                "needs a non-empty `label`: it is what the administrator reads when activating the \
                 role"
                    .to_string(),
            );
        }
        if crate::hub_users::is_admin_role(&role.extends) {
            return reject(format!(
                "cannot extend `{}`: a module never grants administration of the hub (hub#347). \
                 That property comes from the hub itself (`HUB_OWNER_EMAIL`, ADR-0157) and from \
                 the floor the account role imposes at login, never from a manifest. Extend \
                 `manager` instead",
                role.extends
            ));
        }
        if !crate::hub_users::is_extendable_base_role(&role.extends) {
            return reject(format!(
                "declares `extends: {}`, which is not a base role of the hub: expected one of {}",
                role.extends,
                extendable_base_roles().join(", ")
            ));
        }
    }
    Ok(())
}

/// The base roles a declared role may hang from, for error messages. Derived from the catalogue so
/// the message cannot drift from the rule.
fn extendable_base_roles() -> Vec<&'static str> {
    crate::hub_users::BASE_ROLES
        .iter()
        .copied()
        .filter(|base| crate::hub_users::is_extendable_base_role(base))
        .collect()
}

/// Same shape as a module id or a permission segment: lowercase ASCII, digits and `_`.
fn is_valid_role_key(key: &str) -> bool {
    let mut chars = key.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_lowercase())
        && key.len() <= MAX_ROLE_KEY_LEN
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

/// Lee y **compila** el JSON Schema del payload de una query/command (si lo declara).
/// Se compila UNA vez aquí (instalación) y queda cacheado en el `Registry`; un schema
/// ilegible o que no compila aborta la instalación con error tipado (hub#27).
fn load_schema(dir: &Path, name: &str, rel: Option<&str>) -> Result<Option<CompiledSchema>> {
    let Some(rel) = rel else { return Ok(None) };
    let text = loader::read_text(dir, rel)?;
    let value: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| RuntimeError::Schema {
            name: name.to_string(),
            detail: format!("{rel}: JSON inválido: {e}"),
        })?;
    let compiled = CompiledSchema::compile(&value).map_err(|detail| RuntimeError::Schema {
        name: name.to_string(),
        detail: format!("{rel}: {detail}"),
    })?;
    Ok(Some(compiled))
}

/// **Retention gate (hub#314, ADR-0202 guard R2).** Refuses to let a module go while its native
/// engine still owes work to an external authority.
///
/// `uninstall` used to delete the `hub_module` row without looking at the queue, and `deactivate`
/// silenced the module the same way through a quieter door: the VeriFactu records left unsent
/// became literal orphans — no scheduled task, no UI, nobody left to drain them, so the invoices
/// stayed outside the AEAT chain (VeriFactu FAQ §5). The runtime asks the engine first and
/// rejects with its stable domain code, so the refusal is programmable and translatable instead
/// of a mute no-op.
///
/// Structural, not a hardcoded module id: any first-party engine ([`NativeHandler`]) may report
/// what it owes, and one that reports nothing (the default) keeps the lifecycle it always had.
/// The code must live in the engine's OWN namespace — same ABI as `expect_rows` (hub#139); a
/// foreign one is a first-party bug, so it is surfaced as a broken contract and still blocks
/// (failing closed is the safe direction when the thing at stake is a fiscal record).
pub(crate) async fn ensure_no_pending_obligations(
    host: &dyn crate::native::NativeHost,
    registry: &Registry,
    hub_id: &str,
    module_id: &str,
) -> Result<()> {
    let Some(engine) = registry.native.get(module_id).cloned() else {
        return Ok(()); // Declarative module: it owes nothing to anyone.
    };
    let Some(owed) = engine.pending_obligations(hub_id, host).await? else {
        return Ok(());
    };
    if owed.count == 0 {
        return Ok(());
    }
    if !crate::errors::valid_domain_code(module_id, &owed.code) {
        return Err(RuntimeError::Other(format!(
            "el motor de `{module_id}` reportó {} obligación(es) pendiente(s) con el código inválido `{}`; se esperaba `{module_id}.<snake_case>`",
            owed.count, owed.code
        )));
    }
    Err(RuntimeError::Domain {
        code: owed.code,
        message: owed.message,
    })
}

/// Cambia el estado (activar/desactivar) de un módulo instalado y lo persiste para `hub_id`.
pub async fn set_status(
    db: &dyn DatabaseAdapter,
    registry: &mut Registry,
    hub_id: &str,
    module_id: &str,
    status: ModuleStatus,
) -> Result<()> {
    if !registry.set_status(module_id, status) {
        return Err(RuntimeError::CommandNotFound(format!(
            "módulo no instalado: {module_id}"
        )));
    }
    let version = registry
        .installed
        .iter()
        .find(|m| m.id == module_id)
        .map(|m| m.version.clone())
        .unwrap_or_default();
    persist_status(db, hub_id, module_id, &version, status).await?;
    Ok(())
}

/// Desinstala: quita capacidades del registro y borra la fila de `hub_module` **de este hub**
/// (no toca el mismo módulo en otros hubs de la BD compartida). No borra datos.
///
/// **Los roles que declaraba salen del catálogo con él** (paso 2b, hub#352) y su activación se
/// olvida, salvo que otro módulo instalado declare la misma clave. Lo que NO se toca es la gente:
/// un usuario que llevara ese rol conserva su fila y su rol —reasignar a alguien por la espalda
/// sería peor que un rol huérfano—, y lo único que pierde son los permisos que concedía el módulo
/// que se va, que es estrictamente menos, nunca más.
pub async fn uninstall(
    db: &dyn DatabaseAdapter,
    registry: &mut Registry,
    hub_id: &str,
    module_id: &str,
) -> Result<()> {
    // Se leen ANTES de quitarlo del registro: después ya no hay manifest al que preguntar.
    let declared = registry
        .installed
        .iter()
        .find(|m| m.id == module_id)
        .map(crate::roles::declared_by)
        .unwrap_or_default();

    if !registry.remove_module(module_id) {
        return Err(RuntimeError::CommandNotFound(format!(
            "módulo no instalado: {module_id}"
        )));
    }
    let orphaned = crate::roles::no_longer_declared(registry, &declared);
    crate::roles::clear_activation(db, hub_id, &orphaned).await?;
    // Quita las scheduled tasks del módulo (ADR-0011): sus capacidades dejan de existir.
    crate::scheduler::remove_module_tasks(db, module_id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    db.execute(
        "DELETE FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
        &p,
    )
    .await?;
    Ok(())
}

/// Lee de `hub_module` el estado persistido de los módulos **de este hub** (`hub_id`), como
/// `(module_id, status)`. Filtra por `hub_id`: en una BD compartida por org, dos hubs tienen sets
/// distintos y este SELECT solo devuelve los del hub que pregunta. Lo usa la reconstrucción del
/// `Registry` para respetar el estado activo/inactivo por hub tras un reinicio. Idempotente: si la
/// tabla aún no tiene la forma hub-scoped, asegura+migra primero.
/// Los módulos instalados de este hub con su pin de soporte, si lo tienen (hub#516).
///
/// `pinned_version` (migración de sistema v30) es la salida de emergencia: deja a un cliente en
/// `sales@3.1` mientras se arregla la `3.2`, **sin tocar a los demás**. No es una opción de
/// producto —el dueño no elige— sino una herramienta nuestra, y por eso no hay UI.
pub async fn installed_with_pin(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(String, String, Option<String>)>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT module_id, version, pinned_version FROM hub_module \
             WHERE hub_id = :hub_id AND status = 'active'",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|row| {
            (
                row["module_id"].as_str().unwrap_or_default().to_string(),
                row["version"].as_str().unwrap_or_default().to_string(),
                row["pinned_version"].as_str().map(str::to_owned),
            )
        })
        .collect())
}

pub async fn installed_status(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(String, ModuleStatus)>> {
    ensure_hub_module_table(db).await?;
    // Baseline identity (v0): la migración de sistema v8 (ADR-0154) ALTERa `hub_session`, así que
    // debe existir antes de `apply`. Idempotente (CREATE IF NOT EXISTS); cubre instalar en un hub
    // vacío antes de que `ensure_system_tables` corra, igual que ya se asegura `hub_module`.
    crate::identity::ensure_tables(db).await?;
    crate::system_migrations::apply(db, hub_id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT module_id, status FROM hub_module WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    let mut out = Vec::with_capacity(res.rows.len());
    for row in &res.rows {
        let id = row["module_id"].as_str().unwrap_or_default().to_string();
        let status = match row["status"].as_str() {
            Some("inactive") => ModuleStatus::Inactive,
            Some("inactive_auto") => ModuleStatus::InactiveAuto,
            _ => ModuleStatus::Active,
        };
        out.push((id, status));
    }
    Ok(out)
}

/// Como [`installed_status`] pero incluye también la `version` instalada de cada módulo (para
/// localizar su carpeta en la caché de descargas `<cache>/<id>/<version>/` al RE-HIDRATAR el
/// Registry tras un reinicio). Filtra por `hub_id` (BD compartida por org). `(id, version, status)`.
pub async fn installed_status_versioned(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(String, String, ModuleStatus)>> {
    ensure_hub_module_table(db).await?;
    // Baseline identity (v0): la migración de sistema v8 (ADR-0154) ALTERa `hub_session`, así que
    // debe existir antes de `apply`. Idempotente (CREATE IF NOT EXISTS); cubre instalar en un hub
    // vacío antes de que `ensure_system_tables` corra, igual que ya se asegura `hub_module`.
    crate::identity::ensure_tables(db).await?;
    crate::system_migrations::apply(db, hub_id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT module_id, version, status FROM hub_module WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    let mut out = Vec::with_capacity(res.rows.len());
    for row in &res.rows {
        let id = row["module_id"].as_str().unwrap_or_default().to_string();
        let version = row["version"].as_str().unwrap_or_default().to_string();
        let status = match row["status"].as_str() {
            Some("inactive") => ModuleStatus::Inactive,
            Some("inactive_auto") => ModuleStatus::InactiveAuto,
            _ => ModuleStatus::Active,
        };
        out.push((id, version, status));
    }
    Ok(out)
}

/// Ordena módulos topológicamente por `depends_on` (hub#16): una dependencia va **antes** que
/// quien la declara, sin importar el orden del sistema de ficheros. Las dependencias **fuera del
/// lote** (ya instaladas, o que se validarán en `install()`) se ignoran a efectos de orden.
/// Devuelve los índices en orden de instalación; `DependencyCycle` si hay un ciclo.
///
/// `modules` = `(id, depends_on)` por módulo. DFS con marcado tri-estado (post-orden).
pub fn install_order(modules: &[(String, Vec<String>)]) -> Result<Vec<usize>> {
    use std::collections::HashMap;
    // 0 = sin visitar · 1 = en pila (si se reentra ⇒ ciclo) · 2 = terminado.
    let index: HashMap<&str, usize> = modules
        .iter()
        .enumerate()
        .map(|(i, (id, _))| (id.as_str(), i))
        .collect();
    let mut state = vec![0u8; modules.len()];
    let mut order = Vec::with_capacity(modules.len());
    for i in 0..modules.len() {
        visit(i, modules, &index, &mut state, &mut order)?;
    }
    Ok(order)
}

fn visit(
    i: usize,
    modules: &[(String, Vec<String>)],
    index: &std::collections::HashMap<&str, usize>,
    state: &mut [u8],
    order: &mut Vec<usize>,
) -> Result<()> {
    match state[i] {
        2 => return Ok(()),
        1 => {
            return Err(RuntimeError::DependencyCycle {
                module: modules[i].0.clone(),
            })
        }
        _ => {}
    }
    state[i] = 1;
    for dep in &modules[i].1 {
        if let Some(&j) = index.get(dep.as_str()) {
            visit(j, modules, index, state, order)?;
        }
    }
    state[i] = 2;
    order.push(i);
    Ok(())
}

/// Upsert del estado del módulo en `hub_module`, **scoped por `hub_id`** (§2.5). Asegura primero
/// que el esquema hub-scoped existe: baseline (v0) + migración de sistema v1 (que recompone la PK
/// a `(hub_id, module_id)`). Es idempotente y barato (las migraciones ya aplicadas se saltan), y
/// cubre el caso de instalar un módulo en un hub vacío antes de que `ensure_system_tables` corra.
async fn persist_status(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    version: &str,
    status: ModuleStatus,
) -> Result<()> {
    ensure_hub_module_table(db).await?;
    // Baseline identity (v0): la migración de sistema v8 (ADR-0154) ALTERa `hub_session`, así que
    // debe existir antes de `apply`. Idempotente (CREATE IF NOT EXISTS); cubre instalar en un hub
    // vacío antes de que `ensure_system_tables` corra, igual que ya se asegura `hub_module`.
    crate::identity::ensure_tables(db).await?;
    crate::system_migrations::apply(db, hub_id).await?;
    let status_str = match status {
        ModuleStatus::Active => "active",
        ModuleStatus::Inactive => "inactive",
        ModuleStatus::InactiveAuto => "inactive_auto",
    };
    let now = crate::registry::now_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(id));
    p.insert("version".into(), json!(version));
    p.insert("status".into(), json!(status_str));
    p.insert("now".into(), json!(now));
    // upsert por PK compuesta (hub_id, module_id): instalar/activar el mismo módulo en otro hub
    // de la misma BD es una fila distinta, no un conflicto.
    db.execute(
        "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
         VALUES (:hub_id, :module_id, :version, :status, :now, :now) \
         ON CONFLICT(hub_id, module_id) DO UPDATE SET status = :status, version = :version, updated_at = :now",
        &p,
    ).await?;
    Ok(())
}

#[cfg(test)]
mod retention_gate_tests {
    //! hub#314 (ADR-0202 phase 1, guard R2): a module whose native engine still owes work to an
    //! external authority can be neither disabled nor uninstalled. Without the gate, `uninstall`
    //! deleted the `hub_module` row while VeriFactu records sat unsent — nobody drains them
    //! afterwards, so the invoices stay outside the AEAT chain (VeriFactu FAQ §5).
    use std::sync::Arc;

    use erplora_wasm_host::Output;
    use serde_json::Value as Json;

    use super::*;
    use crate::native::{NativeHandler, NativeHost, PendingObligation};

    /// A native engine reporting `count` units of work still owed. `call` is unreachable on
    /// purpose: the gate must ask through its own door, never by dispatching a command.
    #[derive(Debug)]
    struct OwingEngine {
        count: u64,
        code: &'static str,
    }

    #[async_trait::async_trait]
    impl NativeHandler for OwingEngine {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn NativeHost,
        ) -> Result<Output> {
            unreachable!("the retention gate must not dispatch commands")
        }

        async fn pending_obligations(
            &self,
            _hub_id: &str,
            _host: &dyn NativeHost,
        ) -> Result<Option<PendingObligation>> {
            Ok((self.count > 0).then(|| PendingObligation {
                count: self.count,
                code: self.code.to_string(),
                message: format!("{} record(s) still unsent", self.count),
            }))
        }
    }

    /// Host that reads nothing: these engines answer from their own state, so a read would only
    /// hide which door the gate actually used.
    struct SilentHost;

    #[async_trait::async_trait]
    impl NativeHost for SilentHost {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(Vec::new())
        }
    }

    fn registry_with(module_id: &str, engine: OwingEngine) -> Registry {
        let mut registry = Registry::new();
        registry
            .native
            .insert(module_id.to_string(), Arc::new(engine));
        registry
    }

    #[tokio::test]
    async fn a_module_still_owing_records_is_blocked_and_says_how_many() {
        let registry = registry_with(
            "verifactu",
            OwingEngine {
                count: 3,
                code: "verifactu.unsent_records",
            },
        );
        let err = ensure_no_pending_obligations(&SilentHost, &registry, "hub-1", "verifactu")
            .await
            .expect_err("3 unsent records must keep the module in place");
        match err {
            RuntimeError::Domain { code, message } => {
                assert_eq!(
                    code, "verifactu.unsent_records",
                    "the UI programs and translates against the stable namespaced code"
                );
                assert!(
                    message.contains('3'),
                    "the rejection must say how many are left, got `{message}`"
                );
            }
            other => panic!("expected a translatable domain rejection, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn a_module_owing_nothing_is_free_to_go() {
        let registry = registry_with(
            "verifactu",
            OwingEngine {
                count: 0,
                code: "verifactu.unsent_records",
            },
        );
        ensure_no_pending_obligations(&SilentHost, &registry, "hub-1", "verifactu")
            .await
            .expect("with everything handed over the module must be removable");
    }

    #[tokio::test]
    async fn a_module_without_a_native_engine_is_never_gated() {
        let registry = Registry::new();
        ensure_no_pending_obligations(&SilentHost, &registry, "hub-1", "inventory")
            .await
            .expect("a declarative module owes nothing to anyone");
    }

    #[tokio::test]
    async fn a_foreign_error_code_is_a_broken_contract_and_still_blocks() {
        // Same ABI as `expect_rows` (hub#139): an engine may only mint codes in its own
        // namespace. A foreign code is a first-party bug — it must never pass as a domain
        // rejection the UI would translate, and it must still stop the removal.
        let registry = registry_with(
            "verifactu",
            OwingEngine {
                count: 1,
                code: "sales.unsent_records",
            },
        );
        let err = ensure_no_pending_obligations(&SilentHost, &registry, "hub-1", "verifactu")
            .await
            .expect_err("a broken contract must not open the gate");
        assert!(
            !matches!(err, RuntimeError::Domain { .. }),
            "a code minted in another module's namespace is not a valid domain rejection"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::install_order;
    use crate::errors::RuntimeError;

    fn m(id: &str, deps: &[&str]) -> (String, Vec<String>) {
        (id.to_string(), deps.iter().map(|s| s.to_string()).collect())
    }

    /// Comprueba que en el orden devuelto cada dependencia (dentro del lote) precede al módulo.
    fn assert_deps_before(modules: &[(String, Vec<String>)], order: &[usize]) {
        let pos: std::collections::HashMap<&str, usize> = order
            .iter()
            .enumerate()
            .map(|(p, &i)| (modules[i].0.as_str(), p))
            .collect();
        for (id, deps) in modules {
            for dep in deps {
                if let (Some(&pd), Some(&pi)) = (pos.get(dep.as_str()), pos.get(id.as_str())) {
                    assert!(pd < pi, "la dep `{dep}` debe ir antes que `{id}`");
                }
            }
        }
    }

    #[test]
    fn orders_dependency_before_dependent() {
        // invoice depende de inventory; sales de inventory; el orden del FS daría invoice primero.
        let modules = vec![
            m("invoice", &["inventory"]),
            m("sales", &["inventory", "taxes"]),
            m("inventory", &[]),
            m("taxes", &[]),
        ];
        let order = install_order(&modules).unwrap();
        assert_eq!(order.len(), 4);
        assert_deps_before(&modules, &order);
    }

    #[test]
    fn ignores_deps_outside_the_batch() {
        // `payments` depende de `core`, que no está en el lote (ya instalado): no afecta al orden
        // ni es error aquí (lo valida install() por módulo).
        let modules = vec![m("payments", &["core"]), m("cash_register", &[])];
        let order = install_order(&modules).unwrap();
        assert_eq!(order.len(), 2);
    }

    #[test]
    fn detects_cycle() {
        let modules = vec![m("a", &["b"]), m("b", &["a"])];
        let err = install_order(&modules).unwrap_err();
        assert!(matches!(err, RuntimeError::DependencyCycle { .. }));
    }

    #[test]
    fn keeps_all_independent_modules() {
        let modules = vec![m("a", &[]), m("b", &[]), m("c", &[])];
        let order = install_order(&modules).unwrap();
        assert_eq!(order.len(), 3);
        let mut ids: Vec<usize> = order.clone();
        ids.sort_unstable();
        assert_eq!(ids, vec![0, 1, 2]);
    }

    /// hub#139: `expect_rows` is validated at INSTALL time — a foreign-namespace code or a
    /// command mixing the legacy and the translatable gate never reaches runtime.
    #[test]
    fn rejects_foreign_domain_codes_and_ambiguous_row_gates() {
        let foreign: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "inventory", "name": "Inventory", "version": "1.0.0",
            "commands": {
                "inventory.consume": {
                    "permission": "inventory.consume",
                    "expect_rows": { "op": "min", "n": 1, "error": "sales.insufficient_stock" }
                }
            }
        }))
        .unwrap();
        assert!(
            super::validate_command_contracts(&foreign).is_err(),
            "a module cannot mint domain codes in another module's namespace"
        );

        let ambiguous: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "inventory", "name": "Inventory", "version": "1.0.0",
            "commands": {
                "inventory.consume": {
                    "permission": "inventory.consume",
                    "min_affected_rows": 1,
                    "expect_rows": { "op": "min", "n": 1, "error": "inventory.insufficient_stock" }
                }
            }
        }))
        .unwrap();
        assert!(
            super::validate_command_contracts(&ambiguous).is_err(),
            "min_affected_rows and expect_rows cannot coexist on one command"
        );

        let valid: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "inventory", "name": "Inventory", "version": "1.0.0",
            "commands": {
                "inventory.consume": {
                    "permission": "inventory.consume",
                    "expect_rows": { "op": "min", "n": 1, "error": "inventory.insufficient_stock" }
                }
            }
        }))
        .unwrap();
        assert!(super::validate_command_contracts(&valid).is_ok());
    }

    // ── `fiscal_regime`: who says "I implement this regime" (ADR-0273 D6, hub#555) ─────────────

    /// Builds a manifest carrying the given `fiscal_regime` block.
    fn with_regime(regime: serde_json::Value) -> crate::manifest::Manifest {
        serde_json::from_value(serde_json::json!({
            "id": "verifactu", "name": "VeriFactu", "version": "1.5.6", "fiscal_regime": regime
        }))
        .expect("manifest parses")
    }

    /// The message of a rejected `fiscal_regime` block (panics if the block was accepted).
    fn regime_rejection(regime: serde_json::Value) -> String {
        super::validate_fiscal_regime(&with_regime(regime))
            .expect_err("the block must be rejected")
            .to_string()
    }

    /// The happy path: a module declares the regime it implements, and the predicate answers.
    /// This is the core's only question — *«is there any installed and active module fulfilling MY
    /// regime?»* — and the core **counts**, it does not choose: the marketplace may carry N modules
    /// that do the same job.
    #[test]
    fn a_module_can_declare_the_regime_it_implements() {
        let manifest = with_regime(serde_json::json!({ "country": "ES", "regime": "verifactu" }));
        assert!(super::validate_fiscal_regime(&manifest).is_ok());
        assert!(
            manifest.fulfils_regime("ES", "verifactu"),
            "this is the predicate the fiscal profile counts with"
        );
    }

    /// The country is matched too. A French Factur-X module is not a VeriFactu provider for a
    /// Spanish hub, however similar the regime keys of two countries might one day look.
    #[test]
    fn a_provider_of_another_country_does_not_fulfil_this_hubs_regime() {
        let french = with_regime(serde_json::json!({ "country": "FR", "regime": "facturx" }));
        assert!(!french.fulfils_regime("ES", "verifactu"));
        assert!(french.fulfils_regime("FR", "facturx"));
        // Case is an accident of typing, not a difference: `hub_settings.country_code` is
        // normalised to upper case and a manifest is written by hand.
        assert!(french.fulfils_regime("fr", "facturx"));
    }

    /// **The 24 published manifests carry no block, and that must keep being valid.** Absence is
    /// not a failure to declare: it means "I am not a fiscal provider", which is true of an
    /// inventory module — and is exactly why this is fail-closed rather than opt-in. A module that
    /// does not declare simply does not COUNT as a provider; nothing gets unlocked by staying
    /// silent.
    #[test]
    fn a_manifest_without_the_fiscal_regime_block_stays_valid_and_fulfils_nothing() {
        let published: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "inventory", "name": "Inventory", "version": "1.0.0"
        }))
        .unwrap();
        assert!(super::validate_fiscal_regime(&published).is_ok());
        assert!(!published.fulfils_regime("ES", "verifactu"));
    }

    /// The country is an ISO-3166-1 alpha-2 code, because that is what it is joined against: the
    /// hub's `country_code` and the core's regime registry. A free-text country would silently
    /// never match, which reads exactly like "no provider installed" — the failure mode that
    /// blocks a till.
    #[test]
    fn a_country_that_is_not_iso_3166_1_alpha_2_is_rejected() {
        for bad in ["", "E", "ESP", "españa", "E5"] {
            let message = regime_rejection(serde_json::json!({
                "country": bad, "regime": "verifactu"
            }));
            assert!(
                message.contains("ISO-3166-1"),
                "the rejection has to say what a country looks like, got: {message}"
            );
        }
    }

    /// An empty regime key declares nothing while looking like a declaration. It is refused at the
    /// border rather than stored as a provider of the "" regime.
    #[test]
    fn an_empty_regime_key_is_rejected() {
        let message = regime_rejection(serde_json::json!({ "country": "ES", "regime": "  " }));
        assert!(
            message.contains("regime"),
            "the rejection names the field, got: {message}"
        );
    }

    /// Builds a manifest of module `kitchen` carrying the given `roles` block.
    fn with_roles(roles: serde_json::Value) -> crate::manifest::Manifest {
        serde_json::from_value(serde_json::json!({
            "id": "kitchen", "name": "Kitchen", "version": "2.3.1", "roles": roles
        }))
        .expect("manifest parses")
    }

    /// The message of a rejected `roles` block (panics if the block was accepted).
    fn role_rejection(roles: serde_json::Value) -> String {
        super::validate_role_declarations(&with_roles(roles))
            .expect_err("the block must be rejected")
            .to_string()
    }

    /// hub#351 (paso 2b): the happy path. A module hangs its own roles from a base role and the
    /// manifest is accepted — the base catalogue is EXTENDED, never rewritten.
    #[test]
    fn accepts_roles_that_hang_from_a_base_role() {
        let manifest = with_roles(serde_json::json!([
            { "key": "waiter", "label": "Waiter", "extends": "employee" },
            { "key": "accountant", "label": "Accountant", "extends": "manager" }
        ]));
        assert!(
            super::validate_role_declarations(&manifest).is_ok(),
            "a role hanging from `employee`/`manager` is exactly what the block is for"
        );
    }

    /// The ~24 published modules carry no `roles` block: their absence must keep validating, or
    /// the whole catalogue would need republishing (which is precisely what this design avoids).
    #[test]
    fn a_manifest_without_the_roles_block_stays_valid() {
        let published: crate::manifest::Manifest = serde_json::from_value(serde_json::json!({
            "id": "inventory", "name": "Inventory", "version": "1.0.0",
            "role_permissions": {
                "admin": ["*"],
                "manager": ["inventory.view_product", "inventory.add_product"],
                "employee": ["inventory.view_product"]
            }
        }))
        .unwrap();
        assert!(
            super::validate_role_declarations(&published).is_ok(),
            "no `roles` block = nothing to validate; the module installs as it always did"
        );
    }

    /// 🔴 The guard of hub#347, restated at the manifest border: **a module never mints an
    /// administrator.** Administering the hub comes from the hub itself (`HUB_OWNER_EMAIL`,
    /// ADR-0157, and the account role floor), never from a third-party manifest — so `extends`
    /// resolves to the two NON-administrative base roles and `admin`/`owner` are rejected by name.
    #[test]
    fn a_module_cannot_declare_a_role_that_administers_the_hub() {
        for forbidden in ["admin", "owner", "Admin", "OWNER"] {
            let error = role_rejection(serde_json::json!([
                { "key": "backdoor", "label": "Back door", "extends": forbidden }
            ]));
            assert!(
                error.contains("backdoor") && error.contains("administ"),
                "the refusal must say WHICH role and WHY (`{forbidden}`): {error}"
            );
        }

        // And the gate itself does not move: whatever a manifest declares or grants, a custom role
        // is not the "administers the hub" property (hub#347). Belt and braces — a hub running an
        // older/newer runtime never derives administration from a declared role.
        for declared in ["waiter", "bartender", "kitchen", "accountant", "shift_lead"] {
            assert!(
                !crate::hub_users::is_admin_role(declared),
                "`{declared}` is declared by a module, so it never administers the hub"
            );
        }
    }

    /// The three base keys are the FROZEN contract every published module writes against
    /// (24/24 declare `admin`/`manager`/`employee`). A module extends that catalogue; it does not
    /// get to redefine an entry of it — including the legacy `owner` spelling.
    #[test]
    fn a_module_cannot_redefine_a_base_role() {
        for base in ["admin", "manager", "employee", "owner"] {
            let error = role_rejection(serde_json::json!([
                { "key": base, "label": "Mine now", "extends": "employee" }
            ]));
            assert!(
                error.contains(base),
                "the refusal must name the base role it collides with: {error}"
            );
        }
    }

    /// A malformed role is refused with a message that names the offending role and the field, so
    /// the module author can fix it without reading the runtime's source.
    #[test]
    fn rejects_a_malformed_role_with_a_useful_message() {
        // A key is an identifier (same shape as a module id / a permission), not free text: it is
        // what `role_permissions` and the `hub_user.role` column are keyed by.
        let error = role_rejection(serde_json::json!([
            { "key": "Bar tender", "label": "Bartender", "extends": "employee" }
        ]));
        assert!(
            error.contains("Bar tender") && error.contains("key"),
            "the refusal must quote the invalid key: {error}"
        );

        // The label is what the administrator reads when activating the role: blank is not a label.
        let error = role_rejection(serde_json::json!([
            { "key": "bartender", "label": "   ", "extends": "employee" }
        ]));
        assert!(
            error.contains("bartender") && error.contains("label"),
            "the refusal must name the empty field: {error}"
        );

        // `extends` resolves to a base role of the HUB, never to another declared role: that is
        // what keeps every role resolvable to the frozen three-key contract.
        let error = role_rejection(serde_json::json!([
            { "key": "bartender", "label": "Bartender", "extends": "waiter" }
        ]));
        assert!(
            error.contains("waiter") && error.contains("extends"),
            "the refusal must quote the unknown base role: {error}"
        );

        // Two rows, one key: which label and which base would win is undefined, so it is refused.
        let error = role_rejection(serde_json::json!([
            { "key": "waiter", "label": "Waiter", "extends": "employee" },
            { "key": "waiter", "label": "Server", "extends": "manager" }
        ]));
        assert!(
            error.contains("waiter") && error.contains("twice"),
            "a duplicated key must be called out: {error}"
        );
    }

    /// Compatibility MEASURED against the real catalogue instead of asserted: every published
    /// `module.json` keeps parsing and keeps passing the new validation, untouched — no republish,
    /// no migration, which is the whole point of `extends` resolving to a base role.
    ///
    /// A manifest that does not parse at all is reported, not masked: the only claim under test is
    /// that hub#351 did not break it, so its error is asserted NOT to come from the new block.
    /// (Today one does: `tables` ships `"catch_up": false` where the contract says the string enum
    /// `collapse`/`skip` — a defect of that module's repo that predates this block.)
    ///
    /// Skips (loudly) where `modules-workspace` is not checked out, like every other e2e.
    #[test]
    fn every_published_manifest_still_passes_role_validation() {
        if !crate::require_modules_workspace() {
            return;
        }
        let root = crate::e2e_support::modules_root();
        let mut parsed = 0;
        for entry in std::fs::read_dir(&root)
            .expect("modules root is readable")
            .flatten()
        {
            let dir = entry.path();
            if !dir.join("module.json").is_file() {
                continue;
            }
            let module = dir
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();
            match crate::manifest::Manifest::load(&dir) {
                Ok(manifest) => {
                    assert!(
                        manifest.roles.is_empty(),
                        "`{module}` already declares roles: this test asserts the OPTIONALITY of \
                         the block against the catalogue as published"
                    );
                    super::validate_role_declarations(&manifest)
                        .unwrap_or_else(|e| panic!("`{module}` must keep validating: {e}"));
                    parsed += 1;
                }
                Err(error) => {
                    let error = error.to_string();
                    assert!(
                        !error.contains("roles"),
                        "`{module}` stopped parsing because of the new block: {error}"
                    );
                    println!(
                        "⚠  `{module}` does not parse today, for a reason older than hub#351: {error}"
                    );
                }
            }
        }
        assert!(
            parsed >= 20,
            "expected the published catalogue (~24 modules), only {parsed} parsed in {}",
            root.display()
        );
    }
}
