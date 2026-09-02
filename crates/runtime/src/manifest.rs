//! Parseo de `module.json` (el contrato declarativo del módulo). Espejo del JSON Schema
//! en `schemas/module.schema.json`. ARQUITECTURA.md §5.2.
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::Path;

use crate::errors::{Result, RuntimeError};

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Manifest {
    pub id: String,
    pub name: String,
    pub version: String,
    /// Modules this one needs installed, optionally with a MINIMUM version (hub#681).
    ///
    /// Two authoring shapes, mixable in one list: a plain string (`"taxes"`, the shape of every
    /// published manifest — any installed version satisfies it) and
    /// `{ "id": "inventory", "min_version": "1.2.20" }` for a contract that was born in a
    /// concrete version (sales#68: `sales` reads `inventory.products.for_sale`, which exists
    /// since inventory 1.2.20). The installer enforces the floor
    /// (`installer::register_module`); the topo-sort and the cascades read only the id.
    #[serde(default)]
    pub depends_on: Vec<DependencyRef>,
    #[serde(default)]
    pub permissions: Vec<String>,
    #[serde(default)]
    pub role_permissions: HashMap<String, Vec<String>>,
    /// Business roles the module DECLARES for the vertical it serves (paso 2b, hub#351).
    ///
    /// The base catalogue of the hub is frozen at three keys (`admin`/`manager`/`employee`,
    /// [`crate::hub_users::BASE_ROLES`]) because renaming one would cost 24 repos, 24 version
    /// bumps and 24 republications. So a vertical does not rename the base: it adds on top of it.
    /// A restaurant needs Waiter · Bartender · Kitchen · Cashier; a salon needs Receptionist ·
    /// Stylist; both may want Accountant. Each of those is declared here by the module that
    /// invents it, and every one of them hangs from a base role through `extends`.
    ///
    /// Absent = the module declares no role of its own, which is the shape of the ~24 already
    /// published manifests: the block is **optional** and adding it never invalidates them.
    ///
    /// `role_permissions` is what actually GRANTS: a role's effective permissions are the union of
    /// what the installed modules give to that key, so a module may grant to a key another module
    /// declared (`sales` gives `waiter` `add_sale` but not `take_payment`). Declaring is naming a
    /// role; granting is a separate axis on purpose.
    ///
    /// Validated at install time by `installer::validate_role_declarations`.
    #[serde(default)]
    pub roles: Vec<RoleDef>,
    #[serde(default)]
    pub navigation: Vec<Nav>,
    #[serde(default)]
    pub migrations: Migrations,
    /// **Datos de referencia** que el módulo siembra al instalarse (ADR-0147; `taxes` lo usa desde
    /// ADR-0085 para las categorías fiscales canónicas). DML **idempotente por hub** —
    /// `WHERE NOT EXISTS` por la clave natural—, aplicado DESPUÉS de migrar, con `:hub_id`, `:now`
    /// y `:current_user_id` inyectados. Reinstalar no duplica.
    ///
    /// Es para datos que **todo hub necesita** y que no puede aportar el usuario: unidades de
    /// medida, categorías fiscales. No para datos de ejemplo — eso son las blueprints.
    #[serde(default)]
    pub seed: Migrations,
    #[serde(default)]
    pub queries: HashMap<String, QueryDef>,
    #[serde(default)]
    pub commands: HashMap<String, CommandDef>,
    /// Carpeta persistente del módulo dentro del árbol común `media/modules/`.
    ///
    /// El valor del manifest es solo un nombre de carpeta (nunca una ruta). El host decide el
    /// backend físico: disco en Hub Local y almacenamiento de objetos vía Cloud en Hub Cloud.
    /// Ausente = el módulo no puede escribir ficheros persistentes.
    #[serde(default)]
    pub static_files: Option<StaticFilesDef>,
    /// Widgets de dashboard que aporta el módulo (ADR-0054). Mapa `id.completo → WidgetDef`,
    /// misma convención que `queries`/`commands`. El shell del Hub los recolecta de TODOS los
    /// manifests instalados y los pinta en `<ok-widget-board>`. Vía declarativa (`kind`+`query`,
    /// render genérico del shell) o escape hatch a `component` (WC del propio módulo). El runtime
    /// no ejecuta nada por widget: solo transporta el contrato (el shell fetchea el `module.json`
    /// crudo, igual que `navigation`/`provides_slots`). Ver `architecture/hub/dashboard/widgets.md`.
    #[serde(default)]
    pub widgets: HashMap<String, WidgetDef>,
    /// Pantalla de **ajustes declarativa** del módulo (estilo widgets, ADR nuevo). El módulo declara
    /// el formulario (un JSON Schema) + a qué `get`/`set` del propio módulo llama; el shell lo pinta
    /// genéricamente. Escape-hatch a un Web Component propio (`component`) para lo estructural. El
    /// runtime no ejecuta nada por settings: solo transporta el contrato (el shell fetchea el
    /// `module.json` crudo, igual que `widgets`). Ausente = el módulo no expone ajustes declarativos.
    #[serde(default)]
    pub settings: Option<SettingsDef>,
    /// **Is this module configured?** (ADR-0063, extended by hub#369). The module declares a read
    /// query of its own plus the conditions its first row must meet; the runtime evaluates it and
    /// surfaces the result as one item of `hub.setup.status`.
    ///
    /// It used to be transported and nothing else — the shell fetched the raw `module.json` and ran
    /// the loop in the browser. The computation moved to the runtime, so the block is now PARSED
    /// here: one query, one source of truth, and the assistant and the checklist read the same
    /// thing. Absent = the module contributes no checklist item (the shape of 22 of the 24
    /// published manifests, which must keep installing untouched).
    #[serde(default)]
    pub setup: Option<SetupDef>,
    #[serde(default)]
    pub events: Events,
    /// Resumen del módulo para el routing del asistente (nivel 1). ARQUITECTURA.md §9.2b.
    #[serde(default)]
    pub agent: Option<Agent>,
    /// Conocimiento del módulo para RAG (§9.4) — aparcado/en diseño. Se captura tal cual.
    #[serde(default)]
    pub ai_context: Option<serde_json::Value>,
    /// Tareas programadas del módulo (ADR-0011). Cada una ejecuta un command del **propio
    /// módulo** cuando vence su `cron`, sin usuario (contexto de sistema). Se vuelcan a la tabla
    /// de sistema `_scheduled_tasks` al instalar (idempotente). Ver `scheduler.rs`.
    #[serde(default)]
    pub scheduled_tasks: Vec<ScheduledTaskDef>,
    /// Capacidad `host.notify` de alto nivel (ADR-0012): qué canales de notificación
    /// (`email`/`sms`/`whatsapp`) declara necesitar el módulo. El host resuelve DÓNDE viven
    /// los secretos/cuota por canal y por `tier`; el módulo solo declara qué canal usa.
    #[serde(default)]
    pub notify: Option<NotifyCapability>,
    /// Capacidad `http.fetch` mediada (ADR-0012, campo `network` ya en el schema): allowlist de
    /// hosts y secretos que el host inyecta. El WASM no tiene red; el runtime hace la llamada.
    /// **Deprecado** a favor de `capabilities.network`; se pliega en `capabilities` al cargar.
    #[serde(default)]
    pub network: Option<NetworkCapability>,
    /// Permisos que el módulo SOLICITA al host (ADR-0079, estilo Android). Bloque vacío/ausente =
    /// el módulo no pide nada. NO confundir con `permissions` (RBAC de usuario). El usuario los
    /// concede explícitamente; el host media. Consolida los `network`/`notify` de ADR-0012.
    #[serde(default)]
    pub capabilities: Capabilities,
    /// **The fiscal regime this module IMPLEMENTS** (ADR-0273 D6, hub#555). Only declared by
    /// whoever implements one; an inventory module declares nothing.
    ///
    /// It is the answer to the core's single question — *«is there any installed and active module
    /// fulfilling the regime THIS hub owes?»* ([`crate::fiscal_profile`]). The core **counts**, it
    /// does not choose: the marketplace may carry N modules of one regime, swapping one for another
    /// is the user's call, and the profile deliberately does not store which one is in use.
    ///
    /// **This is not the opt-in flag ADR-0203 rejected.** That one would have been a `fiscal: true`
    /// a module could FORGET, emitting without a gate. Here the direction is inverted: declaring
    /// turns nothing off — it is what the core *requires to exist*. A module that does not declare
    /// simply does not count as a provider, and the hub stays blocked. Fail-closed, the same shape
    /// as `capabilities.certificate`, which likewise makes the gate stricter rather than laxer.
    ///
    /// Absent in all 24 published manifests, and it must stay valid there: absence means "I am not
    /// a fiscal provider", which is simply true of them.
    #[serde(default)]
    pub fiscal_regime: Option<FiscalRegimeDef>,
    /// **This module's data belongs to the INSTALLATION that produced it** (hub#380, generalising
    /// ADR-0202 §4.2). A bundle from another hub never applies it; the same hub restoring its own
    /// backup gets it back.
    ///
    /// The import engine used to ask a different question — *«is this section
    /// `modules/verifactu`?»* — which put one country's regime inside a generic engine and would
    /// have needed one more name for TicketBai and another for NF525. Both chain their records
    /// against the previous one under an installation identifier (`NumeroInstalacion` = `hub_id`
    /// here), so applied under another hub the next record would chain on something the tax
    /// authority never received for that installation, and a pending queue would be transmitted
    /// under the wrong installation. That is a property of the DATA, and only the module that owns
    /// it knows it — so the module declares it and [`crate::import`] reads it.
    ///
    /// It is about **portability, not secrecy**: the rows still export (a hub must be able to back
    /// itself up), they simply do not land anywhere else. Absent = portable, which is the shape of
    /// every published manifest and the truth about all but the fiscal ones.
    #[serde(default)]
    pub installation_bound_data: bool,
    /// **The commercial terms the module declares** (`billing`, ADR-0007) — captured VERBATIM, the
    /// way [`Manifest::ai_context`] is, and read for exactly one yes/no question.
    ///
    /// This block belongs to the Cloud: the schema says so in as many words («el Hub ignora
    /// marketplace/billing») because it is what the SaaS turns into Stripe products, and the Hub
    /// prices nothing. The runtime does not change that — it does not read a price, an interval or
    /// a tier to decide anything about money. It asks [`Manifest::sold_under`], and only about a
    /// module that declares [`Manifest::fiscal_regime`], to enforce ADR-0273 D7: **the module a
    /// hub's legal compliance hangs from may not be something the hub can stop paying for**
    /// (`installer::validate_fiscal_provider_is_free`, hub#559).
    ///
    /// It is kept as a raw `Value` on purpose. Until now `serde` simply dropped the block, so a
    /// manifest whose `billing` has an odd shape (`"price": "9.99"`, a field nobody has documented)
    /// installed regardless. Deserialising it into a typed struct would turn every one of those
    /// into a module that no longer loads — a much larger blast radius than the rule is worth. A
    /// `Value` cannot fail, so `Manifest::load` stays exactly as tolerant as it was.
    #[serde(default)]
    pub billing: Option<serde_json::Value>,
    /// **Which cores can run this module** (hub#521). Absent = "any", which is the shape of the 24
    /// published manifests and must keep installing untouched.
    ///
    /// The block name is not new: the SaaS has been reading `compatibility.min_erplora_version`
    /// out of published manifests since the marketplace existed, and republishes it in the
    /// catalogue as `min_core_version`. What was new is that **the hub never looked at it** — it
    /// was a decorative field on both sides of the wire. Now it is the one channel through which a
    /// module can say "I need a newer terminal" and be believed.
    #[serde(default)]
    pub compatibility: Option<Compatibility>,
    /// **Catalog of the domain error codes this module PROVIDES** (ADR-0398, hub#1177). Keyed by
    /// code (`<module>.<snake_case>`, the ADR-0205 ABI); the value carries only the code's state.
    ///
    /// `None` = the module has not migrated yet: the runtime keeps the ADR-0205 behaviour (any
    /// own-namespace code is a `Domain` error). `Some` = strict: an emitted code outside the
    /// catalog is a broken guest contract, and the installer refuses an `expect_rows.error` the
    /// catalog does not list. The human text is NOT here — it lives in `locales/<lang>.json`
    /// (ADR-0055); the manifest declares existence and state, so retiring a code becomes a
    /// visible diff instead of a silent one.
    #[serde(default)]
    pub errors: Option<BTreeMap<String, ErrorDecl>>,
    /// **Route guards this module declares over ANOTHER module's surface** (hub#775).
    ///
    /// A module that owns a precondition for an entire screen declares it here instead of patching
    /// every caller: `cash_register` blocks entry to the POS and the completion of a sale while no
    /// register session is open. The block is parsed here and acted on AUTHORITATIVELY by the
    /// command dispatcher ([`crate::commands::enforce_protects`]) and by the shell (rendered as
    /// `component` instead of mounting the module), so the contract it declares is no longer a
    /// wish the runtime logs and ignores.
    ///
    /// Cross-module by design: the guard runs against the module that owns the protected ROUTE
    /// (parsed out of `route_setting`'s value, e.g. `/m/sales` → `sales`), so a module does not
    /// need to `depends_on` the one it protects. Empty for every published manifest except
    /// `cash_register`, which is the canonical shape.
    #[serde(default)]
    pub protects: Vec<ProtectsDef>,
    /// **Declared mutability per record** (hub#632, decisión de Ioan 2026-08-09): what of this
    /// module's data can be edited after the fact, and through which door.
    ///
    /// `mutable: false` says the record is corrected, never edited (`reason` names why with a
    /// CLOSED vocabulary — fiscal · ledger · identity · audit — so the assistant can explain
    /// "an issued invoice is not edited: it is rectified with `invoice.rectify`", and
    /// `correct_with` points at the correction commands). `mutable: true` names the `update`
    /// command and, optionally, `patch: { read, key }` — which is what turns that update into a
    /// PARTIAL door: the dispatcher reads the current record, merges the sent keys on top
    /// (limited to the update schema's keys), validates the complete object and runs the SQL
    /// untouched (`commands::execute_at`). The conditional validation (mutable:false forbids
    /// update/patch) lives ONLY in `schemas/module.schema.json`, on purpose: no Rust duplicate.
    ///
    /// Absent in every published manifest, and that stays valid: no declaration = no patch door
    /// and nothing said about mutability.
    #[serde(default)]
    pub records: HashMap<String, RecordDef>,
    /// What this core did **not** understand of the manifest, and chose to install anyway
    /// (hub#521). Filled by [`Manifest::load`], never by serde — it describes what serde DROPPED,
    /// so it cannot come from serde.
    ///
    /// It rides on the manifest rather than in a side table because the manifest is what the
    /// registry keeps and what `/api/modules` renders: a warning that lives anywhere else is a
    /// line in a log nobody reads, which is the failure mode this issue is about.
    #[serde(skip)]
    pub warnings: Vec<ManifestWarning>,
}

