//! erplora-cloud-client — cliente del Cloud Portal (ARQUITECTURA.md §2.1–2.3).
//!
//! El Cloud Portal es el plano de control: auth, marketplace, billing, proxy AI. Este crate
//! construye las **peticiones** (URLs + cabeceras) y **verifica la integridad** de los zips
//! descargados (SHA256), pero deja el I/O de red al llamador (inyectable → testeable sin red,
//! y sin atar el runtime a un cliente HTTP concreto todavía).
//!
//! Tres credenciales (verificadas en el hub actual, §2.3):
//!  1. `cloud_api_token` del hub → header `X-Hub-Token` (+ `X-Hub-Id`): bootstrap/máquina.
//!  2. JWT del usuario activo → `Authorization: Bearer …` (+ `X-Hub-Id`).
//!  3. `X-Webhook-Secret` (+ `X-Hub-Id`): M2M de fondo.

use serde::Deserialize;

pub mod entitlement;
pub mod integrity;
pub mod signature;
pub mod user_jwt;

pub use entitlement::{
    verify_entitlement, EntitledModule, EntitlementClaims, EntitlementError, EntitlementResponse,
};
pub use integrity::{verify_sha256, IntegrityError};
pub use signature::{
    ModuleSignature, SignatureError, SignaturePolicy, Signer, TrustedKeyRing,
    PUBLIC_KEY_LEN, SIGNATURE_LEN,
};
pub use user_jwt::{verify_user_jwt, HubMembership, UserClaims, UserJwtError};

/// Credenciales con las que firmar una petición al Cloud.
#[derive(Debug, Clone)]
pub enum Auth {
    /// Token de aplicación del hub (bootstrap / contexto máquina).
    HubToken { hub_id: String, token: String },
    /// JWT del usuario activo.
    UserJwt { hub_id: String, access: String },
    /// Secreto de webhook para M2M de fondo.
    Webhook { hub_id: String, secret: String },
}

impl Auth {
    /// Cabeceras `(nombre, valor)` para esta credencial. Siempre incluye `X-Hub-Id`.
    pub fn headers(&self) -> Vec<(&'static str, String)> {
        match self {
            Auth::HubToken { hub_id, token } => {
                vec![("X-Hub-Id", hub_id.clone()), ("X-Hub-Token", token.clone())]
            }
            Auth::UserJwt { hub_id, access } => {
                vec![
                    ("X-Hub-Id", hub_id.clone()),
                    ("Authorization", format!("Bearer {access}")),
                ]
            }
            Auth::Webhook { hub_id, secret } => {
                vec![
                    ("X-Hub-Id", hub_id.clone()),
                    ("X-Webhook-Secret", secret.clone()),
                ]
            }
        }
    }
}

/// Una petición lista para ejecutar por el cliente HTTP del llamador.
#[derive(Debug, Clone)]
pub struct PreparedRequest {
    pub method: &'static str,
    pub url: String,
    pub headers: Vec<(&'static str, String)>,
}

/// **Where this hub is**, as the marketplace catalogue is asked about it (ADR-0062, hub#69).
///
/// Compliance is sold as atomic modules per regime (`verifactu`, `ticketbai`, `nf525`…) and each
/// declares the countries it applies to. Without saying where the hub is, the catalogue answered
/// with every country's regime at once: a hub in France was offered VeriFactu, which it cannot
/// use, and the one module it does need was buried among the rest.
///
/// **The browser is not in this conversation.** The values come from `hub_settings.country_code` /
/// `region_code` — read by the runtime, appended by the runtime — so the catalogue a till sees is
/// not something a query param from the page can widen. That matters beyond tidiness: which fiscal
/// regime a hub is offered is the first step of what it will end up filing.
///
/// Empty `country` = **no filter at all** (the whole catalogue), which is what a hub that has not
/// answered where it is should see — not an empty shelf.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct CountryFilter {
    /// ISO-3166-1 alpha-2 (`ES`), upper-cased. `""` = the hub has not said.
    pub country: String,
    /// ISO-3166-2 subdivision WITHOUT the country prefix (`PV`), upper-cased. `""` = the whole
    /// country, which is the normal case.
    pub region: String,
}

impl CountryFilter {
    /// No filter: the whole catalogue.
    pub fn none() -> Self {
        Self::default()
    }

    /// Normalises on the way in (trim + upper-case), so a stored `" es "` and an `ES` are the same
    /// filter and neither becomes a country the SaaS does not recognise.
    ///
    /// **And it translates the region between the two spellings.** The hub stores `region_code` as
    /// full ISO-3166-2 (`ES-PV`, enforced by `settings::validate_region`); the marketplace filter
    /// takes the subdivision alone (`PV`), the format the regional scope of a `ModuleCountry` link
    /// holds. Sending the prefixed form errors nowhere and matches nothing — a hub in the Basque
    /// Country would be shown VeriFactu instead of TicketBAI — so the prefix is dropped here, at
    /// the one boundary that knows both spellings. Only when it IS this hub's country: a dash in
    /// front of anything else is part of the code, not a prefix to guess at.
    pub fn new(country: &str, region: &str) -> Self {
        let country = country.trim().to_ascii_uppercase();
        let region = region.trim().to_ascii_uppercase();
        let region = region
            .strip_prefix(&format!("{country}-"))
            .filter(|_| !country.is_empty())
            .unwrap_or(&region)
            .to_string();
        Self { country, region }
    }

    /// `""` · `"?countries=ES"` · `"?countries=ES&region=PV"`.
    ///
    /// A region with no country is dropped: the SaaS ignores it by contract (a region only means
    /// something inside its country) and sending it would advertise a filter nobody applies.
    fn query(&self) -> String {
        if self.country.is_empty() {
            return String::new();
        }
        if self.region.is_empty() {
            format!("?countries={}", self.country)
        } else {
            format!("?countries={}&region={}", self.country, self.region)
        }
    }
}

/// **What the catalogue is asked about**: where the hub is, and in which language (hub#1003).
///
/// The two facets are separate questions with separate reasons — the country decides *which
/// modules* a hub may be offered (ADR-0062: a hub in France must not be shown VeriFactu), the
/// language only decides *how they are spelled* (ADR-0364). They travel together because they end
/// up in the same query string, and **that is exactly why this type exists**: one place knows
/// whether the string has been opened with `?` yet. Appending `&lang=` from the call site produces
/// `…?countries=ES?lang=es` for every hub that declares a country — that is, every real one, and
/// none of the ones a no-filter test covers.
///
/// Both come from the hub's own settings, never from the request: a page cannot widen what its
/// till is offered, and it does not have to know the rule.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct CatalogQuery {
    country: CountryFilter,
    /// Bare lowercase primary subtag (`es`), or `""` for "the Cloud's source language".
    language: String,
}

impl CatalogQuery {
    /// Normalises the language on the way in: `es-ES`, `es_ES` and ` ES ` are all `es`, and
    /// anything not language-shaped becomes `""`.
    ///
    /// Regional variants collapse because the Cloud collapses them too — storing a translation per
    /// region would ask every module author to guess which markets their customers are in. And a
    /// setting is a place a human can type into, so junk is **dropped rather than sent**: a query
    /// param the server cannot parse is worse than no query param at all.
    pub fn new(country: CountryFilter, language: &str) -> Self {
        let primary = language
            .trim()
            .replace('_', "-")
            .split('-')
            .next()
            .unwrap_or_default()
            .to_ascii_lowercase();
        let language = if primary.chars().all(|c| c.is_ascii_alphabetic())
            && (2..=3).contains(&primary.chars().count())
        {
            primary
        } else {
            String::new()
        };
        Self { country, language }
    }

    /// The whole query string, `?` and `&` included — `""` when there is nothing to ask.
    fn query(&self) -> String {
        let country = self.country.query();
        if self.language.is_empty() {
            return country;
        }
        let separator = if country.is_empty() { '?' } else { '&' };
        format!("{country}{separator}lang={}", self.language)
    }
}

