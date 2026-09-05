//! Plugins **nativos first-party** (ADR-0009). Segunda clase de handler junto al WASM
//! Tier 2: un crate Rust horneado en el binario del runtime (no descargable, no para
//! terceros) para módulos compliance-crítico (`verifactu`, `payroll`).
//!
//! Contrato (idéntico en espíritu al WASM, ARQUITECTURA.md §5.3): el plugin **nunca
//! escribe en la BD**. Recibe `{payload, context}` + un [`NativeHost`] para **lecturas
//! mediadas** (solo `SELECT`; el runtime ejecuta la lectura, el plugin no abre conexión
//! propia), calcula y devuelve un [`Output`] con *intenciones* (operaciones `sql` que
//! referencian commands del **mismo módulo** + eventos) que el runtime valida y persiste
//! en UNA transacción (`commands.rs::execute_native`).
//!
//! A diferencia del WASM, un plugin nativo sí puede usar red/cripto plenas (TLS mutua,
//! PKCS#12) — esa es justamente la razón de su existencia (ADR-0009).
use erplora_db::{DatabaseAdapter, Params};
use erplora_wasm_host::Output;
use serde_json::Value as Json;

use crate::errors::{Result, RuntimeError};

/// Lecturas mediadas por el runtime para un plugin nativo. Solo sentencias `SELECT`
/// (las escrituras van SIEMPRE como intenciones en el [`Output`], nunca directas).
#[async_trait::async_trait]
pub trait NativeHost: Send + Sync {
    /// Ejecuta un `SELECT` con parámetros nombrados (`:name`) y devuelve las filas JSON.
    async fn read(&self, sql: &str, params: &Params) -> Result<Vec<Json>>;

    /// **Capacidad de host `certificate` (ADR-0079).** Identidad TLS-cliente (mTLS) del certificado
    /// del negocio (`_hub_certificate`) para que el módulo transmita a Hacienda **sin ver el `.p12`**:
    /// la clave nunca cruza al módulo, el core hace toda la cripto. El gate de la capability lo aplica
    /// el dispatcher. Default: no disponible (host sin certificado).
    async fn certificate_identity(&self, _hub_id: &str) -> Result<reqwest::Identity> {
        Err(RuntimeError::Certificate(
            "la capability `certificate` no está disponible en este host".to_string(),
        ))
    }

    /// Caducidad (notAfter, ISO `YYYY-MM-DD`) del certificado del negocio. `Ok(None)` si no hay.
    async fn certificate_expiry(&self, _hub_id: &str) -> Result<Option<String>> {
        Ok(None)
    }