/// One entry of the `records` block (hub#632): the declared mutability of one record kind.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct RecordDef {
    /// Can this record be edited after creation? `false` = corrected, never edited.
    pub mutable: bool,
    /// Why it is immutable, in a CLOSED vocabulary (`fiscal` · `ledger` · `identity` · `audit`)
    /// enforced by the authoring schema — closed so it is translatable and explainable.
    #[serde(default)]
    pub reason: Option<String>,
    /// Commands that CORRECT an immutable record (`sales.void`, `invoice.rectify`): the road the
    /// assistant points at instead of an edit that does not exist.
    #[serde(default)]
    pub correct_with: Vec<String>,
    /// The full-object update command of a mutable record (`sales.order.update_line`).
    #[serde(default)]
    pub update: Option<String>,
    /// What turns [`update`](Self::update) into a PARTIAL door — see [`PatchDef`].
    #[serde(default)]
    pub patch: Option<PatchDef>,
}

/// The read-merge contract of a partial update (hub#632): before validating, the dispatcher runs
/// [`read`](Self::read) with the caller's [`key`](Self::key) param, merges the sent keys on top of
/// the row (limited to the update schema's keys — the `get` returns columns the update does not
/// accept), and only then validates the COMPLETE object. Explicit `null` overwrites; omitted
/// preserves.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct PatchDef {
    /// Query of the SAME module that returns the current record (`sales.order.get`).
    pub read: String,
    /// Name of the payload key that identifies the record (`order_id`) — it is both the read's
    /// parameter and the update's own key field.
    pub key: String,
}

/// One entry of `depends_on` (hub#681): the module this one needs, and — optionally — the oldest
/// version of it that honours the contract.
///
/// `min_version` is a FLOOR, never a pin: at or above it the dependency satisfies, and absence
/// means "any installed version", which is what every plain-string entry (the shape of the whole
/// published catalogue) keeps meaning. Enforced at install time by `installer::register_module`;
/// blueprints and the install plan are not relaxed by it (they resolve versions upstream).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DependencyRef {
    /// Id of the required module (`inventory`).
    pub id: String,
    /// Oldest acceptable version of it (`1.2.20`), compared as a semver floor
    /// ([`version_triple`]). `None` = any version.
    pub min_version: Option<String>,
}

impl<'de> serde::Deserialize<'de> for DependencyRef {
    /// Accepts the two authoring shapes — `"id"` and `{ "id": ..., "min_version": ... }` — with
    /// errors that name the offending field. An unknown key inside the object form is refused:
    /// a dependency entry changes what the installer enforces, which is the refuse tier of
    /// ADR-0286 (silently dropping a constraint would install a module its author knows to be
    /// broken in this combination).
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct V;
        impl<'de> serde::de::Visitor<'de> for V {
            type Value = DependencyRef;

            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("a module id string or { \"id\": ..., \"min_version\": ... }")
            }

            fn visit_str<E: serde::de::Error>(
                self,
                id: &str,
            ) -> std::result::Result<Self::Value, E> {
                Ok(DependencyRef {
                    id: id.to_string(),
                    min_version: None,
                })
            }

            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut map: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut id: Option<String> = None;
                let mut min_version: Option<String> = None;
                while let Some(key) = map.next_key::<String>()? {
                    match key.as_str() {
                        "id" => id = Some(map.next_value()?),
                        "min_version" => min_version = map.next_value()?,
                        other => {
                            return Err(serde::de::Error::unknown_field(
                                other,
                                &["id", "min_version"],
                            ))
                        }
                    }
                }
                Ok(DependencyRef {
                    id: id.ok_or_else(|| serde::de::Error::missing_field("id"))?,
                    min_version,
                })
            }
        }
        deserializer.deserialize_any(V)
    }
}

/// Which cores can run a module (`compatibility`, hub#521).
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Compatibility {
    /// **Oldest core that can run this module.** Below it the install is refused
    /// ([`RuntimeError::CoreVersionTooOld`]) instead of half-landing: a module whose new blocks
    /// this core cannot read is a module that would look installed and be missing pieces.
    ///
    /// The key keeps the SaaS's spelling (`min_erplora_version`) on purpose — it is the name
    /// already written in published manifests and read by the marketplace git-sync, and renaming
    /// an identifier with an external contract breaks it (there is no republish of the fleet in
    /// this issue).
    #[serde(default)]
    pub min_erplora_version: Option<String>,
    /// **Newest core the author tested against** — parsed so it is not an unknown field, and
    /// deliberately **NOT enforced**.
    ///
    /// Enforcing it would refuse an OLD module on a NEW hub, and that direction working is the
    /// whole reason a hub can upgrade without every module moving the same day. An author who
    /// fills it in is documenting what they tried, not revoking a module the user already paid
    /// for.
    #[serde(default)]
    pub max_erplora_version: Option<String>,
}

/// A **route guard** one module declares over another module's surface (hub#775).
///
/// The contract `cash_register` has been carrying since v1.x: "while `enable_cash_register` is on,
/// the screen at `protected_pos_url` and every sale that goes through it must wait for an open
/// register session." Until hub#775 the runtime reported the block as an unknown field and dropped
/// it — the POS loaded, a cash sale completed, and the money vanished from the drawer reconciliation
/// without an error. The block is now PARSED, and the dispatcher enforces it authoritatively (see
/// [`crate::commands::enforce_protects`]).
///
/// Cross-module on purpose. `cash_register` does not `depends_on` `sales`: it protects a ROUTE the
/// shell happens to serve with `sales`. The dispatcher derives the protected module from
/// `route_setting` (its value is `/m/<module>`), so the guard is read on EVERY command whose owner
/// is that module — not only on the one named in the issue.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ProtectsDef {
    /// Query (of the module that declares the guard) that returns the SETTINGS row carrying
    /// `enabled_setting` and `route_setting`. Resolved in a system context: same `hub_id`, no
    /// permission re-check — the guard is a contract vouched by the module's author, not a user
    /// action (the same rule as `reads`, ADR-0069 §1 rule 2).
    pub settings_query: String,
    /// The boolean column in that settings row that ARMMS the guard. `false` or absent → the guard
    /// is dormant (e.g. a hub that has not turned the cash register on sells as it always did).
    pub enabled_setting: String,
    /// The column whose value is the protected ROUTE (`/m/sales`). The dispatcher parses the module
    /// out of it to decide which commands the guard applies to; the shell renders `component`
    /// instead of mounting the module at that route.
    pub route_setting: String,
    /// Query (of the module that declares the guard) whose rows decide whether the precondition is
    /// met. Resolved in the same system context as `settings_query`.
    pub guard_query: String,
    /// What `guard_query` must return for the precondition to be MET. Today only `non_empty`
    /// ("there is at least one open session"); a future flavour could add `empty`.
    pub expect: ProtectsExpect,
    /// Shell-side Web Component to render INSTEAD of the protected module while the precondition
    /// is unmet (e.g. `erp-cashregister-open`). Transported to the shell by the manifest snapshot,
    /// never executed by the runtime.
    pub component: String,
    /// Event the shell listens for to RE-MOUNT the protected module without a manual reload (e.g.
    /// `cash_register.session_opened`). Transported to the shell, not consumed by the runtime.
    pub resume_on: String,
}

/// What [`ProtectsDef::guard_query`] must return for the guard to be SATISFIED (hub#775).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProtectsExpect {
    /// The precondition is met when `guard_query` returns at least one row (e.g. there is an open
    /// register session). The default reading of a cash drawer: "the drawer is open".
    NonEmpty,
}

impl Default for ProtectsExpect {
    fn default() -> Self {
        Self::NonEmpty
    }
}

impl ProtectsDef {
    /// Parses the protected MODULE out of `route_setting`'s value (`/m/sales` → `sales`).
    ///
    /// Returns `None` when the value is empty or does not match the `/m/<module>` shape the shell's
    /// router serves: a guard pointing at a route this hub does not know how to mount is inert, and
    /// the dispatcher treats it as such rather than refusing the install over a typo.
    pub fn protected_module<'a>(&self, route_value: &'a str) -> Option<&'a str> {
        let stripped = route_value.strip_prefix("/m/")?;
        let module = stripped.split('/').next()?;
        if module.is_empty() {
            return None;
        }
        Some(module)
    }
}

/// Something in a `module.json` this core does not act on, reported instead of dropped (hub#521).
///
/// A warning never blocks: it is the tier for fields whose loss costs a screen, a button or a
/// checklist item. What changes what RUNS is refused outright — see [`Manifest::load`].
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct ManifestWarning {
    /// Dotted path of the field, precise enough to find it in the file: `protects`,
    /// `navigation[1].permission`, `commands.services.services.create.validates`.
    pub path: String,
    /// Why it is a warning and what it costs, in one sentence someone can act on.
    pub detail: String,
}

/// The version of the core this binary IS (`1.0.0`), the number a manifest's
/// `compatibility.min_erplora_version` is compared against (hub#521).
///
/// Same source as everything else that reports it: `[workspace.package] version`, which the release
/// CI rewrites from the `v*` tag (ADR-0280 — the tag is what decides). `crates/server` re-exports
/// this as `HUB_VERSION` rather than reading its own `CARGO_PKG_VERSION`, so the number the hub
/// reports on the wire and the number it refuses a module with can never be two different things.
pub const CORE_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Bloque `fiscal_regime` del manifest (ADR-0273 D6): qué régimen fiscal, y de qué país, cumple
/// este módulo. `{ "country": "ES", "regime": "verifactu" }`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct FiscalRegimeDef {
    /// ISO-3166-1 alpha-2 — la misma forma con la que se compara: `hub_settings.country_code` y
    /// `_hub_fiscal_regime_registry.country_code`.
    pub country: String,
    /// Clave del régimen (`verifactu`, `facturx`…), la misma que el registro de regímenes del core.
    pub regime: String,
    /// Techo de la factura simplificada de ESTE régimen, en céntimos (hub#1010). Opcional: el
    /// proveedor que no lo declara no dice «cero», dice «yo no muevo ese número» — el que hubiera
    /// se queda. Quien conoce el límite es el módulo del país, que además se actualiza en cada
    /// arranque; la ley puede cambiarlo sin tocar el runtime ni migrar nada. La fila y la query
    /// siguen siendo del core (ADR-0357): la respuesta no puede depender de que un módulo esté
    /// instalado.
    #[serde(default)]
    pub simplified_invoice_max_cents: Option<i64>,
}

/// Acción que un **usuario** puede intentar sobre un fichero o carpeta desde la pantalla `/files`.
///
/// Ver y descargar NO están aquí: son siempre posibles (con sesión y permiso de lectura). Esta
/// enumeración cubre solo lo que **modifica** el contenido, que es lo que un módulo debe conceder
/// explícitamente (ADR-0172).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UserFileAction {
    /// Subir ficheros o crear subcarpetas dentro de la carpeta del módulo.
    Upload,
    /// Renombrar un fichero o una subcarpeta.
    Rename,
    /// Borrar un fichero o una subcarpeta.
    Delete,
}

impl UserFileAction {
    /// Nombre declarativo tal y como aparece en `module.json`.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Upload => "upload",
            Self::Rename => "rename",
            Self::Delete => "delete",
        }
    }

    /// Todas las acciones, para construir la política de una carpeta sin módulo dueño.
    pub const ALL: [Self; 3] = [Self::Upload, Self::Rename, Self::Delete];
}

/// A business role declared by a module (`roles[]`, paso 2b / hub#351). Mirror of `$defs/role` in
/// `schemas/module.schema.json`; the three fields are required there and here, so a half-declared
/// role never reaches the validation.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct RoleDef {
    /// Stable identifier of the role (`waiter`, `shift_lead`). It is the key `role_permissions`
    /// grants against and the value stored in `hub_user.role`, so it is an identifier, not a
    /// label: snake_case ASCII, and never one of the base keys.
    pub key: String,
    /// Human name shown to the administrator who activates the role. **English canonical**
    /// (ADR-0055): the translation travels in `locales/<lang>.json`, like `navigation[].label`.
    pub label: String,
    /// Base role this one hangs from — the reason the frozen three-key contract survives: every
    /// declared role resolves to a base one, so the core gate and the 24 published modules keep
    /// working without a republish or a migration.
    ///
    /// Only the NON-administrative base roles can be extended (`manager`, `employee`). See
    /// `installer::validate_role_declarations`: administering the hub is granted by the hub, never
    /// by a manifest (hub#347).
    pub extends: String,
}

/// Almacenamiento persistente declarado por un módulo.
///
/// El nombre se valida también en el toolkit y en el runtime porque el manifest instalado es una
/// frontera de seguridad. Se resuelve siempre como `media/modules/<folder>/`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct StaticFilesDef {
    pub folder: String,
    /// Qué puede hacer el **usuario** con estos ficheros desde `/files`. Ausente o vacío =
    /// **solo ver y descargar**, que es el default deliberado: los documentos que genera un
    /// módulo suelen ser evidencia (los XML de VeriFactu son inalterables por ley) y borrarlos a
    /// mano desde un gestor de archivos no puede ser el camino fácil.
    ///
    /// No limita al módulo: este sigue escribiendo por `ModuleStorage`/`NativeHost`. Es la
    /// diferencia entre "el módulo guarda su XML" y "el cajero puede borrarlo".
    #[serde(default)]
    pub user_actions: Vec<String>,
}

impl StaticFilesDef {
    /// Un solo segmento portable: minúsculas ASCII, dígitos, `_` y `-`; sin separadores ni `..`.
    pub fn is_valid_folder(&self) -> bool {
        let mut chars = self.folder.chars();
        matches!(chars.next(), Some(c) if c.is_ascii_lowercase())
            && self.folder.len() <= 64
            && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
    }

    /// `true` si el módulo concedió esa acción. Una acción que el host no conoce simplemente no
    /// concede nada (compatibilidad hacia adelante: un manifest más nuevo no rompe un hub viejo,
    /// y tampoco le abre una puerta que no entiende).
    pub fn allows(&self, action: UserFileAction) -> bool {
        self.user_actions.iter().any(|a| a == action.as_str())
    }
}

/// Una tarea programada declarada en el manifest (ADR-0011). Espejo de `$defs/scheduledTask`
/// en `schemas/module.schema.json`. El `command` debe pertenecer al **propio módulo** (mismo
/// aislamiento que el handler WASM); se valida al volcar la tarea a `_scheduled_tasks`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ScheduledTaskDef {
    /// Nombre único de la tarea **dentro del módulo** (clave de idempotencia con `module_id`).
    pub name: String,
    /// Command del propio módulo a ejecutar al vencer el cron (sin usuario).
    pub command: String,
    /// Expresión cron de 5 campos (`min hora dom mes dow`) o atajo (`@daily`, `@hourly`…).
    /// Ver `scheduler::cron` para la gramática soportada.
    pub cron: String,
    /// Payload fijo que recibe el command en cada ejecución (opcional).
    #[serde(default)]
    pub payload: Option<serde_json::Value>,
    /// Comportamiento de catch-up tras un apagado (ADR-0011): `collapse` (por defecto) ejecuta
    /// **una sola vez** el backlog al arrancar; `skip` no ejecuta nada vencido durante el apagado
    /// y solo reprograma. (No hay modo "run-all": el ADR fija collapse para tareas idempotentes.)
    #[serde(default)]
    pub catch_up: CatchUp,
}

/// Política de catch-up de una scheduled task tras un periodo apagado (ADR-0011).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CatchUp {
    /// Ejecuta una sola vez si había backlog vencido (idempotente). Por defecto.
    #[default]
    Collapse,
    /// No ejecuta el backlog; solo reprograma al siguiente vencimiento.
    Skip,
}

