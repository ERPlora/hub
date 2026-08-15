//! **Personal = core.** Gestión de los usuarios del hub (`hub_user`) para la pantalla de Personal.
//!
//! La identidad del hub ya es del core (`identity.rs`, §2.9): `hub_user` + `hub_session` + los
//! permisos del rol. Lo que faltaba era la cara de gestión — *listar todos* los usuarios, darlos de
//! alta, editarlos y darlos de baja — que hasta ahora se pedía al **módulo `staff`**. Eso era un
//! error de dependencia: `staff` es un módulo de negocio (profesional reservable, comisiones,
//! horarios) con su propia navegación, así que en un hub sin él la pantalla salía vacía con «No se
//! pudo cargar el personal», y el owner/administrador —que entra por Cloud y **no tiene PIN**— no
//! aparecía por ninguna parte (la única lista era `pin_users`, solo los que tienen PIN).
//!
//! Contrato de esta capa:
//!  - [`list`] devuelve **todos** los usuarios de la BD del hub, activos e inactivos, con PIN o sin
//!    él, con su email del perfil (`hub_user_profile`).
//!  - La baja es **desactivar** (`is_active = 0`), nunca borrar: las sesiones, la auditoría
//!    (`created_by`/`updated_by`) y el historial de ventas apuntan a ese id.
//!  - Los **roles** son del core y salen del catálogo agregado ([`crate::roles`], hub#352):
//!    catálogo base ([`BASE_ROLES`]) ∪ los roles que **declaran** (`roles[]`) los módulos activos
//!    ∪ los que aún carga algún usuario y ya no declara nadie. Aquí solo se decoran con sus
//!    permisos efectivos y sus miembros.
use erplora_db::{DatabaseAdapter, Params};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::identity;
use crate::registry::Registry;
use crate::user_profile;

/// **Namespace reservado del core** en el dispatcher (ADR-0192). Ningún módulo puede registrar
/// queries bajo `hub.`: el instalador rechaza un módulo con ese id y el dispatcher resuelve el
/// prefijo antes de mirar el registry.
pub const CORE_NAMESPACE: &str = "hub.";

/// Permiso que abre las queries `hub.*`. Lo tiene **cualquier rol local** ([`permissions_for_role`]
/// lo añade siempre): el nombre y el rol de la plantilla ya son públicos en el grid de PIN del
/// login, así que no revela nada nuevo. Una **API key** no lo tiene — sus permisos salen del scope
/// de módulos que le dio el admin, y un tercero no lista el personal.
pub const VIEW_USERS_PERMISSION: &str = "hub.users.view";

/// Permiso que dice que una sesión **administra el hub**: identidad fiscal, plan, instalar apps,
/// alta y baja de personal. Lo concede [`crate::identity::session_permissions`] a exactamente los
/// roles que acepta [`is_admin_role`] — y nadie más puede darlo (ver la guarda del namespace del
/// core en [`crate::identity::permissions_for_role`]).
///
/// **Existe para poder FILTRAR con la misma regla con la que el servidor RECHAZA** (hub#435). El
/// rango que el core posee de verdad es uno solo —administra el hub o no—, y hasta ahora vivía
/// únicamente como una pregunta sobre el ROL (`server::auth::require_admin_session`), que
/// [`crate::registry::RequestContext`] no lleva. Sin él, `hub.setup.status` no tenía forma de saber
/// que «los datos de tu negocio» no son tarea de un camarero, y se los ofrecía con un botón a una
/// pantalla que le rechaza.
///
/// **No es una granularidad nueva.** Inventar tres permisos (ajustes, módulos, personal) fingiría
/// una división que ningún gate del hub aplica: los tres los guarda `require_admin_session`. Tres
/// nombres serían una segunda fuente de verdad sobre quién puede qué, que es justo lo que este
/// subsistema existe para cerrar.
pub const ADMINISTER_PERMISSION: &str = "hub.administer";

/// Queries del core disponibles en el dispatcher (`hub.<algo>`).
///
/// `setup.status` (hub#369) no es de personal: es el estado de configuración del hub. Vive en
/// [`crate::setup_status`] y solo se DESPACHA aquí, que es donde el runtime resuelve el namespace
/// reservado.
///
/// `approvals.list` (hub#512) es la puerta de lectura del registro de aprobaciones por PIN
/// (`_elevation_audit`, hub#362). Requiere `hub.administer` (nivel admin, no encargado): quién
/// aprobó qué es información sobre el personal.
const CORE_QUERIES: &[&str] = &["users.list", "roles.list", "setup.status", "approvals.list"];

/// Rol más alto del plano de **NEGOCIO**: administra el hub (identidad fiscal, plan, instalar
/// módulos, reset) y es lo que se siembra al crear el hub ([`identity::seed_owner`]) y el techo del
/// suelo que impone la cuenta ([`CLOUD_ROLE_FLOOR`]). Un único sitio donde está escrito el nombre,
/// para que esos tres usos no puedan divergir.
pub const ADMIN_ROLE: &str = "admin";

/// Roles que el core conoce siempre, aunque no haya ningún módulo instalado. Son **los tres** que
/// declaran los `role_permissions` de los módulos (24/24 del catálogo: `admin`/`manager`/
/// `employee`), y `admin` es además el que abre el gate de administración del Hub
/// ([`is_admin_role`]).
///
/// **`owner` NO está aquí** (paso 2b, hub#349). Era una **colisión de nombres** entre los dos
/// planos —el rol de la CUENTA en el SaaS y el rol del NEGOCIO en el hub compartían la palabra— y
/// solo funcionaba porque el gate del core lo trataba como `admin`: **ningún** módulo le concede
/// nada. `admin` pasa a ser lo más alto del plano de negocio, y la propiedad del hub sigue siendo
/// del plano de la cuenta (`HUB_OWNER_EMAIL`, ADR-0157), donde siempre estuvo.
///
/// Lo que ya llevaba `owner` **no pierde nada**: la migración de sistema **v12** lo renombra a
/// `admin` (mismo conjunto efectivo de permisos, ver [`is_admin_role`] y
/// [`identity::permissions_for_role`]), y el gate sigue reconociendo la grafía vieja para
/// cualquier fila que llegue sin pasar por la migración.
pub const BASE_ROLES: &[&str] = &[ADMIN_ROLE, "manager", "employee"];

/// Rol al que asciende el **suelo** que impone el rol de la cuenta en el Cloud (paso 2b regla C,
/// hub#347). Es [`ADMIN_ROLE`] y solo ese: la propiedad del hub sale del env sembrado al desplegar
/// (`HUB_OWNER_EMAIL`, ADR-0157) y **nunca** de un token. Vive aquí, junto a [`BASE_ROLES`], porque
/// el catálogo de roles es del runtime.
pub const CLOUD_ROLE_FLOOR: &str = ADMIN_ROLE;