    /// **Which of the hub's certificates signs** — `"own"`, `"delegated"` or `None` when the hub
    /// holds neither (ADR-0202 §2.1 — hub#319). The name is
    /// [`CertificateKind::as_str`](crate::certificate::CertificateKind::as_str)'s, i.e. the value
    /// stored in `_hub_certificate.kind`.
    ///
    /// **The selection rule belongs to the core, and this is how a module borrows it instead of
    /// re-deriving it.** `verifactu` used to answer «do I have a certificate?» with its own
    /// `SELECT pkcs12_b64, password FROM _hub_certificate … LIMIT 1`: slot-blind (with two rows it
    /// took whichever the database returned first), blind to the kinds the core refuses to select,
    /// and it pulled the certificate's password into the module just to test it for emptiness —
    /// which is exactly what ADR-0079 exists to prevent. One question, one owner.
    ///
    /// Never touches `pkcs12_b64`/`password`: answering «which one signs?» must not drag a private
    /// key through memory, let alone decrypt one.
    ///
    /// Default: `Ok(None)` — a host without certificates has nothing signing.
    async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
        Ok(None)
    }

    /// **What the signing certificate IS** — `"seal"` or `"representative"`
    /// ([`CertificateType::as_str`](crate::certificate::CertificateType::as_str)), `None` when the
    /// hub holds no certificate or holds one it cannot vouch for (ADR-0202 §2.1 — hub#470).
    ///
    /// The companion of [`certificate_signing_kind`](Self::certificate_signing_kind), and NOT a
    /// synonym: that one says **whose** the certificate is (which is what picks the fallback, and
    /// nothing else — the `Representante` hangs off WHO PRESENTS, not off the slot: ADR-0268 §4,
    /// hub#1460), this one says **what** it is, which is the axis the AEAT segregates its entry
    /// point by. Reading the slot as if it were the type is the defect hub#470 closes.
    ///
    /// **The core answers, and the module does not re-derive it.** Same rule as the slot: one
    /// question, one owner. `verifactu` never touches `_hub_certificate` — the private key does not
    /// cross into a module, and only these two words do.
    ///
    /// Default: `Ok(None)` — «cannot tell», which routes to the holder's entry point.
    async fn certificate_signing_type(&self, _hub_id: &str) -> Result<Option<String>> {
        Ok(None)
    }

    /// **Whose the signing certificate is** — the tax id and the registered name of the entity
    /// that holds it, read from the container's subject (hub#1478).
    ///
    /// The third question of the same family, and independent of the other two:
    /// [`certificate_signing_kind`](Self::certificate_signing_kind) says which SLOT signs,
    /// [`certificate_signing_type`](Self::certificate_signing_type) says WHAT the certificate is,
    /// and this one says WHO it belongs to. A caller that has to declare who is acting for whom
    /// needs this one and cannot derive it from either of the others — deriving it from the slot
    /// is the fourth border defect hub#470 closed, written down as a rule in ADR-0268 §4.
    ///
    /// Same rule as its siblings: the core answers and the module does not re-derive it. The
    /// PKCS#12 crypto stays here; what crosses is the pair of public fields of
    /// [`CertificateHolder`](crate::certificate::CertificateHolder).
    ///
    /// Default: `Ok(None)` — «cannot tell». Absence concludes nothing: a caller reading it is
    /// left exactly where it was before the primitive existed.
    async fn certificate_holder(
        &self,
        _hub_id: &str,
    ) -> Result<Option<crate::certificate::CertificateHolder>> {
        Ok(None)
    }

    /// Igual que [`certificate_identity`](Self::certificate_identity) pero sobre un `.p12` **provisto
    /// en memoria** (DER + contraseña) — validar/usar un certificado recién subido. La cripto PKCS#12
    /// (OpenSSL) vive SOLO en el core; el módulo no la implementa. Default = la cripto del core.
    async fn certificate_identity_from(
        &self,
        pkcs12_der: &[u8],
        password: &str,
    ) -> Result<reqwest::Identity> {
        crate::certificate::identity_from_der(pkcs12_der, password)
    }

    /// Caducidad de un `.p12` provisto en memoria (DER + contraseña). Cripto en el core.
    async fn certificate_expiry_from(
        &self,
        pkcs12_der: &[u8],
        password: &str,
    ) -> Result<Option<String>> {
        crate::certificate::expiry_from_der(pkcs12_der, password)
    }

    /// **The manufacturer's half of `SistemaInformatico`**, as the control plane last served it
    /// (ADR-0202 §5.1 — hub#323), keyed by the literal AEAT element names.
    ///
    /// The engine needs seven fields it cannot know: the manufacturer's identity (one fact about
    /// ERPlora, served from the SaaS so that correcting it is one line instead of rebuilding the
    /// fleet) and `IndicadorMultiplesOT`, which the AEAT computes **per account** over how many
    /// facturaciones its owner created — a hub can only see itself.
    ///
    /// Same split as the certificate: the module does not fetch anything and holds no cloud
    /// credential. `erplora-server` fills the cache from the heartbeat and this is the window the
    /// engine looks through, so nothing below the host learns that a control plane exists.
    ///
    /// Default: `Ok(None)` — «nobody has told this hub», which is NOT a set of defaults. There
    /// are none for a legal declaration, and the engine refuses to build the envelope.
    async fn producer_facts(&self) -> Result<Option<Json>> {
        Ok(None)
    }

    /// **Who this machine is on the wire** (hub#1459) — the hub's enrolled mTLS identity, the CA
    /// that anchors the peer's server certificate and the common name it was issued for.
    ///
    /// A GENERIC primitive, not a door per use case: the host lends an identity and the engine
    /// picks the destination it presents it to, exactly as `certificate_identity` already works
    /// for the business certificate. The difference is only WHOSE identity it is — the machine's
    /// (born on this hub, `gateway_identity.rs`) instead of the business's — and, as there, the
    /// private key never crosses into the engine.
    ///
    /// Default: `Ok(None)` — nothing enrolled. The engine treats it as «this road is not open»
    /// and leaves its work queued with a visible reason; it never panics.
    async fn machine_identity(
        &self,
        _hub_id: &str,
    ) -> Result<Option<crate::gateway_identity::MachineIdentity>> {
        Ok(None)
    }

    /// **Call MY cloud with MY machine credential** (hub#1459) — the host puts the DESTINATION
    /// (this hub's control plane) and the CREDENTIAL (`X-Hub-Token`, a runtime secret the engine
    /// must never hold, ADR-0003); the engine puts the method, the path and the body.
    ///
    /// The one constraint of the primitive, and the reason it exists: a credential handed to a
    /// destination the CALLER chooses is a credential leaked, so this destination is fixed. It is
    /// not a URL allowlist — with [`machine_identity`](Self::machine_identity) no key travels and
    /// the engine keeps choosing where it connects.
    ///
    /// Default: `Ok(None)` — no caller installed (a test host, an embedded runtime) or no machine
    /// credential. `Ok(Some(_))` = the cloud answered, whatever the status: a 404 or a 409 is an
    /// ANSWER, and what it means belongs to the engine that asked.
    async fn cloud_call(
        &self,
        _request: crate::cloud_call::CloudRequest,
    ) -> Result<Option<crate::cloud_call::CloudResponse>> {
        Ok(None)
    }

    /// Escribe dentro de la carpeta `static_files` declarada por el módulo. La implementación real
    /// conoce el módulo que está ejecutándose y media el backend Local/Cloud; el plugin solo aporta
    /// una ruta relativa segura.
    async fn write_static_file(
        &self,
        _relative_path: &str,
        _bytes: &[u8],
        _content_type: &str,
    ) -> Result<String> {
        Err(RuntimeError::Storage(
            "la capacidad `static_files` no está disponible en este host".to_string(),
        ))
    }
}