/// Bloque `notify` del manifest (ADR-0012): los canales de alto nivel que usa el módulo.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NotifyCapability {
    /// Canales declarados (`email`/`sms`/`whatsapp`).
    #[serde(default)]
    pub channels: Vec<String>,
}

/// Bloque `network` del manifest (ADR-0012, §5.5): allowlist de `http.fetch` mediado.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NetworkCapability {
    /// Hosts/patrones permitidos para las llamadas salientes mediadas por el host.
    #[serde(default)]
    pub allow: Vec<String>,
    /// Nombres de secretos del hub que el host inyecta en las llamadas (no su valor).
    #[serde(default)]
    pub secrets: Vec<String>,
}

/// Bloque `capabilities` del manifest (ADR-0079): los permisos que el módulo SOLICITA al host.
/// Consolida los antiguos `network`/`notify` (ADR-0012) y añade `certificate`/`printer`. El
/// usuario los concede explícitamente (toggle en Settings); el host media. Vacío = no pide nada.
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Capabilities {
    #[serde(default)]
    pub network: Option<NetworkCapability>,
    #[serde(default)]
    pub certificate: Option<CertificateCapability>,
    #[serde(default)]
    pub printer: Option<PrinterCapability>,
    #[serde(default)]
    pub notify: Option<NotifyCapability>,
    #[serde(default)]
    pub manage_flows: Option<ManageFlowsCapability>,
}

/// Acceso al certificado PKCS#12 del negocio (firma/transmisión fiscal). El host firma; el
/// módulo nunca recibe la clave privada.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct CertificateCapability {
    /// Para qué se usa (texto legible, p.ej. `fiscal-sign`).
    #[serde(default)]
    pub purpose: Option<String>,
}

/// Acceso a impresora ESC/POS vía el bridge/peripherals. Marcador sin parámetros (de momento).
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct PrinterCapability {}

/// **Administrar el kernel de automatización** del hub — `/api/hub/flows*` (hub#714, ADR-0283 §9).
/// Marcador sin parámetros: no hay grados, o el módulo edita los flujos del negocio o no.
///
/// Es la capability con más alcance de todas, y por eso existe: un flujo ejecuta commands con
/// `Origin::Automation` bajo los grants que `PUT …/grants` escribe, así que quien administra
/// flujos puede hacer que el hub actúe **sin nadie delante**. El resto de capabilities dan un
/// primitivo (red, certificado, impresora, aviso); esta da el resto de primitivos a través de un
/// flujo. Que un módulo de inventario la tuviera por el mero hecho de estar cargado en la sesión
/// de un admin sería una escalada silenciosa — y hasta hub#714 lo era.
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct ManageFlowsCapability {}

/// Clases de capability que el host conoce y puede gatear (ADR-0079). El nombre canónico (kebab)
/// es la clave de grant en `_module_capability_grants` y la etiqueta de la UI.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CapabilityKind {
    Network,
    Certificate,
    Printer,
    Notify,
    /// Administrar los flujos del hub (hub#714). Ver [`ManageFlowsCapability`].
    ManageFlows,
}

impl CapabilityKind {
    /// El set CERRADO, en orden estable. Es contrato del kernel (hub#1235):
    /// `tests/kernel_contract_engine.rs` lo congela, comprueba contra el bloque `capabilities` de
    /// `schemas/module.schema.json` que host y schema no puedan divergir, y lee las variantes del
    /// enum de la propia fuente para que esta lista no se quede corta.
    pub const ALL: &'static [CapabilityKind] = &[
        CapabilityKind::Network,
        CapabilityKind::Certificate,
        CapabilityKind::Printer,
        CapabilityKind::Notify,
        CapabilityKind::ManageFlows,
    ];

    /// Nombre canónico estable (clave de grant + de UI).
    pub fn as_str(self) -> &'static str {
        match self {
            CapabilityKind::Network => "network",
            CapabilityKind::Certificate => "certificate",
            CapabilityKind::Printer => "printer",
            CapabilityKind::Notify => "notify",
            CapabilityKind::ManageFlows => "manage_flows",
        }
    }
    /// Parsea un nombre canónico; `None` si no es una capability conocida.
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "network" => Some(CapabilityKind::Network),
            "certificate" => Some(CapabilityKind::Certificate),
            "printer" => Some(CapabilityKind::Printer),
            "notify" => Some(CapabilityKind::Notify),
            "manage_flows" => Some(CapabilityKind::ManageFlows),
            _ => None,
        }
    }
}

impl Manifest {
    /// Capabilities que el módulo SOLICITA, plegando los campos `network`/`notify` top-level
    /// deprecados (ADR-0012) dentro del modelo `capabilities` (ADR-0079). El bloque
    /// `capabilities` tiene precedencia. Orden estable para UI.
    pub fn requested_capabilities(&self) -> Vec<CapabilityKind> {
        let mut out = Vec::new();
        if self.capabilities.network.is_some() || self.network.is_some() {
            out.push(CapabilityKind::Network);
        }
        if self.capabilities.certificate.is_some() {
            out.push(CapabilityKind::Certificate);
        }
        if self.capabilities.printer.is_some() {
            out.push(CapabilityKind::Printer);
        }
        if self.capabilities.notify.is_some() || self.notify.is_some() {
            out.push(CapabilityKind::Notify);
        }
        if self.capabilities.manage_flows.is_some() {
            out.push(CapabilityKind::ManageFlows);
        }
        out
    }

    /// ¿El módulo declara necesitar esta capability? (incluye los alias deprecados).
    pub fn requests_capability(&self, kind: CapabilityKind) -> bool {
        self.requested_capabilities().contains(&kind)
    }

    /// Does this module fulfil `regime` for `country`? (ADR-0273 D6, hub#555.)
    ///
    /// This is the predicate the fiscal profile **counts** with — never "is this module
    /// `verifactu`". The country is part of it on purpose: a French Factur-X provider is not a
    /// VeriFactu provider for a Spanish hub. Country comparison is case-insensitive because
    /// `hub_settings.country_code` is normalised to upper case while a manifest is typed by hand.
    ///
    /// A module with no `fiscal_regime` block fulfils nothing, which is the whole fail-closed
    /// property: staying silent never counts as complying.
    pub fn fulfils_regime(&self, country: &str, regime: &str) -> bool {
        self.fiscal_regime.as_ref().is_some_and(|f| {
            f.country.eq_ignore_ascii_case(country.trim()) && f.regime.trim() == regime.trim()
        })
    }

    /// **Is this module SOLD?** (ADR-0273 D7.) `None` = free; `Some(term)` names the term that
    /// prices it, so the refusal can say which one instead of "somewhere in your billing block".
    ///
    /// Same reading as the SaaS's `_manifest_declares_paid` (ADR-0105 phase 1, which already bars a
    /// third party from publishing a paid module), and deliberately so — a hub and the marketplace
    /// disagreeing about whether a module is free would be worse than either rule alone:
    ///
    /// - `tier: premium` is monetised by definition (ADR-0006/ADR-0032 collapsed the rest to
    ///   `free`), whether or not a price is filled in yet;
    /// - a single price with `type` `one_time`/`subscription` and `price > 0`;
    /// - any entry of `tiers[]` above zero — a free tier alongside a paid one is a paid module.
    ///
    /// **A block nobody can read counts as sold.** Not as free: the same direction as
    /// [`crate::fiscal_profile::FiscalStatus::parse`], where an unreadable row must not be read as
    /// "owes nothing". A `billing` that is not an object, or a price that is not a number, is a
    /// manifest making a commercial claim the runtime cannot check — and the only module this is
    /// ever asked about is the one a hub's compliance would hang from. It costs nothing today:
    /// zero published manifests combine `fiscal_regime` with a `billing` block of any shape.
    pub fn sold_under(&self) -> Option<String> {
        let billing = self.billing.as_ref()?;
        if billing.is_null() {
            return None;
        }
        let Some(terms) = billing.as_object() else {
            return Some("a `billing` block that is not an object".to_string());
        };
        if terms.is_empty() {
            return None;
        }
        // `Some(false)` = readable and free, `None` = unreadable. Only `Some(true)` and `None` sell.
        let priced = |value: Option<&serde_json::Value>| match value {
            None => Some(false),
            Some(v) if v.is_null() => Some(false),
            Some(v) => v.as_f64().map(|n| n > 0.0),
        };
        match terms.get("tier").map(|t| t.as_str()) {
            Some(Some("premium")) => return Some("`tier: premium`".to_string()),
            Some(None) => return Some("a `tier` that is not a string".to_string()),
            _ => {}
        }
        for (index, tier) in terms
            .get("tiers")
            .and_then(|t| t.as_array())
            .map(|t| t.as_slice())
            .unwrap_or_default()
            .iter()
            .enumerate()
        {
            match priced(tier.get("price")) {
                Some(true) => return Some(format!("a priced entry in `tiers[{index}]`")),
                None => return Some(format!("an unreadable `price` in `tiers[{index}]`")),
                Some(false) => {}
            }
        }
        match terms.get("type").map(|t| t.as_str()) {
            // `type` alone does not sell: `subscription` with `price: 0` is how a manifest says
            // "free, and renewed" — but a price that cannot be read under a paid `type` does.
            Some(Some("one_time")) | Some(Some("subscription")) => match priced(terms.get("price"))
            {
                Some(true) => Some(format!(
                    "`type: {}` with a price above zero",
                    terms["type"].as_str().unwrap_or_default()
                )),
                None => Some("a `price` that is not a number".to_string()),
                Some(false) => None,
            },
            Some(None) => Some("a `type` that is not a string".to_string()),
            _ => match priced(terms.get("price")) {
                Some(true) => Some("a `price` above zero".to_string()),
                None => Some("a `price` that is not a number".to_string()),
                Some(false) => None,
            },
        }
    }
}

/// Bloque `settings` del manifest: la pantalla de ajustes declarativa del módulo. El shell pinta un
/// formulario genérico a partir del `schema` (JSON Schema: campos/tipos/defaults/`title`/`enum`),
/// lo carga con la query `get` y lo guarda con el command `set` (ambos del propio módulo, que ya
/// existen). Si `component` está presente, el shell pinta ese Web Component en vez del form genérico
/// (escape-hatch para ajustes estructurales, p.ej. la estructura del ticket).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SettingsDef {
    /// Título de la sección de ajustes (legible).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    /// Icono ionicons para la sección/pestaña.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon: Option<String>,
    /// Ruta (relativa al paquete del módulo) del JSON Schema que describe el formulario.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub schema: Option<String>,
    /// Query del propio módulo que devuelve los valores actuales (fila singleton). P.ej. `cash_register.settings.get`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub get: Option<String>,
    /// Command del propio módulo que persiste (upsert del snapshot). P.ej. `cash_register.settings.update`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub set: Option<String>,
    /// Escape-hatch: Web Component propio que el shell pinta en vez del form genérico (lo estructural).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub component: Option<String>,
}

/// `setup` block of the manifest: the module's own answer to "am I configured?" (ADR-0063, extended
/// by hub#369). Mirror of `setup` in `schemas/module.schema.json`.
///
/// The runtime runs [`query`](Self::query) through the dispatcher — with the caller's permissions,
/// against real data, zero mocks — takes the FIRST row and evaluates
/// [`configured_when`](Self::configured_when). All checks pass ⇒ configured; a missing row ⇒ not
/// configured. The result becomes one item of `hub.setup.status`.
///
/// What a module may NOT declare is how important it is. `required` maps to 🔴 functional / 🟡
/// recommended, and the ⛔ blocking level stays core-owned (`setup_status`), so a third-party module
/// cannot proclaim itself a blocker of the sale.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SetupDef {
    /// Namespaced read query of the module itself that reports the configuration state.
    pub query: String,
    /// Static params for [`query`](Self::query).
    #[serde(default)]
    pub params: serde_json::Map<String, serde_json::Value>,
    /// Configured ⇔ ALL of these pass on the first row. Empty ⇒ merely having a row is enough.
    #[serde(default)]
    pub configured_when: Vec<SetupCheck>,
    /// Alert title, **English canonical** (ADR-0055) — the translation travels in
    /// `locales/<lang>.json` under `setup.title`.
    pub title: String,
    /// Short help text, English canonical (`locales/<lang>.json` → `setup.description`).
    #[serde(default)]
    pub description: String,
    /// Ionicons name for the item.
    #[serde(default)]
    pub icon: String,
    /// Screen that completes the item.
    pub route: String,
    /// Permission needed to configure it. Only whoever can act is told about it: an item a cashier
    /// cannot clear is noise, and the query would reject them anyway.
    #[serde(default)]
    pub permission: String,
    /// Countries this item applies to (ISO-3166-1 alpha-2). Empty = every country.
    ///
    /// The Hub is international and knows no concrete module, so "VeriFactu does not show outside
    /// Spain" cannot be a rule hardcoded in the core: the module that carries a national obligation
    /// declares where it applies.
    #[serde(default)]
    pub countries: Vec<String>,
    /// Slot in the checklist. The scale belongs to the core (see `setup_status`), which reserves
    /// the positions of its own items; a module takes the slot the core assigned to it. Absent =
    /// after everything the core placed.
    #[serde(default)]
    pub order: Option<i64>,
    /// `true` (the default) = 🔴 functional; `false` = 🟡 recommended. Never ⛔: that list is
    /// core-owned.
    #[serde(default = "default_true")]
    pub required: bool,
}

fn default_true() -> bool {
    true
}

/// One check of [`SetupDef::configured_when`] against a column of the first row. Exactly one of
/// `truthy`/`equals` per entry; neither ⇒ the check never passes (a half-written contract must not
/// silently tick the item as done).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SetupCheck {
    /// Column of the result to evaluate.
    pub field: String,
    /// Passes when the field is truthy (`truthy: false` inverts it).
    #[serde(default)]
    pub truthy: Option<bool>,
    /// Passes when the field equals this value (lax, compared as text).
    #[serde(default)]
    pub equals: Option<serde_json::Value>,
}

/// Bloque `agent` del manifest: descripción del módulo (en inglés) para el routing del
/// asistente y palabras clave opcionales para pre-filtro léxico. ARQUITECTURA.md §9.2b.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Agent {
    pub description: String,
    #[serde(default)]
    pub keywords: Vec<String>,
}