/// Percent-encode de un valor que va en **un segmento de path** (RFC 3986). Deja intacto el
/// conjunto *unreserved* (`A-Z a-z 0-9 - . _ ~`) y codifica el resto como `%XX`. Sin dependencias
/// (el crate no arrastra `url`/`percent-encoding`). Lo usa `members_remove` para poner el email en
/// el path: `ana+x@bar.com` → `ana%2Bx%40bar.com` (el `.` del dominio se preserva por legibilidad).
fn encode_path_segment(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for &b in s.as_bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Construye peticiones contra un Cloud Portal concreto.
#[derive(Debug, Clone)]
pub struct CloudClient {
    base_url: String,
}

impl CloudClient {
    pub fn new(base_url: impl Into<String>) -> Self {
        // normaliza sin barra final
        let mut b = base_url.into();
        while b.ends_with('/') {
            b.pop();
        }
        Self { base_url: b }
    }

    fn get(&self, path: &str, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "GET",
            url: format!("{}{}", self.base_url, path),
            headers: auth.headers(),
        }
    }

    fn public_get(&self, path: &str) -> PreparedRequest {
        PreparedRequest {
            method: "GET",
            url: format!("{}{}", self.base_url, path),
            headers: Vec::new(),
        }
    }

    /// Bootstrap del hub (config inicial), con el token de aplicación. §2.3.
    pub fn bootstrap(&self, hub_id: &str, token: &str) -> PreparedRequest {
        self.get(
            &format!("/api/hubs/{hub_id}/bootstrap/"),
            &Auth::HubToken {
                hub_id: hub_id.to_string(),
                token: token.to_string(),
            },
        )
    }

    /// Lista de módulos del marketplace para el hub (con JWT de usuario). §2.2.
    ///
    /// Filtrada por el país del hub (ADR-0062, hub#69) — ver [`CountryFilter`].
    pub fn marketplace_modules(&self, auth: &Auth, catalog: &CatalogQuery) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{}", catalog.query()),
            auth,
        )
    }

    /// Catálogo público de metadatos para Demo. No concede descarga, compra ni entitlement.
    ///
    /// Lleva el MISMO filtro de país que su hermana de arriba: una demo también está en un país,
    /// y ofrecerle el régimen fiscal de otro sería enseñar un módulo que no puede usar.
    pub fn public_marketplace_modules(&self, catalog: &CatalogQuery) -> PreparedRequest {
        self.public_get(&format!("/api/v1/marketplace/catalog/{}", catalog.query()))
    }

    /// Which build of the installable app the Cloud publishes right now (hub#400).
    ///
    /// **Public on purpose.** The version of a public download is not a secret — it is written on
    /// the store listing — and asking for it without a credential is what lets a hub that is in
    /// demo, unenrolled or asleep still tell its till that a newer app exists. With a credential,
    /// those hubs would answer 401 and the till would read that as "nothing new", which is the
    /// mute failure this whole feature is about.
    pub fn app_release(&self) -> PreparedRequest {
        self.public_get("/api/v1/app/release/")
    }

    /// **Gate de arranque de la app Tauri** — entitlement firmado de módulos del hub
    /// (con JWT de usuario). `GET /api/v1/hub/device/entitlement/`. La respuesta es un
    /// [`EntitlementResponse`]; su `token` se verifica offline con
    /// [`verify_entitlement`] contra la clave pública del Cloud. Ver `entitlement.rs`.
    pub fn entitlement(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/entitlement/", auth)
    }

    /// **Heartbeat de uso/liveness** del Hub hacia el Cloud (hub#199 / saas#806).
    /// `POST /api/v1/hub/device/heartbeat/` con la credencial de máquina; el body
    /// (`orders_today`, `last_sale_at`, `terminals`) lo construye el server desde
    /// la base de datos local. Se ejecuta en el mismo tick que el entitlement.
    pub fn heartbeat(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/heartbeat/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **ERPlora's DELEGATED fiscal certificate for this hub** (ADR-0202 §2, saas#1125 — hub#317).
    /// `GET /api/v1/hub/device/fiscal/certificate/` → [`DelegatedCertificate`].
    ///
    /// **Machine credential, and only that.** The SaaS pins `IsHubMachine` here on purpose — unlike
    /// its neighbours it does NOT accept a member's JWT, because that JWT lives in a browser and
    /// this response carries a private key. So the call is made BY the runtime, with the
    /// `cloud_api_token`, and its body must never be proxied to the web app.
    ///
    /// **404 is a normal answer**, not a failure: `no_delegated_certificate` means the control plane
    /// has never uploaded one (`version == 0`). The hub keeps whatever it has and carries on.
    pub fn fiscal_certificate(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/fiscal/certificate/", auth)
    }

    /// **El otorgamiento de representación firmado** (hub#817 / saas#1438, hub#1293).
    ///
    /// `POST` sube el modelo oficial YA FIRMADO fuera (a mano o con AutoFirma) + la copia del
    /// documento de identidad + la muestra de firma y el justificante de representación cuando
    /// hacen falta; `GET` contesta su estado (`pendiente` / `vigente` / `rechazado` / `revocado` /
    /// ausente + fecha) y **nunca** los documentos. Misma URL para los dos verbos, así que el
    /// builder es uno.
    ///
    /// Credencial de **máquina**, como sus vecinas: la persona que firma en el mostrador no tiene
    /// un JWT del SaaS vivo (ADR-0003), y el `cloud_api_token` no cruza al navegador — la pantalla
    /// llama al runtime y es el runtime quien pone la cabecera.
    pub fn representation_grant(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!(
                "{}/api/v1/hub/device/fiscal/representation-grant/",
                self.base_url
            ),
            headers: auth.headers(),
        }
    }

    /// **El modelo oficial del otorgamiento, pre-relleno** (hub#1293).
    ///
    /// `POST …/representation-grant/model/` con los datos de las dos partes → `application/pdf`.
    /// El texto del modelo (p. 11 del acuerdo de colaboración social 017) «no podrá ser
    /// modificado», así que vive en UN sitio, el SaaS, y el Hub solo trae los bytes: dos copias del
    /// mismo documento legal son dos documentos que acaban diciendo cosas distintas.
    pub fn representation_grant_model(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!(
                "{}/api/v1/hub/device/fiscal/representation-grant/model/",
                self.base_url
            ),
            headers: auth.headers(),
        }
    }

    /// **Identidad fiscal del negocio hacia el SaaS** (ADR-0201 decisión 5, 7/11 — hub#333).
    /// `POST /api/v1/hub/device/fiscal-identity/` con la credencial de máquina; el body (razón
    /// social, NIF, dirección) lo construye el server desde `hub_settings`, que es donde el
    /// usuario ya lo escribió una vez. Crea/actualiza el `BillingProfile` del hub en el SaaS.
    ///
    /// **La llamada la hace el RUNTIME, no el navegador**: el `cloud_api_token` es secreto del hub
    /// y nunca cruza al webview. Y sube una COPIA — el NIF del negocio se queda en `hub_settings`;
    /// el del `BillingProfile` es a quién factura ERPlora. Dos NIF distintos que no se leen.
    pub fn fiscal_identity(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/fiscal-identity/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// Redeems the native-shell one-time courier code.  This request is made by the Hub runtime
    /// with its machine credential, never by browser JavaScript, so the SaaS can bind redemption
    /// to the exact destination Hub.  The body (`{"code":"…"}`) is supplied by the caller.
    pub fn session_courier(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/session-courier/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Catálogo de blueprints** — plantillas de hub publicadas en el vendor portal del SaaS
    /// ([ADR-0121]). `GET /api/v1/catalog/blueprints/`. Es la **«fuente nube»** del panel de
    /// import (Ajustes → Datos). Hub-scoped: el runtime se autentica **a sí mismo**
    /// (`X-Hub-Token`), así que funciona sin JWT de usuario fresco (el día a día del POS es
    /// sesión local/PIN).
    pub fn blueprints_catalog(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/catalog/blueprints/", auth)
    }

    /// **Descarga de un blueprint** — devuelve URL **firmada** de Object Storage + `version` +
    /// `sha256`. `GET /api/v1/catalog/blueprints/{slug}/download/`. El runtime baja el zip de esa
    /// URL y **verifica el sha256 ANTES de aplicar nada** (mismo contrato que el install de
    /// módulos: ruta inmutable + hash). [ADR-0121]
    ///
    /// El `slug` es único **por idioma** (`restaurante` puede existir en `es` y en `fr`), así que
    /// el endpoint contesta **400** ante uno ambiguo sin `?locale=`: elegir al azar sembraría el
    /// hub en el idioma equivocado. Por eso el blueprint declarado por el SaaS viaja como
    /// **slug + locale** (ADR-0212), y ese locale llega aquí.
    pub fn blueprint_download(
        &self,
        slug: &str,
        locale: Option<&str>,
        auth: &Auth,
    ) -> PreparedRequest {
        let query = match locale.map(str::trim).filter(|l| !l.is_empty()) {
            Some(locale) => format!("?locale={}", encode_path_segment(locale)),
            None => String::new(),
        };
        self.get(
            &format!("/api/v1/catalog/blueprints/{slug}/download/{query}"),
            auth,
        )
    }

    /// **Enrolamiento del dispositivo** — el runtime obtiene su credencial de máquina
    /// (`cloud_api_token`) una sola vez. `GET /api/v1/hub/device/enroll/` con el JWT de un
    /// **owner/admin** de la org del hub (`IsHubAdmin`) + `X-Hub-Id`. La respuesta es
    /// [`EnrollGrant`] (`hub_id` + `cloud_api_token`); el runtime la persiste de forma segura
    /// y a partir de ahí usa [`Auth::HubToken`] (`X-Hub-Token`) para llamadas hub-scoped sin
    /// usuario logueado (marketplace, entitlement…). §2.3.
    pub fn enroll(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/enroll/", auth)
    }

    /// **Rotación** de la credencial de máquina — `POST /api/v1/hub/device/enroll/` (mismo endpoint,
    /// `IsHubAdmin`). El Cloud genera un `cloud_api_token` **nuevo** (invalida el anterior) y lo
    /// devuelve como [`EnrollGrant`]; el runtime lo re-persiste. Usar deliberadamente (compromiso de
    /// credencial / rotación periódica): un hub en ECS necesita redeploy para tomar el nuevo env. §2.3.
    pub fn enroll_rotate(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/enroll/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Revocación** (kill-switch) de la credencial de máquina — `DELETE /api/v1/hub/device/enroll/`
    /// (`IsHubAdmin`). Desactiva el token de máquina al instante sin emitir uno nuevo (dispositivo
    /// perdido/robado); se re-habilita re-enrolando (`enroll_rotate`). Normalmente lo invoca el
    /// dashboard/admin del owner (revoca un dispositivo que NO tiene a mano), no el propio hub. §2.3.
    pub fn enroll_revoke(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "DELETE",
            url: format!("{}/api/v1/hub/device/enroll/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Alta de un miembro del hub** (ADR-0157 §7) — `POST /api/v1/hub/device/members/` con la
    /// credencial de **máquina** (`X-Hub-Token`). Cuando un admin del hub da de alta a un usuario
    /// local (con su rol Hub), el runtime avisa al SaaS: éste crea/enlaza la identidad **por email**
    /// + una membresía (pending) + la **invitación**. El SaaS es la fuente de verdad del acceso; el
    /// Hub solo la administra vía esta API. Se usa el token de máquina (no el JWT de usuario) porque
    /// el día a día del POS es sesión local/PIN: casi nunca hay un JWT del SaaS fresco. El body
    /// `{email, role}` lo construye el llamador (server). Ver `members_remove` para la baja.
    pub fn members_add(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/members/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Baja de un miembro del hub** (ADR-0157 §7, *simetría obligatoria* del deprovisioning) —
    /// `DELETE /api/v1/hub/device/members/{email}/` con `X-Hub-Token`. Revoca la membresía: el
    /// usuario sigue autenticándose en el SaaS, pero este hub/org **desaparece de su payload** (y el
    /// gate de presencia del Hub deja de dejarle entrar; ventana ≤1 h hasta que caduque su access,
    /// ADR-0157 §9). El `email` va en el path **percent-encoded** (un email lleva `@`/`+`, que no
    /// son seguros en un segmento crudo). El deprovisioning es el fallo típico del invitation flow:
    /// esta baja es su contrapartida obligatoria del alta.
    pub fn members_remove(&self, auth: &Auth, email: &str) -> PreparedRequest {
        PreparedRequest {
            method: "DELETE",
            url: format!(
                "{}/api/v1/hub/device/members/{}/",
                self.base_url,
                encode_path_segment(email)
            ),
            headers: auth.headers(),
        }
    }

    /// **Refresh del JWT de usuario** contra el Cloud (hub#15, §2.3) — `POST /api/v1/auth/refresh/`
    /// (verificado: `cloud/apps/auth/users/api/urls.py` → `RotatingTokenRefreshView`, rota el
    /// refresh). Es un endpoint **público** en cuanto a cabeceras: NO lleva `Authorization` ni
    /// `X-Hub-Id`; el `refresh` token va en el **body** `{"refresh":"<token>"}`. La respuesta es un
    /// [`RefreshGrant`] (`access` nuevo + `refresh` rotado). El interceptor del Hub lo invoca al
    /// recibir un 401 con un access caducado. El body lo construye el llamador (server).
    pub fn refresh(&self) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/auth/refresh/", self.base_url),
            headers: vec![],
        }
    }

    /// Clave pública RSA del Cloud (para verificar el token de entitlement offline).
    /// `GET /api/v1/auth/public-key/`. Sin auth (endpoint público).
    pub fn public_key(&self) -> PreparedRequest {
        PreparedRequest {
            method: "GET",
            url: format!("{}/api/v1/auth/public-key/", self.base_url),
            headers: vec![],
        }
    }

    /// **Flujo real de instalación, paso 1** — lista las versiones activas de un módulo.
    /// `GET /api/v1/marketplace/modules/{module_id}/versions/` (verificado contra
    /// `cloud/apps/public/modules/api_views.py::versions`). La respuesta es un array JSON
    /// (`ModuleVersionSerializer`): `version`, `changelog`, `is_active`, `file_size_bytes`,
    /// `created_at`. El `sha256` se parsea si el Cloud lo expone (ver `ModuleVersion`). §2.2.
    pub fn versions(&self, auth: &Auth, module_id: &str) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/versions/"),
            auth,
        )
    }

    /// **Flujo real de instalación, paso 2** — descarga el ZIP binario de una versión.
    /// `GET /api/v1/marketplace/modules/{module_id}/download/?version={version}` (FileResponse,
    /// verificado en `api_views.py::download`). §2.2.
    pub fn download(&self, auth: &Auth, module_id: &str, version: &str) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/download/?version={version}"),
            auth,
        )
    }

    /// **ADR-0060 (hub#68), paso 0** — pide el PLAN DE INSTALACIÓN de un módulo.
    /// `POST /api/v1/marketplace/install-plan/` (verificado contra
    /// `saas/apps/public/modules/api_views.py::InstallPlanAPIView` →
    /// `install_plan.py::resolve_hub_install_plan`).
    ///
    /// El Cloud es quien tiene el grafo fresco (`Module.dependencies`) y la verdad del
    /// entitlement, así que resuelve el **cierre transitivo topo-ordenado** y el Hub solo lo
    /// ejecuta. `installed` es el set REAL del registry del runtime (el runtime es la autoridad):
    /// lo que ya está se devuelve en `already_satisfied` y no entra en el plan.
    ///
    /// `version` vacío o `"latest"` viaja como **ausente**: la elige el Cloud (versión activa).
    pub fn install_plan(
        &self,
        auth: &Auth,
        module_id: &str,
        version: &str,
        installed: &[String],
    ) -> PreparedInstallPlan {
        PreparedInstallPlan {
            request: PreparedRequest {
                method: "POST",
                url: format!("{}/api/v1/marketplace/install-plan/", self.base_url),
                headers: auth.headers(),
            },
            body: InstallPlanRequest {
                module_id: module_id.to_string(),
                version: Some(version)
                    .filter(|v| !v.is_empty() && *v != "latest")
                    .map(str::to_string),
                installed: installed.to_vec(),
            },
        }
    }

    /// **Flujo real de instalación, paso 3** — registra la instalación en el Cloud.
    /// `POST /api/v1/marketplace/modules/{module_id}/mark_installed/` con body
    /// `{"version":"…"}` (verificado en `api_views.py::mark_installed`). §2.2.
    pub fn mark_installed(&self, auth: &Auth, module_id: &str) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!(
                "{}/api/v1/marketplace/modules/{module_id}/mark_installed/",
                self.base_url
            ),
            headers: auth.headers(),
        }
    }

    /// Stream SSE del asistente vía el proxy del Cloud (§9.3 — el Hub nunca habla con el LLM
    /// directamente). `POST /api/v1/hub/device/assistant/chat/stream/` con el JWT del usuario
    /// + `X-Hub-Id`. El body lo construye el llamador (server) a partir del payload del frontend.
    pub fn assistant_chat_stream(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/assistant/chat/stream/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **El plan del asistente de ESTE hub** (saas#1540): tier, uso del mes y planes de pago
    /// disponibles. `GET /api/v1/hub/device/assistant/config/`.
    ///
    /// Existe porque el hub solo descubría su plan cuando ya lo había AGOTADO: no leía este
    /// endpoint, así que no conocía ni su tier, ni su consumo, ni qué se podía contratar. Con eso,
    /// quedarse sin mensajes solo podía presentarse como una avería.
    pub fn assistant_config(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "GET",
            url: format!("{}/api/v1/hub/device/assistant/config/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Abrir el checkout del plan del asistente** (saas#1540, ADR-0033).
    /// `POST /api/v1/hub/device/assistant/subscription/checkout/` → `{"checkout_url": …}`.
    ///
    /// Sin este camino, un «ver planes» no lleva a ninguna parte y el único momento de conversión
    /// del tier gratuito muere en una frase.
    pub fn assistant_checkout(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!(
                "{}/api/v1/hub/device/assistant/subscription/checkout/",
                self.base_url
            ),
            headers: auth.headers(),
        }
    }

    /// **Embeddings vía el proxy del Cloud** (§9.3/§9.4/§9.6 — el Hub nunca llama a un proveedor
    /// de embeddings directamente; va por el Cloud, que mide el coste en `AssistantUsage`).
    /// `POST /api/v1/hub/device/assistant/embeddings/` (verificado contra
    /// `cloud/apps/assistant/api/views.py::embed_texts_view`). El body es un
    /// [`EmbeddingsRequest`] (`{"texts":[…], "model"?}`) y la respuesta un
    /// [`EmbeddingsResponse`] (`{"embeddings":[[…]], "model"}`). El cuerpo lo construye el
    /// llamador (server) a partir de los textos a indexar (routing de módulos §9.2b o RAG §9.4).
    ///
    /// Es un endpoint **hub-scoped**: se firma con la credencial de **máquina** del hub
    /// (`X-Hub-Token`) cuando se llama desde el lifecycle de install (sin usuario logueado), o
    /// con el JWT de usuario para la embebida de la petición en query-time del router. El I/O de
    /// red lo hace el cliente HTTP del llamador (espejo de [`assistant_chat_stream`]).
    pub fn embeddings(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/assistant/embeddings/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Notificación WhatsApp PREMIUM de ERPlora vía el proxy del Cloud** (ADR-0012 + ADR-0006).
    /// Como el asistente, el Hub no habla con la Graph API de Meta directamente: la llamada sale
    /// por Cloud, que aplica `check_quota`, inyecta el token de Meta de ERPlora y bloquea al
    /// agotar la cuota (el Hub solo refleja el estado). `POST /api/v1/hub/device/notify/whatsapp/`
    /// con la credencial de **máquina** (`X-Hub-Token`, contexto hub-scoped sin usuario; el envío
    /// lo dispara una scheduled task / un listener del outbox, no un usuario).
    ///
    /// **Body** (lo construye el llamador desde la `NotifyIntent`; contrato verificado contra
    /// `saas/apps/whatsapp_inbox/api/notify.py`, saas#1353):
    /// `{"to": "+34…", "body": "texto libre"}` **o**
    /// `{"to": "+34…", "template": {"name": …, "language": …, "components": […]}}`, más un
    /// `phone_number_id` opcional (uno de los números de ESTE hub). Uno de `body`/`template` es
    /// obligatorio; el `template` es un **objeto** que el SaaS reenvía a Meta tal cual, no el
    /// nombre suelto. Respuesta: `{"message_id": "wamid…"}`.
    ///
    /// El resto de canales (email) tiene su propio proxy — ver [`CloudClient::notify_email`].
    pub fn notify_whatsapp(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/notify/whatsapp/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Email del negocio del hub vía el proxy del Cloud** (ADR-0283 §5 K4, saas#1347).
    ///
    /// Mismo patrón que el LLM y que WhatsApp: el hub **nunca** guarda credenciales de SES/SMTP.
    /// Pide al Cloud que envíe, y el Cloud pone el remitente verificado de ERPlora (`From`) y
    /// resuelve **en el servidor** el `Reply-To` del negocio (owner del hub →
    /// `BillingProfile.billing_email` → `SUPPORT_EMAIL`). Por eso el body **no** lleva `Reply-To`:
    /// un `Reply-To` libre convertiría un correo firmado por ERPlora en phishing.
    ///
    /// `POST /api/v1/hub/device/notify/email/` con la credencial de **máquina** (`X-Hub-Token` +
    /// `X-Hub-Id`, `IsHubMachine`). **Body**: `{"to": "a@b.c" | ["a@b.c", …], "subject": "…",
    /// "text": "…", "html": "…"?}`; respuesta `{"message_id": "<…>"}`.
    pub fn notify_email(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/notify/email/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **Inbound WhatsApp: the hub's own inbox** (ADR-0283 K1c, saas#1353).
    ///
    /// The SaaS may not call a hub (ADR-0213) and hubs sit behind NAT, so an incoming message
    /// waits in `WhatsAppInboundMessage` until its hub comes for it. `GET
    /// /api/v1/hub/device/whatsapp/inbox/` with the **machine** credential (`X-Hub-Token` +
    /// `X-Hub-Id`, `IsHubMachine`): the caller is the runtime's poller, with nobody logged in.
    ///
    /// Response (contract verified against `saas/apps/whatsapp_inbox/api/inbox.py`):
    /// `{"messages": [{"wa_message_id", "from", "payload", "received_at"}, …], "cursor": "<iso>"}`,
    /// oldest first, at most 100 per call.
    ///
    /// `after` is an **optional resume cursor**, never a substitute for the ack: the SaaS already
    /// filters out what this hub acked. Passing it means "skip everything at or before this
    /// instant", which is only safe for a deliberate replay — see [`CloudClient::whatsapp_inbox_ack`].
    pub fn whatsapp_inbox(&self, auth: &Auth, after: Option<&str>) -> PreparedRequest {
        let query = match after.map(str::trim).filter(|s| !s.is_empty()) {
            // The cursor is ISO-8601, so it carries `:` and (with an offset) `+`. A raw `+` in a
            // query string decodes to a SPACE, which `parse_datetime` rejects with a 400.
            Some(cursor) => format!("?after={}", encode_path_segment(cursor)),
            None => String::new(),
        };
        self.get(
            &format!("/api/v1/hub/device/whatsapp/inbox/{query}"),
            auth,
        )
    }

    /// **Acknowledge the inbound messages this hub has already ingested** (ADR-0283 K1c).
    ///
    /// `POST /api/v1/hub/device/whatsapp/inbox/ack/` with the machine credential. **Body**:
    /// `{"wa_message_ids": ["wamid.…", …]}` (500 max per call); response `{"acked": <count>}` —
    /// the number of rows this call actually changed, so a repeated ack answers `0` rather than
    /// failing. That is what makes the ack safe to retry after a crash.
    pub fn whatsapp_inbox_ack(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!(
                "{}/api/v1/hub/device/whatsapp/inbox/ack/",
                self.base_url
            ),
            headers: auth.headers(),
        }
    }

    /// **El plan del canal de WhatsApp y su consumo del mes** (hub#1089).
    ///
    /// `GET /api/v1/hub/device/whatsapp/plan/` con la credencial de **máquina** — el llamador es
    /// el tick de 24 h del runtime y ahí no hay ningún usuario logueado (ADR-0003). Sus dos
    /// hermanos de arriba ya funcionan así.
    ///
    /// Respuesta (contrato leído de `saas/apps/whatsapp_inbox/api/views.py`):
    /// `{"tier": {"slug", "max_billable_messages", "max_conversations", …} | null,
    ///   "usage": {"billable_messages", "month", …}, "available_tiers": [...]}`.
    ///
    /// **Se lee EN VIVO y no de un claim firmado a propósito.** `usage` es un contador que se
    /// mueve con cada mensaje: un claim de 24 h llegaría rancio. El tope del plan viaja con él
    /// porque los dos salen de la misma resolución de tier en el SaaS, y tener el número en dos
    /// sitios es como acaban divergiendo.
    pub fn whatsapp_plan(&self, auth: &Auth) -> PreparedRequest {
        self.get("/api/v1/hub/device/whatsapp/plan/", auth)
    }

    /// **Reporte de error del Hub → Cloud** (registro global de errores, "todo controlado"). El
    /// registro del Hub reenvía aquí TODO error (core, módulos, panics, frontend), best-effort.
    /// `POST /api/v1/hub/device/error-report/` con la credencial de **máquina** del hub
    /// (`X-Hub-Token` + `X-Hub-Id`, contexto hub-scoped sin usuario: el reporte lo dispara el
    /// runtime, no un JWT cloud fresco). El **body** es el contrato JSON
    /// `{ source, module_id, error_code, message, stack, severity, context, occurred_at }`, lo
    /// construye el llamador (server) a partir de su `ErrorEvent`. La respuesta
    /// (`{ ok, report_id, fingerprint, count, deduped, issue_queued }`) se ignora: cualquier 2xx
    /// es éxito. Espejo del estilo de [`notify_whatsapp`]: aquí solo se construye la petición
    /// (método/URL/cabeceras); el I/O del POST lo hace el cliente HTTP del llamador.
    pub fn report_error(&self, auth: &Auth) -> PreparedRequest {
        PreparedRequest {
            method: "POST",
            url: format!("{}/api/v1/hub/device/error-report/", self.base_url),
            headers: auth.headers(),
        }
    }

    /// **DEPRECADO** — apuntaba a un endpoint ficticio `…/versions/{version}/install/` que
    /// **no existe** en el Cloud. Usa el flujo real [`CloudClient::versions`] +
    /// [`CloudClient::download`] + [`CloudClient::mark_installed`]. Se mantiene solo para no
    /// romper a `erplora-installer` (que lo migrará por separado).
    #[deprecated(note = "endpoint ficticio; usar versions()/download()/mark_installed()")]
    pub fn request_install(&self, auth: &Auth, module_id: &str, version: &str) -> PreparedRequest {
        self.get(
            &format!("/api/v1/marketplace/modules/{module_id}/versions/{version}/install/"),
            auth,
        )
    }
}

/// Una versión de módulo tal como la devuelve el endpoint `versions/` del Cloud
/// (`ModuleVersionSerializer`). El `sha256` es **opcional**: el serializer público actual
/// (`cloud/apps/public/modules/serializers.py`) **no** lo incluye todavía — vive en el modelo
/// `ModuleVersion.sha256` y sí se expone en el endpoint de sync. Se parsea si está presente
/// para verificar integridad; si falta, el llamador debe decidir su política (ver server).
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct ModuleVersion {
    pub version: String,
    #[serde(default)]
    pub changelog: String,
    #[serde(default)]
    pub is_active: bool,
    #[serde(default)]
    pub file_size_bytes: u64,
    /// SHA256 hex esperado del ZIP. `None` si el Cloud no lo expone en este endpoint.
    #[serde(default)]
    pub sha256: Option<String>,
    /// Firma ed25519 detached del ZIP (autenticidad, hub#239). `None` si el Cloud aún no la
    /// expone o el publicador no firmó. Bajo `SignaturePolicy::Enforce` un `None` aquí aborta la
    /// instalación (DEFAULT deny); TODO: el serializer del Cloud debe exponerla siempre.
    #[serde(default)]
    pub signature: Option<ModuleSignature>,
}

impl ModuleVersion {
    /// Parsea la lista JSON del endpoint `versions/`.
    pub fn parse_list(json: &str) -> Result<Vec<ModuleVersion>, serde_json::Error> {
        serde_json::from_str(json)
    }
}

// ─────────────────── Install plan (ADR-0060, hub#68) ───────────────────

/// Body de `POST /api/v1/marketplace/install-plan/`. `version` ausente ⇒ el Cloud elige la activa.
#[derive(Debug, Clone, serde::Serialize, PartialEq, Eq)]
pub struct InstallPlanRequest {
    pub module_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    /// Set REAL de módulos instalados en el hub (registry del runtime = autoridad).
    pub installed: Vec<String>,
}

/// Petición del plan lista para ejecutar: cabeceras + body JSON (el I/O lo hace el llamador).
#[derive(Debug, Clone)]
pub struct PreparedInstallPlan {
    pub request: PreparedRequest,
    pub body: InstallPlanRequest,
}

/// Precio + puntero de compra que la UI enseña para un nodo NO entitled.
/// **Nunca se auto-cobra** (ADR-0060): el Hub solo muestra a dónde ir.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct InstallPlanPurchase {
    #[serde(default)]
    pub module_type: String,
    #[serde(default)]
    pub price: String,
    #[serde(default)]
    pub currency: String,
    #[serde(default)]
    pub purchase_url: String,
}

/// Un módulo del plan: SIEMPRE trae `version` + `sha256` (por eso el Hub se salta el
/// round-trip a `versions/`) más su entitlement.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct InstallPlanNode {
    pub module_id: String,
    pub version: String,
    /// SHA256 hex esperado del zip. Puede venir vacío si el Cloud aún no lo tiene publicado
    /// para esa versión; el llamador aplica su política (ADR-0015: sin hash no se instala).
    #[serde(default)]
    pub sha256: String,
    #[serde(default)]
    pub tier: String,
    #[serde(default)]
    pub entitled: bool,
    #[serde(default)]
    pub requires_purchase: bool,
    /// `"requested"` (el módulo pedido) o `"dependency"`.
    #[serde(default)]
    pub reason: String,
    #[serde(default)]
    pub purchase: Option<InstallPlanPurchase>,
    /// Firma ed25519 detached del zip. El serializer del Cloud **aún no la expone** en el plan
    /// (igual que `versions/`, ADR-0194): se parsea por compatibilidad hacia delante. Bajo
    /// `SignaturePolicy::Enforce` un `None` obliga al llamador a resolverla por `versions/` en
    /// vez de degradar en silencio.
    #[serde(default)]
    pub signature: Option<ModuleSignature>,
}

/// Plan topo-ordenado (dependencias primero, lo ya instalado excluido) — ADR-0060.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct InstallPlan {
    #[serde(default)]
    pub requested: String,
    /// Nodos a instalar, **en orden**. El Hub lo ejecuta tal cual: no reordena.
    #[serde(default)]
    pub plan: Vec<InstallPlanNode>,
    /// Lo que el hub ya tenía y por tanto NO entra en el plan.
    #[serde(default)]
    pub already_satisfied: Vec<String>,
    /// `true` si algún nodo exige compra: el Hub **no instala nada**.
    #[serde(default)]
    pub blocked: bool,
    #[serde(default)]
    pub blocked_on: Vec<String>,
}

impl InstallPlan {
    /// Parsea la respuesta JSON de `install-plan/`.
    pub fn parse(json: &str) -> Result<InstallPlan, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Respuesta del Portal al pedir instalar: dónde está el zip y su hash esperado. §2.2.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct InstallGrant {
    pub module_id: String,
    pub version: String,
    /// URL S3 firmada (temporal) para descargar el `module.zip`.
    pub download_url: String,
    /// SHA256 hex esperado del zip (integridad, §2.2).
    pub sha256: String,
    /// Firma ed25519 detached del `module.zip` (autenticidad, hub#239). Opcional: el Cloud la
    /// expone cuando el publicador firmó; si falta y la política es `Enforce`, la instalación se
    /// rechaza (`SignatureError::Missing`). Acepta ausencia en el JSON para compat hacia atrás.
    #[serde(default)]
    pub signature: Option<ModuleSignature>,
}

impl InstallGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// Verifica que `bytes` (el zip descargado) coincide con el `sha256` esperado.
    pub fn verify(&self, bytes: &[u8]) -> Result<(), IntegrityError> {
        verify_sha256(bytes, &self.sha256)
    }

    /// Verifica la **firma** ed25519 de `bytes` bajo `policy` (hub#239). Bajo `Enforce`, exige
    /// firma presente y válida contra el anillo; bajo `DevTrust`, acepta todo. Devuelve el
    /// `key_id` verificado bajo `Enforce` (`None` bajo `DevTrust`).
    pub fn verify_signature(
        &self,
        bytes: &[u8],
        policy: &SignaturePolicy,
    ) -> Result<Option<String>, SignatureError> {
        policy.check(self.signature.as_ref(), bytes)
    }
}

/// Respuesta de [`CloudClient::enroll`]: la credencial de máquina del hub. §2.3.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct EnrollGrant {
    pub hub_id: String,
    /// Token de aplicación del hub para el header `X-Hub-Token` (contexto máquina).
    pub cloud_api_token: String,
}

impl EnrollGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Respuesta de [`CloudClient::refresh`]: el par de tokens renovado por SimpleJWT (hub#15, §2.3).
/// El `refresh` viene rotado (la vista del Cloud es `RotatingTokenRefreshView`); el Hub debe
/// **persistir el refresh nuevo** y reintentar la petición original con el `access` nuevo.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct RefreshGrant {
    /// Access JWT nuevo (RS256, ~1h).
    pub access: String,
    /// Refresh token rotado. `None` si el Cloud no rota (no debería con la vista actual).
    #[serde(default)]
    pub refresh: Option<String>,
}

impl RefreshGrant {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Body de [`CloudClient::embeddings`]: los textos a embeber + el modelo opcional. El Cloud
/// usa su modelo por defecto (`text-embedding-3-small`, 1536 dims, casa con `vector(1536)` de
/// §9.4) si `model` es `None`. El límite de `texts` por llamada lo aplica el Cloud (256 hoy);
/// el llamador debe trocear lotes grandes. Se serializa al body de la petición.
#[derive(Debug, Clone, serde::Serialize, PartialEq, Eq)]
pub struct EmbeddingsRequest {
    pub texts: Vec<String>,
    /// Modelo de embeddings; `None` → el Cloud usa su `DEFAULT_EMBED_MODEL`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
}

impl EmbeddingsRequest {
    /// Construye una petición con los textos dados y el modelo por defecto del Cloud.
    pub fn new(texts: Vec<String>) -> Self {
        Self { texts, model: None }
    }
}

/// Respuesta de [`CloudClient::embeddings`]: un vector por cada texto de entrada (mismo orden) +
/// el modelo realmente usado. El hub almacena estos vectores en su índice local
/// (`erplora-vector`); NUNCA genera embeddings por su cuenta (§9.3).
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct EmbeddingsResponse {
    pub embeddings: Vec<Vec<f32>>,
    #[serde(default)]
    pub model: String,
}

impl EmbeddingsResponse {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

/// Response of [`CloudClient::fiscal_certificate`]: ERPlora's DELEGATED fiscal certificate for this
/// hub (ADR-0202 §2, saas#1125 — hub#317).
///
/// # This value holds someone else's PRIVATE KEY
///
/// Not the customer's: it is the key with which **ERPlora** identifies itself before the AEAT for
/// every hub under its power of attorney, so one leak compromises the fleet rather than one
/// business. Everything about this type is built around not spilling it:
///
/// - [`Debug`] is **hand-written and redacted** (see the impl below). The derived one would print
///   the container and the passphrase in full, and `Debug` is what ends up in a `tracing` field, in
///   an `unwrap()` panic message and in `{:?}` inside an error string.
/// - Nothing here is [`serde::Serialize`]: the value cannot be re-emitted into a response, a log
///   line or a bundle by accident.
/// - The caller must never put a parse/HTTP error's body into a message — see
///   `erplora-server`'s `fiscal_certificate` module, which is the only consumer.
#[derive(Clone, Deserialize)]
pub struct DelegatedCertificate {
    /// Monotonic version of the control plane (`DelegatedCertificate.version` in the SaaS). What the
    /// hub caches to answer «am I up to date?»; `0` never arrives here (the SaaS answers 404).
    pub version: i64,
    /// The PKCS#12 container, base64 — exactly the shape `certificate::set` stores.
    pub pkcs12_b64: String,
    /// Passphrase of that container.
    pub password: String,
    /// `notAfter` as the SaaS read it. **Advisory metadata, not the source of truth**: the hub
    /// derives the expiry from the container it actually stored (`certificate::expiry`), so a wrong
    /// or missing value here cannot make a hub believe a certificate is valid for longer than it is.
    #[serde(default)]
    pub not_after: Option<String>,
    /// **What kind of certificate this is** — `"seal"` (Sello de Entidad) or `"representative"`
    /// (ADR-0202 §2.1 — hub#470). The AEAT segregates its VERI\*FACTU entry point by this, and by
    /// nothing else: `www1`/`prewww1` for a natural person, `www10`/`prewww10` for a seal.
    ///
    /// **It exists because the slot does not answer it.** `delegated` says the control plane handed
    /// the container down, not what is inside it — and the `.p12` ERPlora invoices with today is a
    /// *representative* certificate, so treating the slot as the type would have sent the whole
    /// delegated fleet to `www10` and had every record rejected.
    ///
    /// Like `not_after`, it is **checked, not trusted**: `certificate::set_delegated` derives the
    /// same fact from the container and refuses to install when the two disagree. Unlike
    /// `not_after`, a value the hub cannot derive on its own is honoured — the declaration is what
    /// keeps a real seal working on a build whose classifier could not recognise it.
    ///
    /// `None` = an older control plane that says nothing (this field landed with hub#470). Then the
    /// container answers alone, and «cannot tell» routes to the holder's entry point.
    #[serde(default)]
    pub certificate_type: Option<String>,
}

/// Redacted on purpose — the derived `Debug` would print ERPlora's private key and its passphrase
/// (see the type's docs). What survives is what diagnosing a rotation actually needs and what the
/// heartbeat already announces in the clear: the version and the expiry.
///
/// The secrets are printed as a fixed `«···»`, never as a prefix and never as a length: a redaction
/// that leaked either would still be handing an attacker who reads the log a head start.
impl std::fmt::Debug for DelegatedCertificate {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("DelegatedCertificate")
            .field("version", &self.version)
            .field("pkcs12_b64", &"«···»")
            .field("password", &"«···»")
            .field("not_after", &self.not_after)
            .field("certificate_type", &self.certificate_type)
            .finish()
    }
}

impl DelegatedCertificate {
    pub fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}

#[cfg(test)]
mod tests {

    /// El hub tiene que poder saber SU PLAN sin agotarlo antes (saas#1540).
    ///
    /// El asistente solo descubría su tier cuando ya no quedaban mensajes: el hub nunca leía
    /// `assistant/config/`, así que no conocía ni su plan, ni su consumo, ni los planes de pago
    /// disponibles. Y sin un camino al checkout, el «ver planes» no llevaba a ninguna parte:
    /// el único momento de conversión del tier gratuito moría en una frase.
    #[test]
    fn assistant_config_and_checkout_are_hub_scoped_endpoints() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken { hub_id: "h1".into(), token: "t".into() };

        let cfg = c.assistant_config(&auth);
        assert_eq!(cfg.method, "GET", "leer el plan no muta nada");
        assert!(
            cfg.url.ends_with("/api/v1/hub/device/assistant/config/"),
            "la ruta real del SaaS: {}",
            cfg.url
        );

        let checkout = c.assistant_checkout(&auth);
        assert_eq!(checkout.method, "POST");
        assert!(
            checkout.url.ends_with("/api/v1/hub/device/assistant/subscription/checkout/"),
            "la ruta real del SaaS: {}",
            checkout.url
        );
    }
    use super::*;

    #[test]
    fn base_url_normalized_and_paths() {
        let c = CloudClient::new("https://erplora.com/");
        let r = c.bootstrap("hub-123", "tok");
        assert_eq!(r.url, "https://erplora.com/api/hubs/hub-123/bootstrap/");
        assert_eq!(r.method, "GET");
        // cabeceras de bootstrap: X-Hub-Id + X-Hub-Token
        assert!(r.headers.contains(&("X-Hub-Id", "hub-123".to_string())));
        assert!(r.headers.contains(&("X-Hub-Token", "tok".to_string())));
    }

    #[test]
    fn user_jwt_headers() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::UserJwt {
            hub_id: "h1".into(),
            access: "abc".into(),
        };
        let r = c.marketplace_modules(&auth, &CatalogQuery::new(CountryFilter::none(), ""));
        assert_eq!(r.url, "https://erplora.com/api/v1/marketplace/modules/");
        assert!(r
            .headers
            .contains(&("Authorization", "Bearer abc".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    /// ADR-0157 §7: alta de un miembro del hub. `POST /api/v1/hub/device/members/` firmado con la
    /// credencial de MÁQUINA (`X-Hub-Token`) — el alta la dispara el runtime, no un usuario con JWT
    /// fresco. El body `{email, role}` lo construye el llamador (server); aquí solo la petición.
    #[test]
    fn members_add_is_machine_token_post() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };
        let r = c.members_add(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/members/");
        assert!(r.headers.contains(&("X-Hub-Token", "tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        // Nunca lleva el JWT del usuario: es el HUB quien se autentica a sí mismo.
        assert!(!r.headers.iter().any(|(k, _)| *k == "Authorization"));
    }

    #[test]
    fn session_courier_is_a_machine_authenticated_post() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-secret".into(),
        };
        let r = c.session_courier(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/session-courier/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-secret".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "hub-1".to_string())));
    }

    /// ADR-0157 §7 (simetría obligatoria del deprovisioning): baja de un miembro por email.
    /// `DELETE /api/v1/hub/device/members/{email}/` con `X-Hub-Token`. El email va en el path
    /// **percent-encoded** (`@`, `+`… no son seguros en un segmento crudo).
    #[test]
    fn members_remove_is_machine_token_delete_with_encoded_email() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };
        let r = c.members_remove(&auth, "ana+x@bar.com");
        assert_eq!(r.method, "DELETE");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/members/ana%2Bx%40bar.com/",
            "el email va percent-encoded en el path (@→%40, +→%2B); el punto se preserva"
        );
        assert!(r.headers.contains(&("X-Hub-Token", "tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn public_marketplace_catalog_has_no_hub_credentials() {
        let c = CloudClient::new("https://erplora.com");
        let r = c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::none(), ""));
        assert_eq!(r.url, "https://erplora.com/api/v1/marketplace/catalog/");
        assert!(r.headers.is_empty());
    }

    // ── The catalogue is asked FOR A COUNTRY (ADR-0062, hub#69) ────────────────────────────────
    //
    // A hub in France was offered VeriFactu — a Spanish regime it cannot use — because the request
    // never said where the hub is. The country travels as a query param the RUNTIME appends from
    // `hub_settings.country_code`; the browser is not in the conversation.

    #[test]
    fn the_marketplace_is_asked_about_the_hub_country() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };
        let r = c.marketplace_modules(&auth, &CatalogQuery::new(CountryFilter::new("ES", ""), ""));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/modules/?countries=ES"
        );
    }

    /// 🔴 **The two sides spell a region differently and the mismatch is silent.** The hub stores
    /// `region_code` as FULL ISO-3166-2 — `ES-PV`, enforced by `validate_region` — while the
    /// marketplace filter takes the subdivision alone (`PV`), because that is what the regional
    /// scope of a `ModuleCountry` link holds.
    ///
    /// Sending `ES-PV` would not error anywhere: it would simply match no link, so a hub in the
    /// Basque Country would be offered **VeriFactu and not TicketBAI** — precisely backwards, and
    /// on the one screen where getting the regime wrong is expensive. The prefix is stripped here,
    /// at the boundary that knows both spellings.
    #[test]
    fn the_country_prefix_is_stripped_from_the_region_the_hub_stores() {
        let c = CloudClient::new("https://erplora.com");
        let r =
            c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new("ES", "ES-PV"), ""));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?countries=ES&region=PV"
        );
    }

    #[test]
    fn the_region_refines_the_country_when_the_hub_declares_one() {
        let c = CloudClient::new("https://erplora.com");
        let r =
            c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new("ES", "PV"), ""));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?countries=ES&region=PV",
            "a bare subdivision is already in the wire format and passes through"
        );
    }

    /// A prefix that is NOT this hub's country is left alone: it is not the `XX-` of ISO-3166-2
    /// being spelled out, it is a subdivision code that happens to contain a dash, and guessing
    /// would corrupt it.
    #[test]
    fn a_prefix_from_another_country_is_not_stripped() {
        let c = CloudClient::new("https://erplora.com");
        let r =
            c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new("PT", "ES-PV"), ""));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?countries=PT&region=ES-PV"
        );
    }

    // ── The catalogue is asked IN A LANGUAGE (hub#1003, saas#1457, ADR-0364) ───────────────────
    //
    // A Spanish hub listed «Añadir apps» with the titles and descriptions in English inside an
    // interface that is translated whole. The data travels translated now — the Cloud serves the
    // catalogue per language — but only for a caller that says which one. Silence means English.

    #[test]
    fn the_catalogue_is_asked_in_the_hubs_language() {
        let c = CloudClient::new("https://erplora.com");
        let r = c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::none(), "es"));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?lang=es"
        );
    }

    /// 🔴 **Where this breaks quietly.** `CountryFilter::query()` already opens the query string
    /// with `?` when there IS a filter and returns `""` when there is not, so appending `?lang=`
    /// produces `…?countries=ES?lang=es` for every hub that declares a country — i.e. all of them
    /// in production, and none of them in the test that only checks the no-filter case.
    #[test]
    fn the_language_joins_an_existing_filter_with_an_ampersand() {
        let c = CloudClient::new("https://erplora.com");
        let r =
            c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new("ES", "PV"), "es"));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?countries=ES&region=PV&lang=es"
        );
    }

    #[test]
    fn a_hub_that_names_no_language_asks_exactly_as_before() {
        let c = CloudClient::new("https://erplora.com");
        let r =
            c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new("ES", ""), ""));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?countries=ES",
            "no language = the Cloud serves its source language, which is today's behaviour"
        );
    }

    #[test]
    fn the_language_travels_on_the_credentialled_catalogue_too() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };
        let r =
            c.marketplace_modules(&auth, &CatalogQuery::new(CountryFilter::new("ES", ""), "es"));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/modules/?countries=ES&lang=es"
        );
    }

    /// The hub stores `language` as a bare code, but a setting is a place a human can type into.
    /// A regional tag is the language it belongs to — the Cloud collapses it the same way — and
    /// anything that is not language-shaped is dropped rather than sent, because a query param the
    /// server cannot parse is worse than no query param.
    #[test]
    fn the_language_is_normalised_before_it_goes_on_the_wire() {
        let c = CloudClient::new("https://erplora.com");
        for (stored, expected) in [
            (" ES ", "?lang=es"),
            ("es-ES", "?lang=es"),
            ("es_ES", "?lang=es"),
            ("", ""),
            ("   ", ""),
            ("not a language", ""),
            ("es&countries=FR", ""),
        ] {
            let r = c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::none(), stored));
            assert_eq!(
                r.url,
                format!("https://erplora.com/api/v1/marketplace/catalog/{expected}"),
                "stored language {stored:?}"
            );
        }
    }

    /// A region with no country is NOT sent: the SaaS ignores it (a region only means something
    /// inside its country) and sending it would suggest a filter that is not being applied.
    #[test]
    fn a_region_without_a_country_is_not_sent_at_all() {
        let c = CloudClient::new("https://erplora.com");
        let r = c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new("", "PV"), ""));
        assert_eq!(r.url, "https://erplora.com/api/v1/marketplace/catalog/");
    }

    /// **An unknown country must not silently become "the whole catalogue".** Whatever the hub has
    /// stored is normalised (trimmed, upper-cased) and sent; a hub whose country the SaaS does not
    /// know gets the universal modules back, which is the honest answer.
    #[test]
    fn the_country_is_normalised_before_it_travels() {
        let c = CloudClient::new("https://erplora.com");
        let r = c.public_marketplace_modules(&CatalogQuery::new(CountryFilter::new(" fr ", " oc "), ""));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/marketplace/catalog/?countries=FR&region=OC"
        );
    }

    /// hub#400: which build of the installable app the Cloud publishes. The version of a public
    /// download is public knowledge — it is printed on the store listing — so this carries no
    /// credential at all. That matters beyond tidiness: the answer has to reach a hub that is
    /// asleep, unenrolled or in demo, and a credential would turn "no update news" into a silent
    /// 401 on exactly those.
    #[test]
    fn the_published_app_release_is_asked_for_without_credentials() {
        let c = CloudClient::new("https://erplora.com");
        let r = c.app_release();
        assert_eq!(r.url, "https://erplora.com/api/v1/app/release/");
        assert_eq!(r.method, "GET");
        assert!(r.headers.is_empty());
    }

    /// The address is built from the configured Cloud, not baked: a hub pointed at a local SaaS
    /// (dev) or at a staging one must ask THAT one, or the check answers about another fleet.
    #[test]
    fn the_release_question_follows_the_configured_cloud() {
        let c = CloudClient::new("http://127.0.0.1:8001/");
        assert_eq!(
            c.app_release().url,
            "http://127.0.0.1:8001/api/v1/app/release/"
        );
    }

    /// ADR-0121: catálogo de blueprints (la «fuente nube» del import). Hub-scoped: el runtime
    /// se autentica a sí mismo con `X-Hub-Token` — el token NUNCA llega al navegador.
    #[test]
    fn blueprint_catalog_paths_are_hub_scoped() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "tok".into(),
        };

        let list = c.blueprints_catalog(&auth);
        assert_eq!(list.url, "https://erplora.com/api/v1/catalog/blueprints/");
        assert!(list.headers.contains(&("X-Hub-Token", "tok".to_string())));
        assert!(list.headers.contains(&("X-Hub-Id", "h1".to_string())));

        let dl = c.blueprint_download("barberia-basica", None, &auth);
        assert_eq!(
            dl.url,
            "https://erplora.com/api/v1/catalog/blueprints/barberia-basica/download/"
        );
        assert!(dl.headers.contains(&("X-Hub-Token", "tok".to_string())));

        // ADR-0212: el slug es único POR IDIOMA, así que el locale declarado tiene que viajar —
        // sin él el endpoint contesta 400 ante un slug que existe en dos idiomas.
        let localized = c.blueprint_download("restaurante", Some("es"), &auth);
        assert_eq!(
            localized.url,
            "https://erplora.com/api/v1/catalog/blueprints/restaurante/download/?locale=es"
        );
        // Un locale en blanco no ensucia la URL con un parámetro vacío.
        let blank = c.blueprint_download("restaurante", Some("  "), &auth);
        assert_eq!(
            blank.url,
            "https://erplora.com/api/v1/catalog/blueprints/restaurante/download/"
        );
    }

    #[test]
    fn real_install_flow_paths() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::UserJwt {
            hub_id: "h1".into(),
            access: "abc".into(),
        };

        let v = c.versions(&auth, "inventory");
        assert_eq!(v.method, "GET");
        assert_eq!(
            v.url,
            "https://erplora.com/api/v1/marketplace/modules/inventory/versions/"
        );

        let d = c.download(&auth, "inventory", "1.0.0");
        assert_eq!(
            d.url,
            "https://erplora.com/api/v1/marketplace/modules/inventory/download/?version=1.0.0"
        );

        let m = c.mark_installed(&auth, "inventory");
        assert_eq!(m.method, "POST");
        assert_eq!(
            m.url,
            "https://erplora.com/api/v1/marketplace/modules/inventory/mark_installed/"
        );

        let s = c.assistant_chat_stream(&auth);
        assert_eq!(s.method, "POST");
        assert_eq!(
            s.url,
            "https://erplora.com/api/v1/hub/device/assistant/chat/stream/"
        );
        assert!(s
            .headers
            .contains(&("Authorization", "Bearer abc".to_string())));
        assert!(s.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn embeddings_endpoint_and_machine_token() {
        // La embebida en el lifecycle de install va con la credencial de MÁQUINA del hub
        // (X-Hub-Token): no hay usuario logueado al instalar (§9.6 + ADR-0003).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.embeddings(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/assistant/embeddings/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn embeddings_request_serializes_with_and_without_model() {
        // Sin modelo: no se serializa la clave `model` (el Cloud usa su default).
        let req = EmbeddingsRequest::new(vec!["hello".into(), "world".into()]);
        let body = serde_json::to_value(&req).unwrap();
        assert_eq!(body["texts"][0], "hello");
        assert!(body.get("model").is_none(), "model None no se serializa");

        // Con modelo explícito.
        let req = EmbeddingsRequest {
            texts: vec!["x".into()],
            model: Some("custom".into()),
        };
        let body = serde_json::to_value(&req).unwrap();
        assert_eq!(body["model"], "custom");
    }

    /// ADR-0201 (7/11, hub#333): the hub uploads the identity ERPlora invoices. Machine
    /// credential, canonical path, POST — the `cloud_api_token` never reaches the browser, so
    /// this call is made BY the runtime, not proxied from the web app.
    #[test]
    fn fiscal_identity_uses_machine_token_and_canonical_path() {
        let c = CloudClient::new("https://erplora.com/");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.fiscal_identity(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/fiscal-identity/");
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
    }

    #[test]
    fn heartbeat_uses_machine_token_and_canonical_path() {
        let c = CloudClient::new("https://erplora.com/");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.heartbeat(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/heartbeat/");
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
    }

    #[test]
    fn embeddings_response_parses() {
        // El Cloud devuelve un vector por texto (mismo orden) + el modelo usado.
        let body =
            r#"{"embeddings":[[0.1,0.2,0.3],[0.4,0.5,0.6]],"model":"text-embedding-3-small"}"#;
        let resp = EmbeddingsResponse::parse(body).unwrap();
        assert_eq!(resp.embeddings.len(), 2);
        assert_eq!(resp.embeddings[0], vec![0.1, 0.2, 0.3]);
        assert_eq!(resp.model, "text-embedding-3-small");
    }

    #[test]
    fn notify_whatsapp_uses_machine_token() {
        // WhatsApp premium sale por el proxy de Cloud con la credencial de máquina del hub
        // (X-Hub-Token), no con JWT de usuario: lo dispara una scheduled task / el relay del
        // outbox, sin usuario logueado (ADR-0012/ADR-0003).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.notify_whatsapp(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/notify/whatsapp/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn notify_email_uses_machine_token() {
        // El email del negocio sale por el MISMO proxy y con la MISMA credencial: lo dispara el
        // relay del outbox, sin usuario logueado (ADR-0003). El hub no guarda credenciales de SES.
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.notify_email(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/notify/email/");
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        // Nunca el JWT de un usuario: el endpoint es `IsHubMachine`.
        assert!(!r.headers.iter().any(|(k, _)| *k == "Authorization"));
    }

    #[test]
    fn report_error_uses_machine_token() {
        // El reporte de error lo dispara el runtime con la credencial de MÁQUINA del hub
        // (X-Hub-Token), sin usuario logueado (registro global de errores → Cloud).
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.report_error(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/error-report/");
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
    }

    #[test]
    fn refresh_is_public_post_with_body_token() {
        // El refresh del JWT de usuario va sin cabeceras de auth (el refresh token va en el body).
        let c = CloudClient::new("https://erplora.com");
        let r = c.refresh();
        assert_eq!(r.method, "POST");
        assert_eq!(r.url, "https://erplora.com/api/v1/auth/refresh/");
        assert!(
            r.headers.is_empty(),
            "refresh no lleva Authorization ni X-Hub-Id"
        );

        // La respuesta (access nuevo + refresh rotado) parsea.
        let g = RefreshGrant::parse(r#"{"access":"a2","refresh":"r2"}"#).unwrap();
        assert_eq!(g.access, "a2");
        assert_eq!(g.refresh.as_deref(), Some("r2"));
    }

    #[test]
    fn module_version_list_parses_with_and_without_sha() {
        // El serializer público actual NO trae sha256 → debe parsear igualmente (None).
        let body = r#"[{"version":"1.0.0","changelog":"init","is_active":true,
            "file_size_bytes":1234,"created_at":"2026-01-01T00:00:00Z"}]"#;
        let vs = ModuleVersion::parse_list(body).unwrap();
        assert_eq!(vs.len(), 1);
        assert_eq!(vs[0].version, "1.0.0");
        assert!(vs[0].is_active);
        assert_eq!(vs[0].sha256, None);

        // Si el Cloud lo expone, se captura.
        let with_sha = r#"[{"version":"2.0.0","sha256":"deadbeef"}]"#;
        let vs = ModuleVersion::parse_list(with_sha).unwrap();
        assert_eq!(vs[0].sha256.as_deref(), Some("deadbeef"));
    }

    #[test]
    fn install_grant_parse_and_verify() {
        let body = r#"{"module_id":"inventory","version":"1.0.0",
            "download_url":"https://s3/x.zip","sha256":"PLACEHOLDER"}"#;
        // calcula el sha real de unos bytes y mete el grant con ese hash
        let bytes = b"zip-bytes";
        let real = crate::integrity::sha256_hex(bytes);
        let body = body.replace("PLACEHOLDER", &real);
        let g = InstallGrant::parse(&body).unwrap();
        assert_eq!(g.module_id, "inventory");
        assert!(g.verify(bytes).is_ok());
        assert!(g.verify(b"otros-bytes").is_err());
    }

    // ── ADR-0060: install plan (hub#68) ────────────────────────────────────────

    /// The request carries the hub's real installed set so the Cloud can drop what is already
    /// there, and `latest`/empty is sent as *absent* (the Cloud resolves the active version).
    #[test]
    fn install_plan_request_is_a_post_with_the_installed_set() {
        let c = CloudClient::new("https://erplora.com/");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let p = c.install_plan(&auth, "verifactu", "latest", &["taxes".to_string()]);
        assert_eq!(p.request.method, "POST");
        assert_eq!(
            p.request.url,
            "https://erplora.com/api/v1/marketplace/install-plan/"
        );
        assert!(p.request.headers.contains(&("X-Hub-Id", "h1".to_string())));
        assert_eq!(p.body.module_id, "verifactu");
        assert_eq!(
            p.body.version, None,
            "`latest` is omitted: the Cloud picks the active version"
        );
        assert_eq!(p.body.installed, ["taxes"]);

        // A pinned version travels as-is.
        let pinned = c.install_plan(&auth, "verifactu", "1.3.0", &[]);
        assert_eq!(pinned.body.version.as_deref(), Some("1.3.0"));
    }

    /// The response shape of `resolve_hub_install_plan` (saas `install_plan.py`): topo-ordered
    /// `plan`, `already_satisfied` excluded, and per-node entitlement with `purchase`.
    #[test]
    fn install_plan_response_parses_topo_order_and_purchase() {
        let body = r#"{
            "requested": "verifactu",
            "plan": [
              {"module_id":"taxes","version":"1.2.0","sha256":"aa","tier":"free",
               "entitled":true,"requires_purchase":false,"reason":"dependency"},
              {"module_id":"verifactu","version":"2.0.0","sha256":"bb","tier":"premium",
               "entitled":true,"requires_purchase":false,"reason":"requested"}
            ],
            "already_satisfied": ["sales"],
            "blocked": false,
            "blocked_on": []
        }"#;
        let plan = InstallPlan::parse(body).unwrap();
        assert_eq!(plan.requested, "verifactu");
        assert!(!plan.blocked);
        assert_eq!(plan.already_satisfied, ["sales"]);
        // Topo order is the Cloud's; the Hub executes it verbatim (dependency BEFORE requested).
        let ids: Vec<&str> = plan.plan.iter().map(|n| n.module_id.as_str()).collect();
        assert_eq!(ids, ["taxes", "verifactu"]);
        assert_eq!(plan.plan[0].reason, "dependency");
        assert_eq!(plan.plan[1].version, "2.0.0");
        assert_eq!(plan.plan[1].sha256, "bb");
        assert!(plan.plan[0].purchase.is_none());
    }

    /// A premium dependency the hub has not bought makes the whole plan `blocked` and carries the
    /// `purchase` pointer the UI needs. Never auto-charge (ADR-0060).
    #[test]
    fn install_plan_response_parses_blocked_with_purchase_pointer() {
        let body = r#"{
            "requested": "verifactu",
            "plan": [
              {"module_id":"invoice","version":"1.0.0","sha256":"aa","tier":"premium",
               "entitled":false,"requires_purchase":true,"reason":"dependency",
               "purchase":{"module_type":"premium","price":"9.00","currency":"EUR",
                           "purchase_url":"/marketplace/invoice/"}}
            ],
            "already_satisfied": [],
            "blocked": true,
            "blocked_on": ["invoice"]
        }"#;
        let plan = InstallPlan::parse(body).unwrap();
        assert!(plan.blocked);
        assert_eq!(plan.blocked_on, ["invoice"]);
        let purchase = plan.plan[0].purchase.as_ref().expect("purchase pointer");
        assert_eq!(purchase.price, "9.00");
        assert_eq!(purchase.currency, "EUR");
        assert_eq!(purchase.purchase_url, "/marketplace/invoice/");
    }

    // ── ERPlora's delegated fiscal certificate (ADR-0202 §2, hub#317) ─────────────────────────
    // The response of this endpoint is a PRIVATE KEY plus its passphrase, so the security tests
    // come first: what the type prints, and which credential the request carries.

    const SERVED_CERTIFICATE: &str = r#"{
        "version": 4,
        "pkcs12_b64": "TUlJS3RnSUJBekNDQ25JR0NTcUdTSWIzRFFFSEFhQ0NDbU1FZ2dwZg==",
        "password": "the-passphrase-of-erplora",
        "not_after": "2028-06-10"
    }"#;

    /// 🔒 **The private key must not be printable.** `Debug` is not cosmetic here: it is what a
    /// `tracing` field, an `unwrap()` panic and a `{:?}` inside an error string all reach for. A
    /// derived `Debug` would hand the container and the passphrase to every one of them, so the
    /// redaction is the type's job and not the discipline of each call site.
    #[test]
    fn debugging_the_delegated_certificate_never_prints_the_key_or_its_passphrase() {
        let cert = DelegatedCertificate::parse(SERVED_CERTIFICATE).unwrap();

        let printed = format!("{cert:?}");
        assert!(
            !printed.contains("TUlJS3RnSUJBekNDQ25JR0NTcUdTSWIzRFFFSEFhQ0NDbU1FZ2dwZg=="),
            "el Debug ha impreso el contenedor PKCS#12: {printed}"
        );
        assert!(
            !printed.contains("the-passphrase-of-erplora"),
            "el Debug ha impreso la contraseña: {printed}"
        );
        // It still has to be USEFUL for diagnosis: the version is the whole point of the fetch and
        // is not a secret (the heartbeat announces it in the clear).
        assert!(
            printed.contains('4'),
            "el Debug debería seguir diciendo la versión: {printed}"
        );
    }

    /// 🔒 A *fragment* of the passphrase must not leak either — a redaction that printed the first
    /// characters, or the length, would still be a redaction that helps whoever reads the log.
    #[test]
    fn the_redacted_debug_leaks_neither_a_prefix_nor_the_length_of_the_secret() {
        let cert = DelegatedCertificate::parse(SERVED_CERTIFICATE).unwrap();
        let printed = format!("{cert:?}");
        for fragment in ["the-passphrase", "the-pass", "TUlJS3Rn", "erplora-"] {
            assert!(
                !printed.contains(fragment),
                "el Debug filtra el fragmento {fragment:?}: {printed}"
            );
        }
        assert!(
            !printed.contains(&"the-passphrase-of-erplora".len().to_string()),
            "el Debug filtra la longitud de la contraseña: {printed}"
        );
    }

    /// 🔒 The MACHINE credential and nothing else: the SaaS pins `IsHubMachine` on this endpoint
    /// precisely so a member's JWT — which lives in a browser — can never be what asks for the key.
    #[test]
    fn fiscal_certificate_uses_the_machine_token_and_the_canonical_path() {
        let c = CloudClient::new("https://erplora.com/");
        let auth = Auth::HubToken {
            hub_id: "h1".into(),
            token: "machine-tok".into(),
        };
        let r = c.fiscal_certificate(&auth);
        assert_eq!(r.method, "GET");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/fiscal/certificate/"
        );
        assert!(r.headers.contains(&("X-Hub-Id", "h1".to_string())));
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-tok".to_string())));
        // Never the user's JWT: it is the HUB that authenticates itself.
        assert!(!r.headers.iter().any(|(k, _)| *k == "Authorization"));
    }

    /// The contract of saas#1125 §2.4, parsed as served.
    #[test]
    fn the_delegated_certificate_parses_the_served_contract() {
        let cert = DelegatedCertificate::parse(SERVED_CERTIFICATE).unwrap();
        assert_eq!(cert.version, 4);
        assert_eq!(
            cert.pkcs12_b64,
            "TUlJS3RnSUJBekNDQ25JR0NTcUdTSWIzRFFFSEFhQ0NDbU1FZ2dwZg=="
        );
        assert_eq!(cert.password, "the-passphrase-of-erplora");
        assert_eq!(cert.not_after.as_deref(), Some("2028-06-10"));
    }

    /// `not_after` is advisory (the hub reads the expiry from the container it stored), so its
    /// absence must not throw away a certificate that is otherwise perfectly usable. Unknown fields
    /// are tolerated too — the SaaS may add metadata without breaking deployed runtimes.
    #[test]
    fn a_certificate_without_not_after_still_parses() {
        let cert = DelegatedCertificate::parse(
            r#"{"version": 1, "pkcs12_b64": "QQ==", "password": "p", "issuer": "ERPlora SL"}"#,
        )
        .unwrap();
        assert_eq!(cert.version, 1);
        assert_eq!(cert.not_after, None);
    }

    /// Inbound WhatsApp (ADR-0283 K1c, saas#1353): the hub POLLS its own inbox with the MACHINE
    /// credential — the caller is the Rust runtime's poller, with nobody logged in. Contract read
    /// off `saas/apps/whatsapp_inbox/urls.py` + `api/inbox.py` on `origin/develop`.
    #[test]
    fn whatsapp_inbox_is_a_machine_authenticated_get() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-secret".into(),
        };
        let r = c.whatsapp_inbox(&auth, None);
        assert_eq!(r.method, "GET");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/whatsapp/inbox/");
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-secret".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "hub-1".to_string())));
        // Never the user JWT: the poller runs with no session at all.
        assert!(!r.headers.iter().any(|(k, _)| *k == "Authorization"));
    }

    /// `after` is an ISO-8601 cursor and travels in the query string, so `+` and `:` MUST be
    /// percent-encoded: a raw `+` decodes to a space server-side and `parse_datetime` then answers
    /// `400 invalid_cursor`.
    #[test]
    fn whatsapp_inbox_percent_encodes_the_after_cursor() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "h".into(),
            token: "t".into(),
        };
        let r = c.whatsapp_inbox(&auth, Some("2026-08-09T10:00:00+00:00"));
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/whatsapp/inbox/\
             ?after=2026-08-09T10%3A00%3A00%2B00%3A00"
        );
    }

    /// The channel's plan + live usage (hub#1089). MACHINE credential, like its two siblings
    /// above: the caller is the 24 h tick of the Rust runtime, where nobody is logged in. The
    /// SaaS half moved this endpoint from `IsHubMember` to `IsHubMachine` for exactly that.
    #[test]
    fn whatsapp_plan_is_a_machine_authenticated_get() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-secret".into(),
        };
        let r = c.whatsapp_plan(&auth);
        assert_eq!(r.method, "GET");
        assert_eq!(r.url, "https://erplora.com/api/v1/hub/device/whatsapp/plan/");
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-secret".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "hub-1".to_string())));
        // Never the user JWT: a background tick has no session to borrow one from.
        assert!(!r.headers.iter().any(|(k, _)| *k == "Authorization"));
    }

    /// The ack is what ENDS the redelivery loop. Same machine credential; the body
    /// (`{"wa_message_ids": [...]}`) is the caller's to build, as with every sibling here.
    #[test]
    fn whatsapp_inbox_ack_is_a_machine_authenticated_post() {
        let c = CloudClient::new("https://erplora.com");
        let auth = Auth::HubToken {
            hub_id: "hub-1".into(),
            token: "machine-secret".into(),
        };
        let r = c.whatsapp_inbox_ack(&auth);
        assert_eq!(r.method, "POST");
        assert_eq!(
            r.url,
            "https://erplora.com/api/v1/hub/device/whatsapp/inbox/ack/"
        );
        assert!(r
            .headers
            .contains(&("X-Hub-Token", "machine-secret".to_string())));
        assert!(r.headers.contains(&("X-Hub-Id", "hub-1".to_string())));
    }
}