/// ¿Este rol **administra el hub**? `admin` —y `owner`, que es su alias **legacy**—, insensible a
/// mayúsculas. Conjunto cerrado y conservador (ADR-0057 §6).
///
/// Una única definición para los tres sitios que la necesitan, para que no puedan divergir: el gate
/// de administración HTTP y las API keys (`server::auth`), la gestión de usuarios-login
/// (`server::hub_users`) y el suelo de rol del login cloud (`identity::get_or_link_cloud_user`),
/// que la usa para saber si el rol local ya está en el suelo o hay que subirlo.
///
/// **`owner` sigue aquí aunque haya salido de [`BASE_ROLES`]** (hub#349), por DOS motivos, y el
/// segundo no es legacy:
///
/// 1. **Filas del hub sin migrar.** La migración de sistema v12 renombra a `admin` las filas que lo
///    llevaban, pero una fila puede llegar al hub sin pasar por ella —un backup restaurado, una
///    importación, un runtime clavado a una imagen anterior escribiendo en la BD—. Resuelto por el
///    lado conservador: reconocerla no concede nada nuevo (`admin` ya concede exactamente lo mismo)
///    y **no** reconocerla dejaría al dueño de un hub sin migrar fuera de su propio negocio, sin
///    nadie que pueda reabrirle la puerta desde dentro.
/// 2. **El plano de la CUENTA conserva `owner`.** `server::auth::role_floor_for_cloud_login` usa
///    esta misma función sobre el rol que firma el SaaS (`owner`/`admin`/`member`), donde `owner`
///    es un valor vigente, no una reliquia: quitarlo de aquí dejaría al dueño de la cuenta sin
///    suelo en su propio hub. Solo `owner` salió del plano de NEGOCIO; el de la cuenta no cambia.
///
/// Que la misma pregunta sirva para los dos planos es deliberado —el conjunto es idéntico— pero es
/// el único punto donde se tocan: si algún día divergen, se parte en dos predicados.
///
/// Un rol **custom** de un módulo (`bartender`, `kitchen`…) devuelve `false` aunque su
/// `role_permissions` sea generoso: los permisos que declara un manifest no son la propiedad
/// "administra el hub", y darla por supuesta concedería administración sin que nadie la conceda.
pub fn is_admin_role(role: &str) -> bool {
    matches!(role.to_ascii_lowercase().as_str(), "owner" | "admin")
}

/// ¿Es `role` una clave que **posee el core**? El catálogo base ([`BASE_ROLES`]) más la grafía
/// legacy `owner`, insensible a mayúsculas.
///
/// Lo usa la validación del bloque `roles[]` de un manifest (paso 2b, hub#351): un módulo
/// **extiende** el catálogo base, nunca redefine una de sus entradas. Que `manager` signifique lo
/// mismo en los 24 módulos publicados es justamente lo que hace innecesaria una republicación.
pub fn is_base_role(role: &str) -> bool {
    BASE_ROLES
        .iter()
        .any(|base| base.eq_ignore_ascii_case(role))
        || is_admin_role(role)
}

/// ¿Puede un rol **declarado por un módulo** colgar de `role` (su `extends`)? Los roles base que
/// **no administran el hub**: hoy `manager` y `employee`.
///
/// Se deriva de [`is_base_role`] y [`is_admin_role`] en vez de copiar una lista, para que ampliar
/// el catálogo no deje esta regla atrás. La exclusión de `admin` es la misma guarda de hub#347
/// vista desde el manifest: administrar el hub sale del propio hub (`HUB_OWNER_EMAIL`, ADR-0157) y
/// del suelo que impone la cuenta, **nunca** de lo que declare un paquete de terceros. Sin ella,
/// un `module.zip` podría acuñar administradores con tres líneas de JSON.
pub fn is_extendable_base_role(role: &str) -> bool {
    is_base_role(role) && !is_admin_role(role)
}

/// Longitud válida de un PIN local (dígitos). El login es un pinpad numérico.
const PIN_LEN: std::ops::RangeInclusive<usize> = 4..=8;

/// Un usuario del hub tal y como lo pinta la pantalla de Personal.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HubUserRow {
    pub id: String,
    pub name: String,
    /// Email del perfil (`hub_user_profile`); vacío si el usuario aún no tiene perfil.
    pub email: String,
    pub role: String,
    /// Id del usuario en el Cloud si la identidad está vinculada al portal (owner/admin), o `None`
    /// para el personal **solo-local** (§2.9).
    pub cloud_user_id: Option<String>,
    pub is_active: bool,
    /// `true` si puede entrar con PIN local. El owner suele entrar por Cloud, así que es `false`.
    pub has_pin: bool,
    /// `true` si lleva una **placa** enrolada (hub#658). Hermana de `has_pin`: la pantalla enseña
    /// las dos por separado porque revocar una no toca la otra, y ese es el contrato entero.
    pub has_badge: bool,
    pub created_at: String,
    /// Por qué el backfill v19 NO pudo llevar el email de esta persona a donde se administra el
    /// acceso (hub#436/#463); `None` —lo normal— si no hay nada que resolver.
    ///
    /// Va **en la fila** y no en un endpoint aparte a propósito: `email` de arriba sale de un
    /// `COALESCE(hub_user.email, perfil.email)`, así que una fila así enseña una dirección de
    /// aspecto sano mientras su baja **no revoca** la membresía en el SaaS y su primer login
    /// aterriza en otra fila. Con el motivo pegado a la fila, el aviso no puede acabar junto a la
    /// persona equivocada, y la pantalla deja de prometer algo que no va a pasar.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub access_email_conflict: Option<crate::access_email::AccessEmailConflict>,
}

/// Un rol del hub con lo que concede y cuánta gente lo tiene.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HubRole {
    pub name: String,
    /// Etiqueta legible (inglés canónico).
    pub label: String,
    /// Rol base del que cuelga.
    pub extends: String,
    /// De dónde sale el rol.
    pub source: crate::roles::RoleSource,
    /// ¿Está activo en ESTE hub?
    pub active: bool,
    /// Permisos efectivos = unión de `role_permissions[rol]` de los módulos **activos**.
    pub permissions: usize,
    /// Usuarios **activos** con este rol.
    pub members: usize,
}

/// Alta de un usuario del hub. `pin` vacío = sin PIN (entra por Cloud), `email` vacío = sin perfil.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct NewHubUser {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub email: String,
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub pin: String,
    /// La **placa** (RFID/NFC/banda/iButton) que el lector rellena — y que se puede teclear, porque
    /// un iButton lleva el número grabado y un lector de banda no siempre está a mano (hub#658).
    /// Vacío = sin placa. Nunca sustituye al PIN.
    #[serde(default)]
    pub badge: String,
    /// The **«Local user»** checkbox of the alta (plan step 2b, hub#355): this person exists only
    /// in this hub's database — name + PIN, no email, nothing created in the SaaS.
    ///
    /// It is an explicit intent, not something inferred from an empty email, because the two
    /// mistakes it prevents are silent: an alta meant to be local that forgets the PIN produces a
    /// person who can never sign in, and an alta meant to be an account user that forgets the
    /// email produces a person the SaaS never invited. `false` (the default) keeps the generic
    /// alta exactly as it was — the account-user half is hub#356.
    #[serde(default)]
    pub local: bool,
}

/// Edición parcial: solo se toca lo que viene. `pin: Some("")` **retira** el PIN;
/// `badge: Some("")` **revoca la placa** sin tocar el PIN; `is_active: Some(false)` es la baja.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct UpdateHubUser {
    pub name: Option<String>,
    pub email: Option<String>,
    pub role: Option<String>,
    pub is_active: Option<bool>,
    pub pin: Option<String>,
    /// La placa. **Revocación independiente** (hub#658): `Some("")` la retira y el PIN sigue
    /// exactamente donde estaba — volver a solo-PIN es siempre posible. El caso Lightspeed
    /// L-Series (tarjeta irrevocable, producto descatalogado) es por qué esto no es opcional.
    pub badge: Option<String>,
}