/// Una lectura pre-cargada (ADR-0069). Dos formas, y la primera es la de siempre:
///
/// ```json
/// "reads": [
///   "taxes.rules.list",
///   { "query": "inventory.products.unit_of", "params": { "product_id": "payload.product_id" } },
///   { "query": "taxes.rules.list", "required": true }
/// ]
/// ```
///
/// **Sin parámetros** (string) el handler recibe la query entera — sirve para catálogos pequeños
/// como las reglas de IVA. **Con parámetros** recibe solo la fila que le importa, que es lo que
/// hacía falta para validar contra el dato concreto: sin esto, un handler podía pedir «todas las
/// reglas» pero no «la unidad de ESTE producto», y cualquier validación por fila se quedaba sin
/// sitio — en el SQL no vale (un `WHERE` que no casa responde `ok`, no error) y pedírselo al
/// cliente rompe que el servidor sea la autoridad.
///
/// Los valores de `params` referencian el **payload del command** (`payload.<campo>`). Solo eso:
/// nada de expresiones ni de leer otras reads, para que el manifest siga siendo declarativo y
/// auditable de un vistazo.
///
/// **`required`** (hub#701) es opt-in y solo vive en la forma objeto. El defecto sigue siendo el
/// fallo GRACEFUL (regla 3 de ADR-0069): una read que no resuelve se omite y el handler degrada —
/// cobrar es lo último que puede romperse en un TPV. Pero una read de la que depende el IMPUESTO
/// no puede admitir adivinar: si falla, el runtime aborta el command con `ReadUnavailable` en vez
/// de entregarle al handler un catálogo vacío indistinguible de «este hub no tiene reglas». La
/// forma string no puede ser `required` a propósito: el caso simple sigue siendo el caso graceful.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(untagged)]
pub enum ReadDef {
    /// `"taxes.rules.list"` — la query entera, sin filtrar. Nunca `required`.
    Query(String),
    /// `{ "query": …, "params": { … }, "required": bool }` — filtrada por campos del payload.
    Parameterized {
        query: String,
        #[serde(default)]
        params: HashMap<String, String>,
        /// `true` ⇒ si la query falla, el command se ABORTA con `ReadUnavailable` en vez de
        /// omitirse. Default `false`: el defecto sigue siendo graceful. Ver hub#701.
        #[serde(default)]
        required: bool,
    },
}

impl ReadDef {
    /// El nombre de la query, sea cual sea la forma.
    pub fn query(&self) -> &str {
        match self {
            ReadDef::Query(q) => q,
            ReadDef::Parameterized { query, .. } => query,
        }
    }
    /// Resuelve los parámetros contra el payload del command. `payload.<campo>` toma un campo de
    /// primer nivel; cualquier otra cosa se pasa como literal (útil para constantes).
    pub fn resolve_params_from_map(&self, payload: &erplora_db::Params) -> erplora_db::Params {
        let mut out = erplora_db::Params::new();
        if let ReadDef::Parameterized { params, .. } = self {
            for (name, expr) in params {
                let value = match expr.strip_prefix("payload.") {
                    Some(field) => payload
                        .get(field)
                        .cloned()
                        .unwrap_or(serde_json::Value::Null),
                    None => serde_json::Value::String(expr.clone()),
                };
                out.insert(name.clone(), value);
            }
        }
        out
    }

    /// ¿Esta read es obligatoria? Solo la forma objeto puede declararlo (hub#701); la forma
    /// string es siempre graceful, como hasta ahora.
    pub fn is_required(&self) -> bool {
        matches!(self, ReadDef::Parameterized { required: true, .. })
    }
}

/// Operation supported by the declarative affected-rows contract (hub#139).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExpectRowsOp {
    Min,
}

/// The `dedup_key` half of a `command.emit` entry (hub#1076): the name of a field in the
/// command's bound payload (`context.payload` plus what `system_params` injects — same source a
/// `:name` bind reads from) whose value derives the outbox row's id.
///
/// This is what makes a repeated emission with the same key a no-op instead of a second event —
/// `outbox::insert_op` turns it into the exact `ON CONFLICT (id) DO NOTHING` shape
/// `outbox::insert_core_event_once` already uses for a core-ingested event
/// (`"wa-<wa_message_id>"`). It is the outbox idempotency-key pattern (Stripe's
/// `Idempotency-Key`, Kafka's keyed dedup): the key is evaluated against the request, and a
/// repeat within the store's own uniqueness window is absorbed, never rejected — the shape a
/// webhook redelivery or an outbox-relay retry needs, which `min_affected_rows`/`expect_rows`
/// cannot give (both roll back the whole transaction and hand the caller an error).
#[derive(Debug, Clone, serde::Deserialize)]
pub struct EmitDedupKey {
    pub event: String,
    pub dedup_key: String,
}

/// One entry of a command's `emit` list (hub#1076).
///
/// Two wire shapes, kept wire-compatible with every published module:
/// - a plain string (`"sale.completed"`) — the legacy, always-emits-by-execution behaviour;
/// - an object naming `dedup_key` (`{"event": "...", "dedup_key": "wa_message_id"}`) — opt-in,
///   see [`EmitDedupKey`].
///
/// A manifest that only ever wrote `emit: ["a.b"]` deserialises exactly as it always has: the
/// field is additive, never a behaviour change for a module that has not adopted it.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(untagged)]
pub enum EmitDef {
    Name(String),
    Keyed(EmitDedupKey),
}

impl EmitDef {
    /// The event name, whichever wire shape declared it.
    pub fn event(&self) -> &str {
        match self {
            EmitDef::Name(name) => name,
            EmitDef::Keyed(k) => &k.event,
        }
    }

    /// The payload field this entry derives its outbox dedup id from, if it declared one.
    pub fn dedup_key(&self) -> Option<&str> {
        match self {
            EmitDef::Name(_) => None,
            EmitDef::Keyed(k) => Some(&k.dedup_key),
        }
    }
}

impl From<&str> for EmitDef {
    fn from(name: &str) -> Self {
        EmitDef::Name(name.to_string())
    }
}

impl From<String> for EmitDef {
    fn from(name: String) -> Self {
        EmitDef::Name(name)
    }
}

/// State of one declared domain error code (ADR-0398). An empty object is the normal entry;
/// `deprecated` names the version since which consumers are told to stop relying on it — the
/// first of the two publications retiring a code needs (the second one deletes it).
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct ErrorDecl {
    #[serde(default)]
    pub deprecated: Option<String>,
}

/// Gate of a declarative SQL command (hub#139) that turns an `UPDATE ... WHERE` matching fewer
/// rows than expected into a stable business rejection instead of an ambiguous `200 ok`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ExpectRows {
    pub op: ExpectRowsOp,
    pub n: u64,
    /// Namespaced code the caller programs/translates against (`inventory.insufficient_stock`).
    pub error: String,
    /// Optional human fallback. When omitted, the runtime generates one without internal data.
    #[serde(default)]
    pub message: Option<String>,
    /// **Ancla la guarda a UNA sentencia** del command (hub#1091): la ruta del fichero SQL, tal
    /// cual aparece en `commands.<name>.sql`. Ausente = el comportamiento de siempre: la suma
    /// del lote entero.
    ///
    /// # Por qué existe
    ///
    /// La suma del lote es la semántica DOCUMENTADA de `expect_rows`/`min_affected_rows`, pero un
    /// command con una sentencia incondicional al lado de la que lleva la guarda queda
    /// NEUTRALIZADO sin señal alguna: en `online_booking.bookings.create` (online_booking#25)
    /// el INSERT de la reserva no casa (fuera de ventana), el UPSERT del contador afecta 1, el
    /// `min: 1` se cumple con la fila que NO era la vigilada — `200 ok`, reserva sin guardar y
    /// evento de una reserva inexistente. Mismo patrón en `appointments.*` (historia) y
    /// `tables.tables.hold` (upsert idempotente).
    ///
    /// No se cambia el DEFAULT a propósito: hay commands legítimos de varias sentencias cuya
    /// suma ES el contrato (`customers.consent.grant` exige 3 filas de 3 sentencias que afectan
    /// 1 cada una) y otros con pasos que legítimamente afectan 0 (`customers.anonymize`:
    /// «sin notas que borrar» no es un fallo). Sólo el módulo sabe cuál sentencia porta la
    /// guarda — y esta campo es cómo lo declara.
    ///
    /// El installer rechaza una ruta que no esté en la lista `sql` del command (un ancla que no
    /// apunta a nada se leería como protegido y no lo estaría, que es justo el fallo que
    /// hub#1091 cierra).
    #[serde(default)]
    pub statement: Option<String>,
}

#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Migrations {
    #[serde(default)]
    pub sqlite: Vec<MigrationEntry>,
    #[serde(default)]
    pub postgres: Vec<MigrationEntry>,
}

/// Una migración declarada: la ruta, y qué dice el módulo que hace (hub#542).
///
/// **Un string sigue siendo válido y se lee como `expand`**, así que los 24 manifests publicados
/// valen sin tocarlos — que es lo que permite meter el contrato sin republicar la flota.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(untagged)]
pub enum MigrationEntry {
    /// `"migrations/postgres/001_init.sql"` — aditiva, el 95% de los casos.
    Path(String),
    Declared {
        file: String,
        #[serde(default)]
        kind: crate::migration_guard::Kind,
        /// Versión del módulo que dejó de usar lo que este `contract` retira. Todavía no se
        /// consume: la ventana del contract es la segunda iteración de hub#542.
        #[serde(default)]
        since: Option<String>,
    },
}

impl MigrationEntry {
    pub fn file(&self) -> &str {
        match self {
            MigrationEntry::Path(file) => file,
            MigrationEntry::Declared { file, .. } => file,
        }
    }

    pub fn kind(&self) -> crate::migration_guard::Kind {
        match self {
            MigrationEntry::Path(_) => crate::migration_guard::Kind::Expand,
            MigrationEntry::Declared { kind, .. } => *kind,
        }
    }
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Nav {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub icon: Option<String>,
    pub component: String,
    /// Permiso que ABRE esta pestaña. Sin él, `/api/navigation` no la sirve (hub#1052).
    ///
    /// El manifest declara a quién le sirve la pestaña, y el runtime revalida siempre la
    /// query/command real detrás — esto no es la puerta, es no enseñar una puerta cerrada. `None`
    /// = visible para todos, que es como se comportan los manifests publicados hasta hoy.
    #[serde(default)]
    pub permission: Option<String>,
}

/// Un widget de dashboard declarado en el manifest (ADR-0054). Espejo de `$defs/widget` en
/// `schemas/module.schema.json`. El módulo declara metadatos (título/icono/categoría/tamaño,
/// `sectors`+`default` para la diferenciación por tipo de negocio) y EXACTAMENTE UNA de las dos
/// vías de render: declarativa (`kind` + `query` + `map`/`options`/`params`) o `component` (WC
/// propio). El runtime no ejecuta nada por widget; solo parsea y transporta el contrato (el shell
/// fetchea el `module.json` crudo y construye el `WidgetDef` de `ok-widget-board`).
///
/// CERO MOCKS (directriz del proyecto): la vía declarativa SIEMPRE se alimenta de una `query` real
/// del módulo; un widget sin datos reales no se inventa, se omite. La regla "exactamente uno de
/// { kind, component }" la valida el JSON Schema (no este struct, permisivo por compat hacia
/// adelante igual que el resto del fichero).
#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct WidgetDef {
    /// Título mostrado en el board y en el selector. OBLIGATORIO.
    pub title: String,
    /// Nombre de icono ionicons para el selector (p. ej. `trending-up-outline`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon: Option<String>,
    /// Grupo en el selector (p. ej. "Ventas", "Inventario").
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub category: Option<String>,
    /// Tamaño en la rejilla de 12 columnas (`sm`=3, `md`=6, `lg`=8). Por defecto `md`.
    #[serde(default)]
    pub size: WidgetSize,
    /// Permiso para ver el widget (se filtra en cliente; la `query` lo revalida server-side).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub permission: Option<String>,
    /// Tipos de negocio a los que aplica (`hosteleria`/`retail`/`gestoria`/`rrhh`/`belleza`/`general`).
    /// Ausente/vacío = todos.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub sectors: Vec<String>,
    /// Sugerido ACTIVO cuando el sector del hub coincide con `sectors` (preset "Recomendado").
    #[serde(default)]
    pub default: bool,
    /// Refresco EN VIVO (ADR-0054 T1): eventos de dominio cuya emisión re-ejecuta la `query` de
    /// este widget. El shell se suscribe al canal push existente (Outbox→broadcast) y re-consulta
    /// con debounce. Ausente/vacío = el widget se monta una vez. El Hub solo TRANSPORTA el campo
    /// (el shell lee el `module.json` crudo); aquí se declara para no perderlo en un round-trip.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub refresh_on: Vec<String>,
    /// Tipo de render declarativo. Mutuamente excluyente con `component` (lo valida el schema).
    /// Si está presente, `query` es obligatoria.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<WidgetKind>,
    /// Query YA declarada del módulo que alimenta el widget (vía declarativa). Nombre completo
    /// namespaced (p. ej. `sales.metrics.today`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub query: Option<String>,
    /// Params estáticos pasados a la `query` (opcional).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub params: Option<serde_json::Value>,
    /// Mapeo COLUMNA del resultado → prop del widget (`prop → nombreColumna`). Las props válidas
    /// dependen del `kind` (ver `architecture/hub/dashboard/widgets.md`). Permisivo aquí.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub map: Option<serde_json::Value>,
    /// Props LITERALES estáticas (label, icon, format, currency, …). El shell parte de `options`
    /// y luego sobreescribe con lo resuelto por `map` desde los datos.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub options: Option<serde_json::Value>,
    /// Escape hatch: custom element del propio módulo (de su `ui.entry`). Mutuamente excluyente
    /// con `kind`. El shell lo carga con la misma maquinaria que `provides_slots`/`module-loader`
    /// y el WC consulta sus datos vía el cliente del Hub.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub component: Option<String>,
}

/// Tamaño de un widget en la rejilla de 12 columnas del dashboard. `sm`=3, `md`=6, `lg`=8.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum WidgetSize {
    Sm,
    #[default]
    Md,
    Lg,
}

/// Tipo de render declarativo de un widget → componente OutfitKit que el shell construye.
/// Cada `kind` acepta un conjunto distinto de columnas en `map` y props en `options`
/// (contrato en `architecture/hub/dashboard/widgets.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum WidgetKind {
    /// `ok-kpi` — valor único con delta/trend.
    Kpi,
    /// `ok-stat` — valor único con label/severity.
    Stat,
    /// `ok-kpi`+`ok-sparkline` (o `ok-sparkline` suelto) — serie numérica por filas.
    Sparkline,
    /// `ok-bar-list` — lista label/valor.
    #[serde(rename = "bar-list")]
    BarList,
    /// `ok-timeline` — eventos cronológicos.
    Timeline,
    /// `ok-chart` — serie única (multi-serie → usar `component`).
    Chart,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct QueryDef {
    pub permission: String,
    pub sql: String,
    #[serde(default)]
    pub schema: Option<String>,
    /// Si está presente, la query es **paginada/lista**: el runtime envuelve el SELECT base
    /// como subconsulta y compone búsqueda + filtro por columna + orden (whitelist) +
    /// LIMIT/OFFSET, devolviendo `{rows,total,limit,offset}`. ARQUITECTURA.md §4, §8.2.
    #[serde(default)]
    pub list: Option<ListSpec>,
    /// Si está presente, expone esta query al asistente como tool (nivel 2). El permiso y el
    /// schema se heredan de la propia query, no se redeclaran. ARQUITECTURA.md §9.2.
    #[serde(default)]
    pub ai: Option<AiTool>,
    /// Opt-in: expone esta query en la **API pública REST/OpenAPI** por módulo (ADR-0057,
    /// `architecture/hub/public-api.md`). Doble puerta: además de este flag, la API key debe
    /// tener el `permission` de la query (lectura del módulo). Por defecto `false` → la query no
    /// es accesible vía API key aunque la key tuviera el permiso. El gate del runtime no cambia.
    #[serde(default)]
    pub expose_api: bool,
}