/// Work a native engine still owes an EXTERNAL authority, reported by
/// [`NativeHandler::pending_obligations`] (hub#314, ADR-0202 guard R2). The runtime turns it
/// into the refusal that keeps the module in place; the engine owns the numbers and the words
/// because only it knows what "not handed over yet" means in its domain.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingObligation {
    /// How many units are still owed. The operator is told this number, so it must be the same
    /// one the module's own UI shows (for `verifactu`: the pending-records KPI).
    pub count: u64,
    /// Since when the OLDEST unit has been owed (RFC 3339), if the engine knows. The daily
    /// heartbeat forwards it to the SaaS next to the count (hub#326 / hub#1406): a fleet panel
    /// that only sees «how many» cannot tell a hiccup from a hub that stopped remitting weeks
    /// ago. `None` when nothing is owed or the engine cannot date it.
    pub oldest_pending_at: Option<String>,
    /// Stable domain code, `<module>.<snake_case>` in the engine's OWN namespace — same public
    /// ABI as `expect_rows` (hub#139). The UI programs and translates against it.
    pub code: String,
    /// Human fallback, already carrying the count. Never the only channel: the code is.
    pub message: String,
}

/// Un plugin nativo first-party: el motor de un módulo, horneado en el runtime y
/// registrado por `module_id` ([`crate::Runtime::register_native`]). `function` es el
/// nombre declarado en `module.json` (`handler.function`); una función desconocida debe
/// devolver [`RuntimeError::Native`].
#[async_trait::async_trait]
pub trait NativeHandler: Send + Sync + std::fmt::Debug {
    async fn call(&self, function: &str, input: &Json, host: &dyn NativeHost) -> Result<Output>;

    /// **Retention gate (hub#314, ADR-0202 guard R2).** What this engine still owes an external
    /// authority for `hub_id`, or `None` when it owes nothing. The runtime asks BEFORE
    /// deactivating or uninstalling the module (and before dragging it down in a cascade) and
    /// refuses while something is owed — otherwise the work is stranded with nobody left to
    /// drain it (VeriFactu FAQ §5: an invoice whose record never reached the AEAT).
    ///
    /// Reads go through `host` (SELECT only), like every other native read. Default: engines
    /// owe nothing, so the lifecycle is unchanged for every plugin that does not opt in.
    async fn pending_obligations(
        &self,
        _hub_id: &str,
        _host: &dyn NativeHost,
    ) -> Result<Option<PendingObligation>> {
        Ok(None)
    }
}