fn invalid(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidPayload {
        name: "hub.users".into(),
        detail: detail.into(),
    }
}

/// A **stable** rejection of the alta/edit of a hub user (hub#139 `Domain`, HTTP 409): `code` is
/// what the shell programs and translates against, the message is only the English fallback.
///
/// Separate from [`invalid`] on purpose. `InvalidPayload` collapses every reason into a single
/// `invalid_payload` code, which is enough for "this field has the wrong shape" but not for the
/// rejections of the local-user alta (hub#355): the administrator has to be told **why** — a
/// duplicate PIN is fixed by typing another one, an administrative role is not fixable here at all,
/// and a name already known means "reinstate that person, do not create a second identity".
fn reject(code: &str, message: impl Into<String>) -> RuntimeError {
    RuntimeError::Domain {
        code: format!("{CORE_NAMESPACE}users.{code}"),
        message: message.into(),
    }
}

/// Nombre visible: obligatorio y acotado (el mismo límite que el perfil).
fn clean_name(value: &str) -> Result<String> {
    let name = value.trim();
    if name.is_empty() {
        return Err(invalid("el nombre es obligatorio"));
    }
    if name.chars().count() > 150 {
        return Err(invalid("el nombre supera 150 caracteres"));
    }
    Ok(name.to_string())
}

/// Rol: obligatorio y acotado. Esto es solo la **forma**; quién puede llevarlo lo decide
/// [`crate::roles::ensure_assignable`] (hub#352), que es donde vive el catálogo.
///
/// Sigue sin validarse contra un catálogo **cerrado**, a propósito: un módulo puede conceder
/// contra una clave que inventó otro, y hay hubs con roles tecleados a mano de antes de que
/// existiera el catálogo. Lo que la guarda estrecha es lo nuevo — un rol **declarado** que este
/// hub no ha encendido —, no todo lo que no reconozca.
fn clean_role(value: &str) -> Result<String> {
    let role = value.trim();
    if role.is_empty() {
        return Err(invalid("el rol es obligatorio"));
    }
    if role.chars().count() > 50 {
        return Err(invalid("el rol supera 50 caracteres"));
    }
    Ok(role.to_string())
}

/// PIN: vacío (sin PIN) o entre 4 y 8 **dígitos** — lo que acepta el pinpad del login — y que no
/// sea de los que se adivinan a la primera ([`is_guessable_pin`], hub#355).
fn clean_pin(value: &str) -> Result<String> {
    let pin = value.trim();
    if pin.is_empty() {
        return Ok(String::new());
    }
    if !pin.chars().all(|c| c.is_ascii_digit()) || !PIN_LEN.contains(&pin.chars().count()) {
        return Err(invalid("el PIN debe tener entre 4 y 8 dígitos"));
    }
    if is_guessable_pin(pin) {
        return Err(reject(
            "pin_too_simple",
            "this PIN is too easy to guess: avoid repeated digits (1111) and straight runs (1234)",
        ));
    }
    Ok(pin.to_string())
}

/// The two PIN shapes anybody tries first: **all the same digit** (`0000`, `9999`) and a **straight
/// run** up or down (`1234`, `4321`, `345678`). With four digits typed in front of customers these
/// are not a PIN, they are a formality — and the PIN is what attributes a sale to a person.
///
/// Checked at the only moment the hub ever sees the digits in clear (an alta or a PIN change from
/// Personal); afterwards they are a salted argon2id hash. Deliberately a **short, closed list** and
/// not a dictionary: a longer blacklist buys little and starts rejecting PINs people can remember,
/// which pushes the shop back to sharing one.
fn is_guessable_pin(pin: &str) -> bool {
    let digits: Vec<i64> = pin.chars().filter_map(|c| c.to_digit(10)).map(i64::from).collect();
    if digits.len() < 2 {
        return true;
    }
    let step_is = |step: i64| digits.windows(2).all(|pair| pair[1] - pair[0] == step);
    step_is(0) || step_is(1) || step_is(-1)
}

/// Longitud admisible de una placa. El suelo son 4 caracteres —por debajo se teclea a mano en
/// menos de lo que se tarda en decirlo— y el techo, holgado, cubre desde un UID EM4100 de 10
/// dígitos hasta la pista 2 de una banda magnética.
const BADGE_LEN: std::ops::RangeInclusive<usize> = 4..=64;

/// Placa: vacío (sin placa) o el volcado del lector — alfanumérico, con `-` y `_` tolerados.
///
/// Deliberadamente **no** se restringe a dígitos como el PIN: aquí caben un UID hex de MIFARE, el
/// número grabado de un iButton y el código de barras de un badge de Odoo. Lo que sí se cierra es
/// el conjunto de caracteres, porque lo que llega es una **ráfaga de teclado** de un dispositivo
/// que nadie audita: un separador o un carácter de control colado ahí acabaría en la traza, y la
/// traza es el motivo por el que existe esta credencial.
fn clean_badge(value: &str) -> Result<String> {
    let badge = value.trim();
    if badge.is_empty() {
        return Ok(String::new());
    }
    if !BADGE_LEN.contains(&badge.chars().count()) {
        return Err(invalid("la placa debe tener entre 4 y 64 caracteres"));
    }
    if !badge
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err(invalid(
            "la placa solo admite letras, dígitos, `-` y `_`",
        ));
    }
    Ok(badge.to_string())
}

/// Email: vacío u opcional con forma mínima válida (misma regla que el perfil propio).
fn clean_email(value: &str) -> Result<String> {
    let email = value.trim();
    if email.is_empty() {
        return Ok(String::new());
    }
    if email.chars().count() > 254
        || !email.contains('@')
        || email.starts_with('@')
        || email.ends_with('@')
    {
        return Err(invalid("email no válido"));
    }
    Ok(email.to_string())
}

/// Parte el nombre visible en nombre/apellidos para el perfil (misma convención que `user_profile`).
fn split_name(name: &str) -> (String, String) {
    let mut parts = name.splitn(2, char::is_whitespace);
    (
        parts.next().unwrap_or_default().to_string(),
        parts.next().unwrap_or_default().trim().to_string(),
    )
}

/// Rechaza dos usuarios **activos** con el mismo nombre: el login por PIN resuelve por nombre
/// (`identity::verify_pin`), así que un duplicado haría ambiguo quién entra.
async fn ensure_name_is_free(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    name: &str,
    excluding_id: Option<&str>,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("id".into(), json!(excluding_id.unwrap_or_default()));
    let res = db
        .query(
            "SELECT id FROM hub_user \
              WHERE hub_id = :hub_id AND name = :name AND is_active = 1 AND id != :id",
            &p,
        )
        .await?;
    if res.rows.is_empty() {
        Ok(())
    } else {
        Err(invalid(format!("ya hay un usuario activo llamado «{name}»")))
    }
}