/// Contrato declarativo de una query de lista (`list` en `module.json`). Espejo de
/// `$defs/listSpec` en `schemas/module.schema.json`. El runtime lo consume en `queries.rs`
/// para componer el SQL paginado. ARQUITECTURA.md §4, §8.2.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ListSpec {
    /// Columnas sobre las que aplica el buscador global (LIKE).
    #[serde(default)]
    pub search: Vec<String>,
    /// Whitelist de columnas ordenables (anti-inyección: solo estas se interpolan en ORDER BY).
    #[serde(default)]
    pub sort: Vec<String>,
    /// Columna de orden por defecto (debe estar en `sort`).
    #[serde(default)]
    pub default_sort: Option<String>,
    /// Dirección por defecto (`asc`/`desc`).
    #[serde(default)]
    pub default_dir: Option<String>,
    /// Filtros por columna (orden determinista para SQL estable → `BTreeMap`).
    #[serde(default)]
    pub filters: std::collections::BTreeMap<String, FilterSpec>,
    /// Tamaño de página por defecto si el llamador no envía `limit`.
    #[serde(default = "default_page_size")]
    pub page_size: u64,
}

fn default_page_size() -> u64 {
    50
}

/// Operador de un filtro por columna.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct FilterSpec {
    pub op: FilterOp,
}

/// Tipos de filtro soportados. `eq`: igualdad. `like`: subcadena. `range`: rango (from/to).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FilterOp {
    Eq,
    Like,
    Range,
}

/// Bloque `ai` inline de una operación: la descripción legible (en inglés) que ve el LLM.
/// `permission`/`schema`/`sql` se heredan de la operación. ARQUITECTURA.md §9.2.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct AiTool {
    pub description: String,
    /// Nombre opcional que ve el LLM (por defecto, el nombre de la operación).
    #[serde(default)]
    pub name: Option<String>,
    /// **Cuánto daño hace esta operación** si el asistente la ejecuta (hub#1042).
    ///
    /// Lo DECLARA el módulo, y no se infiere del nombre a propósito: `delete` en un nombre no
    /// significa nada portable —`sales.void` es destructivo y no lo dice— y un core que lo
    /// adivinara estaría decidiendo por el módulo cuánto vale su propio dato. El módulo lo sabe.
    ///
    /// Ausente = `normal`: el bloque es opcional.
    ///
    /// Se lee con [`deserialize_risk`] y no con el `Deserialize` derivado, para que un valor
    /// fuera del vocabulario NO impida instalar el módulo.
    #[serde(default, deserialize_with = "deserialize_risk")]
    pub risk: Option<AiRisk>,
}

/// Vocabulario CERRADO de peligrosidad (hub#1042), como el `reason` de ADR-0331: cerrado para
/// que el core pueda aplicar una política sin conocer el dominio, y para que sea traducible.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AiRisk {
    /// Lo corriente: la tarjeta de confirmación de siempre.
    Normal,
    /// Borra o anula UN registro de forma que el usuario no puede deshacer solo.
    Destructive,
    /// Alcanza a un CONJUNTO cuyo tamaño el usuario no ve al confirmar.
    BulkDestructive,
    /// Un valor que este core no conoce — **nunca lo escribe un manifest**: lo produce la
    /// degradación de [`deserialize_risk`] cuando llega algo fuera del vocabulario.
    ///
    /// Se comporta como `destructive` en toda política: un riesgo que no entendemos no se trata
    /// como inofensivo.
    #[serde(skip)]
    Unknown,
}

/// Lee `ai.risk` SIN poder tumbar la instalación del módulo (hub#1042).
///
/// `erplora validate` comprueba las CLAVES del manifest, no los valores de un enum: un módulo con
/// `risk: "catastrophic"` pasa la puerta del autor y se publica. Si aquí se usara el
/// `Deserialize` derivado, ese valor haría fallar el parseo del manifest ENTERO y el módulo
/// dejaría de instalarse — con el fallo apareciendo en el hub de un cliente, no en el CI de quien
/// lo escribió. Es el modo de fallo que `module-toolkit/src/manifest-schema.mjs` documenta como
/// el peor de los dos.
///
/// Así que se degrada, y hacia el lado SEGURO: lo que no se entiende se trata como destructivo.
fn deserialize_risk<'de, D>(d: D) -> std::result::Result<Option<AiRisk>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    use serde::Deserialize as _;
    let raw = <Option<String> as serde::Deserialize>::deserialize(d)?;
    Ok(raw.map(|value| match value.as_str() {
        "normal" => AiRisk::Normal,
        "destructive" => AiRisk::Destructive,
        "bulk_destructive" => AiRisk::BulkDestructive,
        _ => AiRisk::Unknown,
    }))
}

impl AiRisk {
    /// El nombre que viaja al cliente. `Normal` se envía explícito, no ausente: «no lo declaró»
    /// y «lo declaró normal» tienen que verse igual desde fuera, o la política se vuelve
    /// dependiente de si alguien se acordó de escribirlo.
    pub fn as_str(self) -> &'static str {
        match self {
            AiRisk::Normal => "normal",
            AiRisk::Destructive => "destructive",
            AiRisk::BulkDestructive => "bulk_destructive",
            // Hacia fuera se presenta como destructivo: el cliente aplica la política estricta
            // sin tener que conocer una cuarta palabra.
            AiRisk::Unknown => "destructive",
        }
    }
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct CommandDef {
    pub permission: String,
    #[serde(default)]
    pub transaction: bool,
    #[serde(default)]
    pub sql: Vec<String>,
    /// Ruta (relativa a la carpeta del módulo) del JSON Schema del payload. Si está
    /// presente, el runtime valida el payload del llamador contra él ANTES de ejecutar
    /// (se compila una vez al instalar y se cachea en el `Registry`). §5.2, hub#27.
    #[serde(default)]
    pub schema: Option<String>,
    /// **Lecturas PRE-CARGADAS** que el runtime le entrega al handler antes de invocarlo
    /// (ADR-0069): nombres de query cuyas filas aterrizan en `context.reads["<query>"]`.
    ///
    /// Existe porque el handler WASM corre en un **sandbox** y no puede leer la BD. Sin esto, un
    /// handler solo sabe lo que le cuenta el cliente — y eso es exactamente cómo el navegador
    /// acababa decidiendo **el IVA que se le declara a la AEAT**: `sales.complete_sale` recibía el
    /// `tax_rate` de cada línea en el payload y se fiaba. Con `reads`, el handler resuelve el % del
    /// **catálogo de confianza del hub** (`taxes.rules.list`) y la pista del cliente pasa a ser solo
    /// un fallback.
    ///
    /// **Alcance**: queries del propio módulo o de los declarados en `depends_on`. Se gatea por la
    /// DEPENDENCIA, no por el permiso del usuario: el permiso del command ya se comprobó y las reads
    /// son contrato *vouched* por el autor del módulo (un empleado de POS sin `taxes.view_tax` igual
    /// necesita los tipos para cobrar). Una read que falle se **omite**: cobrar es lo último que
    /// puede romperse en un TPV.
    #[serde(default)]
    pub reads: Vec<ReadDef>,
    /// Events this command emits. See [`EmitDef`] for the two wire shapes (plain name, or an
    /// object naming `dedup_key`, hub#1076).
    #[serde(default)]
    pub emit: Vec<EmitDef>,
    /// **Contrato de mutación** (hub#140): mínimo de filas que la(s) sentencia(s) `sql` del
    /// command DEBEN afectar para que el command se considere exitoso y se emitan sus `emit`.
    /// Si el recuento real queda por debajo, la transacción se revierte entera y NO se escribe
    /// ningún evento en el outbox (ni notificación al WS) — porque el hecho declarado nunca ocurrió.
    ///
    /// - `None` (default, opt-in): la gate está **desactivada**. Comportamiento de siempre: el
    ///   command emite sus eventos tanto si muta 1 fila como 0. Así no rompemos los módulos ya
    ///   publicados ni los commands genuinamente idempotentes (`UPDATE … WHERE NOT EXISTS`).
    /// - `Some(n)`: exige `>= n` filas afectadas en TOTAL por las sentencias `sql` del command
    ///   (no cuenta los INSERT del outbox). `Some(1)` es el caso habitual de un command de
    ///   transición: "confirmar" / "anular" / "cerrar" que NO debe emitir su evento si el `WHERE`
    ///   no casa (recurso inexistente o ya en el estado destino). `Some(0)` declararía
    ///   explícitamente un no-op idempotente permitido que igual emite.
    ///
    /// **Solo sobre UNA sentencia** (hub#1091). Siendo un entero no tiene dónde nombrar la
    /// sentencia que porta la guarda, así que sobre un lote queda neutralizable sin cura: una
    /// sentencia incondicional hermana satisface el mínimo por la que falló y el caller recibe
    /// `200 ok` con un evento de un hecho que no ocurrió. El installer rechaza el manifest que lo
    /// declare con más de una `sql`; la guarda sobre una sentencia de un lote se declara con
    /// [`ExpectRows::statement`].
    ///
    /// Ver [`crate::commands`] para el gate y
    /// [`crate::errors::RuntimeError::MinAffectedRows`].
    #[serde(default)]
    pub min_affected_rows: Option<u64>,
    /// Declarative domain error based on affected rows (hub#139). The translatable, namespaced
    /// flavour of `min_affected_rows`; the two fields cannot coexist on one command (the
    /// installer rejects the manifest).
    #[serde(default)]
    pub expect_rows: Option<ExpectRows>,
    /// Handler de lógica: Tier 2 (WASM sandbox) o **plugin nativo first-party**
    /// (ADR-0009, crate horneado en el runtime). Si está presente, el command ejecuta
    /// el handler en vez de su `sql` directo. ARQUITECTURA.md §5.3.
    #[serde(default)]
    pub handler: Option<HandlerRef>,
    /// Si está presente, expone este command al asistente como tool (nivel 2). El permiso y el
    /// schema se heredan del propio command, no se redeclaran. ARQUITECTURA.md §9.2.
    #[serde(default)]
    pub ai: Option<AiTool>,
    /// Opt-in: expone este command en la **API pública REST/OpenAPI** por módulo (ADR-0057,
    /// `architecture/hub/public-api.md`). Doble puerta: además de este flag, la API key debe
    /// tener el `permission` del command (escritura del módulo). Por defecto `false` → el command
    /// no es accesible vía API key aunque la key tuviera el permiso. El gate del runtime no cambia.
    #[serde(default)]
    pub expose_api: bool,
    /// Marca este command como **INTERNO** (hub#131, hub#145): solo lo puede invocar el propio
    /// runtime (un listener del outbox entregado por el relay, una scheduled task del mismo
    /// módulo) — nunca un caller EXTERNO (HTTP `/api/command`, API pública de API keys,
    /// asistente/SDK). Aditivo al convenio legacy de prefijo `_` en el último segmento del nombre
    /// (`cash_register._reverse_sale`): un command internal puede DEMÁS no llevar `_`, para
    /// módulos que prefieren blindarlo explícitamente sin ese prefijo. Ver [`CommandDef::is_internal`].
    #[serde(default)]
    pub internal: bool,
}

impl CommandDef {
    /// ¿Es `self` (registrado bajo `name`, el nombre namespaced completo) un command INTERNO?
    /// Dos señales, aditivas — cualquiera de las dos basta (hub#131, hub#145):
    ///  1. `internal: true` explícito en el manifest.
    ///  2. El **último segmento** de `name` (tras el último `.`) empieza por `_` — el convenio
    ///     legacy que ya usan los listeners cross-módulo (`cash_register._reverse_sale`,
    ///     `inventory._restock_on_void`) sin tener que migrar manifests existentes.
    pub fn is_internal(&self, name: &str) -> bool {
        self.internal
            || name
                .rsplit('.')
                .next()
                .map(|last| last.starts_with('_'))
                .unwrap_or(false)
    }
}

/// Referencia al handler de un command. ARQUITECTURA.md §5.3, §9.2.
///
/// - `type: "wasm"` — Tier 2: fichero `.wasm` del módulo (`file`) + función exportada.
/// - `type: "native"` — plugin nativo first-party (ADR-0009): la función vive en un
///   crate Rust horneado en el runtime, registrado por `module_id` vía
///   [`crate::Runtime::register_native`]. No lleva `file`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct HandlerRef {
    /// Tipo de handler: `"wasm"` | `"native"`.
    #[serde(rename = "type")]
    pub kind: String,
    /// Ruta (relativa a la carpeta del módulo) del `.wasm`. Solo para `type: "wasm"`.
    #[serde(default)]
    pub file: Option<String>,
    /// Función del handler a invocar (exportada del guest WASM o del plugin nativo).
    pub function: String,
}

#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Events {
    #[serde(default)]
    pub listen: HashMap<String, Listener>,
    /// **El catálogo completo de eventos que el módulo emite** — los de sus commands declarativos
    /// y los que devuelven sus handlers (WASM/nativo).
    ///
    /// Nació (hub#240) como el allowlist de lo que un HANDLER puede encolar en el outbox: `emit`
    /// declaraba los de un command declarativo y los del handler no tenían dónde declararse, así
    /// que no se validaban contra nada — el handler elegía el nombre y el relay se lo entregaba a
    /// los listeners de otros módulos y al **listener-host de `host.notify`** (`*.reminder.due` →
    /// email/SMS/WhatsApp).
    ///
    /// hub#709 la ensancha a **catálogo**: el hub no tiene un registro central de eventos (se
    /// desincronizaría del código el primer día) — la lista de «cosas que pueden pasar en mi
    /// negocio» que ofrece el editor de flujos ES la agregación de este campo en los módulos
    /// instalados. Por eso un `emit` de command que no aparezca aquí queda REPORTADO en
    /// [`Manifest::warnings`] (aviso, no rechazo: ver `Manifest::undeclared_emit_warnings`).
    ///
    /// Declarar esta lista pone además al módulo en **modo estricto**: solo estos nombres (más los
    /// `emit` de sus commands) pueden salir de sus handlers. Un manifest que no la declara mantiene
    /// la compatibilidad con lo ya publicado, pero sigue sujeto a las dos reglas duras: no emitir
    /// en el namespace de otro módulo instalado y no emitir `*.reminder.due` sin la capability
    /// `notify`. Ver `commands::validate_handler_event`.
    #[serde(default)]
    pub emits: Vec<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Listener {
    pub command: String,
}

// ─── The manifest contract: what this core knows, and what it does about the rest (hub#521) ───
//
// `Manifest` deserialises WITHOUT `deny_unknown_fields` and with `#[serde(default)]` nearly
// everywhere, which is a deliberate tolerance — a hub must survive a manifest written for a newer
// core — but it was implemented as SILENCE: anything unknown was dropped with no error, no warning
// and no log. Twice already that silence shipped: `cash_register` carries a top-level `protects`
// block nothing reads, and seven commands of `inventory`/`services` declare a `validates` guard the
// runtime never runs (hub#610) — a manifest that reads as if it validates and does not.
//
// A blanket `deny_unknown_fields` is the wrong fix. The runtime is NOT the only reader of a
// `module.json`: the shell reads `ui`/`widgets`/`provides_slots`, the SaaS reads
// `billing`/`marketplace`/`compatibility`. "serde dropped it" and "nobody understands it" are
// different statements, and the same tolerance is load-bearing elsewhere on purpose (see
// `cloud-client::entitlement`, whose test REQUIRES an unknown claim to be ignored).
//
// So the contract is a list, and a severity that follows the blast radius:
//
//   · known here            → acted on, or deliberately left to the shell/SaaS. Silent.
//   · unknown, and it would change what RUNS or who may run it  → the install is REFUSED.
//   · unknown anywhere else → the module installs and the field is REPORTED (`warnings`).
//   · RETIRED              → a name we know to be dead. Installs, reported BY NAME with its issue.
//
// The lists below are the runtime half of the contract; `schemas/module.schema.json` is the
// authoring half, and `tests/manifest_fields_match_the_schema.rs` fails if the two ever disagree.