/// [`NativeHost`] real sobre el adaptador de BD del runtime.
///
/// `pub` para que un test pueda preguntarle a un motor nativo lo mismo que le pregunta el
/// dispatcher, **con el host de verdad**: la coherencia de hub#319 (el gate fiscal, el ⛔ de la
/// checklist y el `can_sign` del motor contestan lo mismo) no se puede comprobar contra un
/// host de mentira, porque un gemelo escrito a mano es justo la forma en que dos lecturas de la
/// misma pregunta empiezan a divergir.
pub struct DbHost<'a> {
    pub db: &'a dyn DatabaseAdapter,
    pub storage: Option<&'a dyn crate::module_storage::ModuleStorage>,
    pub hub_id: &'a str,
    pub module_id: &'a str,
    pub static_folder: Option<&'a str>,
}

#[async_trait::async_trait]
impl NativeHost for DbHost<'_> {
    async fn read(&self, sql: &str, params: &Params) -> Result<Vec<Json>> {
        if !sql.trim_start().to_ascii_uppercase().starts_with("SELECT") {
            return Err(RuntimeError::Native(
                "lectura nativa rechazada: solo se permite SELECT".to_string(),
            ));
        }
        Ok(self.db.query(sql, params).await?.rows)
    }

    async fn certificate_identity(&self, hub_id: &str) -> Result<reqwest::Identity> {
        crate::certificate::identity(self.db, hub_id).await
    }

    async fn certificate_expiry(&self, hub_id: &str) -> Result<Option<String>> {
        crate::certificate::expiry(self.db, hub_id).await
    }

    async fn certificate_signing_kind(&self, hub_id: &str) -> Result<Option<String>> {
        Ok(crate::certificate::active_kind(self.db, hub_id)
            .await?
            .map(|k| k.as_str().to_string()))
    }

    async fn certificate_signing_type(&self, hub_id: &str) -> Result<Option<String>> {
        Ok(crate::certificate::active_type(self.db, hub_id)
            .await?
            .map(|t| t.as_str().to_string()))
    }

    async fn certificate_holder(
        &self,
        hub_id: &str,
    ) -> Result<Option<crate::certificate::CertificateHolder>> {
        crate::certificate::active_holder(self.db, hub_id).await
    }

    async fn producer_facts(&self) -> Result<Option<Json>> {
        Ok(crate::producer_facts::ProducerFactsCache::global()
            .current()
            .map(|facts| facts.to_json()))
    }

    async fn machine_identity(
        &self,
        hub_id: &str,
    ) -> Result<Option<crate::gateway_identity::MachineIdentity>> {
        Ok(crate::gateway_identity::client_identity(self.db, hub_id)
            .await?
            .map(|(identity, ca_pem)| crate::gateway_identity::MachineIdentity {
                identity,
                ca_pem,
                common_name: crate::gateway_identity::common_name(hub_id),
            }))
    }

    async fn cloud_call(
        &self,
        request: crate::cloud_call::CloudRequest,
    ) -> Result<Option<crate::cloud_call::CloudResponse>> {
        // The path is checked HERE, before any caller exists to be trusted with it: the check is
        // the primitive's security property, not the server's private business.
        crate::cloud_call::check_path(&request.path)?;
        match crate::cloud_call::CloudCallerCell::global().current() {
            Some(caller) => caller.call(request).await,
            None => Ok(None),
        }
    }

    async fn write_static_file(
        &self,
        relative_path: &str,
        bytes: &[u8],
        content_type: &str,
    ) -> Result<String> {
        if !crate::module_storage::valid_relative_file_path(relative_path) {
            return Err(RuntimeError::Storage(format!(
                "ruta de fichero inválida para `{}`",
                self.module_id
            )));
        }
        let folder = self.static_folder.ok_or_else(|| {
            RuntimeError::Storage(format!(
                "el módulo `{}` no declara `static_files.folder`",
                self.module_id
            ))
        })?;
        let storage = self.storage.ok_or_else(|| {
            RuntimeError::Storage("el host no configuró un backend de módulos".to_string())
        })?;
        storage
            .write_module_file(self.hub_id, folder, relative_path, bytes, content_type)
            .await
    }
}