/// Rechaza un PIN que ya abre la sesión de **otro usuario activo** (hub#355). Se comprueba en el
/// alta y en cada cambio de PIN: sin la segunda mitad, la primera es decorativa (se da de alta con
/// un PIN libre y se edita acto seguido al del encargado). Ver
/// [`identity::pin_is_taken`] para por qué no se puede resolver con una restricción de la BD.
async fn ensure_pin_is_free(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    pin: &str,
    excluding_id: Option<&str>,
) -> Result<()> {
    if identity::pin_is_taken(db, hub_id, pin, excluding_id).await? {
        return Err(reject(
            "pin_in_use",
            "another active user already has this PIN: a PIN says who is at the till, so no two \
             people can share one",
        ));
    }
    Ok(())
}

/// El gemelo de [`ensure_pin_is_free`] para la placa (hub#658), y por una razón más fuerte: un PIN
/// se comparte contándolo, una tarjeta se comparte prestándola. Dos filas detrás de una placa
/// harían que la traza —lo único que contesta «alguien usó mi tarjeta»— nombrase a quien la BD
/// devolviese primero.
async fn ensure_badge_is_free(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    badge: &str,
    excluding_id: Option<&str>,
) -> Result<()> {
    if identity::badge_is_taken(db, hub_id, badge, excluding_id).await? {
        return Err(reject(
            "badge_in_use",
            "another active user already carries this badge: a badge says who is at the till, so \
             no two people can share one",
        ));
    }
    Ok(())
}

/// Rechaza la edición que dejaría a alguien **con placa y sin ninguna otra puerta** (hub#658).
///
/// `pin`/`badge` son lo que trae la edición (`None` = no se toca); `current` es la fila tal y como
/// está. El veredicto se emite sobre el estado RESULTANTE, que es lo que permite retirar la placa y
/// el PIN en la misma edición —una persona que no inicia sesión es un registro legítimo— y lo que
/// impide retirar solo el PIN.
///
/// El email cuenta como salida: quien entra con su cuenta de ERPlora conserva una puerta pase lo
/// que pase con la tarjeta. La guarda es sobre el **respaldo**, no sobre el PIN.
fn ensure_the_badge_is_not_the_only_way_in(
    current: &HubUserRow,
    pin: Option<&str>,
    badge: Option<&str>,
) -> Result<()> {
    let will_have_badge = match badge {
        Some(value) => !value.is_empty(),
        None => current.has_badge,
    };
    let will_have_pin = match pin {
        Some(value) => !value.is_empty(),
        None => current.has_pin,
    };
    if !will_have_badge || will_have_pin || !current.email.trim().is_empty() {
        return Ok(());
    }
    Err(reject(
        "badge_without_fallback",
        "a badge cannot be somebody's only way in: a lost card would lock them out of their own \
         till. Keep their PIN, give them an account, or remove the badge as well.",
    ))
}

/// Lo que hace admisible el alta de un **usuario LOCAL** (plan paso 2b, hub#355) — la casilla
/// «Local user»: alguien que existe solo en la BD de este hub y que, en cuanto entra, puede operar
/// la caja. Cuatro guardas, todas resueltas por el lado conservador:
///
/// 1. **Sin email.** Un email aquí sería una cuenta de ERPlora que nadie invitó: el SaaS es la
///    fuente de verdad del ACCESO (ADR-0157 §7) y este alta no lo llama nunca. Pedir la cuenta es
///    otro alta (hub#356), no un campo que se rellena sin querer.
/// 2. **Con PIN, obligatorio.** Un usuario local sin PIN no puede entrar por ningún sitio: sería
///    una ficha muda. En el alta genérica un usuario sin PIN y sin cuenta es un estado legítimo
///    («persona que no inicia sesión»); marcar «Local user» dice justo lo contrario.
/// 3. **Nunca administra el hub.** Administrar —identidad fiscal, plan, instalar módulos, borrar
///    los datos— es del plano de la CUENTA: se siembra desde `HUB_OWNER_EMAIL` (ADR-0157) y lo sube
///    el suelo del login cloud (hub#347), y hub#351 ya impide que un manifest acuñe administradores.
///    Cuatro dígitos tecleados delante de clientes no pueden ser la tercera vía.
/// 4. **Un nombre que el hub no conozca ya**, ni siquiera desactivado. Es la puerta de atrás de la
///    regla D (hub#348): dar de alta un homónimo al lado de quien acaba de ser desactivado —por el
///    admin o por el SaaS— le devuelve un PIN que funciona y deja DOS identidades para una persona,
///    justo lo que «una persona = una fila `hub_user`» existe para evitar. Se reincorpora la fila,
///    que es una decisión explícita y auditada del administrador.
async fn ensure_local_identity(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    name: &str,
    email: &str,
    pin: &str,
    role: &str,
) -> Result<()> {
    if !email.is_empty() {
        return Err(reject(
            "local_has_email",
            "a local user has no email: they exist only in this hub. Invite them as an account \
             user instead",
        ));
    }
    if pin.is_empty() {
        return Err(reject(
            "local_needs_pin",
            "a local user signs in with a PIN: without one, nobody could ever use this account",
        ));
    }
    if is_admin_role(role) {
        return Err(reject(
            "local_cannot_administer",
            "a local user cannot administer the hub: administration comes from an ERPlora account, \
             never from a PIN",
        ));
    }
    if identity::name_is_known(db, hub_id, name).await? {
        return Err(reject(
            "name_taken",
            format!(
                "this hub already knows somebody called «{name}»: edit that user — reinstate them \
                 if they were deactivated — instead of creating a second identity for one person"
            ),
        ));
    }
    Ok(())
}

/// ¿Puede el SaaS poner este rol en una membresía? Exactamente [`BASE_ROLES`], insensible a
/// mayúsculas (plan paso 2b, hub#356).
///
/// **No** se deriva de [`is_base_role`] a propósito: aquel admite además la grafía **legacy**
/// `owner`, y `owner` es justo lo que el SaaS nunca concede — la propiedad del hub sale de
/// `HUB_OWNER_EMAIL` (ADR-0157), no de una invitación. Este conjunto es el espejo del `HUB_ROLES`
/// del SaaS (`services/members.py`), que responde **400** a cualquier otra cosa.
///
/// Un rol **declarado por un módulo** (`kitchen`, `waiter`…) es un rol de ESTE hub y de ninguno
/// más: el SaaS no lo conoce, así que una invitación con él no llega a existir. Es lo que hace que
/// los roles de módulo sean del personal LOCAL y el usuario de cuenta lleve uno de los tres.
pub fn is_grantable_account_role(role: &str) -> bool {
    BASE_ROLES.iter().any(|base| base.eq_ignore_ascii_case(role))
}

/// [`is_grantable_account_role`] como guarda: el rechazo estable que comparten las **dos** puertas
/// del alta de un usuario de cuenta — `POST /api/hub/users` (Personal) y `POST /api/members`
/// (ADR-0157 §7, vía [`identity::create_login_user`]).
///
/// Se rechaza **antes** de escribir nada. Dejarlo pasar significaría crear la fila local, llamar al
/// SaaS y llevarse un 400: una persona con ficha, con email, sin membresía y sin invitación — y sin
/// forma de entrar. Media provisión es peor que ninguna.
pub(crate) fn ensure_account_role_is_grantable(role: &str) -> Result<()> {
    if is_grantable_account_role(role) {
        return Ok(());
    }
    Err(reject(
        "account_role_not_grantable",
        format!(
            "«{role}» is not a role an ERPlora account can carry in this hub: invite them as \
             admin, manager or employee — roles a module declares belong to local staff"
        ),
    ))
}