/// Blocks whose contents this core acts on. The `*` stands for "any key of the map" and `[]` for
/// "any item of the array"; the empty path is the root of the document.
const ROOT_FIELDS: &[&str] = &[
    "id",
    "name",
    "description",
    "icon",
    "version",
    "agent",
    "ai_context",
    "depends_on",
    "permissions",
    "roles",
    "role_permissions",
    "static_files",
    "navigation",
    "provides_slots",
    "migrations",
    "queries",
    "commands",
    "events",
    "widgets",
    "setup",
    "settings",
    "network",
    "notify",
    "capabilities",
    "fiscal_regime",
    "installation_bound_data",
    "scheduled_tasks",
    "ui",
    "marketplace",
    "billing",
    "seed",
    "compatibility",
    "protects",
    "records",
    "errors",
];

/// ADR-0398: one entry of the `errors` catalog carries only the code's state.
const ERROR_FIELDS: &[&str] = &["deprecated"];

const COMMAND_FIELDS: &[&str] = &[
    "permission",
    "transaction",
    "sql",
    "schema",
    "reads",
    "emit",
    "min_affected_rows",
    "expect_rows",
    "handler",
    "ai",
    "expose_api",
    "internal",
];

const QUERY_FIELDS: &[&str] = &["permission", "sql", "schema", "list", "ai", "expose_api"];
const EVENTS_FIELDS: &[&str] = &["listen", "emits"];
const LISTENER_FIELDS: &[&str] = &["command"];
const CAPABILITY_FIELDS: &[&str] = &[
    "network",
    "certificate",
    "printer",
    "notify",
    "manage_flows",
];
const DIALECT_FIELDS: &[&str] = &["sqlite", "postgres"];
const ROLE_FIELDS: &[&str] = &["key", "label", "extends"];
const SCHEDULED_TASK_FIELDS: &[&str] = &["name", "command", "cron", "payload", "catch_up"];
const NAV_FIELDS: &[&str] = &["id", "label", "icon", "component", "chrome", "permission"];
const PROTECTS_FIELDS: &[&str] = &[
    "settings_query",
    "enabled_setting",
    "route_setting",
    "guard_query",
    "expect",
    "component",
    "resume_on",
];
const WIDGET_FIELDS: &[&str] = &[
    "title",
    "icon",
    "category",
    "size",
    "permission",
    "sectors",
    "default",
    "refresh_on",
    "kind",
    "query",
    "params",
    "map",
    "options",
    "component",
];
const SETUP_FIELDS: &[&str] = &[
    "required",
    "query",
    "params",
    "configured_when",
    "title",
    "description",
    "icon",
    "route",
    "permission",
    "countries",
    "order",
];
const SETTINGS_FIELDS: &[&str] = &["title", "icon", "schema", "get", "set", "component"];
const AGENT_FIELDS: &[&str] = &["description", "keywords"];
const STATIC_FILES_FIELDS: &[&str] = &["folder", "user_actions"];
const COMPATIBILITY_FIELDS: &[&str] = &["min_erplora_version", "max_erplora_version"];
const RECORD_FIELDS: &[&str] = &["mutable", "reason", "correct_with", "update", "patch"];

/// The fields this core knows at `path`, or `None` if it judges nothing there.
///
/// Public because it is one half of a contract written twice: the other half is
/// `schemas/module.schema.json`, and the test that compares them is what stops the two from
/// drifting apart the way they already had (`compatibility` was read by the SaaS and forbidden by
/// both; `navigation[].actions` existed here and was forbidden there until hub#521 aligned them,
/// and hub#1237 retired the field from both because nothing ever rendered it).
pub fn known_fields(path: &str) -> Option<&'static [&'static str]> {
    Some(match path {
        "" => ROOT_FIELDS,
        "commands.*" => COMMAND_FIELDS,
        "queries.*" => QUERY_FIELDS,
        "events" => EVENTS_FIELDS,
        "events.listen.*" => LISTENER_FIELDS,
        "capabilities" => CAPABILITY_FIELDS,
        "migrations" | "seed" => DIALECT_FIELDS,
        "roles[]" => ROLE_FIELDS,
        "scheduled_tasks[]" => SCHEDULED_TASK_FIELDS,
        "navigation[]" => NAV_FIELDS,
        "protects[]" => PROTECTS_FIELDS,
        "widgets.*" => WIDGET_FIELDS,
        "setup" => SETUP_FIELDS,
        "settings" => SETTINGS_FIELDS,
        "agent" => AGENT_FIELDS,
        "static_files" => STATIC_FILES_FIELDS,
        "compatibility" => COMPATIBILITY_FIELDS,
        "records.*" => RECORD_FIELDS,
        "errors.*" => ERROR_FIELDS,
        _ => return None,
    })
}

/// Names this core has **retired**: this core once declared them, manifests already published may
/// carry them, and they do nothing.
///
/// Refusing them would be the consistent reading where the path refuses (`commands.*`) — and would
/// stop `inventory` and `services` from installing on hubs that already run them, with no way to
/// update an installed module (ADR-0269). So they install, reported by name and pointed at the
/// issue that decides their fate. Where the path only warns (`navigation[]`), the entry is what
/// turns a generic "this core does not read this field" into the sentence that says WHY it is
/// gone. Every entry is a debt with a number; the list is not a place to park a field to make a
/// warning go away (`tests/manifest_fields_match_the_schema.rs` asserts a retired name is never
/// also a known one, nor declared by `schemas/module.schema.json`).
pub const RETIRED_FIELDS: &[(&str, &str, &str)] = &[
    (
        "commands.*",
        "validates",
        "declared by published commands of `inventory` and NEVER implemented by the runtime \
         (hub#610): the validation it describes does NOT run — use `reads` + `expect_rows`",
    ),
    (
        "navigation[]",
        "actions",
        "topbar actions of ADR-0048 «level 2», RETIRED by hub#1237: the shell never painted them \
         and `/api/navigation` never served them, so no `module-action` event ever reached a Web \
         Component — declare the button inside your own component instead",
    ),
];

/// Where an unknown field is refused rather than reported.
///
/// The line is what the misunderstanding costs. Inside an operation or a gate, ignoring a field
/// means running a command without a guard its author declared, migrating without knowing what the
/// migration does, or subscribing an event that will never fire — the module would be WRONG, not
/// merely smaller. Everywhere else the cost is a screen, a button or a checklist item, and
/// bricking a till over a tab that does not render is the wrong trade for a point of sale.
fn refuses_unknown_fields(path: &str) -> bool {
    matches!(
        path,
        "commands.*"
            | "queries.*"
            | "events"
            | "events.listen.*"
            | "capabilities"
            | "migrations"
            | "seed"
            | "roles[]"
            | "scheduled_tasks[]"
            // hub#632: a record entry decides whether the dispatcher runs a read-merge before an
            // update — ignoring a field here would change what executes, the refuse tier.
            | "records.*"
    )
}

/// Reads a version as a comparable triple. A pre-release/build suffix is dropped (`1.2.3-rc1`
/// floors at `1.2.3`) and missing components read as zero (`2` = `2.0.0`): this compares a FLOOR,
/// so being generous about the shape is right, while a fourth component or a non-numeric one is
/// not a version anybody released and returns `None`.
pub(crate) fn version_triple(value: &str) -> Option<(u64, u64, u64)> {
    let core = value.trim().split(['-', '+']).next()?;
    let mut parts = core.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next().unwrap_or("0").parse().ok()?;
    let patch = parts.next().unwrap_or("0").parse().ok()?;
    parts.next().is_none().then_some((major, minor, patch))
}

impl Manifest {
    /// Lee y parsea `<dir>/module.json`, y **audita lo que no entiende** (hub#521).
    ///
    /// Three ways this returns `Err`, and all three used to be silence:
    ///
    /// 1. the JSON does not parse, or a field it declares has the wrong type (as before);
    /// 2. the module declares a core floor this hub is below
    ///    ([`RuntimeError::CoreVersionTooOld`]) — checked FIRST, because "your terminal is too
    ///    old" is the actionable sentence and every unknown block below it is a symptom of it;
    /// 3. it declares a field this core does not understand, where not understanding it changes
    ///    what runs ([`RuntimeError::ManifestUnknownField`]).
    ///
    /// Everything else unknown lands in [`Manifest::warnings`] and the module installs.
    ///
    /// The audit reads the document a second time as a raw `Value` on purpose: `Manifest` is what
    /// SURVIVED serde, so it cannot answer what serde dropped. Parsing twice also means the typed
    /// error above keeps its exact line/column, which a `from_value` round-trip would lose.
    pub fn load(dir: &Path) -> Result<Manifest> {
        let path = dir.join("module.json");
        let text = std::fs::read_to_string(&path)?;
        let to_err = |source| RuntimeError::Manifest {
            path: path.display().to_string(),
            source,
        };
        let mut manifest: Manifest = serde_json::from_str(&text).map_err(to_err)?;
        let raw: serde_json::Value = serde_json::from_str(&text).map_err(to_err)?;
        manifest.require_core_version()?;
        let mut warnings = manifest.audit(&raw)?;
        // hub#709: and the same channel for a manifest this core understands PERFECTLY but that
        // does not declare what it emits. It is not an unknown field — it is a hole in the event
        // catalogue the whole hub is built out of. See `undeclared_emit_warnings`.
        warnings.extend(manifest.undeclared_emit_warnings());
        manifest.warnings = warnings;
        Ok(manifest)
    }

    /// Refuses a module whose declared core floor is above this hub (hub#521).
    ///
    /// No floor = runs anywhere, which is the shape of every published manifest and stays valid.
    /// A floor this core cannot even parse is refused too, in the same direction as
    /// [`Manifest::sold_under`]: a claim the runtime cannot check is not read as "fine".
    fn require_core_version(&self) -> Result<()> {
        let Some(required) = self
            .compatibility
            .as_ref()
            .and_then(|c| c.min_erplora_version.as_deref())
        else {
            return Ok(());
        };
        let Some(floor) = version_triple(required) else {
            return Err(RuntimeError::ManifestCoreFloorUnreadable {
                module: self.id.clone(),
                declared: required.to_string(),
            });
        };
        // `CORE_VERSION` comes from `[workspace.package]` and the release CI writes it from the
        // tag, so it is a real semver; an unreadable one would be a build that lies about itself,
        // and refusing every module then would be worse than trusting the manifest.
        match version_triple(CORE_VERSION) {
            Some(core) if core < floor => Err(RuntimeError::CoreVersionTooOld {
                module: self.id.clone(),
                required: required.to_string(),
                core: CORE_VERSION.to_string(),
            }),
            _ => Ok(()),
        }
    }

    /// Walks the raw document against [`known_fields`], refusing at the first field that would
    /// change what runs and collecting the rest as [`ManifestWarning`]s.
    ///
    /// Only the blocks this core acts on are walked. `ui`, `marketplace`, `billing`, `ai_context`
    /// and `provides_slots` are recognised at the root and their CONTENTS are left alone on
    /// purpose: they belong to the shell and to the SaaS, and a runtime that has never read a
    /// field has no business ruling on it.
    fn audit(&self, raw: &serde_json::Value) -> Result<Vec<ManifestWarning>> {
        let Some(root) = raw.as_object() else {
            return Ok(Vec::new());
        };
        let mut warnings = Vec::new();
        self.check(raw, "", "", &mut warnings)?;

        for (block, table) in [
            ("commands", "commands.*"),
            ("queries", "queries.*"),
            ("widgets", "widgets.*"),
            ("records", "records.*"),
            ("errors", "errors.*"),
        ] {
            if let Some(entries) = root.get(block).and_then(|v| v.as_object()) {
                for (name, entry) in entries {
                    self.check(entry, table, &format!("{block}.{name}"), &mut warnings)?;
                }
            }
        }
        for block in [
            "events",
            "capabilities",
            "migrations",
            "seed",
            "setup",
            "settings",
            "agent",
            "static_files",
            "compatibility",
        ] {
            if let Some(entry) = root.get(block) {
                self.check(entry, block, block, &mut warnings)?;
            }
        }
        if let Some(listeners) = raw.pointer("/events/listen").and_then(|v| v.as_object()) {
            for (event, listener) in listeners {
                let at = format!("events.listen.{event}");
                self.check(listener, "events.listen.*", &at, &mut warnings)?;
            }
        }
        for (block, table) in [
            ("roles", "roles[]"),
            ("scheduled_tasks", "scheduled_tasks[]"),
            ("navigation", "navigation[]"),
            ("protects", "protects[]"),
        ] {
            if let Some(items) = root.get(block).and_then(|v| v.as_array()) {
                for (i, item) in items.iter().enumerate() {
                    self.check(item, table, &format!("{block}[{i}]"), &mut warnings)?;
                }
            }
        }
        Ok(warnings)
    }

    /// Judges ONE object against the table for `table_path`, reporting under `at` (the dotted path
    /// a human can find in the file). A non-object is left to serde, which already refused it.
    fn check(
        &self,
        value: &serde_json::Value,
        table_path: &str,
        at: &str,
        warnings: &mut Vec<ManifestWarning>,
    ) -> Result<()> {
        let (Some(entries), Some(known)) = (value.as_object(), known_fields(table_path)) else {
            return Ok(());
        };
        for field in entries.keys() {
            if known.contains(&field.as_str()) {
                continue;
            }
            let path = if at.is_empty() {
                field.clone()
            } else {
                format!("{at}.{field}")
            };
            if let Some((_, _, why)) = RETIRED_FIELDS
                .iter()
                .find(|(p, name, _)| *p == table_path && name == field)
            {
                warnings.push(ManifestWarning {
                    path,
                    detail: (*why).to_string(),
                });
                continue;
            }
            if refuses_unknown_fields(table_path) {
                return Err(RuntimeError::ManifestUnknownField {
                    module: self.id.clone(),
                    path,
                    core: CORE_VERSION.to_string(),
                });
            }
            warnings.push(ManifestWarning {
                path,
                detail: format!(
                    "this hub's core (v{CORE_VERSION}) does not read this field: whatever it \
                     declares has no effect here"
                ),
            });
        }
        Ok(())
    }