/// Lo que hace admisible el alta de un **usuario de CUENTA** (plan paso 2b, hub#356) — la casilla
/// «Local user» SIN marcar: alguien que entra con su cuenta de ERPlora, a quien el SaaS invita por
/// email. Es la frontera con el SaaS, así que las tres guardas se resuelven por su lado:
///
/// 1. **Email obligatorio.** Sin la casilla, el email ES la identidad: es por lo que el SaaS crea la
///    cuenta, manda la invitación y enlaza la membresía, y por lo que el primer login encuentra
///    esta fila. Un alta de cuenta sin email produce a alguien a quien nadie invitó y que no puede
///    entrar por ningún sitio — el descuido silencioso que la casilla explícita existe para evitar
///    (el otro, un local sin PIN, lo cierra [`ensure_local_identity`]).
/// 2. **Un rol que el SaaS pueda conceder** ([`ensure_account_role_is_grantable`]).
/// 3. **Un email que el hub no conozca ya**, activo **o dado de baja**, ignorando mayúsculas. Es el
///    gemelo de `name_taken` y cierra la misma puerta de atrás por el otro lado: el SaaS **borra la
///    fila** al revocar una membresía, así que para él una segunda invitación es una membresía
///    nueva y limpia — nada allí puede notar que este hub había cerrado esa puerta (regla D,
///    hub#348). Reincorporar es [`update`]: una decisión explícita y auditada del administrador,
///    no el efecto de volver a teclear un email.
async fn ensure_account_identity(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    email: &str,
    role: &str,
) -> Result<()> {
    if email.is_empty() {
        return Err(reject(
            "account_needs_email",
            "an account user signs in with their ERPlora account: without an email there is \
             nobody to invite. Tick «Local user» to create somebody who works this hub with a PIN",
        ));
    }
    ensure_account_role_is_grantable(role)?;
    ensure_email_is_free(db, hub_id, email, None).await
}

/// Rechaza un email que este hub ya conoce (activo o no). Compartido por el alta y la edición: sin
/// la segunda mitad la primera es teatro —dos altas con emails distintos y una editada al del
/// otro— y el hub acaba con dos filas peleándose por una sola membresía.
async fn ensure_email_is_free(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    email: &str,
    excluding_id: Option<&str>,
) -> Result<()> {
    if !identity::email_is_known(db, hub_id, email, excluding_id).await? {
        return Ok(());
    }
    Err(reject(
        "email_taken",
        format!(
            "this hub already knows «{email}»: edit that user — reinstate them if they were \
             deactivated — instead of inviting a second identity for one person"
        ),
    ))
}

/// Todos los usuarios del hub, activos primero y por nombre. Incluye al owner cloud (sin PIN) y a
/// los desactivados (marcados `is_active = false`) — la pantalla de Personal los muestra todos.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<HubUserRow>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            // `hub_user.email` PRIMERO, el perfil como respaldo (hub#356). Leer solo el perfil
            // dejaba sin email en pantalla al owner sembrado desde `HUB_OWNER_EMAIL` (ADR-0157) y a
            // todo el que entrase por `/api/members` —que escriben la columna de identidad y no el
            // perfil—, y eso NO era cosmético: `sync_access` se salta la llamada al SaaS cuando la
            // fila trae el email vacío, así que su BAJA nunca revocaba su membresía.
            "SELECT u.id AS id, u.name AS name, u.role AS role, u.cloud_user_id AS cloud_user_id, \
                    u.is_active AS is_active, u.created_at AS created_at, \
                    CASE WHEN u.pin_hash IS NULL OR u.pin_hash = '' THEN 0 ELSE 1 END AS has_pin, \
                    CASE WHEN u.badge_hash IS NULL OR u.badge_hash = '' THEN 0 ELSE 1 END \
                      AS has_badge, \
                    COALESCE(NULLIF(u.email, ''), p.email, '') AS email \
               FROM hub_user u \
               LEFT JOIN hub_user_profile p ON p.user_id = u.id AND p.hub_id = :hub_id \
              WHERE u.hub_id = :hub_id \
              ORDER BY u.is_active DESC, u.name",
            &p,
        )
        .await?;
    // hub#463 — las filas que el backfill v19 dejó en paz, por id. Es una consulta más sobre dos
    // tablas pequeñas y solo en una pantalla de administración; el precio de NO hacerla es una lista
    // en la que una fila irrevocable es idéntica a una sana.
    let conflicts = crate::access_email::unresolved(db, hub_id).await?;
    Ok(res
        .rows
        .iter()
        .map(|r| {
            let id = r["id"].as_str().unwrap_or_default().to_string();
            HubUserRow {
                access_email_conflict: conflicts
                    .iter()
                    .find(|c| c.user_id == id)
                    .map(|c| c.reason),
                id,
                name: r["name"].as_str().unwrap_or_default().to_string(),
                email: r["email"].as_str().unwrap_or_default().to_string(),
                role: r["role"].as_str().unwrap_or_default().to_string(),
                cloud_user_id: r["cloud_user_id"].as_str().map(ToString::to_string),
                is_active: truthy(&r["is_active"]),
                has_pin: truthy(&r["has_pin"]),
                has_badge: truthy(&r["has_badge"]),
                created_at: r["created_at"].as_str().unwrap_or_default().to_string(),
            }
        })
        .collect())
}

/// SQLite devuelve enteros donde Postgres puede devolver booleanos: acepta ambos.
fn truthy(value: &serde_json::Value) -> bool {
    value.as_bool().unwrap_or_else(|| value.as_i64().unwrap_or(0) != 0)
}

/// Un usuario por id (cualquier estado). `None` si no existe en este hub.
pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, user_id: &str) -> Result<Option<HubUserRow>> {
    Ok(list(db, hub_id).await?.into_iter().find(|u| u.id == user_id))
}

/// Alta de usuario: valida, crea la identidad (con PIN si lo trae) y guarda su email.
///
/// El alta es **exhaustiva** desde hub#356: la casilla **«Local user»** (`input.local`) elige entre
/// las dos identidades del paso 2b, y las dos son la MISMA fila `hub_user`.
///
///  - `local: true` → nombre + PIN y nada más, con las guardas de [`ensure_local_identity`]
///    (hub#355). No se llama al SaaS: no hay cuenta que invitar.
///  - `local: false` → **usuario de cuenta**: email obligatorio, con las guardas de
///    [`ensure_account_identity`]. La invitación la manda el SaaS; quien la dispara es la capa HTTP
///    (`server::hub_users::create_user` → `members::notify_member_added`), que es la que tiene la
///    credencial de máquina. La **contraseña la pone el invitado**: el hub nunca la ve ni la manda.
///
/// Ya no queda un tercer estado creable —«sin PIN y sin cuenta»—, que es el que el plan llama
/// descuido silencioso: una ficha que no puede entrar por ningún sitio y que nada en pantalla
/// distingue de un alta correcta. Las filas que ya lo están (a las que se les retiró el PIN, p. ej.)
/// siguen existiendo y se siguen editando.
///
/// El PIN es **opcional en las dos** —un usuario de cuenta que atiende la barra lo necesita en el
/// dispositivo compartido— y, si viene, pasa por el mismo embudo: forma, no adivinable
/// ([`clean_pin`]) y **suyo** ([`ensure_pin_is_free`]).
pub async fn create(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    input: &NewHubUser,
) -> Result<String> {
    let name = clean_name(&input.name)?;
    let role = clean_role(&input.role)?;
    let pin = clean_pin(&input.pin)?;
    let badge = clean_badge(&input.badge)?;
    let email = clean_email(&input.email)?;
    crate::roles::ensure_assignable(db, registry, hub_id, &role).await?;
    if input.local {
        ensure_local_identity(db, hub_id, &name, &email, &pin, &role).await?;
    } else {
        ensure_account_identity(db, hub_id, &email, &role).await?;
        ensure_name_is_free(db, hub_id, &name, None).await?;
    }
    ensure_pin_is_free(db, hub_id, &pin, None).await?;
    ensure_badge_is_free(db, hub_id, &badge, None).await?;

    let id = identity::create_user(db, hub_id, &name, &pin, &role, None).await?;
    if !email.is_empty() {
        write_email(db, hub_id, &id, &name, &email).await?;
    }
    if !badge.is_empty() {
        identity::set_badge(db, hub_id, &id, &badge).await?;
    }
    Ok(id)
}

/// Guarda el email en los **dos** sitios que lo necesitan, siempre a la vez: `hub_user.email` —la
/// clave por la que se administra el ACCESO (login por email, revocación, `/api/members`)— y
/// `hub_user_profile` —lo que la persona ve en su perfil—. Son campos distintos, y escribir uno
/// solo es un desacuerdo silencioso: la pantalla enseña un email y el SaaS trabaja con otro.
async fn write_email(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    user_id: &str,
    name: &str,
    email: &str,
) -> Result<()> {
    identity::set_email(db, hub_id, user_id, email).await?;
    let (first, last) = split_name(name);
    user_profile::set_identity(db, hub_id, user_id, &first, &last, email).await
}