    /// The PRODUCER side of the event contract (hub#709): every event a command declares in
    /// `emit` has to be listed in `events.emits`.
    ///
    /// # Why it exists
    ///
    /// `installer::validate_event_listeners` (hub#659) already forces the CONSUMER to declare
    /// well. Nothing forced the producer, and the result was not a rough edge: `sale.completed` —
    /// the hub's central event, emitted on every sale and listened to by `inventory`, `customers`,
    /// `cash_register`, `invoice` and `tables` — was declared in NO place the runtime could read.
    /// The catalogue of "things that can happen in my business" that the flow editor offers the
    /// owner is the aggregation of what every installed module declares in its own manifest (it is
    /// not a central registry — that would drift from the code on day one), so a module that keeps
    /// quiet does not appear in it at all.
    ///
    /// # Why a WARNING and not a refusal
    ///
    /// ADR-0286 (hub#521) settled the tier by the RADIUS OF THE DAMAGE: what changes what RUNS or
    /// who may run it is refused; what costs a screen, a button or a checklist item installs and
    /// is REPORTED. An undeclared emit is squarely the second: the event still leaves (a
    /// declarative `emit` goes into the outbox without passing through
    /// [`crate::commands::validate_handler_event`], which only judges what a HANDLER returns), the
    /// listeners still receive it, and nothing about permissions changes. What is lost is a line
    /// in a catalogue.
    ///
    /// And the enforcement would cost far more than the mistake: `Manifest::load` is also the door
    /// the boot scan re-registers every INSTALLED module through, so refusing here would make a
    /// module that has been running for months VANISH from a till over a missing line — with no
    /// way to update it out of trouble (ADR-0269). Better a warning that travels in
    /// `/api/modules` than a POS that stops.
    ///
    /// The warning is per EVENT, not per emit: two commands emitting the same undeclared name is
    /// one hole in the catalogue. Sorted by event name because `commands` is a `HashMap` and a
    /// warning that reshuffles on every boot is one nobody can diff.
    fn undeclared_emit_warnings(&self) -> Vec<ManifestWarning> {
        let declared: HashSet<&str> = self.events.emits.iter().map(String::as_str).collect();
        let mut by_event: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
        for (name, command) in &self.commands {
            for event in &command.emit {
                if declared.contains(event.event()) {
                    continue;
                }
                by_event
                    .entry(event.event())
                    .or_default()
                    .insert(name.as_str());
            }
        }
        by_event
            .into_iter()
            .map(|(event, commands)| {
                let commands = commands
                    .into_iter()
                    .map(|c| format!("`{c}`"))
                    .collect::<Vec<_>>()
                    .join(", ");
                ManifestWarning {
                    path: "events.emits".to_string(),
                    detail: format!(
                        "`{event}` is emitted by {commands} and is not declared in \
                         `events.emits`: the hub's event catalogue is the aggregation of what \
                         each installed module declares, so nothing can be built to react to it"
                    ),
                }
            })
            .collect()
    }

    /// Carga las traducciones del módulo desde `<dir>/locales/*.json` → `lang → ModuleLocale`
    /// (ADR-0055). Best-effort: si no hay carpeta o un fichero está roto, se omite (un locale
    /// inválido NUNCA rompe la instalación; siempre queda el fallback al manifest).
    pub fn load_locales(dir: &Path) -> HashMap<String, ModuleLocale> {
        let mut out: HashMap<String, ModuleLocale> = HashMap::new();
        let Ok(entries) = std::fs::read_dir(dir.join("locales")) else {
            return out;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            let Some(lang) = path.file_stem().and_then(|s| s.to_str()) else {
                continue;
            };
            if let Ok(text) = std::fs::read_to_string(&path) {
                if let Ok(loc) = serde_json::from_str::<ModuleLocale>(&text) {
                    out.insert(lang.to_string(), loc);
                }
            }
        }
        out
    }
}

/// Catálogo de traducciones de un módulo para UN idioma (`locales/<lang>.json`, ADR-0055). El
/// runtime resuelve `name`, `navigation[].label` y `setup.{title,description}`; el bloque `ui` lo
/// consume el Web Component (lo hornea el toolkit en el `dist`), por eso aquí se ignora.
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct ModuleLocale {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub navigation: HashMap<String, NavLocale>,
    /// Checklist item copy (ADR-0055, hub#762): the translation of the module's `setup.title` /
    /// `setup.description`. The manifest values stay as the English-canonical fallback
    /// (`locale → en → manifest`).
    #[serde(default)]
    pub setup: SetupLocale,
}

/// Translation of a module's `setup` block (`locales/<lang>.json`, ADR-0055, hub#762).
///
/// Mirrors [`SetupDef::title`] / [`SetupDef::description`]: both are optional, so a module that
/// ships only the translated title still resolves it and falls back to the manifest for the rest.
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct SetupLocale {
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
}

/// Traducción de una entrada de navegación (`navigation.<id>` en el locale del módulo).
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct NavLocale {
    #[serde(default)]
    pub label: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Un `risk` fuera del vocabulario NO puede impedir que el módulo se instale (hub#1042).
    ///
    /// `erplora validate` comprueba las CLAVES del manifest, no los valores del enum: un módulo
    /// con `risk: "catastrophic"` pasa la puerta del autor y se publica. Si el runtime se negara a
    /// parsearlo, el módulo entero dejaría de instalarse —y el fallo aparecería en el hub de un
    /// cliente, no en el CI de quien lo escribió. Es exactamente el modo de fallo que el toolkit
    /// documenta como el peor de los dos.
    ///
    /// Así que se degrada, y se degrada HACIA EL LADO SEGURO: un riesgo que no entendemos se
    /// trata como destructivo, no como normal. Y se deja dicho en `warnings`, que es el canal que
    /// el manifest ya tiene para «esto no lo entendí y seguí».
    #[test]
    fn an_unknown_risk_degrades_to_destructive_instead_of_bricking_the_install() {
        let raw = r#"{"id":"x","name":"X","version":"1.0.0",
          "commands":{"x.wipe":{"permission":"x.d","ai":{"description":"d","risk":"catastrophic"}}}}"#;

        let manifest: Manifest = serde_json::from_str(raw).expect("el módulo TIENE que instalarse");

        let ai = manifest.commands["x.wipe"].ai.as_ref().expect("bloque ai");
        assert_eq!(
            ai.risk.map(AiRisk::as_str),
            Some("destructive"),
            "un riesgo desconocido se trata como destructivo: fallar hacia el lado seguro"
        );
    }

    /// El vocabulario conocido sigue leyéndose tal cual.
    #[test]
    fn the_declared_vocabulary_is_read_as_declared() {
        for (raw, expected) in [
            ("normal", AiRisk::Normal),
            ("destructive", AiRisk::Destructive),
            ("bulk_destructive", AiRisk::BulkDestructive),
        ] {
            let json = format!(
                r#"{{"id":"x","name":"X","version":"1.0.0",
                   "commands":{{"x.op":{{"permission":"p","ai":{{"description":"d","risk":"{raw}"}}}}}}}}"#
            );
            let m: Manifest = serde_json::from_str(&json).expect("parsea");
            assert_eq!(
                m.commands["x.op"].ai.as_ref().unwrap().risk,
                Some(expected),
                "{raw}"
            );
        }
    }

    /// Sin declarar sigue siendo «sin declarar», que el ensamblado traduce a `normal`.
    #[test]
    fn an_undeclared_risk_stays_undeclared() {
        let raw = r#"{"id":"x","name":"X","version":"1.0.0",
          "commands":{"x.op":{"permission":"p","ai":{"description":"d"}}}}"#;
        let m: Manifest = serde_json::from_str(raw).expect("parsea");
        assert_eq!(m.commands["x.op"].ai.as_ref().unwrap().risk, None);
    }
    use super::*;

    /// hub#380 — «my data belongs to the installation that produced it» is something the MODULE
    /// says, not something the core knows by name.
    ///
    /// The import engine used to compare the section against the literal `modules/verifactu`: a
    /// Spanish regime hard-coded into a generic engine, which would have needed one more `||` for
    /// TicketBai and another for NF525. The module declares it here instead.
    #[test]
    fn a_module_declares_that_its_data_is_bound_to_its_installation() {
        let bound: Manifest = serde_json::from_str(
            r#"{
            "id": "verifactu",
            "name": "VeriFactu",
            "version": "1.2.3",
            "installation_bound_data": true
        }"#,
        )
        .expect("manifest parses");
        assert!(bound.installation_bound_data);
    }

    /// Absent = portable, which is the shape of EVERY published manifest: adding the field must
    /// not change what any of them means today.
    #[test]
    fn a_module_that_says_nothing_carries_portable_data() {
        let plain: Manifest = serde_json::from_str(
            r#"{ "id": "inventory", "name": "Inventory", "version": "1.0.0" }"#,
        )
        .expect("manifest parses");
        assert!(!plain.installation_bound_data);
    }

    #[test]
    fn parses_module_static_files_folder() {
        let json = r#"{
            "id": "verifactu",
            "name": "VeriFactu",
            "version": "1.2.3",
            "static_files": { "folder": "verifactu" }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert_eq!(storage.folder, "verifactu");
    }

    /// Lo que el USUARIO puede hacer desde `/files` con los ficheros de un módulo (ADR-0172).
    /// Por defecto: solo ver y descargar. El módulo tiene que pedir explícitamente lo demás.
    /// (El propio módulo sigue escribiendo por `ModuleStorage`: esto no le limita a él.)
    #[test]
    fn static_files_are_read_only_for_the_user_unless_the_module_opts_in() {
        let json = r#"{
            "id": "verifactu",
            "name": "VeriFactu",
            "version": "1.2.3",
            "static_files": { "folder": "verifactu" }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert!(
            storage.user_actions.is_empty(),
            "el default es solo-lectura"
        );
        assert!(!storage.allows(UserFileAction::Delete));
        assert!(!storage.allows(UserFileAction::Rename));
        assert!(!storage.allows(UserFileAction::Upload));
    }

    #[test]
    fn a_module_can_open_up_its_folder_action_by_action() {
        let json = r#"{
            "id": "scans",
            "name": "Scans",
            "version": "1.0.0",
            "static_files": { "folder": "scans", "user_actions": ["upload", "delete"] }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert!(storage.allows(UserFileAction::Upload));
        assert!(storage.allows(UserFileAction::Delete));
        // Lo que no se pide, no se concede.
        assert!(!storage.allows(UserFileAction::Rename));
    }

    /// Un manifest con una acción desconocida no debe "colar" como si fuese válida ni tumbar la
    /// instalación entera: se ignora lo que el host no entiende (compatibilidad hacia adelante).
    #[test]
    fn unknown_user_actions_are_ignored_not_granted() {
        let json = r#"{
            "id": "scans",
            "name": "Scans",
            "version": "1.0.0",
            "static_files": { "folder": "scans", "user_actions": ["delete", "encrypt"] }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let storage = manifest.static_files.expect("static_files present");
        assert!(storage.allows(UserFileAction::Delete));
        assert!(!storage.allows(UserFileAction::Rename));
    }

    /// Parsea un manifest con un bloque `widgets` (uno por la vía declarativa `kind`+`query` y
    /// uno por el escape hatch `component`) y verifica que se deserializa y RE-SERIALIZA sin
    /// perder campos (ADR-0054).
    #[test]
    fn parses_and_roundtrips_widgets_block() {
        let json = r#"{
            "id": "sales",
            "name": "Sales",
            "version": "1.2.3",
            "queries": {
                "sales.metrics.today": { "permission": "sales.read", "sql": "SELECT 1" }
            },
            "widgets": {
                "sales.today": {
                    "title": "Ventas de hoy",
                    "icon": "trending-up-outline",
                    "category": "Ventas",
                    "size": "md",
                    "permission": "sales.read",
                    "sectors": ["hosteleria", "retail"],
                    "default": true,
                    "kind": "kpi",
                    "query": "sales.metrics.today",
                    "params": { "period": "day" },
                    "map": { "value": "total", "delta": "delta_pct", "trend": "trend" },
                    "options": { "label": "Hoy", "format": "currency", "currency": "EUR" },
                    "refresh_on": ["sale.completed", "sale.voided"]
                },
                "sales.live_feed": {
                    "title": "Actividad en vivo",
                    "size": "lg",
                    "component": "erp-sales-live-feed"
                }
            }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        assert_eq!(manifest.widgets.len(), 2);

        let kpi = manifest
            .widgets
            .get("sales.today")
            .expect("kpi widget present");
        assert_eq!(kpi.title, "Ventas de hoy");
        assert_eq!(kpi.size, WidgetSize::Md);
        assert_eq!(kpi.kind, Some(WidgetKind::Kpi));
        assert_eq!(kpi.query.as_deref(), Some("sales.metrics.today"));
        assert!(kpi.default);
        assert_eq!(
            kpi.sectors,
            vec!["hosteleria".to_string(), "retail".to_string()]
        );
        assert_eq!(
            kpi.refresh_on,
            vec!["sale.completed".to_string(), "sale.voided".to_string()]
        );
        assert!(kpi.component.is_none());
        assert!(kpi.options.is_some());
        assert!(kpi.map.is_some());

        let custom = manifest
            .widgets
            .get("sales.live_feed")
            .expect("component widget present");
        assert_eq!(custom.size, WidgetSize::Lg);
        assert_eq!(custom.component.as_deref(), Some("erp-sales-live-feed"));
        assert!(custom.kind.is_none());
        assert!(custom.query.is_none());

        // Re-serializa y vuelve a parsear: ningún campo del contrato se pierde en el round-trip.
        let serialized = serde_json::to_value(&manifest.widgets).expect("widgets serialize");
        let kpi_json = &serialized["sales.today"];
        assert_eq!(kpi_json["title"], "Ventas de hoy");
        assert_eq!(kpi_json["kind"], "kpi");
        assert_eq!(kpi_json["size"], "md");
        assert_eq!(kpi_json["query"], "sales.metrics.today");
        assert_eq!(kpi_json["default"], true);
        assert_eq!(kpi_json["sectors"][0], "hosteleria");
        assert_eq!(kpi_json["options"]["currency"], "EUR");
        assert_eq!(kpi_json["map"]["value"], "total");
        // El refresco en vivo (refresh_on, ADR-0054 T1) sobrevive el round-trip: sin el campo en
        // el struct, serde lo DESCARTA en silencio y este assert cae (Null != "sale.completed").
        assert_eq!(kpi_json["refresh_on"][0], "sale.completed");
        assert_eq!(kpi_json["refresh_on"][1], "sale.voided");

        let custom_json = &serialized["sales.live_feed"];
        assert_eq!(custom_json["component"], "erp-sales-live-feed");
        assert_eq!(custom_json["size"], "lg");
        // `bar-list` se serializa con su rename, no como `barlist`.
        assert_eq!(
            serde_json::to_value(WidgetKind::BarList).unwrap(),
            serde_json::Value::String("bar-list".to_string())
        );
    }

    /// hub#351 (paso 2b): a module declares its own business roles on top of the frozen base
    /// catalogue. The three fields land verbatim; `extends` says which base role it hangs from.
    #[test]
    fn parses_the_declared_roles_block() {
        let json = r#"{
            "id": "kitchen",
            "name": "Kitchen",
            "version": "2.3.1",
            "roles": [
                { "key": "kitchen", "label": "Kitchen", "extends": "employee" },
                { "key": "shift_lead", "label": "Shift lead", "extends": "manager" }
            ],
            "role_permissions": {
                "kitchen": ["kitchen.view_ticket", "kitchen.bump_ticket"]
            }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        assert_eq!(manifest.roles.len(), 2);
        assert_eq!(manifest.roles[0].key, "kitchen");
        assert_eq!(manifest.roles[0].label, "Kitchen");
        assert_eq!(manifest.roles[0].extends, "employee");
        assert_eq!(manifest.roles[1].key, "shift_lead");
        assert_eq!(manifest.roles[1].extends, "manager");
        // The block is additive: `role_permissions` keeps working exactly as before, and may now
        // grant to a declared key as well as to the three base ones.
        assert_eq!(manifest.role_permissions["kitchen"].len(), 2);
    }

    /// The ~24 published modules do NOT carry a `roles` block, and adding the field must not make
    /// a single one of them unparseable: absent = the module declares no role of its own.
    #[test]
    fn a_manifest_without_the_roles_block_declares_none() {
        let json = r#"{
            "id": "inventory",
            "name": "Inventory",
            "version": "1.0.0",
            "role_permissions": {
                "admin": ["*"],
                "manager": ["inventory.view_product"],
                "employee": ["inventory.view_product"]
            }
        }"#;

        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        assert!(
            manifest.roles.is_empty(),
            "no `roles` block = no declared role, never a parse error"
        );
        assert_eq!(manifest.role_permissions.len(), 3);
    }

    /// A role is `key` + `label` + `extends`, the three of them: the struct mirrors the `required`
    /// of `schemas/module.schema.json`, so a half-declared role never reaches the validation — it
    /// dies at parse time with an error that names the missing field.
    #[test]
    fn a_role_missing_one_of_its_three_fields_does_not_parse() {
        let json = r#"{
            "id": "kitchen",
            "name": "Kitchen",
            "version": "2.3.1",
            "roles": [{ "key": "kitchen", "extends": "employee" }]
        }"#;

        let error = serde_json::from_str::<Manifest>(json)
            .expect_err("a role without `label` is not a role")
            .to_string();
        assert!(
            error.contains("label"),
            "the error must name the missing field: {error}"
        );
    }

    /// hub#131/#145: `internal: true` parsea (aditivo, opcional) y `is_internal()` lo detecta
    /// aunque el nombre del command NO lleve prefijo `_`.
    #[test]
    fn command_internal_flag_parses_and_is_internal_true_without_underscore() {
        let json = r#"{
            "id": "pricing",
            "name": "Pricing",
            "version": "1.0.0",
            "commands": {
                "pricing.reindex_catalog": {
                    "permission": "pricing.write",
                    "sql": ["UPDATE x SET y = 1"],
                    "internal": true
                }
            }
        }"#;
        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");
        let cmd = &manifest.commands["pricing.reindex_catalog"];
        assert!(cmd.internal, "`internal: true` debe parsear a true");
        assert!(
            cmd.is_internal("pricing.reindex_catalog"),
            "internal:true → is_internal() aunque el nombre no lleve `_`"
        );
    }

    /// Un manifest legacy que NO declara `internal` sigue considerando interno un command cuyo
    /// ÚLTIMO segmento namespaced empieza por `_` (convenio ya en uso: `cash_register._reverse_sale`),
    /// y NO interno el resto — el campo por defecto es `false` (aditivo, no rompe manifests viejos).
    #[test]
    fn command_internal_defaults_false_and_underscore_suffix_is_internal_by_convention() {
        let json = r#"{
            "id": "cash_register",
            "name": "Cash register",
            "version": "1.0.0",
            "commands": {
                "cash_register._reverse_sale": {
                    "permission": "cash_register.write",
                    "sql": ["UPDATE x SET y = 1"]
                },
                "cash_register.movement.add": {
                    "permission": "cash_register.write",
                    "sql": ["INSERT INTO x VALUES (1)"]
                }
            }
        }"#;
        let manifest: Manifest = serde_json::from_str(json).expect("manifest parses");

        let internal_cmd = &manifest.commands["cash_register._reverse_sale"];
        assert!(
            !internal_cmd.internal,
            "el campo `internal` no se declaró: default false"
        );
        assert!(
            internal_cmd.is_internal("cash_register._reverse_sale"),
            "el último segmento empieza por `_` → interno por convención, sin migrar el manifest"
        );

        let public_cmd = &manifest.commands["cash_register.movement.add"];
        assert!(
            !public_cmd.is_internal("cash_register.movement.add"),
            "sin prefijo `_` ni `internal:true` → NO es interno"
        );
    }

    // ── `billing`: the one question the runtime asks about it (ADR-0273 D7, hub#559) ───────────

    /// A manifest carrying `billing`, or none at all when `terms` is `null`.
    fn with_billing(terms: serde_json::Value) -> Manifest {
        let mut manifest = serde_json::json!({ "id": "m", "name": "M", "version": "1.0.0" });
        if !terms.is_null() {
            manifest["billing"] = terms;
        }
        serde_json::from_value(manifest).expect("manifest parses")
    }

    /// **23 of the 24 published manifests carry no `billing` block**, and no fiscal provider ships
    /// one today. Absence is free, which is what keeps this rule inert until somebody changes a
    /// price.
    #[test]
    fn a_manifest_with_no_billing_block_is_free() {
        assert_eq!(with_billing(serde_json::Value::Null).sold_under(), None);
        assert_eq!(with_billing(serde_json::json!({})).sold_under(), None);
    }

    /// The explicitly-free shapes. `type: subscription` with `price: 0` is how a manifest says
    /// "free, and renewed": the type alone never sells.
    #[test]
    fn a_zero_price_is_free_however_it_is_written() {
        for terms in [
            serde_json::json!({ "tier": "free" }),
            serde_json::json!({ "tier": "free", "type": "free" }),
            serde_json::json!({ "type": "subscription", "price": 0 }),
            serde_json::json!({ "type": "subscription", "price": 0, "interval": "month" }),
            serde_json::json!({ "tiers": [{ "slug": "free", "name": "Free", "price": 0 }] }),
        ] {
            assert_eq!(
                with_billing(terms.clone()).sold_under(),
                None,
                "{terms} declares no money"
            );
        }
    }

    /// The paid shapes — the same three the SaaS's `_manifest_declares_paid` reads (ADR-0105), so a
    /// hub and the marketplace cannot disagree about whether a module is free.
    #[test]
    fn a_module_is_sold_by_premium_tier_by_price_or_by_any_paid_tier() {
        for terms in [
            // Monetised by definition, price not filled in yet (ADR-0006/ADR-0032).
            serde_json::json!({ "tier": "premium" }),
            serde_json::json!({ "type": "subscription", "price": 9.99 }),
            serde_json::json!({ "type": "one_time", "price": 49.99 }),
            // A free tier next to a paid one is a paid module — the `whatsapp_inbox` shape.
            serde_json::json!({ "tiers": [
                { "slug": "free", "name": "Free", "price": 0 },
                { "slug": "starter", "name": "Starter", "price": 14.99 }
            ] }),
        ] {
            assert!(
                with_billing(terms.clone()).sold_under().is_some(),
                "{terms} prices the module"
            );
        }
    }

    /// **A block nobody can read counts as SOLD**, never as free — the same direction as
    /// `FiscalStatus::parse`, where an unreadable row must not be read as "owes nothing". The only
    /// module this is ever asked about is the one a hub's legal compliance would hang from.
    #[test]
    fn an_unreadable_billing_block_is_not_read_as_free() {
        for terms in [
            serde_json::json!("gratis"),
            serde_json::json!({ "type": "subscription", "price": "9.99" }),
            serde_json::json!({ "tier": 1 }),
            serde_json::json!({ "tiers": [{ "slug": "starter", "price": "14.99" }] }),
        ] {
            assert!(
                with_billing(terms.clone()).sold_under().is_some(),
                "{terms} makes a commercial claim the runtime cannot check"
            );
        }
    }

    /// The block keeps being **captured verbatim**: an unknown or oddly-typed field inside it does
    /// not stop the manifest from loading, because that is how every published module behaves today
    /// and turning `billing` into a typed struct would have broken them.
    #[test]
    fn an_odd_billing_block_never_stops_a_manifest_from_loading() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"id":"m","name":"M","version":"1.0.0",
                "billing":{"price":"nine","undocumented":{"deep":[1,2]},"tiers":"none"}}"#,
        )
        .expect("an odd `billing` block must not break `Manifest::load`");
        assert!(manifest.billing.is_some());
    }

    /// hub#521 — how a declared core floor is compared.
    ///
    /// It is a FLOOR, so the reading is deliberately generous about shape: a shorthand (`2`) and a
    /// pre-release suffix (`1.2.3-rc1`) both name a real point on the line. What is not generous is
    /// what happens to something that is NOT a version — see the test below.
    #[test]
    fn a_core_floor_is_read_as_a_semver_triple() {
        assert_eq!(version_triple("1.2.3"), Some((1, 2, 3)));
        assert_eq!(version_triple(" 1.2.3 "), Some((1, 2, 3)));
        // Shorthand: a floor of "2" means 2.0.0, not "anything starting with 2".
        assert_eq!(version_triple("2"), Some((2, 0, 0)));
        assert_eq!(version_triple("2.1"), Some((2, 1, 0)));
        // A pre-release floors at its release: `1.2.3-rc1` requires at least 1.2.3.
        assert_eq!(version_triple("1.2.3-rc1"), Some((1, 2, 3)));
        assert_eq!(version_triple("1.2.3+build.7"), Some((1, 2, 3)));
        // Ordering is numeric, not lexicographic — the trap `"10" < "9"` as text.
        assert!(version_triple("1.10.0") > version_triple("1.9.0"));
        // Not versions.
        for bad in ["", "latest", "v1.2.3", "1.2.3.4", "1.x", "-1.0.0"] {
            assert_eq!(version_triple(bad), None, "{bad:?} is not a version");
        }
    }

    /// A floor this hub cannot compare against is REFUSED, not waved through.
    ///
    /// Same direction as [`Manifest::sold_under`]: a claim the runtime cannot check must not be
    /// read as the permissive answer. "We could not parse your compatibility statement, so we
    /// assumed you were compatible" is exactly the silence hub#521 is about, one level up.
    #[test]
    fn an_unreadable_core_floor_is_refused_by_name() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"id":"m","name":"M","version":"1.0.0",
                "compatibility":{"min_erplora_version":"latest"}}"#,
        )
        .unwrap();
        let message = manifest
            .require_core_version()
            .expect_err("a floor that is not a version must not read as `compatible`")
            .to_string();
        assert!(
            message.contains("latest"),
            "the refusal must quote what it could not read: {message}"
        );
    }

    /// A manifest with no `compatibility` block runs anywhere — the shape of all 24 published
    /// modules, and the reason this issue is not a fleet-wide republish.
    #[test]
    fn no_compatibility_block_means_no_floor() {
        let manifest: Manifest =
            serde_json::from_str(r#"{"id":"m","name":"M","version":"1.0.0"}"#).unwrap();
        assert!(manifest.require_core_version().is_ok());
        assert!(manifest.compatibility.is_none());
    }

    /// `max_erplora_version` is parsed and deliberately NOT enforced (see [`Compatibility`]).
    ///
    /// Enforcing it would refuse an OLD module on a NEW hub, which is the direction that has to
    /// keep working for a hub to be upgradable at all. The test pins the decision so that
    /// "completing" the check later is a conscious act, not a tidy-up.
    #[test]
    fn a_max_core_version_below_this_hub_does_not_refuse_anything() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"id":"m","name":"M","version":"1.0.0",
                "compatibility":{"max_erplora_version":"0.0.1"}}"#,
        )
        .unwrap();
        assert!(
            manifest.require_core_version().is_ok(),
            "an old module on a new hub keeps installing: that is the tolerance that makes \
             upgrading a hub possible"
        );
    }

    // ── The producer side of the event contract (hub#709) ────────────────────────────────────

    /// 🔴 The hole this closes. `installer::validate_event_listeners` (hub#659) already forces the
    /// CONSUMER to declare well; nothing forced the PRODUCER, so `sale.completed` — the hub's
    /// central event — was declared in no place the runtime could read, and the catalogue the
    /// flow editor builds out of the installed manifests came out empty.
    #[test]
    fn an_emit_missing_from_events_emits_is_reported() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"id":"sales","name":"Sales","version":"1.0.0",
                "commands":{"sales.void":{"permission":"sales.void","sql":[],
                            "emit":["sale.voided"]}}}"#,
        )
        .unwrap();

        let warnings = manifest.undeclared_emit_warnings();

        assert_eq!(warnings.len(), 1, "one warning per undeclared event");
        assert_eq!(warnings[0].path, "events.emits");
        assert!(
            warnings[0].detail.contains("sale.voided") && warnings[0].detail.contains("sales.void"),
            "the warning has to name the event AND the command that emits it: {}",
            warnings[0].detail
        );
    }

    /// The rule is satisfiable and it does not nag a manifest that already declares what it emits
    /// — otherwise the 24 published modules would warn forever and the channel would be noise.
    #[test]
    fn an_emit_listed_in_events_emits_says_nothing() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"id":"sales","name":"Sales","version":"1.0.0",
                "commands":{"sales.void":{"permission":"sales.void","sql":[],
                            "emit":["sale.voided"]}},
                "events":{"emits":["sale.voided","sale.completed"]}}"#,
        )
        .unwrap();

        assert!(
            manifest.undeclared_emit_warnings().is_empty(),
            "a declared emit is exactly what this rule asks for"
        );
        // And declaring MORE than the commands emit is not an error: `events.emits` is also where
        // the handler's own events live (`sale.completed` comes out of the WASM, not a command).
    }

    /// Two commands emitting the same undeclared name is ONE hole in the catalogue, not two — and
    /// the order has to be stable, because `commands` is a `HashMap` and a warning that reshuffles
    /// on every boot is unreadable.
    #[test]
    fn the_same_undeclared_event_is_reported_once_with_every_command_that_emits_it() {
        let manifest: Manifest = serde_json::from_str(
            r#"{"id":"cash_register","name":"Cash","version":"1.0.0",
                "commands":{
                  "cash_register.movement.add":{"permission":"p","sql":[],
                        "emit":["cash_register.movement_added"]},
                  "cash_register.record_sale":{"permission":"p","sql":[],
                        "emit":["cash_register.movement_added"]},
                  "cash_register.session.open":{"permission":"p","sql":[],
                        "emit":["cash_register.session_opened"]}}}"#,
        )
        .unwrap();

        let warnings = manifest.undeclared_emit_warnings();

        assert_eq!(warnings.len(), 2, "two distinct events, not three emits");
        assert!(
            warnings[0].detail.contains("cash_register.movement_added"),
            "sorted by event name so two boots read the same: {warnings:?}"
        );
        assert!(
            warnings[0].detail.contains("cash_register.movement.add")
                && warnings[0].detail.contains("cash_register.record_sale"),
            "both commands that emit it get named: {}",
            warnings[0].detail
        );
    }

    /// Wired into the door every module goes through — install AND the boot re-registration — so
    /// the warning rides on `Manifest::warnings` into `/api/modules` like the hub#521 ones.
    #[test]
    fn load_carries_the_undeclared_emit_warning() {
        let dir = std::env::temp_dir().join(format!("erplora-emits-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("module.json"),
            r#"{"id":"sales","name":"Sales","version":"1.0.0",
                "commands":{"sales.void":{"permission":"sales.void","sql":[],
                            "emit":["sale.voided"]}}}"#,
        )
        .unwrap();

        let manifest = Manifest::load(&dir).expect("an under-declared producer still INSTALLS");

        assert!(
            manifest
                .warnings
                .iter()
                .any(|w| w.path == "events.emits" && w.detail.contains("sale.voided")),
            "the warning travels with the manifest: {:?}",
            manifest.warnings
        );
        std::fs::remove_dir_all(dir).unwrap();
    }
}