/// Edición parcial de un usuario existente. Devuelve la fila resultante.
pub async fn update(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    user_id: &str,
    input: &UpdateHubUser,
) -> Result<HubUserRow> {
    let current = get(db, hub_id, user_id)
        .await?
        .ok_or_else(|| RuntimeError::Other("usuario no encontrado".into()))?;

    let name = match &input.name {
        Some(value) => clean_name(value)?,
        None => current.name.clone(),
    };
    let role = match &input.role {
        Some(value) => clean_role(value)?,
        None => current.role.clone(),
    };
    let email = match &input.email {
        Some(value) => Some(clean_email(value)?),
        None => None,
    };
    let pin = match &input.pin {
        Some(value) => Some(clean_pin(value)?),
        None => None,
    };
    let badge = match &input.badge {
        Some(value) => Some(clean_badge(value)?),
        None => None,
    };
    let is_active = input.is_active.unwrap_or(current.is_active);
    // El rol solo pasa por el catálogo cuando la edición lo CAMBIA (hub#352): revalidar el rol que
    // ya tenía la fila convertiría desinstalar un módulo en «este usuario ya no se puede editar»,
    // y quien queda con un rol huérfano es justo a quien hay que poder reasignar.
    if input.role.is_some() && role != current.role {
        crate::roles::ensure_assignable(db, registry, hub_id, &role).await?;
    }
    if is_active && name != current.name {
        ensure_name_is_free(db, hub_id, &name, Some(user_id)).await?;
    }
    // Un PIN nuevo tiene que seguir siendo suyo (hub#355). Se comprueba ANTES de escribir nada:
    // si el alta rechaza el PIN del encargado pero la edición lo acepta, la guarda no existe.
    if let Some(pin) = pin.as_deref() {
        ensure_pin_is_free(db, hub_id, pin, Some(user_id)).await?;
    }
    // Y una placa nueva tiene que seguir siendo suya, por lo mismo (hub#658).
    if let Some(badge) = badge.as_deref() {
        ensure_badge_is_free(db, hub_id, badge, Some(user_id)).await?;
    }
    // **La placa nunca puede quedarse como la ÚNICA vía de entrada** (hub#658). Square directamente
    // no lo permite, y el caso Lightspeed L-Series es por qué: una tarjeta que se pierde y ninguna
    // otra puerta = una persona fuera de su propia caja, sin gesto en ninguna pantalla que la deje
    // volver. El estado se juzga DESPUÉS de aplicar la edición —no campo a campo— para que quitar la
    // placa y el PIN a la vez siga siendo legítimo: lo que se rechaza es el resultado.
    ensure_the_badge_is_not_the_only_way_in(&current, pin.as_deref(), badge.as_deref())?;
    // Y un email nuevo tiene que seguir siendo suyo, por lo mismo (hub#356): mover el email de una
    // ficha al de otra dejaría dos filas peleándose por una sola membresía del SaaS, y el login por
    // email resolvería a la que devolviese primero la BD.
    if let Some(email) = email.as_deref().filter(|e| !e.is_empty()) {
        ensure_email_is_free(db, hub_id, email, Some(user_id)).await?;
    }

    let mut p = Params::new();
    p.insert("id".into(), json!(user_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("role".into(), json!(role));
    p.insert("is_active".into(), json!(i64::from(is_active)));
    // `cloud_revoked_at` (paso 2b regla D, hub#348) solo se toca cuando la edición **decide sobre
    // la puerta** (`is_active` presente): dar de baja desde aquí es una decisión **del hub**, que
    // ningún login reabre, y reactivar cierra un episodio de revocación del SaaS para que la marca
    // no sobreviva a una baja posterior. Una edición que NO habla de la puerta —renombrar, cambiar
    // el rol— la deja como está: reetiquetar de paso una revocación del cloud como baja del hub
    // dejaría al usuario varado, con su membresía de vuelta y la puerta cerrada sin motivo visible.
    let touches_the_door = input.is_active.is_some();
    db.execute(
        if touches_the_door {
            "UPDATE hub_user SET name = :name, role = :role, is_active = :is_active, \
               cloud_revoked_at = '' WHERE id = :id AND hub_id = :hub_id"
        } else {
            "UPDATE hub_user SET name = :name, role = :role, is_active = :is_active \
               WHERE id = :id AND hub_id = :hub_id"
        },
        &p,
    )
    .await?;

    if let Some(email) = email {
        write_email(db, hub_id, user_id, &name, &email).await?;
    }
    if let Some(pin) = pin {
        identity::set_pin(db, hub_id, user_id, &pin).await?;
    }
    // **Revocación independiente** (hub#658): esto escribe SOLO las columnas de la placa. Perder
    // la tarjeta no puede dejar a nadie fuera, así que `badge: Some("")` la mata y el PIN de arriba
    // sigue exactamente donde estaba.
    if let Some(badge) = badge {
        identity::set_badge(db, hub_id, user_id, &badge).await?;
    }
    // Desactivar cierra sus sesiones abiertas: la baja tiene que ser inmediata, no esperar al TTL.
    if !is_active {
        let mut p = Params::new();
        p.insert("id".into(), json!(user_id));
        p.insert("hub_id".into(), json!(hub_id));
        db.execute(
            "DELETE FROM hub_session WHERE user_id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    }

    get(db, hub_id, user_id)
        .await?
        .ok_or_else(|| RuntimeError::Other("usuario no encontrado".into()))
}

/// Roles del hub: el **catálogo agregado** ([`crate::roles::catalog`], hub#352) decorado con los
/// permisos efectivos de cada rol y sus miembros activos.
///
/// Antes esta función construía su propia lista y metía en ella las **claves de
/// `role_permissions`** de los módulos activos. Ya no: **declarar nombra un rol y `role_permissions`
/// concede**, y son ejes distintos a propósito (un módulo puede conceder a una clave que inventó
/// otro), así que una clave contra la que alguien concede no es, por sí sola, un rol del hub. En el
/// catálogo publicado no cambia nada —los 24 módulos conceden **solo** a `admin`/`manager`/
/// `employee`, medido— y un rol que nadie declara pero alguien lleva sigue saliendo, ahora marcado
/// como huérfano (`in_use`).
pub async fn list_roles(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
) -> Result<Vec<HubRole>> {
    let mut scope = Params::new();
    scope.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT role, COUNT(*) AS members FROM hub_user \
              WHERE hub_id = :hub_id AND is_active = 1 GROUP BY role",
            &scope,
        )
        .await?;
    let mut members: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for row in &res.rows {
        let role = row["role"].as_str().unwrap_or_default().trim().to_string();
        if !role.is_empty() {
            members.insert(role, row["members"].as_i64().unwrap_or(0).max(0) as usize);
        }
    }

    Ok(crate::roles::catalog(db, registry, hub_id)
        .await?
        .into_iter()
        .map(|role| HubRole {
            permissions: identity::permissions_for_role(registry, &role.key).len(),
            members: members.get(&role.key).copied().unwrap_or(0),
            label: role.label,
            extends: role.extends,
            source: role.source,
            active: role.active,
            name: role.key,
        })
        .collect())
}

/// Despacha una query del namespace reservado `hub.` (ADR-0192). `rest` es el nombre sin prefijo.
///
/// Lo que ve un módulo es **menos** que lo que ve la pantalla de Personal: id, nombre, rol y estado
/// — lo justo para vincular su ficha a una persona (p. ej. `staff_member.user_id`). **Sin email ni
/// vía de acceso**: eso es dato del core y no hay motivo para dárselo a un módulo de terceros.
pub async fn core_query(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    name: &str,
    rest: &str,
    ctx: &crate::registry::RequestContext,
    params: &erplora_db::Params,
) -> Result<crate::queries::QueryPage> {
    if !CORE_QUERIES.contains(&rest) {
        // NOT `ModuleNotInstalled`: `hub` is not an absent module, it is the core. A name that does
        // not exist here is a broken contract and must blow up (`queryOptional` does not forgive it).
        return Err(RuntimeError::QueryNotFound(name.to_string()));
    }
    // Per-query gate: `approvals.list` requires admin (who approved what is information about the
    // staff, not the cashier's). The other core queries open with a local session.
    if rest == "approvals.list" {
        crate::permissions::check(ctx, ADMINISTER_PERMISSION)?;
    } else {
        crate::permissions::check(ctx, VIEW_USERS_PERMISSION)?;
    }
    // Non-paginated core queries answer with the whole (small) set: `total` = row count, no offset.
    // `approvals.list` is the exception — the audit grows forever, so it pages (hub#884).
    let whole = |rows: Vec<serde_json::Value>| {
        let total = rows.len() as u64;
        crate::queries::QueryPage { rows, total, limit: total, offset: 0 }
    };
    match rest {
        // Setup status of the hub (hub#369): ONE document joining the core's items with the ones
        // installed modules declare. The gate is the namespace's — having a local session —; which
        // items each session sees is filtered by each item's `permission`.
        "setup.status" => Ok(whole(vec![
            crate::setup_status::status(db, registry, hub_id, ctx).await?,
        ])),
        // The PIN approval record (hub#362 writes, hub#512 reads, hub#884 pages). Double
        // attribution: who asked for the elevation and who approved it. The ids resolve to names
        // against `hub_user`, or the screen shows UUIDs and nobody uses it.
        "approvals.list" => list_approvals(db, hub_id, params).await,
        "users.list" => Ok(whole(
            list(db, hub_id)
                .await?
                .into_iter()
                .map(|u| {
                    json!({
                        "id": u.id,
                        "name": u.name,
                        "role": u.role,
                        "is_active": u.is_active,
                    })
                })
                .collect(),
        )),
        // Roles are not PII: they are returned whole (name, permissions, members).
        _ => Ok(whole(
            list_roles(db, registry, hub_id)
                .await?
                .into_iter()
                .map(|r| json!({ "name": r.name, "permissions": r.permissions, "members": r.members }))
                .collect(),
        )),
    }
}

/// Core queries whose wire shape is the list envelope `{rows,total,limit,offset}` (they paginate),
/// mirroring what `list` in a module manifest declares. The server keys the response shape off
/// this — every other core query stays a plain array (dropdowns, not pagers).
pub fn is_core_list_query(name: &str) -> bool {
    name == "hub.approvals.list"
}

/// Reads the PIN approval record (`_elevation_audit`; hub#362 writes, hub#512 reads, hub#884
/// pages), through the runtime's OWN list engine — the same one every module list query goes
/// through, contract included.
///
/// Double attribution: `created_by` (the cashier who asked for the elevation) and `approved_by`
/// (the manager who approved it). The ids are `hub_user.id` and resolve to names via a JOIN, or
/// the screen shows UUIDs and nobody uses it.
///
/// The audit grows forever by design (nothing deletes it), so this never ships whole: the engine
/// serves `{rows,total,limit,offset}` and understands the standard list params — `limit`/`offset`,
/// `sort`/`dir` (whitelist: `created_at`), `search` over person names and command, `f_command`/
/// `f_permission`/`f_created_by`/`f_approved_by` (exact) and `f_created_at_from`/`_to` (range: the
/// date filter lives HERE, not in the client — filtering client-side only worked while the whole
/// trail was in memory, which was the bug).
async fn list_approvals(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    params: &erplora_db::Params,
) -> Result<crate::queries::QueryPage> {
    use crate::manifest::{FilterOp, FilterSpec, ListSpec};

    // The same spec a module would write in its manifest's `list` block; static because the audit
    // is a core table, not a manifest. No free-text search beyond names/command, on purpose.
    let filters = [
        ("command", FilterOp::Eq),
        ("permission", FilterOp::Eq),
        ("created_by", FilterOp::Eq),
        ("approved_by", FilterOp::Eq),
        ("created_at", FilterOp::Range),
    ]
    .into_iter()
    .map(|(col, op)| (col.to_string(), FilterSpec { op }))
    .collect();
    let spec = ListSpec {
        search: vec![
            "command".into(),
            "created_by_name".into(),
            "approved_by_name".into(),
        ],
        sort: vec!["created_at".into()],
        default_sort: Some("created_at".into()),
        default_dir: Some("desc".into()),
        filters,
        page_size: 50,
    };

    // LEFT JOIN resolves both ids to names in one pass. COALESCE: if the user was deleted
    // (identity is per deployment, no soft-delete) the name comes back empty instead of excluding
    // the row — an audit record must not be lost because an employee is gone. The ORDER BY is the
    // engine's, from the spec's whitelist.
    const BASE_SQL: &str = "SELECT a.id AS id, a.command AS command, a.permission AS permission, \
                a.created_by AS created_by, COALESCE(creator.name, '') AS created_by_name, \
                a.approved_by AS approved_by, COALESCE(approver.name, '') AS approved_by_name, \
                a.payload_fingerprint AS payload_fingerprint, a.created_at AS created_at \
           FROM _elevation_audit a \
           LEFT JOIN hub_user creator  ON creator.id  = a.created_by \
           LEFT JOIN hub_user approver ON approver.id = a.approved_by \
          WHERE a.hub_id = :hub_id";

    // The caller's list params travel as-is; `hub_id` is inserted LAST so nothing in the payload
    // can override the tenant.
    let mut bound = params.clone();
    bound.insert("hub_id".into(), json!(hub_id));
    crate::queries::run_list(db, BASE_SQL, &spec, &bound).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::{testutil::fresh_db, PgAdapter};

    /// The hub these unit tests belong to (hub#497).
    const HUB: &str = "hub-users-test";

    async fn db() -> PgAdapter {
        let db = fresh_db().await;
        identity::ensure_tables(&db).await.unwrap();
        db
    }

    #[test]
    fn only_owner_and_admin_administer_the_hub() {
        // Single, closed definition shared by the HTTP admin gate, the API keys, the login-user
        // panel and the cloud role floor (hub#347). Widening it grants administration everywhere
        // at once, so it stays an explicit two-role list.
        //
        // `owner` stays on that list after hub#349: it left the hub role CATALOGUE (`BASE_ROLES`),
        // but it is still a live role on the ACCOUNT plane —`role_floor_for_cloud_login` asks this
        // very question about the role the SaaS signs— and it is still the spelling carried by any
        // hub row that never went through the v12 rename.
        for r in ["owner", "admin", "Owner", "ADMIN"] {
            assert!(is_admin_role(r), "{r} administra el hub");
        }
        // A custom role from a module never administers the hub, however generous its
        // `role_permissions`: that property is granted by the hub, not declared by a manifest.
        for r in ["manager", "employee", "member", "bartender", "kitchen", ""] {
            assert!(!is_admin_role(r), "{r} NO administra el hub");
        }
        // The floor the cloud login can impose is `admin` — never `owner` (ADR-0157: hub ownership
        // comes from `HUB_OWNER_EMAIL`, never from a token).
        assert_eq!(CLOUD_ROLE_FLOOR, "admin");
        assert!(is_admin_role(CLOUD_ROLE_FLOOR));
    }

    /// hub#351 (paso 2b): which base roles a module-declared role may hang from.
    ///
    /// The catalogue is the core's, so a manifest can neither redefine an entry of it nor hang a
    /// role from the administrative one — the two halves of the same rule, derived from
    /// [`BASE_ROLES`] and [`is_admin_role`] so a change to the catalogue cannot leave them behind.
    #[test]
    fn a_module_extends_the_base_catalogue_but_never_the_administrative_role() {
        // The keys the core owns: the catalogue plus the legacy `owner` spelling.
        for base in ["admin", "manager", "employee", "owner", "Admin", "EMPLOYEE"] {
            assert!(is_base_role(base), "`{base}` is a key of the core");
        }
        for declared in ["waiter", "bartender", "kitchen", "accountant", ""] {
            assert!(!is_base_role(declared), "`{declared}` is not a base role");
        }

        // What a declared role may extend: every base role EXCEPT the administrative one. A
        // manifest that could hang from `admin` would mint administrators, which is exactly the
        // door hub#347 closed.
        for extendable in ["manager", "employee"] {
            assert!(is_extendable_base_role(extendable));
        }
        for forbidden in ["admin", "owner", "ADMIN", "waiter", "member", ""] {
            assert!(
                !is_extendable_base_role(forbidden),
                "`{forbidden}` cannot be the base of a declared role"
            );
        }
        // Derived, not copied: whatever administers is never extendable.
        assert!(!is_extendable_base_role(ADMIN_ROLE));
        assert!(!is_extendable_base_role(CLOUD_ROLE_FLOOR));
    }

    #[test]
    fn validates_name_role_pin_and_email() {
        assert!(clean_name("  ").is_err());
        assert_eq!(clean_name("  Ana  ").unwrap(), "Ana");
        assert!(clean_role("").is_err());
        assert_eq!(clean_pin("").unwrap(), "");
        assert_eq!(clean_pin("4821").unwrap(), "4821");
        assert!(clean_pin("12").is_err(), "menos de 4 dígitos");
        assert!(clean_pin("123456789").is_err(), "más de 8 dígitos");
        assert!(clean_pin("12ab").is_err(), "solo dígitos");
        // hub#355: la forma ya no basta, el PIN tampoco puede ser de los que se adivinan a la
        // primera. `1234` era el ejemplo de este test justamente por ser el primero que se prueba.
        assert!(clean_pin("1234").is_err(), "una cuesta arriba no es un PIN");
        assert_eq!(clean_email("").unwrap(), "");
        assert!(clean_email("ana@example.com").is_ok());
        assert!(clean_email("ana.example.com").is_err());
        assert!(clean_email("@example.com").is_err());
    }

    /// hub#355 — the closed list of PIN shapes the hub refuses, and its edges.
    #[test]
    fn a_pin_that_is_all_one_digit_or_a_straight_run_is_guessable() {
        for weak in ["0000", "1111", "9999", "1234", "4321", "345678", "98765"] {
            assert!(is_guessable_pin(weak), "`{weak}` is guessable");
        }
        // A run has to be strictly consecutive: a jump of two, a repeat inside, or a wrap-around
        // are ordinary PINs. Rejecting them would start refusing digits people can remember, which
        // is what pushes a shop back to sharing one PIN.
        for good in ["4821", "5390", "13579", "90210", "1233", "9012"] {
            assert!(!is_guessable_pin(good), "`{good}` is a legitimate PIN");
        }
    }

    #[test]
    fn splits_the_visible_name_into_first_and_last() {
        assert_eq!(split_name("Ana"), ("Ana".into(), String::new()));
        assert_eq!(
            split_name("Marta Ruiz Gil"),
            ("Marta".into(), "Ruiz Gil".into())
        );
    }

    #[tokio::test]
    async fn rejects_two_active_users_with_the_same_name() {
        let db = db().await;
        identity::create_user(&db, HUB, "Marta", "1234", "cashier", None)
            .await
            .unwrap();
        let err = ensure_name_is_free(&db, HUB, "Marta", None).await.unwrap_err();
        assert!(err.to_string().contains("Marta"), "{err}");
        // Editarse a uno mismo con el mismo nombre no choca consigo mismo.
        let id = identity::create_user(&db, HUB, "Luis", "2222", "cashier", None)
            .await
            .unwrap();
        ensure_name_is_free(&db, HUB, "Luis", Some(&id)).await.unwrap();
    }

    #[test]
    fn truthy_accepts_sqlite_integers_and_postgres_booleans() {
        assert!(truthy(&json!(1)));
        assert!(!truthy(&json!(0)));
        assert!(truthy(&json!(true)));
        assert!(!truthy(&json!(null)));
    }
}
