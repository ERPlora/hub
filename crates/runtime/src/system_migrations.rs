//! Migraciones del **esquema de sistema** del runtime, versionadas e idempotentes (hub#37).
//!
//! Las tablas de sistema (`hub_module`, `hub_user`, `hub_session`, `_event_outbox`,
//! `_event_delivery`, `_scheduled_tasks`, `_hub_migrations`…) se crean con `CREATE TABLE
//! IF NOT EXISTS` (ensure-create) al arrancar. Eso **no altera** tablas que ya existen: una BD
//! de un hub ya desplegado no recibiría cambios de esquema de sistema solo con el ensure-create.
//!
//! Este módulo es el espejo de [`crate::migrations`] (migraciones de **módulos**), pero para el
//! esquema **interno** del runtime: el SQL va **embebido en el binario** y se aplica en orden,
//! registrando cada migración aplicada en `_hub_system_migrations` para no reaplicarla.
//!
//! Modelo (decisión humano, hub#37):
//!  - **v0 = baseline** = los `CREATE TABLE IF NOT EXISTS` actuales (outbox/scheduler/identity).
//!    `ensure_system_tables` los asegura primero (cubre el hub vacío) y *no* se registra como
//!    migración: es el suelo sobre el que corren las versiones ≥ 1.
//!  - A partir de v1, cada cambio de esquema de sistema es una migración **versionada** (SQL
//!    Postgres, ADR-0154), aplicada idempotentemente al arrancar dentro de su propia transacción
//!    junto con el registro en `_hub_system_migrations`.
//!
//! Idempotente: re-arrancar no reaplica (se comprueba la versión en la tabla de control).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::migration_guard::Kind;
use crate::registry::now_rfc3339;

/// Tabla de control de las migraciones de sistema aplicadas (espejo de `_hub_migrations`, pero
/// versionada por número en vez de por fichero, porque el SQL va horneado en el binario).
const ENSURE_CONTROL: &str = "CREATE TABLE IF NOT EXISTS _hub_system_migrations (\
    version INTEGER NOT NULL, name TEXT NOT NULL, applied_at TEXT NOT NULL, \
    PRIMARY KEY (version));";

/// Una migración de sistema: número de versión (orden), nombre legible y SQL Postgres (ADR-0154).
/// El SQL puede ser un batch (varias sentencias separadas por `;`).
struct SystemMigration {
    version: i64,
    name: &'static str,
    /// Qué hace, con el mismo vocabulario que las migraciones de módulo (hub#542):
    /// `expand` aditiva · `backfill` datos · `contract` **no admite vuelta atrás**.
    ///
    /// **Esta marca ES lo que hace seguro el auto-rollback** (saas#1246). Al revertir **no se
    /// ejecuta nada sobre el esquema** (ADR-0269): se revierte el código y la columna se queda,
    /// y el binario anterior la ignora porque su SQL no la menciona. Eso solo funciona si lo
    /// aplicado era aditivo — así que marcar lo que **no** lo es es la única forma de saber qué
    /// versiones no se pueden desandar.
    ///
    /// Nada de `down`: deshacer borraría los datos que la versión nueva escribió, y además es
    /// imposible de ejecutar (un binario ya publicado no puede traer la inversa de algo que no
    /// existía cuando se publicó).
    kind: Kind,
    postgres: &'static str,
}

/// Conjunto **ORDENADO** de migraciones de sistema. Añade nuevas al final con `version`
/// estrictamente creciente; NUNCA reedites una ya publicada (rompe BD existentes), igual que
/// las rutas S3 inmutables de los módulos.
///
/// El orden de este slice es el orden de aplicación; se valida en [`apply`] que las versiones
/// sean estrictamente crecientes (defensa contra un duplicado/desorden al editar).
const MIGRATIONS: &[SystemMigration] = &[
    // ── v1 — hub#31 / ADR-0005: `hub_module` pasa a ser hub-scoped (PK compuesta) ──────────
    // Antes: `hub_module(module_id TEXT PRIMARY KEY, ...)` → un único set de módulos por BD.
    // En cloud/Aurora varios hubs de una org comparten BD (datos separados por `hub_id`), así
    // que el set activo debe ser **por hub**: PK `(hub_id, module_id)`.
    //
    // Migración ADITIVA: a las filas existentes (que no tienen hub_id) se les asigna el `hub_id`
    // del despliegue (`:hub_id`, inyectado por el runtime, no spoofable).
    SystemMigration {
        version: 1,
        name: "hub_module_hub_scoped",
        kind: Kind::Contract,
        // Postgres: añade la columna nullable, sella el hub_id del despliegue en las filas
        // existentes (UPDATE con `:hub_id`, bind seguro — no se mete un parámetro en un DEFAULT
        // de DDL, que Postgres rechazaría en sentencia preparada), luego la pone NOT NULL y
        // recompone la PK a `(hub_id, module_id)`.
        postgres: "\
ALTER TABLE hub_module ADD COLUMN IF NOT EXISTS hub_id TEXT;\
UPDATE hub_module SET hub_id = :hub_id WHERE hub_id IS NULL;\
ALTER TABLE hub_module ALTER COLUMN hub_id SET NOT NULL;\
ALTER TABLE hub_module DROP CONSTRAINT hub_module_pkey;\
ALTER TABLE hub_module ADD PRIMARY KEY (hub_id, module_id);",
    },
    // ── v2 — hub#15 / §2.9: device-trust local (login por PIN solo en dispositivo de confianza) ──
    // Un dispositivo se marca de confianza tras el PRIMER LOGIN ONLINE (cloud) correcto; el login
    // por PIN se rechaza mientras el dispositivo no sea de confianza. Tabla nueva (no `CREATE IF
    // NOT EXISTS` — va versionada para llegar también a una `erplora.db` ya existente). NO es la
    // credencial de máquina del hub (esa la gestiona el Cloud vía enroll); ver identity.rs.
    SystemMigration {
        version: 2,
        name: "hub_trusted_device",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS hub_trusted_device (\
  device_id TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', trusted_at TEXT NOT NULL);",
    },
    // ── v3 — ADR-0057 / public-api.md: API keys de la API pública por módulo ─────────────────
    // Credencial LOCAL del hub (hermana del login por PIN, NO un plano Hub↔Cloud). Un token
    // bearer opaco `erpl_live_<id>_<secret>`: se guarda solo el `secret_hash` (argon2id, mismo
    // helper que el PIN, identity.rs) + un `prefix` visible para la UI; el secreto en claro se
    // muestra UNA sola vez al crear/rotar. `scope_json` = array de {module, read, write} (matriz
    // módulo × {lectura, escritura}, §7); el runtime lo EXPANDE a los `permission` de las
    // queries/commands `expose_api` de cada módulo al resolver la key a un RequestContext. Tabla
    // hub-scoped (`hub_id`) como el resto del esquema: en BD compartida por org cada hub tiene sus
    // keys. `status` = 'active'|'revoked' (revocar = kill-switch inmediato). `created_by` audita
    // quién la creó (`apikey:<id>` no, un hub_user/sesión admin). Va versionada (no CREATE IF NOT
    // EXISTS) para llegar también a una `erplora.db` ya existente.
    SystemMigration {
        version: 3,
        name: "hub_api_key",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS hub_api_key (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, name TEXT NOT NULL, prefix TEXT NOT NULL, \
  secret_hash TEXT NOT NULL, scope_json TEXT NOT NULL DEFAULT '[]', \
  status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, \
  last_used_at TEXT, created_by TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (id));\
CREATE INDEX IF NOT EXISTS ix_hub_api_key_hub ON hub_api_key (hub_id);",
    },
    // ── v4 — settings del hub: store key/value de SISTEMA (scoped por hub_id) ───────────────────
    // Tabla genérica key/value de configuración del hub (moneda, idioma, flag de docs API…). El
    // CONJUNTO de claves conocidas + su validador + su default vive en el SERVER (`settings.rs`),
    // NO en la BD: añadir una clave nueva = una entrada en el registro del runtime, sin migración.
    // PK compuesta `(hub_id, key)`, hub-scoped como el resto del esquema: en BD compartida por org
    // cada hub tiene sus propios settings. `updated_by` audita quién hizo el último cambio (un
    // `hub_user:<id>` admin). Va versionada (no CREATE IF NOT EXISTS) para llegar también a una
    // `erplora.db` ya existente.
    SystemMigration {
        version: 4,
        name: "hub_settings",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS hub_settings (\
  hub_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, \
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (hub_id, key));",
    },
    // ── v5 — grants de capabilities por módulo (ADR-0079) ───────────────────────────────────────
    // Permisos módulo→host que el USUARIO concede explícitamente (estilo Android): un módulo declara
    // en su `module.json` las `capabilities` que necesita (red/certificado/impresora/notify) y el
    // dueño/admin las concede en Ajustes → Permisos. **Default-deny**: sin fila `granted=1` = NO
    // concedido. PK `(hub_id, module_id, capability)`, hub-scoped. `granted_by` audita quién (un
    // `hub_user:<id>` admin) y `granted_at` cuándo. El CONJUNTO de capabilities conocidas vive en el
    // runtime (`capabilities.rs` / `manifest::CapabilityKind`), no en la BD: añadir una = tocar el
    // runtime, sin migración. ERPlora SQL (TEXT pk, INTEGER bool), idéntico SQLite/Postgres.
    SystemMigration {
        version: 5,
        name: "module_capability_grants",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _module_capability_grants (\
  hub_id TEXT NOT NULL, module_id TEXT NOT NULL, capability TEXT NOT NULL, \
  granted INTEGER NOT NULL DEFAULT 0, granted_at TEXT, granted_by TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (hub_id, module_id, capability));",
    },
    // ── v6 — certificado fiscal del NEGOCIO en el core (ADR-0079) ────────────────────────────────
    // El certificado PKCS#12 del negocio (identidad fiscal: VeriFactu y futuros B2B) deja de vivir
    // en la tabla del módulo verifactu y pasa a ser un **recurso del HUB**, subido en Ajustes →
    // Negocio (junto al NIF y el nombre). Un módulo solo lo USA si tiene la capability `certificate`
    // concedida (el host media; la clave nunca cruza al sandbox). Singleton por hub (PK `hub_id`).
    // `password` en claro **de momento** (mismo estado que verifactu hoy; el cifrado at-rest de
    // secretos es decisión pendiente — ADR-0016). `uploaded_by` audita. ERPlora SQL, idéntico
    // SQLite/Postgres.
    SystemMigration {
        version: 6,
        name: "hub_certificate",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _hub_certificate (\
  hub_id TEXT NOT NULL, pkcs12_b64 TEXT NOT NULL, password TEXT NOT NULL DEFAULT '', \
  uploaded_at TEXT, uploaded_by TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (hub_id));",
    },
    // ── v7 — perfil y preferencias PERSONALES, aislados por Hub + usuario ────────────────────
    // Una preferencia vacía significa «heredar el valor del Hub». El frontend ya no usa
    // localStorage como autoridad, evitando que dos usuarios del mismo dispositivo compartan tema
    // o idioma. El perfil también queda hub-scoped: cada runtime solo conoce su propio negocio.
    SystemMigration {
        version: 7,
        name: "hub_user_profile_preferences",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS hub_user_profile (\
  hub_id TEXT NOT NULL, user_id TEXT NOT NULL, first_name TEXT NOT NULL DEFAULT '', \
  last_name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', \
  avatar_path TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id, user_id));\
CREATE TABLE IF NOT EXISTS hub_user_pref (\
  hub_id TEXT NOT NULL, user_id TEXT NOT NULL, language TEXT NOT NULL DEFAULT '', \
  theme_mode TEXT NOT NULL DEFAULT '', theme_palette TEXT NOT NULL DEFAULT '', \
  updated_at TEXT NOT NULL, PRIMARY KEY (hub_id, user_id));",
    },
    // ── v8 — sesión única por dispositivo: `hub_session.device_id` (ADR-0154, hub#200) ──────────
    // El baseline v0 de identity (`identity::ensure_tables`) crea `hub_session` SIN device_id; esta
    // migración ADITIVA añade la columna (nullable) para que llegue también a una `erplora.db` ya
    // existente (un `CREATE IF NOT EXISTS` no altera una tabla creada). El runtime persiste ahí el
    // id del dispositivo del login y, con `max_devices == 1` (claim del entitlement), desaloja las
    // sesiones de otros dispositivos al abrir una nueva (`identity::enforce_device_limit`). Añadir
    // una columna nullable NO toca la PK, así que `ALTER TABLE ADD COLUMN` basta en ambos dialectos
    // (a diferencia de v1, que recreaba la tabla por cambiar la PK). Va versionada (no CREATE IF NOT
    // EXISTS) para no reeditar el baseline.
    SystemMigration {
        version: 8,
        name: "hub_session_device_id",
        kind: Kind::Expand,
        postgres: "ALTER TABLE hub_session ADD COLUMN IF NOT EXISTS device_id TEXT;",
    },
    // ── v9 — identidad por EMAIL: `hub_user.email` (ADR-0157, corrección owner sembrado) ─────────
    // El owner del hub es el CREADOR, sembrado por el provisioning del SaaS (`HUB_OWNER_EMAIL`)
    // ANTES del primer login; el alta de miembros del admin (ADR-0157 §7) también identifica por
    // email. El baseline v0 de identity (`identity::ensure_tables`) crea `hub_user` SIN email; esta
    // migración ADITIVA añade la columna (`NOT NULL DEFAULT ''`, así las filas existentes reciben ''
    // sin romper) + un índice para el lookup por email (enlace del JWT→hub_user por email cuando el
    // `cloud_user_id` aún no está vinculado). Añadir una columna con default NO toca la PK, así que
    // `ALTER TABLE ADD COLUMN` basta (como v8). Va versionada (no CREATE IF NOT EXISTS) para llegar
    // también a una BD ya desplegada. El índice NO es único: la unicidad por email la garantiza el
    // código (SELECT-then-write), igual que `ix_hub_user_cloud` con `cloud_user_id`.
    SystemMigration {
        version: 9,
        name: "hub_user_email",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE hub_user ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT '';\
CREATE INDEX IF NOT EXISTS ix_hub_user_email ON hub_user (email);",
    },
    // ── v10 — #42: cuota durable de API keys ────────────────────────────────────────────────
    SystemMigration {
        version: 10,
        name: "api_key_rate_limit",
        kind: Kind::Expand,
        postgres:
            "\
ALTER TABLE hub_api_key ADD COLUMN IF NOT EXISTS rate_limit_per_minute INTEGER NOT NULL DEFAULT 60;\
CREATE TABLE IF NOT EXISTS hub_api_key_rate_window (\
  api_key_id TEXT PRIMARY KEY, window_epoch_minute BIGINT NOT NULL, request_count BIGINT NOT NULL);",
    },
    // ── v11 — hub#348 (paso 2b regla D): POR QUÉ está cerrada la puerta de un `hub_user` ─────────
    // Revocar la membresía en el SaaS DESACTIVA el `hub_user` (`is_active = 0`). Pero `is_active`
    // solo dice que está cerrada, no **quién** la cerró, y hay dos autoridades distintas: el propio
    // hub (baja del admin en Personal / `/api/members`, ADR-0157 §7) y el SaaS (esta regla D). Sin
    // distinguirlas hay que elegir entre dos fallos: si un login puede reactivar, una membresía
    // rancia deshace la baja que decidió el admin del hub; si no puede, una revocación por error
    // deja al dueño fuera de su propio hub para siempre.
    //
    // `cloud_revoked_at` guarda el instante en que la regla D cerró la fila (`''` = no la cerró el
    // cloud). Solo esas filas las reabre un login, y solo si el SaaS vuelve a acreditar la
    // membresía; cualquier otra baja sigue siendo del hub y solo el hub la levanta. Columna
    // ADITIVA (`NOT NULL DEFAULT ''`): las filas existentes quedan como «no revocada por el cloud»,
    // que es la lectura conservadora para un hub ya desplegado.
    SystemMigration {
        version: 11,
        name: "hub_user_cloud_revoked_at",
        kind: Kind::Expand,
        postgres: "ALTER TABLE hub_user ADD COLUMN IF NOT EXISTS cloud_revoked_at TEXT NOT NULL DEFAULT '';",
    },
    // ── v12 — hub#349 (paso 2b): `owner` sale del catálogo de roles del hub ──────────────────────
    // `owner` era la MISMA palabra en los dos planos —el rol de la CUENTA en el SaaS y el rol del
    // NEGOCIO en el hub— y solo funcionaba como rol del hub porque el gate del core lo trataba como
    // `admin`: **ningún** módulo del catálogo declara `role_permissions.owner` (24/24 solo conocen
    // admin/manager/employee). `admin` pasa a ser lo más alto del plano de negocio.
    //
    // Los hubs ya desplegados SÍ tienen filas con `owner` (el provisioning sembraba al creador con
    // ese rol, `identity::seed_owner`), así que hay que renombrarlas o se quedarían con un rol que
    // ya no está en el catálogo. Es un **renombrado, no una degradación**: el conjunto efectivo de
    // permisos antes y después es idéntico —`is_admin_role` ya decía que sí a los dos y
    // `permissions_for_role` ya resolvía `owner` como `admin`—, así que nadie gana ni pierde nada.
    //
    // `lower(role)` porque el gate compara sin mayúsculas: una fila `Owner`/`OWNER` administraba el
    // hub igual y tiene que migrar igual. Alcanza también a las filas INACTIVAS: si no, una
    // reincorporación futura resucitaría el rol viejo. Idempotente por naturaleza (tras correr no
    // queda ninguna fila que casar) y además registrada, como el resto.
    SystemMigration {
        version: 12,
        name: "hub_user_owner_role_to_admin",
        kind: Kind::Backfill,
        postgres: "UPDATE hub_user SET role = 'admin' WHERE lower(role) = 'owner';",
    },
    // ── v13 — hub#352 (paso 2b): qué roles del catálogo están ACTIVOS en este hub ────────────────
    // hub#351 dejó que un módulo DECLARE sus roles de negocio (`roles[]`); el catálogo que sale de
    // agregarlos con los tres roles base es el mismo para cualquier hub que instale esos módulos,
    // pero **qué roles usa este negocio** no lo decide el paquete: lo decide su administrador. Un
    // restaurante quiere Waiter · Bartender · Kitchen · Cashier; una peluquería, Receptionist ·
    // Stylist. Esa decisión es lo que vive aquí.
    //
    // **La fila ES la activación** (presente = activo, ausente = inactivo), y por tanto el default
    // es OPT-IN: instalar un módulo nunca enciende sus roles solo. Es lo conservador —nadie recibe
    // un rol que no pidió— y es lo que deja hueco a que el blueprint pre-active el juego correcto
    // por vertical (hub#354) en vez de que todo hub herede todos los roles de todo lo que instala.
    //
    // Los roles BASE (`admin`/`manager`/`employee`) **no se guardan aquí**: son el contrato
    // congelado, están siempre activos y no se pueden apagar. Guardarlos abriría la puerta a un
    // hub sin ningún rol vivo, que es un hub en el que no puede trabajar nadie.
    //
    // `hub_id` como el resto del esquema de sistema (en BD compartida por org, dos hubs tienen sets
    // distintos). `activated_by` audita QUIÉN lo encendió — la traza importa: activar un rol es
    // decidir que existe una figura con acceso en el negocio.
    SystemMigration {
        version: 13,
        name: "hub_role_activation",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS hub_role_activation (\
  hub_id TEXT NOT NULL, role_key TEXT NOT NULL, \
  activated_at TEXT NOT NULL, activated_by TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (hub_id, role_key));",
    },
    // ── v14 — hub#316 / ADR-0202 §2.1: `_hub_certificate` deja de ser singleton — DOS SLOTS ──────
    // Un hub podía tener UN certificado fiscal: el que su dueño sube en Ajustes → Negocio. La fase 2
    // de VeriFactu añade un segundo origen —el certificado DELEGADO de ERPlora, que reparte el plano
    // de control (saas#1124/#1125)— y los dos tienen que convivir: el propio no se puede borrar para
    // hacerle sitio al delegado (es la identidad del negocio, y su renovación siempre fue del
    // cliente) ni al revés (el delegado lo rota ERPlora, sin pasar por el hub).
    //
    // Por eso la PK pasa de `hub_id` a `(hub_id, kind)`: la fila deja de ser «el certificado del
    // hub» y pasa a ser «el certificado de ESTE origen en este hub». El `kind` es un slot, NO una
    // preferencia — cuál se usa lo decide la regla de selección del core (propio si está subido, si
    // no el delegado), no una columna que alguien pueda cambiar.
    //
    // ADITIVA y conservadora: `DEFAULT 'own'` sella como PROPIAS las filas de los hubs ya
    // desplegados, que es exactamente lo que son (las subió su dueño por `PUT /api/business/
    // certificate`). Si el default fuese `delegated`, un hub ya en producción se encontraría de
    // pronto con que su certificado «es de ERPlora»: dejaría de exportarse en su backup y quedaría
    // a merced de una rotación central que nunca pidió.
    SystemMigration {
        version: 14,
        name: "hub_certificate_slots",
        kind: Kind::Contract,
        postgres: "\
ALTER TABLE _hub_certificate ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'own';\
ALTER TABLE _hub_certificate DROP CONSTRAINT _hub_certificate_pkey;\
ALTER TABLE _hub_certificate ADD PRIMARY KEY (hub_id, kind);",
    },
    // ── v16 — hub#317 / ADR-0202 §2: el certificado DELEGADO guarda la VERSIÓN con la que llegó ──
    // El plano de control reparte su `.p12` con un entero monótono (`DelegatedCertificate.version`,
    // saas#1124) y la convergencia de la flota entera se apoya en él: el heartbeat anuncia la
    // versión del plano de control, el hub la compara con la suya y refetchea si difieren (#318), y
    // la reporta de vuelta para que el panel pueda decir «987/1000 en v4» (saas#1126/#1127).
    //
    // Va en ESTA tabla, en la fila del certificado, y no en `hub_settings`: el número describe unos
    // bytes concretos, así que tiene que moverse en el MISMO upsert que ellos. Separados, una
    // escritura a medias deja la fila con el `.p12` nuevo bajo el número viejo — y un hub que
    // reporta una versión que no tiene es un hub al que el panel da por al día mientras firma con
    // una clave superada (en el peor caso, revocada).
    //
    // NULLable a propósito: el slot `own` NO tiene versión. Lo sube y lo renueva su dueño, no hay
    // rotación central que numerar, y un `0` por defecto haría que un hub con certificado propio
    // reportase «tengo la v0 de ERPlora» en vez de «no tengo ninguna».
    //
    // ⚠️ El hueco de la v15 queda VACÍO PARA SIEMPRE, y no reserva nada. Se dejó para hub#341
    // (la cola de impresión), pero un hueco NO es una reserva: `apply` compara contra el
    // MÁXIMO aplicado, así que una migración numerada por debajo de él se salta EN SILENCIO.
    // Cuando esta v16 (y la v17) llegaron a `develop` antes que hub#341, cualquier hub
    // desplegado desde ahí quedó en max=17 y jamás habría corrido una v15 → la cola se fue a
    // la v18. Un número libre en medio es inofensivo (el test de orden solo exige que crezcan);
    // lo que no se puede es RELLENARLO después. La única regla segura: coge el siguiente
    // número POR ENCIMA del máximo del catálogo.
    SystemMigration {
        version: 16,
        name: "hub_certificate_delegated_version",
        kind: Kind::Expand,
        postgres: "ALTER TABLE _hub_certificate ADD COLUMN IF NOT EXISTS cert_version BIGINT;",
    },
    // ── v17 — hub#357 (paso 2b): QUÉ CLASE de dispositivo es este — `shared` vs `personal` ───────
    // El mismo negocio tiene el TPV del mostrador (varias personas se turnan) y el portátil del
    // despacho (de una sola), y la MISMA persona usa los dos. Así que no puede ser un ajuste del
    // hub: es del dispositivo, y la clave ya existe (`X-Device-Id`, ADR-0154). De aquí cuelgan el
    // pinpad condicionado (hub#358) y el ajuste «Pedir PIN: siempre / turno / nunca» (hub#359).
    //
    // Va en `hub_trusted_device` y no en una tabla nueva, y ese es el punto de SEGURIDAD del
    // diseño: `personal` es el modo LAXO (sin pinpad, sesión larga) y el `device_id` es un
    // identificador que el cliente manda en claro, no una credencial. Colgando el modo de la fila
    // del device-trust (§2.9, hub#330), un dispositivo solo puede tener modo si ya probó identidad
    // con un login ONLINE — y `untrust_device` (portátil robado) BORRA la fila, así que se lleva el
    // modo laxo con ella sin ninguna cascada que recordar. Con una tabla aparte, olvidar esa
    // cascada dejaría al ladrón el dispositivo «personal».
    //
    // `DEFAULT 'shared'` sella como COMPARTIDOS los dispositivos ya de confianza de un hub
    // desplegado, que es la lectura conservadora: lo que se hereda es la fricción, nunca su
    // ausencia. `mode_set_by` audita quién lo decidió (como `activated_by` en la v13): bajar la
    // fricción de identidad de un terminal es una decisión que tiene que dejar rastro.
    //
    // ⚠️ La v15 sigue RESERVADA por hub#341 (cola de impresión, `architecture/hub/print-queue.md`)
    // igual que cuando se escribió la v16: esta PR salta a la 17 en vez de ocupar el hueco. `apply`
    // compara `version >` el máximo aplicado y el test de orden solo exige que crezcan.
    SystemMigration {
        version: 17,
        name: "hub_trusted_device_mode",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE hub_trusted_device ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'shared';\
ALTER TABLE hub_trusted_device ADD COLUMN IF NOT EXISTS mode_set_at TEXT NOT NULL DEFAULT '';\
ALTER TABLE hub_trusted_device ADD COLUMN IF NOT EXISTS mode_set_by TEXT NOT NULL DEFAULT '';",
    },
    // ── v18 — hub#341 / ADR-0196 §6: the print queue lives in the HUB ───────────────────────
    // ⚠️ **v18 and not the v15 hub#317 left free for this.** A gap does NOT reserve a number:
    // `apply` compares against the MAXIMUM applied version, so anything numbered at or below it
    // is skipped IN SILENCE — the hub boots believing it is up to date, with the table missing
    // and nothing logged. v16/v17 reached `develop` before this branch, so any hub deployed
    // from it is already at max=17 and would never have run a v15. The gap stays open (empty
    // numbers are harmless: the order test only requires growth); the queue takes the next
    // number above the maximum. `a_hub_already_migrated_still_receives_the_print_queue` is the
    // test that caught this — it failed on v15 for exactly this reason.
    // Any device (the PWA included) enqueues `{role, html, jobId}` here; the device that has the
    // installable app and sits on the printer's network drains it as the PRINT HOST of that
    // `role`. The queue used to live in the device's Bridge process: with nobody running the app
    // the job was not queued anywhere — it was lost. Here it waits.
    //
    // `PRIMARY KEY (hub_id, job_id)` **is** the idempotency guarantee: `job_id` is chosen by the
    // producer, and a second `INSERT … ON CONFLICT DO NOTHING` with the same id writes nothing, so
    // a retry (a lost HTTP response, a double tap on "print", a reconnect) never produces a second
    // ticket. It is the PK and not a separate unique index because that IS the contract's key.
    //
    // `seq BIGSERIAL` gives the hand-out ORDER. `created_at` is not enough: two jobs queued in the
    // same instant tie, and the order that came in first could be printed second.
    //
    // `lease_expires_at` bounds what a host takes away: if the device dies between the claim and
    // the confirmation, the expiry returns the job to the queue instead of stranding it. Like
    // `_event_outbox`, instants are TEXT RFC3339 (lexicographically comparable in UTC) for
    // consistency with the rest of the system schema.
    SystemMigration {
        version: 18,
        name: "print_queue",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _print_queue (\
  hub_id TEXT NOT NULL, job_id TEXT NOT NULL, seq BIGSERIAL NOT NULL, \
  role TEXT NOT NULL, html TEXT NOT NULL, format TEXT NOT NULL DEFAULT 'receipt', \
  status TEXT NOT NULL DEFAULT 'pending', attempts BIGINT NOT NULL DEFAULT 0, \
  claimed_by TEXT NOT NULL DEFAULT '', lease_expires_at TEXT NOT NULL DEFAULT '', \
  last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, completed_at TEXT, \
  PRIMARY KEY (hub_id, job_id));\
CREATE INDEX IF NOT EXISTS ix_print_queue_next ON _print_queue (hub_id, role, status, seq);\
CREATE INDEX IF NOT EXISTS ix_print_queue_lease ON _print_queue (hub_id, status, lease_expires_at);",
    },
    // ── v19 — hub#436: the email of the rows written before hub#356, moved to where ACCESS is ───
    // hub#356 (PR #432) fixed the code — the alta now writes the email in the two places that need
    // it — but not the rows that were already in the deployed hubs. Those hold the address **only**
    // in `hub_user_profile.email`, what the person sees in their profile, while everything that
    // administers access resolves against `hub_user.email` (v9): `get_or_link_cloud_user` links by
    // it on the first login, `revoke_cloud_access` closes the door by it when the SaaS revokes a
    // membership (rule D, hub#348), and it is the key of the `/api/members` alta and baja.
    //
    // So for those people **deactivating revokes nothing**: the SaaS takes their membership away
    // and the hub matches no row — session, PIN and pinpad all keep working. That is the security
    // half of hub#436 and the reason this is a migration and not a screen: the rows are already out
    // there and nobody is going to find them by hand.
    //
    // ⚠️ **v19 and not a number reused from the 15 gap.** `apply` compares against the MAXIMUM
    // applied version, so anything at or below it is skipped IN SILENCE — see the v18 note. The
    // maximum in `develop` when this was written was 18; this takes the next number above it, and a
    // rebase that brings another migration in must renumber this one, not squeeze it underneath.
    //
    // **What it deliberately does NOT do.** `hub_user.email` has no unique constraint (v9 creates a
    // plain index; uniqueness is a SELECT-then-write in code), so a blind copy cannot fail — it
    // would quietly leave two rows answering for one address. The two `NOT EXISTS` guards are that
    // refusal, and the first one is a security guard, not tidiness: `/api/profile` is self-service
    // and unchecked, so a cashier can type the administrator's address into their own profile.
    // Copying it would give that row the administrator's access key, and the next cloud login could
    // land on it and raise it to the role floor (hub#347) — a privilege escalation performed by the
    // migration itself. The second guard covers the pair hub#356 produced (the row the admin created
    // plus the row the first login provisioned): picking one means deciding which id keeps the
    // sales, the sessions and the audit trail, and which of two different roles is the real one.
    // Nothing in the data says that, so neither is touched and both are reported at every boot
    // (`access_email::report_unresolved`) for a human to resolve.
    //
    // Scoped through the profile's `hub_id` (`hub_user` has none: since ADR-0201 each hub owns its
    // database), exactly like the Personal listing. Copied VERBATIM after trimming — the access
    // lookups compare the string exactly, so lower-casing it here would be a change of identity,
    // not a normalisation; the guards compare case-insensitively because the alta guard that
    // catches duplicates (`identity::email_is_known`) does.
    //
    // Idempotent by construction: it only writes rows whose access column is empty, so a second run
    // finds none of the ones it fixed. Silent on a healthy hub — a new hub, or one where every alta
    // went through the fixed code, matches nothing and this is a no-op.
    SystemMigration {
        version: 19,
        name: "hub_user_access_email_backfill",
        kind: Kind::Backfill,
        postgres: "\
UPDATE hub_user AS u SET email = TRIM(pr.email) \
  FROM hub_user_profile AS pr \
 WHERE pr.user_id = u.id \
   AND pr.hub_id = :hub_id \
   AND COALESCE(TRIM(u.email), '') = '' \
   AND TRIM(pr.email) <> '' \
   AND NOT EXISTS (SELECT 1 FROM hub_user AS o \
                    WHERE o.id <> u.id \
                      AND LOWER(TRIM(COALESCE(o.email, ''))) = LOWER(TRIM(pr.email))) \
   AND NOT EXISTS (SELECT 1 FROM hub_user_profile AS r \
                     JOIN hub_user AS ru ON ru.id = r.user_id \
                    WHERE r.hub_id = pr.hub_id AND r.user_id <> pr.user_id \
                      AND LOWER(TRIM(r.email)) = LOWER(TRIM(pr.email)) \
                      AND COALESCE(TRIM(ru.email), '') = '');",
    },
    // ── v21 — hub#470 / ADR-0202 §2.1: QUÉ ES el certificado, que es lo que la AEAT segrega ──────
    // `kind` (v14) dice de QUIÉN es el certificado — `own` del negocio, `delegated` del plano de
    // control—, y hub#320 lo usó para elegir la puerta de la AEAT como si dijera QUÉ es. No lo dice:
    // que el slot delegado contenga un Sello de Entidad era una premisa de ADR-0202 que nunca viajó
    // por la frontera, y el `.p12` con el que ERPlora factura hoy es de **representante**. Subido
    // como delegado, toda la flota delegada habría POSTeado a `www10` y la AEAT habría rechazado
    // todos sus registros, uno a uno y sin nada que avisara.
    //
    // Va en la fila del certificado —y en el MISMO upsert que los bytes, como `cert_version` (v16)—
    // porque describe ESOS bytes: separados, una escritura a medias deja el `.p12` nuevo bajo el
    // tipo del anterior, que es exactamente elegir la puerta de un certificado que ya no se tiene.
    //
    // **Sin backfill, a propósito.** Las filas ya desplegadas se quedan con `''` = «no consta», y
    // `certificate::slot_type` deriva la respuesta del contenedor cuando la lee. Rellenar a ciegas
    // sería adivinar de qué tipo es el certificado de alguien, y esta misma cola ya se libró por
    // poco de una escalada de privilegio por un backfill «obvio» (v19, hub#436). Leer los bytes que
    // la fila tiene es una lectura; deducir del slot es una suposición.
    //
    // `''` y no NULL: la columna se compara con dos literales (`'seal'`/`'representative'`) y un
    // tercer estado nulo solo añade una rama por la que colarse. Es la misma forma que `password`
    // y `uploaded_by` (v6).
    //
    // ⚠️ **v21 y no v20.** `apply` compara contra el MÁXIMO aplicado: una migración numerada por
    // debajo de él se salta EN SILENCIO. La v20 está en vuelo en hub#342 (PR #460, el registro de
    // hosts de impresión); si esta entra antes, esa hay que RENUMERARLA al rebasar, nunca meterla
    // por debajo. Y nace **re-ejecutable** (`IF NOT EXISTS`): una migración que no lo era reventó
    // 15 tests de otra suite con un 42P07 (hub#483).
    SystemMigration {
        version: 21,
        name: "hub_certificate_type",
        kind: Kind::Expand,
        postgres: "ALTER TABLE _hub_certificate \
                     ADD COLUMN IF NOT EXISTS certificate_type TEXT NOT NULL DEFAULT '';",
    },
    // ── v22 — hub#342 / ADR-0196 §6: WHO drains each printer role ───────────────────────────
    // ⚠️ **v22, and it was born as v19, then v20.** `apply` compares against the MAXIMUM applied
    // version, so anything at or below it is skipped IN SILENCE — the hub boots believing it is up
    // to date, with the table missing and nothing logged. This branch picked v19 when 18 was the
    // maximum and hub#436 merged ITS v19 first; it moved to v20 and hub#470 merged a v21 before
    // this landed, which left v20 sitting *below* the maximum — free, but unreachable. Hence v22.
    //
    // Two rules come out of that, and neither is optional:
    //   * **Take the next number ABOVE the maximum, re-checked at the moment you rebase** — not the
    //     lowest free one. v20 is empty and would still never run.
    //   * **Renumbering is free; RENAMING breaks.** The number is an accident of merge order; the
    //     `name` is the contract that `_hub_system_migrations` and every fixture key on. This has
    //     been renumbered three times and has always been `print_host`.
    //
    // The v15 gap is still open and still reserves nothing.
    //
    // The queue (v18) guarantees a job is never lost for want of somebody holding a device. This
    // is the other half: the device with the installable app, on the printer's network, that says
    // "I print what goes to `kitchen`".
    //
    // `PRIMARY KEY (hub_id, device_id, role)` makes a role a SET of hosts, not a slot. Two tills
    // within reach of the kitchen printer are a spare, not a conflict — `claim_next` hands out
    // under `FOR UPDATE SKIP LOCKED`, so they take different jobs — and one device can hold
    // several roles (the counter till prints `receipt` AND `kitchen`).
    //
    // **There is no `live` column, on purpose.** A device that lost power writes nothing, so
    // liveness cannot be a flag anybody sets: it is DERIVED by comparing `last_seen_at` against
    // the heartbeat window at read time. A stored flag would need a sweeper — one more thing that
    // can be down — and while it was down it would claim a dead till is printing.
    //
    // `registered_at`/`registered_by` are the audit of who set this device up and when, and a
    // reconnect deliberately does NOT move them (see `print_hosts::register`). Instants are TEXT
    // RFC3339 like `_print_queue` and `_event_outbox`.
    //
    // ⚠️ **`IF NOT EXISTS` on the table AND the index: this migration must be RE-EXECUTABLE.**
    // The control table records *versions*, not schema, so anything that deletes rows from
    // `_hub_system_migrations` makes `apply` replay the SQL over a database where the objects are
    // already there. That is not hypothetical: `tests/access_email_backfill.rs` rewinds
    // `version >= 19` to re-run hub#436's backfill, which sweeps every LATER migration with it —
    // this one. A bare `CREATE TABLE` fails 42P07 there and takes 15 of that suite's tests down.
    //
    // Most of the catalogue above is NOT idempotent (hub#483); it gets away with it only because
    // nothing rewinds past it yet. New migrations should not inherit the defect: re-appliability
    // is the same property hub#436 demanded of its own backfill.
    SystemMigration {
        version: 22,
        name: "print_host",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _print_host (\
  hub_id TEXT NOT NULL, device_id TEXT NOT NULL, role TEXT NOT NULL, \
  label TEXT NOT NULL DEFAULT '', registered_at TEXT NOT NULL, \
  registered_by TEXT NOT NULL DEFAULT '', last_seen_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id, device_id, role));\
CREATE INDEX IF NOT EXISTS ix_print_host_role ON _print_host (hub_id, role, last_seen_at);",
    },
    // ── v23 — hub#489 / ADR-0261: el device-trust pasa a ser POR HUB (PK compuesta) ────────────
    //
    // `hub_trusted_device` nació (v2) con la clave `device_id` **a secas**, la única tabla de
    // sistema sin `hub_id` — `hub_settings`, `hub_api_key`, `hub_module` y `_print_host` van todas
    // `(hub_id, …)`. En la forma **pre-ADR-0201**, con varios hubs sobre una misma BD, eso hacía de
    // la tabla terreno común: la confianza ganada en el hub A abría el gate de PIN del hub B
    // (§2.9), un admin de A podía marcar `personal` o revocar un dispositivo de B, y desde hub#455
    // la pantalla de dispositivos **le enseñaba** a A los de B — etiqueta, último uso y sesiones
    // abiertas. Pasó de fuga silenciosa a exposición entre inquilinos.
    //
    // ⚠️ **Número: el SIGUIENTE POR ENCIMA DEL MÁXIMO (22), no el hueco más bajo.** [`apply`]
    // compara contra el **máximo** aplicado, así que v15 y v20 están libres y son **inalcanzables**:
    // cogerlas es el fallo mudo que ya renumeró hub#341, hub#342 (dos veces) y hub#470. Re-comprobar
    // al rebasar.
    //
    // 🔴 **Las filas que ya existen NO se atribuyen a nadie — se van.** Es la única decisión de esta
    // migración, y va por el lado conservador:
    //
    //  - una fila anterior a esta columna **no dice de qué hub es**. En una BD compartida, sellarla
    //    con `:hub_id` se la regalaría al hub que **arranque primero** (el control
    //    `_hub_system_migrations` tampoco es per-hub: la migración corre UNA vez por base de datos),
    //    y ese regalo es exactamente el privilegio que esta issue quita — la trampa que hub#436
    //    acaba de pagar con un backfill a ciegas;
    //  - lo que se pierde es **fricción, nunca autorización**: sin fila, el dispositivo vuelve a ser
    //    desconocido → modo `shared` (pinpad) y sin login por PIN hasta que alguien haga UN login
    //    online en él, que reescribe la fila ya con su hub. `label`/`trusted_at`/`mode` son
    //    recuperables por ese camino; adivinar el dueño no se deshace.
    //  - el censo real es pequeño: tras hub#454 (ADR-0257) el barrido de cada arranque ya borra la
    //    fila cuyo id era el del hub, que en un hub servido por navegador —el caso normal, ADR-0154
    //    cloud-first— era **la única** que existía. Lo que queda son instalaciones Tauri.
    //
    // `hub_id = ''` es, pues, el valor reservado de «esta fila no nombra hub». El runtime no lo
    // escribe nunca (`Runtime::hub_scope` falla cerrado con un `hub_id` vacío), así que el `DELETE`
    // de abajo solo puede alcanzar filas heredadas — y por eso es seguro RE-EJECUTARLO.
    //
    // ⚠️ **Re-ejecutable** (regla de hub#342/#483): `ADD COLUMN IF NOT EXISTS`, el `DELETE` acotado
    // al centinela y el par `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT` con **nombre explícito**
    // (el que Postgres le habría puesto igualmente) hacen del segundo pase un no-op. Sin eso,
    // rebobinar el control —lo que hace `tests/access_email_backfill.rs`— la mata con un 42701/42P16
    // y se lleva por delante la suite entera.
    SystemMigration {
        version: 23,
        name: "hub_trusted_device_hub_scoped",
        kind: Kind::Contract,
        postgres: "\
ALTER TABLE hub_trusted_device ADD COLUMN IF NOT EXISTS hub_id TEXT NOT NULL DEFAULT '';\
DELETE FROM hub_trusted_device WHERE hub_id = '';\
ALTER TABLE hub_trusted_device DROP CONSTRAINT IF EXISTS hub_trusted_device_pkey;\
ALTER TABLE hub_trusted_device ADD CONSTRAINT hub_trusted_device_pkey \
  PRIMARY KEY (hub_id, device_id);",
    },
    // ── v25 — hub#501: el documento de la cola pasa a ser ESTRUCTURADO, y el HTML se retira ─────
    // Decisión de Ioan (2026-08-08). La cola guardaba `html`, un documento autocontenido, y
    // `escpos::render_document` renderiza `document_type` + un JSON con la forma de cada documento:
    // **no había forma de convertir lo uno en lo otro**, así que el ciclo tique → host → papel no se
    // podía cerrar. Se decide que viaje ESTRUCTURADO y que el traductor HTML→ESC/POS **no se
    // escriba** — ni ahora ni como puente. Con un dato estructurado el mismo tique se renderiza a
    // 58 mm, a 80 mm, a PDF o a una pantalla, y se puede **volver a renderizar mañana**; con un HTML
    // congelado tienes una foto atada al ancho de impresora de aquel día.
    //
    // **Se BORRA la columna `html`, no se deja de escribir.** Lo que guardaba es inservible por
    // construcción: sin traductor, ningún host puede sacarlo por papel, y conservarla dejaría en el
    // esquema una columna que el contrato declara muerta — la clase de resto sobre la que alguien
    // vuelve a escribir dentro de seis meses.
    //
    // **Y los trabajos que ya estaban encolados se DEJAN MUERTOS con su motivo.** Un `pending` en el
    // formato viejo no se puede imprimir: dejarlo ahí lo haría reclamar por un host que no tiene con
    // qué renderizarlo, quemar sus cinco entregas y morir con un error que no explica nada. Aquí
    // muere una vez, con la frase que dice qué hacer (volver a imprimirlo desde la venta). En la
    // práctica alcanza a cero filas —hoy ningún productor encola de verdad, `sdk.print` sigue siendo
    // hub#344—, y por eso mismo es barato hacerlo bien.
    //
    // ⚠️ **Re-ejecutable** (regla de hub#342/#483): `ADD COLUMN IF NOT EXISTS`, `DROP COLUMN IF
    // EXISTS` y un `UPDATE` acotado a `document_type = ''` — que solo pueden cumplir las filas
    // heredadas, porque toda fila nueva pasa por `enqueue`, que exige un tipo del vocabulario. El
    // segundo pase es un no-op. Sin eso, rebobinar el control (lo que hace
    // `tests/access_email_backfill.rs` con su `version >= 19`) la mata y se lleva la suite de otro.
    //
    // ⚠️ **v25 y no un hueco.** `apply` compara contra el **máximo** aplicado: cualquier número en o
    // por debajo se salta EN SILENCIO. Los huecos v15 y v20 siguen libres e **inalcanzables**, y
    // cogerlos ES ese fallo mudo. Esta nació v24 y se renumeró a la v25 porque hub#362 reclamó la
    // 24 estando esta sin mergear — el máximo del catálogo se re-comprueba **al rebasar**, no al
    // empezar. Renumerar es gratis; **renombrar rompe** (los fixtures rebobinan por `name`).
    //
    // 🚨 **Y por eso la v24 queda en manos de quien mergee SEGUNDO.** Si esta entra antes que
    // hub#362, su v24 pasa a estar **por debajo del máximo** de cualquier hub que ya haya aplicado
    // la v25: `apply` se la saltaría **en silencio** y ese hub arrancaría sin su cambio, sin fallar
    // y sin un solo log. Quien llegue segundo **renumera** (v26), no rellena el hueco.
    SystemMigration {
        version: 25,
        name: "print_queue_structured_document",
        kind: Kind::Contract,
        postgres: "\
ALTER TABLE _print_queue ADD COLUMN IF NOT EXISTS document_type TEXT NOT NULL DEFAULT '';\
ALTER TABLE _print_queue ADD COLUMN IF NOT EXISTS document TEXT NOT NULL DEFAULT '';\
UPDATE _print_queue SET status = 'dead', \
  last_error = 'queued as HTML, which no printer could ever render (hub#501): print it again from the sale' \
  WHERE document_type = '' AND status IN ('pending', 'printing');\
ALTER TABLE _print_queue DROP COLUMN IF EXISTS html;",
    },
    // ── v26 — hub#362 / ADR-0265: the receipt of a spent step-up approval ────────────────────
    // Rule 3 of the PIN elevation plan: `created_by` is the cashier who was at the till,
    // `approved_by` the manager who authorised. hub#361 exposed the manager as the system
    // parameter `:approved_by`, but a parameter only becomes a record if somebody writes it —
    // and leaving that to each module means a module that never declares the column loses the
    // attribution IN SILENCE (today, none of the 24 published modules declares one).
    //
    // So the runtime keeps the record itself, here: it is the only component that knows an
    // approval happened at all. Note the deliberate contrast with the grant, which ADR-0246 keeps
    // out of the database on purpose — a grant is a *spendable credential* and must not survive a
    // restart or travel in a dump; this is a *receipt* for something that already happened, and
    // must survive precisely that.
    //
    // No soft-delete: an audit trail with an `is_deleted` flag is not an audit trail. `hub_id`
    // stays per row (row contract, ADR-0201) even though each hub now owns its database.
    SystemMigration {
        version: 26,
        name: "elevation_audit",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _elevation_audit (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, command TEXT NOT NULL, permission TEXT NOT NULL, \
  created_by TEXT NOT NULL, approved_by TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, \
  created_at TEXT NOT NULL, PRIMARY KEY (hub_id, id));\
CREATE INDEX IF NOT EXISTS idx_elevation_audit_when ON _elevation_audit (hub_id, created_at);",
    },
    // ── v27 — hub#549 / ADR-0273 D1/D6: the CORE decides THAT there is a fiscal obligation ─────
    // The rule: a fiscal obligation can never depend on a module being installed, enabled,
    // licensed or available. The module implements HOW to comply; the core determines THAT
    // compliance is owed. Today it is the other way round — uninstall the provider with an empty
    // queue (R2, hub#314, only looks at the queue) and the till keeps selling with nobody
    // generating the record. Five distinct paths end there; this table is what closes all five.
    //
    // `_hub_fiscal_profile` is the AUTHORITY, singleton per hub. What it deliberately does NOT
    // hold is which MODULE complies: it holds the *regime*, and the core counts how many installed
    // and active modules fulfil it — the same shape the ADR-0203 gate already uses for the
    // `certificate` capability without ever naming `verifactu`. Sealing a `module_id` would make
    // "swap one provider for an equivalent one" a runtime transition, which it is not.
    //
    // `_hub_fiscal_regime_registry` is DATA, not code, and carries exactly one row: `ES` →
    // `verifactu`. A country with no row resolves to `NOT_REQUIRED` and the hub is asked for
    // nothing, so France is one row plus a module the day it matters and Spain is never shipped to
    // hubs that do not owe it. The key is `(country_code, regime_key)` with `since` so a country
    // that CHANGES regime is one more row rather than a schema change; the resolver takes the most
    // recent `since` that has already arrived.
    //
    // Types follow the row contract: instants are RFC3339 TEXT with `''` for "never" (not NULL —
    // a third state is one more branch to slip through), flags are INTEGER 0/1, never BOOLEAN.
    // `can_go_live` defaults to 1 because a normal hub may go live; the demo turns it off
    // (hub#552). `status` defaults to `NOT_REQUIRED` because owing nothing is what a hub with no
    // country resolved yet owes — the row is then re-resolved on every boot until it goes live.
    //
    // ⚠️ **v27: the next number ABOVE THE MAXIMUM, re-checked at rebase.** `apply` compares against
    // the MAXIMUM applied version, so anything at or below it is skipped IN SILENCE — the hub boots
    // believing it is up to date, with the table missing and nothing logged. The v15, v20 and v24
    // gaps are free and permanently UNREACHABLE; taking one is that silent failure. This has
    // already renumbered hub#341, hub#342 (twice), hub#470 and hub#501. Renumbering is free;
    // RENAMING breaks (fixtures rewind by `name`).
    //
    // ⚠️ **Re-executable** (hub#342/#483): `CREATE TABLE IF NOT EXISTS` and an `ON CONFLICT DO
    // NOTHING` seed. `tests/access_email_backfill.rs` rewinds `_hub_system_migrations` to
    // `version >= 19`, which replays every later migration over a database where the objects are
    // already there; a bare `CREATE TABLE` fails 42P07 and takes 15 of that suite's tests with it.
    SystemMigration {
        version: 27,
        name: "hub_fiscal_profile",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _hub_fiscal_profile (\
  hub_id TEXT NOT NULL PRIMARY KEY, country_code TEXT NOT NULL DEFAULT '', \
  taxpayer_id TEXT NOT NULL DEFAULT '', fiscal_system TEXT NOT NULL DEFAULT '', \
  status TEXT NOT NULL DEFAULT 'NOT_REQUIRED', environment TEXT NOT NULL DEFAULT 'testing', \
  activated_at TEXT NOT NULL DEFAULT '', first_record_at TEXT NOT NULL DEFAULT '', \
  system_id TEXT NOT NULL DEFAULT '', fiscal_trigger_events TEXT NOT NULL DEFAULT '[]', \
  can_go_live INTEGER NOT NULL DEFAULT 1, needs_review INTEGER NOT NULL DEFAULT 0);\
CREATE TABLE IF NOT EXISTS _hub_fiscal_regime_registry (\
  country_code TEXT NOT NULL, regime_key TEXT NOT NULL, since TEXT NOT NULL DEFAULT '', \
  note TEXT NOT NULL DEFAULT '', PRIMARY KEY (country_code, regime_key));\
INSERT INTO _hub_fiscal_regime_registry (country_code, regime_key, since, note) \
  VALUES ('ES', 'verifactu', '', 'RD 1007/2023 — VERI*FACTU (ADR-0202)') \
  ON CONFLICT (country_code, regime_key) DO NOTHING;",
    },
    // ── v28 — hub#557 / ADR-0273 D2: the cessation of activity leaves a RECORD ────────────────
    // `CLOSED` already existed as a status and the dispatcher already refused writes in it
    // (hub#556). What did not exist was the way IN — and a one-way door with nothing written down
    // is a state somebody will later have to guess the origin of: was it the owner? a bug? which
    // day did the business actually stop?
    //
    // So the transition stamps the two facts nobody can reconstruct afterwards: WHEN it ceased and
    // WHO decided it. `closed_by` follows the same shape as `mode_set_by` (v17) and
    // `uploaded_by` (`_hub_certificate`): the `hub_user` id the door authenticated, never anything
    // read from a payload.
    //
    // Not a new table: this is one more fact about the singleton profile, and a row that already
    // carries `activated_at` (when it started filing for real) is exactly where "and when it
    // stopped" belongs.
    //
    // ⚠️ **v28: the next number ABOVE THE MAXIMUM, re-checked at rebase.** `apply` compares against
    // the MAXIMUM applied version, so anything at or below it is skipped IN SILENCE. The v15, v20
    // and v24 gaps are free and permanently UNREACHABLE; taking one is that silent failure.
    //
    // ⚠️ **Re-executable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS`. `tests/access_email_backfill.rs`
    // rewinds the control table and replays every later migration over a database that already has
    // the objects; a bare `ADD COLUMN` fails 42701 and takes that suite down with it.
    SystemMigration {
        version: 28,
        name: "hub_fiscal_profile_closed",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS closed_at TEXT NOT NULL DEFAULT '';\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS closed_by TEXT NOT NULL DEFAULT '';",
    },
    // ── v29 — hub#558 / ADR-0273 D8: taking over ANOTHER installation leaves a receipt ────────
    // `NumeroInstalacion = hub_id` (ADR-0202): a profile whose `system_id` is not this hub was
    // written by a different installation, so its chain is not this hub's to continue. The way out
    // is explicit and manual (`fiscal_profile::adopt_installation`) — never the boot deciding by
    // itself, because adopting somebody else's installation in silence is exactly how two chains
    // get mixed, and a record the tax authority already accepted is neither re-sent nor deleted
    // (ADR-0189).
    //
    // The takeover OVERWRITES `system_id`, which destroys the one fact nobody could reconstruct
    // afterwards: *which* installation these rows came from. `adopted_from` keeps it, and it is
    // the only evidence left that two chains could have been mixed here — worth more than the
    // other two columns put together. `adopted_at`/`adopted_by` follow the shape of `closed_at`/
    // `closed_by` (v28) and `mode_set_at`/`mode_set_by` (v17).
    //
    // ⚠️ **v29: the next number ABOVE THE MAXIMUM, re-checked at rebase.** `apply` compares against
    // the maximum applied version, so anything at or below it is skipped IN SILENCE.
    //
    // ⚠️ **Re-executable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS`.
    SystemMigration {
        version: 29,
        name: "hub_fiscal_profile_adopted",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS adopted_at TEXT NOT NULL DEFAULT '';\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS adopted_from TEXT NOT NULL DEFAULT '';\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS adopted_by TEXT NOT NULL DEFAULT '';",
    },
    // ── v30 — hub#516: el PIN DE SOPORTE de un módulo ──────────────────────────────────────
    // Con la actualización automática, el arranque resuelve la ÚLTIMA versión instalable de cada
    // módulo en vez de la registrada. `pinned_version` es la salida de emergencia: cuando un
    // cliente tiene un problema con `sales@3.2`, se le deja en `3.1` mientras se arregla, **sin
    // tocar a los demás**.
    //
    // No es una opción de producto —el dueño no elige, ADR-0269— sino una herramienta nuestra, y
    // por eso no hay UI: se pone a mano y se quita a mano.
    //
    // ADITIVA: columna nullable, así que un binario anterior la ignora y sus INSERT siguen
    // funcionando (la regla de hub#517 para que el rollback no tenga nada que deshacer).
    SystemMigration {
        version: 30,
        name: "hub_module_pinned_version",
        kind: Kind::Expand,
        postgres: "ALTER TABLE hub_module ADD COLUMN IF NOT EXISTS pinned_version TEXT;",
    },
    // ── v31 — hub#661 / ADR-0283 K1: `_flow`, the flow itself ────────────────────────────────
    // A flow is a core row with a VERSIONED JSON definition (`schema_version`, 1 from day one:
    // an unknown version is refused, never guessed). The definition is stored as it was written,
    // not exploded into columns, because the shape that gets frozen is the DOCUMENT (§9) — and a
    // document the kernel can round-trip is what lets a future `schema_version: 2` read what v1
    // wrote instead of migrating rows.
    //
    // Row contract of `tenancy.md`, in full: `hub_id`, soft-delete (`deleted_at`/`deleted_by`) and
    // audit on both ends. It is not ceremony here — a flow row is a standing authorisation for the
    // hub to act with nobody watching, so "who created this, who last changed it, and when did it
    // stop existing" is the minimum an audit can ask.
    //
    // ⚠️ **v31: the next number ABOVE THE MAXIMUM, re-checked at rebase** (hub#573). `apply`
    // aborts loudly on a catalogue entry at or below the maximum applied version, but only after a
    // hub already has the higher number — pick the number against `origin/develop`, not memory.
    SystemMigration {
        version: 31,
        name: "flow",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, name TEXT NOT NULL, \
  enabled INTEGER NOT NULL DEFAULT 1, schema_version INTEGER NOT NULL DEFAULT 1, \
  definition TEXT NOT NULL DEFAULT '{}', \
  created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', \
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
  deleted_at TEXT, deleted_by TEXT, \
  PRIMARY KEY (id));\
CREATE INDEX IF NOT EXISTS ix_flow_hub ON _flow (hub_id);",
    },
    // ── v32 — hub#661 / ADR-0283 D2: `_flow_grants`, what a flow is allowed to do ─────────────
    // **Default-deny by absence**: no row, no permission. There is deliberately no `granted`
    // boolean — a grant either exists and is alive, or it does not exist. A column would allow a
    // row that says "no", and then two places would have to agree on what that means.
    //
    // Revocation is a SOFT-DELETE, so the partial unique index has to be partial: without the
    // `WHERE deleted_at IS NULL`, revoking a grant and granting it again later would collide with
    // its own tombstone, and the owner would be told the permission is already given while the
    // gate refuses it. `granted_by`/`revoked_by` name the admin on both ends — a grant is the one
    // thing in the kernel that a person, not a machine, has to decide.
    //
    // ⚠️ v32: number re-checked against the maximum at rebase (hub#573).
    SystemMigration {
        version: 32,
        name: "flow_grants",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_grants (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, flow_id TEXT NOT NULL, \
  kind TEXT NOT NULL, value TEXT NOT NULL, \
  created_at TEXT NOT NULL, granted_by TEXT NOT NULL DEFAULT '', \
  deleted_at TEXT, revoked_by TEXT, \
  PRIMARY KEY (id));\
CREATE UNIQUE INDEX IF NOT EXISTS ux_flow_grant_live \
  ON _flow_grants (hub_id, flow_id, kind, value) WHERE deleted_at IS NULL;\
CREATE INDEX IF NOT EXISTS ix_flow_grant_flow ON _flow_grants (hub_id, flow_id);",
    },
    // ── v33 — hub#661 / ADR-0283 §3: `_flow_triggers`, materialised from the definition ───────
    // The triggers live INSIDE the flow document; this table is the index the hot paths read —
    // the outbox relay asking "does this event start anything?" and the tick asking "is anything
    // due?". Re-saving a flow re-seeds it idempotently and **preserves `next_run`** (the
    // `seed_module_tasks` pattern): editing the name of a flow must not silently reschedule a
    // nightly job to now.
    //
    // `trigger_key` is the identity of a trigger WITHIN its flow, so re-seeding updates instead of
    // duplicating. `claim_expires_at` mirrors `_scheduled_tasks`/`_event_outbox`: with start-first
    // deploys (ADR-0269) two runtimes of the same hub share this table, and a due trigger must
    // fire once, not twice.
    //
    // `_scheduled_tasks` is deliberately NOT reused (ADR-0283 §3): it is keyed by
    // `(module_id, name)` and fires a command of that module. A flow is not a module.
    //
    // ⚠️ v33: number re-checked against the maximum at rebase (hub#573).
    SystemMigration {
        version: 33,
        name: "flow_triggers",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_triggers (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, flow_id TEXT NOT NULL, \
  trigger_key TEXT NOT NULL, kind TEXT NOT NULL, \
  event_name TEXT NOT NULL DEFAULT '', filter TEXT NOT NULL DEFAULT '{}', \
  input_map TEXT NOT NULL DEFAULT '{}', cron TEXT NOT NULL DEFAULT '', \
  run_at TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, \
  next_run TEXT, last_run TEXT, claim_expires_at TEXT, \
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT, \
  PRIMARY KEY (id));\
CREATE UNIQUE INDEX IF NOT EXISTS ux_flow_trigger_key \
  ON _flow_triggers (hub_id, flow_id, trigger_key) WHERE deleted_at IS NULL;\
CREATE INDEX IF NOT EXISTS ix_flow_trigger_event \
  ON _flow_triggers (hub_id, kind, event_name) WHERE deleted_at IS NULL;\
CREATE INDEX IF NOT EXISTS ix_flow_trigger_due ON _flow_triggers (next_run);",
    },
    // ── v34 — hub#661 / ADR-0283 §8: `_flow_runs`, one execution of one flow ──────────────────
    // The run is the unit of recovery: `claim_expires_at` + `FOR UPDATE SKIP LOCKED` (the outbox
    // and print-queue model) so a runtime that dies mid-run does not strand it, and `wake_at` so a
    // `delay` step costs a row update instead of a held task.
    //
    // **`depth` is the anti-loop guard and it is why this column exists** (an addition to the
    // design in flows.md §3, which relied on the event depth alone). A run inherits the depth of
    // the event that started it and passes it to `execute_at`, so the events its commands emit
    // come out one level deeper. Without it every flow-emitted event would be born at depth 1 and
    // a flow that triggers itself would spin forever at a depth the guard never notices — the
    // guard would be describing a ceiling nothing ever climbs.
    //
    // ⚠️ v34: number re-checked against the maximum at rebase (hub#573).
    SystemMigration {
        version: 34,
        name: "flow_runs",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_runs (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, flow_id TEXT NOT NULL, \
  trigger_id TEXT NOT NULL DEFAULT '', trigger_kind TEXT NOT NULL DEFAULT '', \
  parent_event_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending', \
  current_step INTEGER NOT NULL DEFAULT 0, input TEXT NOT NULL DEFAULT '{}', \
  vars TEXT NOT NULL DEFAULT '{}', depth INTEGER NOT NULL DEFAULT 0, \
  wake_at TEXT, attempts INTEGER NOT NULL DEFAULT 0, \
  last_error TEXT NOT NULL DEFAULT '', claim_expires_at TEXT, \
  started_at TEXT, finished_at TEXT, \
  created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', \
  updated_at TEXT NOT NULL, deleted_at TEXT, \
  PRIMARY KEY (id));\
CREATE INDEX IF NOT EXISTS ix_flow_run_due ON _flow_runs (hub_id, status, wake_at);\
CREATE INDEX IF NOT EXISTS ix_flow_run_flow ON _flow_runs (hub_id, flow_id, created_at);",
    },
    // ── v35 — hub#661 / ADR-0283 §8: `_flow_run_steps`, what each step did ────────────────────
    // One row per step attempted, with its resolved input and its output. The output is not a log
    // line: the mapping language reads it back as `steps.<step_id>.<field>`, so this table is the
    // *memory* of a run, and losing it would break the next step, not just the audit.
    //
    // `(run_id, step_index)` is unique among live rows: v1 is LINEAR (ADR-0283 §5), so a step
    // index happening twice in one run is a bug, and the index is where that bug surfaces instead
    // of quietly doubling an invoice.
    //
    // ⚠️ v35: number re-checked against the maximum at rebase (hub#573).
    SystemMigration {
        version: 35,
        name: "flow_run_steps",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_run_steps (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, run_id TEXT NOT NULL, \
  step_index INTEGER NOT NULL, step_id TEXT NOT NULL, kind TEXT NOT NULL, \
  status TEXT NOT NULL DEFAULT 'pending', input TEXT NOT NULL DEFAULT '{}', \
  output TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', \
  started_at TEXT, finished_at TEXT, \
  created_at TEXT NOT NULL, deleted_at TEXT, \
  PRIMARY KEY (id));\
CREATE UNIQUE INDEX IF NOT EXISTS ux_flow_run_step \
  ON _flow_run_steps (run_id, step_index) WHERE deleted_at IS NULL;\
CREATE INDEX IF NOT EXISTS ix_flow_run_step_run ON _flow_run_steps (hub_id, run_id, step_index);",
    },
    // ── v36 — hub#662 / ADR-0283 §4: `_flow_secrets`, the credentials an `http` step carries ────
    // WRITE-ONLY by construction. The column holds the `secret_box` envelope (AES-256-GCM, master
    // key in the environment — hub#114), so a backup, a support dump or a stolen volume carries the
    // ciphertext and never the key: the key was never next to the data it protects.
    //
    // There is deliberately NO read path for a human — `flows::secrets::list` answers names, and the
    // only reader is the executor while it builds the request that is about to leave. A "reveal"
    // button would turn every admin session into a copy of every API key the hub holds.
    //
    // Unique per (hub, name) among LIVE rows, partial for the same reason as `_flow_grants`:
    // forgetting a credential and adding it again later must not collide with its own tombstone.
    //
    // ⚠️ v36: number re-checked against the maximum on `origin/develop` right before the push
    // (hub#573) — three flow issues were in flight at once and each wanted a number.
    SystemMigration {
        version: 36,
        name: "flow_secrets",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_secrets (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, name TEXT NOT NULL, \
  value_enc TEXT NOT NULL DEFAULT '', \
  created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', \
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
  deleted_at TEXT, deleted_by TEXT, \
  PRIMARY KEY (id));\
CREATE UNIQUE INDEX IF NOT EXISTS ux_flow_secret_name \
  ON _flow_secrets (hub_id, name) WHERE deleted_at IS NULL;",
    },
    // ── v37 — hub#731: en qué reloj se armó cada trigger de reloj ──────────────────────────────
    // `next_run` siempre es UTC (es una columna TEXT que se compara con `<=`, y un `+02:00` en la
    // cadena ordenaría como otro instante). Lo que cambia con hub#731 es **cómo se lee** el cron:
    // en la zona del negocio, porque «cierra la caja a las 21:00» son las 21:00 de la tienda.
    //
    // Esta columna guarda la zona con la que se calculó el `next_run` que hay en la fila, y con
    // eso una sola comprobación en el barrido resuelve los DOS casos que el cambio abre:
    //   1. los triggers que ya estaban armados **en UTC** antes de este arreglo, y
    //   2. un negocio que se muda de huso (o corrige su país) y espera que sus flujos le sigan.
    // En ambos la fila dice una zona distinta de la del hub y se re-arma sola en el siguiente
    // tick. Sin la columna habría que resembrar a mano o dejar el reloj viejo hasta el próximo
    // disparo, que es medio año de diferencia para un flujo anual.
    //
    // `''` = «se calculó antes de que esto existiera» (o sea, UTC), que es justo lo que dispara
    // el re-armado la primera vez.
    //
    // ⚠️ v37: número re-comprobado contra el máximo de `origin/develop` justo antes del push
    // (hub#573) — hay varias ramas de flujos a la vez y cada una quiere un número.
    SystemMigration {
        version: 37,
        name: "flow_trigger_timezone",
        kind: Kind::Expand,
        postgres: "ALTER TABLE _flow_triggers ADD COLUMN IF NOT EXISTS tz TEXT NOT NULL DEFAULT '';",
    },
    // ── v38 — hub#665 / ADR-0283 D3: `_flow_approvals`, the write that waits for a person ─────
    // The row an `ai` step writes instead of the booking. Everything a person needs to decide at
    // 9 AM about something a model proposed at 3 AM is HERE and not in a log line: the `command`
    // and the `payload` that will run, verbatim, and the `reason` the model gave. A tray that
    // showed an opaque id would be a button people press without reading.
    //
    // `payload` is the whole contract of the feature: approving runs EXACTLY this, re-checking the
    // grant at that moment, and never re-entering the model (ADR-0283 §7). So it is stored, not
    // re-derived — a re-derived payload is a different booking with the same name.
    //
    // `decided_by`/`decided_at` are written from the resolved SESSION, never from a body (same
    // rule as `discarded_by` in `outbox_admin.rs`): "who authorised the hub to write while nobody
    // was watching" is the one fact this table exists to keep.
    //
    // `expires_at` bounds it. A proposal is not a standing authorisation, and one left in the tray
    // for a month is about a Tuesday that has passed.
    //
    // ⚠️ v38, and it has been renumbered TWICE: it started life as v36 (hub#662 landed
    // `_flow_secrets` there while this branch was in flight), was pushed as v37, and hub#731 took
    // that one too with `_flow_triggers.tz` before this branch merged. `apply` aborts loudly on a
    // catalogue entry at or below the maximum applied version — but only once a hub already carries
    // the higher number, which is far too late to notice. Several flow issues wanted a number in
    // the same wave; re-check it against `origin/develop` at push time, do not remember it.
    SystemMigration {
        version: 38,
        name: "flow_approvals",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_approvals (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, run_id TEXT NOT NULL, flow_id TEXT NOT NULL, \
  step_id TEXT NOT NULL, command TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', \
  reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending', \
  decided_by TEXT NOT NULL DEFAULT '', decided_at TEXT, expires_at TEXT, \
  error TEXT NOT NULL DEFAULT '', \
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT, \
  PRIMARY KEY (id));\
CREATE INDEX IF NOT EXISTS ix_flow_approval_tray \
  ON _flow_approvals (hub_id, status, created_at);\
CREATE INDEX IF NOT EXISTS ix_flow_approval_run ON _flow_approvals (hub_id, run_id);",
    },
    // ── v39 — hub#670: the user-activity mark stops being memory and becomes a row ──────────────
    // `ActivityState` (ADR-0175) held the only proof that somebody had entered this hub, in an
    // `AtomicI64`. Fine while a restart was rare; with `order: start-first` (ADR-0269) **every
    // update kills a task**, and a visit between the mark and the next heartbeat died with the
    // process. The Cloud counts silence: 60 days ⇒ powered off, 90 ⇒ flagged, **120 ⇒ deleted**.
    // Losing that mark costs a customer's hub, and deleting is not undoable.
    //
    // One row per hub (`hub_id` PK) — the same row contract as the rest of the system schema
    // (ADR-0201), so a legacy shared database keeps each hub's clock apart. Timestamps are
    // RFC3339 UTC TEXT like `_print_queue`/`_event_outbox`: fixed width and always `Z`, so the
    // `GREATEST` of the upsert compares them chronologically without a cast.
    //
    // `last_reported_at` is nullable on purpose: NULL is "the Cloud has never confirmed one",
    // which is a different fact from "the epoch" and is what makes the mark pending again.
    //
    // ⚠️ v39: number re-checked against `origin/develop` right before the push (hub#573) — the
    // flow wave renumbered itself twice in a week.
    SystemMigration {
        version: 39,
        name: "hub_activity",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _hub_activity (\
  hub_id TEXT NOT NULL, last_activity_at TEXT NOT NULL, last_reported_at TEXT, \
  updated_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id));",
    },
    // ── v40 — hub#564 / ADR-0269 §3.5: `_update_history`, what we changed and from which version ─
    // We update on our own, without asking. The counterpart is that the owner can find out WHAT we
    // changed — and that answer cannot be derived from anywhere else: the hub knows its current
    // version and each module's current version, and a current state cannot be subtracted from
    // itself to produce a history. The transition has to be written down WHEN it happens.
    //
    // One row per **component** (`hub` | `module`), not a `hub_module_update`: the screen puts
    // `ERPlora 1.1.3 → 1.1.4` and `Inventory 1.1.1 → 1.1.2` on the same list, so a module-only
    // table would be the wrong shape with its correction migration already behind it (the reason
    // hub#516 deliberately did not build it).
    //
    // `name` is stored, not joined: it is what the owner reads ("Inventory", not `inventory` —
    // ADR-0254), and it has to survive the module being uninstalled. A history that degrades into
    // ids the moment an app is removed is a history about us, not about them.
    //
    // `outcome = 'baseline'` is bookkeeping, never shown: the first version we ever see is not a
    // change, but without it the NEXT jump would have no `from`, and `from` is half the value.
    //
    // ⚠️ v40, and it was born v39: hub#670 landed `_hub_activity` on that number while this
    // branch was in flight, so it was renumbered at rebase time. `apply` aborts loudly on a
    // catalogue entry at or below the maximum applied version — but only once a hub already
    // carries the higher number, which is far too late to notice. Re-check it against
    // `origin/develop` at push time (hub#573); do not remember it.
    SystemMigration {
        version: 40,
        name: "update_history",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _update_history (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, \
  component TEXT NOT NULL, component_id TEXT NOT NULL DEFAULT '', \
  name TEXT NOT NULL DEFAULT '', \
  from_version TEXT NOT NULL DEFAULT '', to_version TEXT NOT NULL, \
  outcome TEXT NOT NULL DEFAULT 'updated', reason TEXT NOT NULL DEFAULT '', \
  created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', \
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
  deleted_at TEXT, deleted_by TEXT, \
  PRIMARY KEY (id));\
CREATE INDEX IF NOT EXISTS ix_update_history_recent \
  ON _update_history (hub_id, created_at);\
CREATE INDEX IF NOT EXISTS ix_update_history_component \
  ON _update_history (hub_id, component, component_id, created_at);",
    },
    // ── v41 — hub#571: la copia PROPIA del `module.zip` de cada módulo instalado ──────────────
    //
    // Hub Cloud es **stateless a propósito** (`HUB_MODULE_CACHE=/tmp/module-cache`, sin volumen —
    // así el contenedor se reprograma a cualquier worker). El precio era que un crash, un redeploy
    // o un reschedule dejaba la caché de descargas vacía y la ÚNICA forma de recuperarla era volver
    // al marketplace: con el SaaS caído, el hub arrancaba **sin un solo módulo** y el bar sin TPV.
    //
    // Esta tabla es la copia que sobrevive a eso. Va en la BD del hub y no en Object Storage a
    // propósito: el hub **no tiene credenciales S3** (infra#44), así que su Object Storage se lee
    // por el proxy `Hub→Cloud→S3` — es decir, por el SaaS, que es justo lo que puede estar caído.
    // Su propia base es lo único duradero que no es el SaaS y que tampoco ata el contenedor a un
    // nodo, y encima viaja con el hub si hay que restaurarlo en otra máquina.
    //
    // `zip_base64` y no BYTEA: los parámetros del adaptador son JSON (`Params = Map<String, Json>`),
    // así que un binario solo viaja como texto — el mismo camino que ya usa el `.p12` fiscal. Un
    // zip de módulo real pesa 100–400 KB, así que un hub completo son unos pocos MB toasteados.
    //
    // `sha256` + `signature_json` viajan CON los bytes porque la copia se repone por la MISMA
    // puerta verificada que una descarga (`ModuleStore::install`): sin ellos habría que confiar en
    // la fila, y una caché que confía en sí misma es una vía de carga de código sin verificar.
    //
    // Una fila por (hub, módulo): interesa la versión que corre, no el histórico.
    //
    // ⚠️ v41, y nació como v39: hub#670 (`_hub_activity`) se llevó el 39 y hub#564
    // (`_update_history`) el 40 mientras esta rama estaba en vuelo — dos renumerados en el mismo
    // día. `apply` aborta ruidosamente si una entrada del catálogo cae en o por debajo del máximo
    // aplicado, pero solo cuando un hub ya lleva el número más alto, que es tardísimo para
    // enterarse. Recompruébalo contra `origin/develop` en el push (hub#573); no lo recuerdes.
    SystemMigration {
        version: 41,
        name: "hub_module_package",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS hub_module_package (\
  hub_id TEXT NOT NULL, module_id TEXT NOT NULL, version TEXT NOT NULL, \
  sha256 TEXT NOT NULL, signature_json TEXT, zip_base64 TEXT NOT NULL, \
  stored_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id, module_id));",
    },
    // ── v42 — hub#497: la IDENTIDAD también es de un hub, no de una base de datos ───────────────
    // `hub_user` y `hub_session` eran las dos últimas tablas de sistema sin `hub_id`, cuando todas
    // las demás —`hub_settings`, `hub_api_key`, `hub_module`, `hub_user_profile` y, desde hub#489,
    // `hub_trusted_device`— van por `(hub_id, …)`. El **perfil** de una persona era por hub; la
    // persona no, y la sesión tampoco.
    //
    // En una BD compartida eso no era «ver de más», era **entrar**: `resolve_session` casaba por
    // `token` a secas, así que un token del hub B autenticaba contra el A con el rol que su titular
    // tiene *allí*; `verify_pin` buscaba por nombre en toda la tabla, así que un PIN de 4 dígitos
    // del negocio de al lado era un login aquí; el desalojo de ADR-0154 y el corte de un
    // dispositivo (hub#489) borraban sesiones de los vecinos.
    //
    // ⚠️ **El backfill NO adivina.** Se sella `:hub_id` —el del despliegue— en las filas que no
    // dicen de quién son, y eso es correcto **porque desde ADR-0201 cada hub es dueño de su propia
    // base de datos** (`Hub.database_name` + rol propio). Comprobado antes de escribir esto contra
    // la producción real: 5 hubs, 5 bases distintas, 5 roles distintos, ninguna compartida, y el
    // más antiguo creado DESPUÉS de que ADR-0201 se cerrara — no queda ni un hub heredado que
    // migrar. Y el camino que las compartía se borró, no se capó (`sibling_url` no existe en el
    // SaaS; `_provision_hub_prerequisites` crea siempre `hub_{uuid12}`), así que tampoco puede
    // volver a aparecer una. En una BD de un solo hub, «toda fila es de este hub» es un hecho, no
    // una conjetura.
    //
    // **Y no se borra nada.** v23 sí borró las filas sin `hub_id` de `hub_trusted_device`: allí lo
    // perdido era una confianza que se recupera con un login. Aquí las filas son **personas** —su
    // historial, sus ventas, su auditoría cuelgan de ese id— y el criterio de hub#436 (señalar, no
    // adivinar) no puede aplicarse borrándolas.
    //
    // **La PK no se recompone** a `(hub_id, id)`: `hub_user.id` es un UUID y `hub_session.token`
    // son 32 bytes aleatorios, así que no pueden chocar entre hubs. Una clave compuesta no
    // aportaría unicidad y rompería todo lo que ya viaja solo por id — `hub_user_profile(hub_id,
    // user_id)`, los `hub_user:<id>` de cada columna de auditoría, los bundles exportados y las
    // sesiones ya emitidas. Lo que faltaba nunca fue una clave: era un `WHERE`.
    //
    // ⚠️ **Re-ejecutable** (regla hub#342/#483): `ADD COLUMN IF NOT EXISTS`, un `UPDATE` acotado a
    // `hub_id IS NULL` y `SET NOT NULL` (idempotente). El segundo pase es un no-op — importa porque
    // los fixtures rebobinan el control por versión.
    //
    // ⚠️ **v42 porque 41 es el máximo del catálogo hoy.** `apply` aborta si una entrada cae en o por
    // debajo del máximo ya aplicado. Recomprobado contra `origin/develop` en el push (hub#573); los
    // huecos v15/v20/v24 siguen libres e **inalcanzables** — cogerlos ES el fallo mudo.
    SystemMigration {
        version: 42,
        name: "hub_identity_hub_scoped",
        kind: Kind::Contract,
        postgres: "\
ALTER TABLE hub_user ADD COLUMN IF NOT EXISTS hub_id TEXT;\
UPDATE hub_user SET hub_id = :hub_id WHERE hub_id IS NULL;\
ALTER TABLE hub_user ALTER COLUMN hub_id SET NOT NULL;\
ALTER TABLE hub_session ADD COLUMN IF NOT EXISTS hub_id TEXT;\
UPDATE hub_session SET hub_id = :hub_id WHERE hub_id IS NULL;\
ALTER TABLE hub_session ALTER COLUMN hub_id SET NOT NULL;\
CREATE INDEX IF NOT EXISTS ix_hub_user_hub ON hub_user (hub_id, name);\
CREATE INDEX IF NOT EXISTS ix_hub_session_hub ON hub_session (hub_id);",
    },
    // ── v43 — hub#817 / saas#1438: el OTORGAMIENTO firmado, recordado en el perfil ─────────────
    // ERPlora remite los registros **en nombre del** obligado, y eso exige su consentimiento
    // firmado (Anexo I de la Resolución DG AEAT de 18/12/2024, bajo el Convenio 17). El documento
    // lo **custodia el SaaS** —es a ERPlora a quien se otorga—, así que este hub no puede ser la
    // autoridad sobre un papel que no guarda: estas dos columnas son una COPIA de lo que el plano
    // de control contestó.
    //
    // Por qué se copia en vez de preguntar: `fiscal_profile::go_live` es una transición de base de
    // datos, y meterle una llamada de red la haría fallar cuando el SaaS no responde —justo el
    // momento en que un negocio menos quiere que le bloqueen el paso a producción— o la obligaría
    // a adivinar. Guardada, la respuesta **sobrevive al reinicio**: en memoria, un redespliegue la
    // convertiría en «no sé», que es o una puerta abierta o una atascada.
    //
    // `''` = «nunca se preguntó», distinto de `absent` = «se preguntó y no hay ninguno». Son dos
    // estados distintos para la pantalla: uno dice «cargando», el otro «tienes que firmar». Las dos
    // columnas siguen el contrato de fila: TEXT, `''` para «desconocido», nunca NULL.
    //
    // ⚠️ v43, y nació como v42: `hub_identity_hub_scoped` (hub#497) se llevó el 42 mientras esta
    // rama estaba en vuelo, y el rebase lo destapó como conflicto — que es exactamente para lo
    // que sirve tener el número a mano. `apply` aborta ruidosamente si una entrada del catálogo
    // cae en o por debajo del máximo aplicado, pero solo cuando un hub ya lleva el número más
    // alto: tardísimo para enterarse. Recompruébalo contra `origin/develop` en el push
    // (hub#573); no lo recuerdes.
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS`. `tests/access_email_backfill.rs`
    // rebobina la tabla de control y reaplica todo lo posterior sobre una BD que ya tiene los
    // objetos; un `ADD COLUMN` pelado falla 42701 y se lleva esa suite por delante.
    SystemMigration {
        version: 43,
        name: "hub_fiscal_representation",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS representation_status TEXT NOT NULL DEFAULT '';\
ALTER TABLE _hub_fiscal_profile ADD COLUMN IF NOT EXISTS representation_at TEXT NOT NULL DEFAULT '';",
    },
    // ── v44 — hub#494: el dispositivo tiene un NOMBRE que pone el negocio ─────────────────────
    // La única etiqueta legible de un dispositivo era `label`, y la escribe el login online con el
    // nombre de la **persona** que entró (viaja en el body, o sea que la elige el cliente) y la
    // pisa en cada entrada. Con ADR-0257 el `device_id` es opaco a propósito, así que en un negocio
    // con tres tablets la lista eran tres filas con el mismo nombre de persona y tres ids que no
    // dicen nada — justo delante del botón que corta una. `name` es el hueco de lo que decide el
    // dueño: lo escribe una puerta admin (`PUT /api/devices/:id`) y el login NO lo toca nunca.
    //
    // Columna nueva, **no** se reutiliza `label`: «quién entró la última vez» sigue siendo un dato
    // útil (una pista) y merece su hueco. `''` = «nadie lo ha nombrado todavía», que la pantalla
    // convierte en «sin nombre»; distinto de un nombre en blanco. Contrato de fila: TEXT, `''`
    // para desconocido, nunca NULL.
    //
    // ⚠️ El número es DECLARADO, no la posición en este slice (faltan la 15, la 20 y la 24), así
    // que contar entradas no vale: recompruébalo contra `origin/develop` justo antes de empujar
    // (hub#573 hizo que una versión en o por debajo del máximo aplicado ABORTE el arranque
    // nombrándola, en vez de saltarse en silencio). Comprobado contra `origin/develop` 430285b5.
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS`, como las otras dos de esta
    // misma tabla (v17 `hub_trusted_device_mode`, v23 `hub_trusted_device_hub_scoped`). Aditiva y
    // sin backfill: no hereda nada de hub#489, que ya dio `hub_id` a la tabla.
    SystemMigration {
        version: 44,
        name: "hub_trusted_device_name",
        kind: Kind::Expand,
        postgres: "ALTER TABLE hub_trusted_device ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';",
    },
    // ── v45 — hub#972: qué le pasa al RUN cuando su aprobación caduca, escrito en la FILA ──────
    // El TTL de 72 h solo se miraba al leer (`claim_pending`): una fila vencida no se podía ni
    // aprobar ni rechazar —las dos vías pasan por ahí— y su run se quedaba en `waiting_approval`
    // para siempre, exento de la poda de 90 días con el `payload` verbatim dentro (RGPD). El
    // barrido que lo saca de ahí necesita saber QUÉ hacer, y esa respuesta no puede ser una
    // constante en el código: el step `approval` genérico (hub#950) la elige **por documento**
    // (`on_expire: reject | cancel | continue`), así que el dato viaja donde viaja la decisión —
    // en la fila, junto al `payload` que también se guarda en vez de re-derivarse.
    //
    // `'reject'` por defecto, y es la respuesta conservadora a propósito: los steps escritos
    // después de un `ai` asumían que la escritura ocurrió, así que «nadie contestó» se parece
    // mucho más a un «no» que a un «sí». `continue` es opt-in de quien escribió el documento.
    //
    // Aditiva y re-ejecutable (`ADD COLUMN IF NOT EXISTS`), sin backfill: el DEFAULT ya deja a las
    // filas existentes con la política que tendrían igualmente.
    //
    // ⚠️ El número es DECLARADO, no la posición en el slice, y hay varias ramas de flujos a la vez
    // queriendo número: recompruébalo contra `origin/develop` justo antes de empujar (hub#573 hace
    // que una versión en o por debajo del máximo aplicado ABORTE el arranque en vez de saltarse en
    // silencio). Comprobado contra `origin/develop` 6a0e8e27.
    SystemMigration {
        version: 45,
        name: "flow_approval_on_expire",
        kind: Kind::Expand,
        postgres: "ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS on_expire TEXT NOT NULL DEFAULT 'reject';",
    },
    // ── v46 — hub#735: `_event_delivery` también es de un hub ────────────────────────────────
    // Era la última tabla del radio del kernel de flujos **sin `hub_id` a nivel de esquema**, y no
    // es una tabla cualquiera: es donde se escribe el marcador de idempotencia de cada entrega —
    // el de los listeners de un módulo (`_event_delivery(event_id, listener_command)`) y el del
    // disparador de un flujo, bajo el listener sintético `_flow:<trigger_id>`. Es la pieza que
    // garantiza «un evento produce UN run», y estaba fuera del contrato de fila de `tenancy.md`.
    //
    // ⚠️ **El backfill NO adivina.** Sella `:hub_id` —el del despliegue— en los marcadores que no
    // dicen de quién son, y eso es correcto **porque desde ADR-0201 cada hub es dueño de su propia
    // base de datos** (`Hub.database_name` + rol propio): en una BD de un solo hub, «todo marcador
    // es de este hub» es un hecho, no una conjetura. Es el mismo criterio y el mismo párrafo que
    // la v42 escribió para `hub_user`/`hub_session`.
    //
    // **Y no se borra nada**: un marcador perdido no es espacio recuperado, es un listener que
    // vuelve a correr y un evento que produce un segundo run.
    //
    // **La PK NO se recompone** a `(hub_id, event_id, listener_command)`, por la misma razón que
    // v42 no la recompuso en `hub_user`: `event_id` es un UUID v4 y no puede chocar entre hubs, así
    // que una clave más ancha no añadiría unicidad — y la ESTRECHA es más fuerte. Ampliarla sería
    // permitir dos marcadores para el mismo evento con `hub_id` distinto, que es exactamente el
    // «entregado dos veces» que esta tabla existe para impedir. Lo que faltaba era un `WHERE`.
    //
    // El índice `(hub_id, event_id)` es lo que hace respondible «los marcadores de este hub» sin
    // recorrer la tabla entera; las lecturas calientes siguen entrando por la PK.
    //
    // ⚠️ **`NOT NULL` y no `DEFAULT ''`, a sabiendas de la ventana del start-first** (ADR-0269).
    // Mientras el contenedor viejo sigue vivo, sus `INSERT` de marcador (sin `hub_id`) fallan: la
    // transacción del listener hace **rollback entera**, así que no hay entrega a medias ni
    // marcador huérfano, y la fila del outbox se reintenta con backoff hasta que el contenedor
    // nuevo la coge. Un `DEFAULT ''` evitaría ese fallo y a cambio dejaría marcadores sin dueño que
    // el lector scopeado **no vería nunca** y que chocarían con la PK para siempre: el evento
    // reentregado, el listener corriendo dos veces y la fila muerta en dead-letter. El fallo
    // transitorio es el que se puede desandar solo.
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS`, `UPDATE` acotados a
    // `hub_id IS NULL`, `SET NOT NULL` idempotente y `CREATE INDEX IF NOT EXISTS`. Importa porque
    // los fixtures rebobinan la tabla de control por versión y reaplican todo lo posterior sobre
    // una BD que ya tiene los objetos.
    //
    // ⚠️ **v46, y nació como v45**: `flow_approval_on_expire` (hub#972) se llevó el 45 mientras
    // esta rama estaba en vuelo, y el rebase lo destapó como conflicto — que es exactamente para
    // lo que sirve tener el número a mano. `apply` aborta si una entrada cae en o por debajo del
    // máximo ya aplicado, pero solo cuando un hub ya lleva el número más alto: tardísimo para
    // enterarse. Recomprobado contra `origin/develop` en el push (hub#573); los huecos v15/v20/v24
    // siguen libres e **inalcanzables**: cogerlos ES el fallo mudo.
    SystemMigration {
        version: 46,
        name: "event_delivery_hub_scoped",
        kind: Kind::Contract,
        // El `CREATE … IF NOT EXISTS` de cabeza no es redundante: la tabla la pone
        // `outbox::ensure_tables` (v0, el suelo) y en un hub real ya existe cuando esto corre —
        // pero una migración que se cae si la tabla no está solo se puede aplicar en un orden, y
        // este catálogo se reaplica entero sobre bases en cualquier estado.
        postgres: "\
CREATE TABLE IF NOT EXISTS _event_delivery (\
  event_id TEXT NOT NULL, listener_command TEXT NOT NULL, delivered_at TEXT NOT NULL, \
  hub_id TEXT NOT NULL, \
  PRIMARY KEY (event_id, listener_command));\
ALTER TABLE _event_delivery ADD COLUMN IF NOT EXISTS hub_id TEXT;\
UPDATE _event_delivery SET hub_id = :hub_id WHERE hub_id IS NULL;\
ALTER TABLE _event_delivery ALTER COLUMN hub_id SET NOT NULL;\
CREATE INDEX IF NOT EXISTS ix_event_delivery_hub ON _event_delivery (hub_id, event_id);",
    },
    // ── v47 — hub#457: las estaciones de impresión pasan a ser FILAS con id ───────────────────
    // Hasta aquí «qué impresora imprime esto» viajaba como **cadena libre comparada literalmente**:
    // `enqueue` guardaba el `role` que llegara, `register` registraba el `role` que llegara, y
    // `claim_next` unía los dos lados con `role = :role`. Nadie comprobaba nunca que ambos hubieran
    // tecleado lo mismo, así que `Kitchen`, `kitchen` y `kitchn` eran **tres colas distintas** — y
    // la tercera no tenía host jamás, en silencio, hasta que faltaba el plato.
    //
    // La decisión es de MERCADO (12 referencias + foros, 15/08): Toast, Square, Lightspeed K, Odoo,
    // Clover, Loyverse, Simphony, Epson y Star hacen todos lo mismo — `ítem → (FK) ESTACIÓN (id,
    // nombre) ← (FK) impresora`. **Ni un solo sistema maduro compara una cadena tecleada al
    // imprimir**: el vocabulario es ABIERTO (los nombres reales son *Grill*, *Frío*, *Barra 2*) y lo
    // CERRADO es el enlace, porque es una FK elegida de un selector. Clover, la única referencia con
    // el set cerrado, es la que tiene el foro lleno de comerciantes que no pueden expresar su local.
    //
    // Esta migración es **solo DDL**. La siembra de las cuatro estaciones de ADR-0196, la adopción
    // de las que este hub ya tenga configuradas en hardware, el plegado de variantes de mayúsculas
    // y el backfill de `station_id` viven en `print_stations::ensure_stations`, que corre en CADA
    // arranque desde [`apply`]. El motivo no es estético: una migración de sistema se registra **por
    // BASE DE DATOS**, así que un hub que llega a una BD cuyas migraciones ya corrieron no recibiría
    // NADA — y ese es justo el hub legacy pre-ADR-0201 (varios hubs, una BD) que arrancaría sin
    // poder imprimir absolutamente nada.
    //
    // `station_id` entra con `DEFAULT ''` y no `NOT NULL` sin defecto, a propósito y al revés que la
    // v46: aquí la ventana del start-first (ADR-0269) no puede fallar en abierto. Un `INSERT` del
    // contenedor viejo (sin `station_id`) escribe `''`, que **no resuelve a ninguna estación** — el
    // trabajo espera y `ensure_stations` lo apunta a su estación en el siguiente arranque. Con `NOT
    // NULL` a secas el encolado del contenedor viejo reventaría y la venta se quedaría sin tique.
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): todo es `IF NOT EXISTS`. Importa porque los fixtures
    // rebobinan la tabla de control por versión y reaplican lo posterior sobre una BD que ya tiene
    // los objetos.
    //
    // ⚠️ El número es DECLARADO, no la posición en el slice. Hoy hay varias ramas de esta tanda
    // pidiendo número (hub#658 estrena otra) y ya hubo una colisión en la v45: recomprobado contra
    // `origin/develop` justo antes del push (hub#573 hace que una versión en o por debajo del máximo
    // aplicado ABORTE el arranque en vez de saltarse en silencio). Los huecos v15/v20/v24 siguen
    // libres e **inalcanzables**: cogerlos ES el fallo mudo.
    SystemMigration {
        version: 47,
        name: "print_stations",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _print_station (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, key TEXT NOT NULL, \
  label TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, \
  PRIMARY KEY (id));\
CREATE UNIQUE INDEX IF NOT EXISTS ux_print_station_key ON _print_station (hub_id, key);\
ALTER TABLE _print_queue ADD COLUMN IF NOT EXISTS station_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _print_host ADD COLUMN IF NOT EXISTS station_id TEXT NOT NULL DEFAULT '';\
CREATE INDEX IF NOT EXISTS ix_print_queue_station ON _print_queue (hub_id, station_id, status, seq);\
CREATE INDEX IF NOT EXISTS ix_print_host_station ON _print_host (hub_id, station_id, last_seen_at);",
    },
    // ── v48 — hub#658: la PLACA de empleado, hermana del PIN, y la traza de qué se usó ────────
    // Decisión de mercado publicada en la issue (15 referencias). Tres cosas, y las tres aditivas:
    //
    // 1. **`hub_user.badge_index` + `hub_user.badge_hash`** — la credencial. Hermana de `pin_hash`,
    //    en la MISMA fila, porque placa y PIN son dos presentaciones de la misma identidad. Dos
    //    columnas y no una: el índice (HMAC-SHA256 con la clave del hub) es por lo que se BUSCA, el
    //    argon2 es lo que PRUEBA. Copiar el patrón de `pin_is_taken` —recorrer las filas verificando
    //    argon2— sería un argon2 por fila en cada tap de la puerta de login: con cuatro dígitos vale,
    //    con una placa de alta entropía es un DoS contra la propia caja. El índice estrecha a una
    //    fila en SQL; de ahí `ix_hub_user_badge`.
    //
    // 2. **`_hub_badge_key`** — la clave del hub con la que se deriva ese índice. Tabla propia y no
    //    `hub_settings` a propósito: en settings la leería cualquiera que pueda leer la
    //    configuración, y esa clave es lo único que impide construir el índice de un número de
    //    tarjeta a voluntad (el espacio de UIDs EM4100/MIFARE es pequeño y público, así que un hash
    //    sin clave se invierte con una tabla precalculada). Se acuña una vez, con aleatoriedad del
    //    SO, la primera vez que alguien enrola una placa.
    //
    // 3. **`credential_kind` + `credential_ref` en `hub_session` y en `_elevation_audit`** — la
    //    traza, que es el criterio de aceptación que más valor tiene de toda la issue: ningún
    //    competidor la registra, y sin ella «alguien usó mi tarjeta» es estructuralmente
    //    irresoluble porque el log solo dice el empleado. `credential_ref` guarda el **índice** de
    //    la placa, nunca el número impreso: identifica QUÉ tarjeta se pasó sin que la auditoría se
    //    convierta en una lista de credenciales vivas.
    //
    // ⚠️ **`DEFAULT ''`, no `'pin'`.** Las filas anteriores a esta versión no dicen con qué se
    // entró, y «no consta» es una respuesta distinta de «fue el PIN»: rellenarlas con `'pin'` sería
    // inventar el dato exacto que esta columna existe para poder disputar. Vacío = anterior a la
    // traza. Y `DEFAULT ''` en vez de `NOT NULL` a secas porque en la ventana del start-first
    // (ADR-0269) el contenedor viejo sigue insertando sesiones sin estas columnas — y ahí un fallo
    // NO se desanda solo: sería un login rechazado, no un reintento con backoff como en la v46.
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`
    // y `CREATE INDEX IF NOT EXISTS`. Sin backfill: los DEFAULT ya dejan a las filas existentes
    // exactamente como tienen que quedar (sin placa, sin credencial declarada).
    //
    // ⚠️ **El número es DECLARADO, no la posición en el slice.** Al escribirla el máximo en
    // `origin/develop` era v46 y había otra rama de esta misma tanda (hub#457) tomando la v47, así
    // que esta tomó la **v48** dejando el hueco a propósito — un hueco por delante es inalcanzable
    // y por tanto inofensivo, mientras que un número repetido ABORTA el arranque (hub#573) y, si se
    // cuela, deja la tabla sin crear en un hub ya desplegado. hub#457 se mergeó antes y ocupó su
    // v47, así que el hueco duró lo que duró el rebase y el catálogo queda seguido. Recomprobado
    // contra `origin/develop` en cada push.
    SystemMigration {
        version: 48,
        name: "hub_user_badge_credential",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE hub_user ADD COLUMN IF NOT EXISTS badge_index TEXT NOT NULL DEFAULT '';\
ALTER TABLE hub_user ADD COLUMN IF NOT EXISTS badge_hash TEXT NOT NULL DEFAULT '';\
CREATE INDEX IF NOT EXISTS ix_hub_user_badge ON hub_user (hub_id, badge_index);\
CREATE TABLE IF NOT EXISTS _hub_badge_key (\
  hub_id TEXT NOT NULL, key_hex TEXT NOT NULL, created_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id));\
ALTER TABLE hub_session ADD COLUMN IF NOT EXISTS credential_kind TEXT NOT NULL DEFAULT '';\
ALTER TABLE hub_session ADD COLUMN IF NOT EXISTS credential_ref TEXT NOT NULL DEFAULT '';\
ALTER TABLE _elevation_audit ADD COLUMN IF NOT EXISTS credential_kind TEXT NOT NULL DEFAULT '';\
ALTER TABLE _elevation_audit ADD COLUMN IF NOT EXISTS credential_ref TEXT NOT NULL DEFAULT '';",
    },
    // ── v49 — hub#950: `_flow_approvals` deja de ser «lo que propuso un modelo» ────────────────
    // La tabla nació para UNA cosa: la escritura que propone un step `ai` y que espera a que
    // alguien la apruebe (v38). El step `approval` genérico necesita exactamente la misma fila —
    // la misma bandeja, la misma regla de idempotencia, el mismo barrido de caducidad, la misma
    // auditoría de quién decidió— pero SIN command que ejecutar: lo que se aprueba es una
    // pregunta, y el trabajo lo hace el step siguiente.
    //
    // Se GENERALIZA la fila, no se bifurca la tabla. Una segunda tabla habría duplicado las cinco
    // cosas de arriba para que difiriera una: qué ejecuta «aprobar». Eso es un `kind` y una rama
    // en un método, no un esquema paralelo que se desincroniza a la primera corrección.
    //
    // - **`kind`** (`'command' | 'decision'`) — con DEFAULT `'command'`, que es lo que TODAS las
    //   filas ya escritas son. Un default `'decision'` convertiría un `payload` guardado en una
    //   pregunta que no ejecuta nada, tirando en silencio la escritura que alguien aprobó.
    // - **`title` / `summary`** — la pregunta, YA TEMPLADA al crearla. Es la propiedad que hace
    //   que editar el flujo no mute una solicitud viva, igual que el `payload` se guarda en vez de
    //   re-derivarse: lo que lee la persona a las 9 es lo que se escribió a las 3.
    // - **`assignee_role`** — un ROL, nunca una persona (el `Allowed Group` de Odoo). Nombrar a
    //   alguien en un documento se rompe el día que se va, que es el agujero que Business Central
    //   tuvo que parchear inventando el «sustituto».
    // - **`comment`** — lo que tecleó quien decidió. Es media auditoría y es uno de los cuatro
    //   campos que el step deja en `steps.<id>` para los pasos siguientes.
    // - **`on_reject`** — qué le cuesta al run un «no», por el MISMO motivo que `on_expire` (v45)
    //   es columna: la respuesta es de quien escribió el flujo y tiene que ser la que estaba en
    //   vigor cuando se hizo la pregunta. `'cancel'` por defecto = lo que un rechazo hace hoy.
    // - **`command` pasa a tener DEFAULT `''`** — una `decision` no ejecuta nada, y «vacío» es
    //   cómo se dice eso. Se deja `NOT NULL`: un `NULL` sería un tercer estado que nadie lee.
    //
    // Aditiva y re-ejecutable (`ADD COLUMN IF NOT EXISTS`), sin backfill: los DEFAULT dejan a las
    // filas existentes exactamente como ya son — propuestas de un modelo, sin pregunta, sin rol y
    // canceladas al rechazarlas.
    //
    // ⚠️ **El número es DECLARADO, no la posición en el slice**, y hay varias ramas de flujos a la
    // vez queriendo número (la v45 nació v45, la v46 nació v45 y la v48 dejó un hueco a propósito
    // por esto mismo). Recomprobado contra `origin/develop` justo antes de empujar: máximo v48
    // (`hub_user_badge_credential`, hub#658). Una versión en o por debajo del máximo ya aplicado
    // ABORTA el arranque (hub#573), y para cuando se nota el hub ya lleva el número más alto.
    SystemMigration {
        version: 49,
        name: "flow_approval_generic_decision",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'command';\
ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';\
ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';\
ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS assignee_role TEXT NOT NULL DEFAULT '';\
ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS comment TEXT NOT NULL DEFAULT '';\
ALTER TABLE _flow_approvals ADD COLUMN IF NOT EXISTS on_reject TEXT NOT NULL DEFAULT 'cancel';\
ALTER TABLE _flow_approvals ALTER COLUMN command SET DEFAULT '';",
    },
    // ── v50 — hub#987: el mapa `documentType → estación`, la otra mitad del diagrama de la v47 ──
    // La v47 convirtió el DESTINO en una fila y dejó sin construir la flecha de la izquierda:
    //
    //     tipo de documento ──(FK)──▶ ESTACIÓN (id, nombre) ◀──(FK)── impresora
    //     ^^^^^^^^^^^^^^^^^^^^^^^^^^                          esto ya estaba (v47 + hub#342)
    //     esto es la v50
    //
    // Sin ella, `sales` llevaba `role: 'receipt'` a fuego e `inventory` `role: 'label'`: **un módulo
    // de negocio nombrando el periférico del comerciante**, que es la fuga que señaló la decisión de
    // mercado de hub#457. Un módulo no puede saber que ESTE restaurante manda sus comandas a *Grill*
    // y sus chits a *Barra 2*; el hub sí, porque el hub es del comerciante. El eje que un módulo sí
    // es competente para declarar ya viajaba en el mismo payload: `documentType` (vocabulario
    // cerrado de 8). Es el *print class* de Simphony y el split recibos/comandas/etiquetas de Square.
    //
    // **Solo DDL**, y por el mismo motivo exacto que la v47: la siembra por hub vive en
    // `print_routes::ensure_routes`, que corre desde [`apply`] en CADA arranque, porque una
    // migración de sistema se registra **por BASE DE DATOS** y el hub legacy pre-ADR-0201 (varios
    // hubs, una BD) que llega a una BD ya migrada no recibiría ninguna ruta.
    //
    // **Sin FK declarada hacia `_print_station`** a propósito. Una FK con `ON DELETE CASCADE`
    // borraría la fila al borrar la estación y una `RESTRICT` impediría borrarla; las dos le quitan
    // al comerciante la traza de que su mapa quedó roto. La fila **se queda colgando** y
    // `print_routes::route_for` falla ABIERTO hacia `receipt` (la protegida), que es lo que pide
    // hub#987: un trabajo sin destino sale por la caja, nunca por ningún sitio. `list` la devuelve
    // con la estación vacía para que la pantalla la enseñe rota y el comerciante la reapunte.
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): `CREATE TABLE IF NOT EXISTS`. Sin backfill — un hub sin
    // filas está exactamente en el estado de fallo abierto, que es correcto, y `ensure_routes` lo
    // siembra en el mismo arranque.
    //
    // ⚠️ **El número es DECLARADO, no la posición en el slice**, y esta entrada es el caso de libro.
    // Nació pidiendo la **v49** (el máximo en `origin/develop` era la v48) y, con la rama ya en
    // vuelo, apareció hub#950 pidiendo también la 49. Se movió a la **v50** dejando el hueco POR
    // DELANTE —la jugada de hub#658 con la v47, y la lección de la v46 al revés—: un hueco por
    // delante es inalcanzable y por tanto inofensivo, mientras que un número repetido ABORTA el
    // arranque (hub#573) de un hub ya desplegado. hub#950 se mergeó antes, así que el hueco duró lo
    // que duró el rebase y el catálogo queda seguido: 47, 48, 49, 50. Recomprobado en cada rebase
    // contra TODAS las ramas remotas, no solo `develop`. Los huecos v15/v20/v24 siguen libres e
    // inalcanzables (cogerlos ES el fallo mudo que ya renumeró hub#341/#342/#470/#501).
    SystemMigration {
        version: 50,
        name: "print_routes",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _print_route (\
  hub_id TEXT NOT NULL, document_type TEXT NOT NULL, station_id TEXT NOT NULL, \
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (hub_id, document_type));",
    },
    // ── v51 — hub#297: el techo de la factura SIMPLIFICADA, en la fila del régimen que lo impone ─
    // La v27 dejó `_hub_fiscal_regime_registry` como **datos, no código**: qué régimen debe cada
    // país. El techo de la simplificada es un dato del mismo tipo y de la misma fila —lo impone el
    // régimen, no el runtime—, así que va aquí y no en un `match country_code` compilado. Francia
    // el día que toque es una fila; una rebaja del importe es un `UPDATE`, no un despliegue.
    //
    // **`0` significa «este régimen NO pone techo», nunca «techo cero»** — y por eso la query lo
    // devuelve como `null`. Un `0` que se leyera como importe pararía TODAS las ventas del hub, que
    // es exactamente el fallo que un default numérico invita a cometer. Se elige `0` y no NULL en la
    // columna por el contrato de fila (nada de NULLs: un tercer estado es una rama más por la que
    // colarse); la traducción a `null` se hace una sola vez, en [`crate::fiscal_profile::limits`].
    //
    // **300000 = 3.000,00 € en céntimos, y NO son los 3.010,00 de `xsd.rs`.** El validador de red
    // (§15.8, hub#964) valida contra el techo MÁS los 10,00 € de tolerancia, porque eso es lo que la
    // AEAT rechaza de verdad. Lo que se publica aquí es el techo a secas: la tolerancia es holgura
    // de redondeo de la agencia, no margen del comerciante, y un mostrador que se la gasta construye
    // el producto sobre los decimales que la AEAT se guarda para sí. Dos capas, dos números, y
    // ninguno enmascara al otro (el patrón de `print_queue.rs` con `DOCUMENT_TYPES`).
    //
    // ⚠️ **Re-ejecutable** (hub#342/#483): `ADD COLUMN IF NOT EXISTS` + un `UPDATE` que solo escribe
    // donde aún no hay valor. `tests/access_email_backfill.rs` rebobina la tabla de control y repite
    // todas las migraciones posteriores sobre una BD que ya tiene los objetos; un `ADD COLUMN` pelado
    // falla 42701. Y la guarda `= 0` del `UPDATE` es lo que impide que un rearranque le pise al
    // comerciante un techo que él hubiera movido.
    //
    // ⚠️ **v51: el siguiente número POR ENCIMA DEL MÁXIMO, recomprobado en el rebase.** `apply`
    // compara contra el MÁXIMO aplicado, así que un número repetido ABORTA el arranque (hub#573) de
    // un hub ya desplegado y uno por debajo se salta EN SILENCIO. Comprobado contra TODAS las ramas
    // remotas (solo `develop` llega a la v50) y contra los 10 worktrees locales de la flota. Los
    // huecos v15/v20/v24 siguen libres e inalcanzables: cogerlos ES el fallo mudo que ya renumeró
    // hub#341/#342/#470/#501.
    SystemMigration {
        version: 51,
        name: "fiscal_regime_simplified_limit",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE _hub_fiscal_regime_registry \
  ADD COLUMN IF NOT EXISTS simplified_invoice_max_cents BIGINT NOT NULL DEFAULT 0;\
UPDATE _hub_fiscal_regime_registry SET simplified_invoice_max_cents = 300000 \
  WHERE country_code = 'ES' AND regime_key = 'verifactu' AND simplified_invoice_max_cents = 0;",
    },
    // hub#963 — the public claim: the one row a stranger with no session can act on.
    //
    // `token_hash` and not the locator: a dump of this table must not hand over every open ticket
    // in the hub. `UNIQUE (hub_id, kind, subject_id)` is what makes minting idempotent, so the POS
    // can call it on every reprint and the customer's copy keeps working.
    SystemMigration {
        version: 52,
        name: "public_claim",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _public_claim_key (\
  hub_id TEXT NOT NULL, key_hex TEXT NOT NULL, created_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id));\
CREATE TABLE IF NOT EXISTS _public_claim (\
  id TEXT NOT NULL, hub_id TEXT NOT NULL, token_hash TEXT NOT NULL, kind TEXT NOT NULL, \
  subject_id TEXT NOT NULL, command TEXT NOT NULL, \
  sealed_payload TEXT NOT NULL DEFAULT '{}', public_fields TEXT NOT NULL DEFAULT '[]', \
  expires_at TEXT NOT NULL, redeemed_at TEXT, result_ref TEXT NOT NULL DEFAULT '', \
  created_by TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, \
  PRIMARY KEY (id));\
CREATE UNIQUE INDEX IF NOT EXISTS ux_public_claim_token ON _public_claim (hub_id, token_hash);\
CREATE UNIQUE INDEX IF NOT EXISTS ux_public_claim_subject ON _public_claim (hub_id, kind, subject_id);",
    },
    // ── v53 — hub#951: `_flow_run_waits`, las OTRAS salidas de una espera ──────────────────────
    // Hasta aquí una espera (`delay`) tenía UNA salida: su reloj. Nada podía despertar un run
    // dormido salvo `wake_at`, así que un recordatorio de cita se mandaba igual aunque la cita se
    // hubiera cancelado — el hilo de la comunidad de Square prueba que eso pasa en un producto de
    // primera línea. Esta tabla es la forma que el mercado le da al problema (SuiteFlow): la espera
    // es un ESTADO con varias salidas, y la primera transición atómica se lleva el run.
    //
    // **Solo el id correlacionado, jamás el payload** (criterio de retención de la issue). Una fila
    // guarda el nombre del evento que la despierta y el VALOR que tiene que casar; el payload del
    // evento que la disparó no se copia a ningún sitio.
    //
    // El índice es **parcial** y ese es el punto: el match corre en el camino caliente de CADA
    // entrega de evento del hub. Con `WHERE status = 'armed'` el índice solo contiene las esperas
    // vivas —un puñado— en vez de todo el histórico de esperas que ya se resolvieron.
    //
    // ⚠️ **El número es DECLARADO, no la posición en el slice — y este se movió DOS veces.** Nació
    // pidiendo la **v39** (lo que decía la decisión publicada en la issue el 15/08); para cuando se
    // implementó, ese número llevaba desde hub#821 ocupado por otra cosa y el máximo real era la
    // v50, así que pasó a la **v51**. Con la rama ya en vuelo, hub#1000 mergeó ANTES con SU v51
    // (`fiscal_regime_simplified_limit`, justo aquí arriba) y hub#1001 se rebasó a la v52 — de ahí
    // la **v53**. Recomprobado contra TODAS las ramas remotas justo antes del push, no solo contra
    // `develop`: un número repetido ABORTA el arranque de un hub ya desplegado (hub#573) y uno por
    // debajo del máximo se salta EN SILENCIO.
    //
    // 🔴 **ORDEN DE MERGE, no solo número.** El hueco de la v52 es de hub#1001 y tiene que entrar
    // ANTES que esta. `apply` aborta cuando una versión del catálogo está SIN REGISTRAR y por
    // debajo del máximo aplicado: si esta v53 llegara primero a un hub, la v52 de hub#1001 caería
    // luego por debajo de su máximo y ese hub NO volvería a arrancar. Un hueco por delante es
    // inofensivo; un hueco que se rellena por detrás, no.
    SystemMigration {
        version: 53,
        name: "flow_run_waits",
        kind: Kind::Expand,
        postgres: "\
CREATE TABLE IF NOT EXISTS _flow_run_waits (\
  id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, run_id TEXT NOT NULL, flow_id TEXT NOT NULL, \
  step_id TEXT NOT NULL, step_index BIGINT NOT NULL, kind TEXT NOT NULL, \
  event_name TEXT NOT NULL, filter TEXT NOT NULL DEFAULT '{}', \
  correlate TEXT NOT NULL DEFAULT '{}', correlate_key TEXT NOT NULL DEFAULT '', \
  correlate_value TEXT NOT NULL DEFAULT '', until_path TEXT NOT NULL DEFAULT '', \
  offset_seconds BIGINT NOT NULL DEFAULT 0, max_wait BIGINT, \
  past_due_policy TEXT NOT NULL DEFAULT 'skip', reschedules BIGINT NOT NULL DEFAULT 0, \
  status TEXT NOT NULL DEFAULT 'armed', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, \
  deleted_at TEXT);\
CREATE INDEX IF NOT EXISTS ix_flow_wait_event \
  ON _flow_run_waits (hub_id, event_name, correlate_value) \
  WHERE status = 'armed' AND deleted_at IS NULL;\
CREATE INDEX IF NOT EXISTS ix_flow_wait_run ON _flow_run_waits (hub_id, run_id);",
    },

    // hub#1108 — el sello del DESCARTE de un trabajo de impresión. `discarded` es un estado más de
    // `_print_queue.status` (no hace falta DDL para eso), pero quién lo cerró, cuándo y por qué sí
    // son columnas: descartar **nunca** borra la fila —es la única prueba de que el tique existió—
    // y una fila cerrada sin autor ni motivo convertiría en invisible justo lo que pasó. Mismas
    // tres columnas y mismos tipos que hub#660/hub#955 pusieron en `_event_outbox`, porque es el
    // mismo gesto sobre la otra cola durable del runtime.
    //
    // 🔴 El número es el SIGUIENTE POR ENCIMA del máximo del catálogo (53), nunca un hueco: `apply`
    // compara contra el máximo aplicado y una versión por debajo se salta EN SILENCIO — el hub
    // arrancaría creyendo estar al día, sin las columnas y sin un solo log.
    SystemMigration {
        version: 54,
        name: "print_queue_discard",
        kind: Kind::Expand,
        postgres: "\
ALTER TABLE _print_queue ADD COLUMN IF NOT EXISTS discarded_at TEXT;\
ALTER TABLE _print_queue ADD COLUMN IF NOT EXISTS discarded_by TEXT;\
ALTER TABLE _print_queue ADD COLUMN IF NOT EXISTS discard_reason TEXT NOT NULL DEFAULT '';",
    },

];

/// Crea la tabla de control de migraciones de sistema (idempotente).
pub async fn ensure_control_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_CONTROL).await?;
    Ok(())
}

/// Aplica en orden las migraciones de sistema que aún no estén registradas, para `hub_id`
/// (el del despliegue, ARQUITECTURA.md §2.5). Cada migración se aplica en **su propia
/// transacción** junto con el `INSERT` en `_hub_system_migrations` (atomicidad: o se aplica y
/// queda registrada, o no se aplica). Idempotente: una versión ya registrada se salta.
///
/// **Coherencia del catálogo (hub#573).** Antes este bucle trataba `version <= max_aplicado`
/// como «ya hecha» y saltaba en silencio. Pero dos ramas paralelas que eligen el mismo número
/// (o una migración que cae por debajo del máximo tras un renumerado) dejan exactamente este
/// estado: la versión está en el catálogo, el máximo del hub está por encima, pero su fila de
/// control **nunca se escribió** — la tabla no existe en el hub desplegado y nadie se entera.
/// Ahora, antes de iterar, se comprueba que toda versión del catálogo ≤ máximo esté **registrada**;
/// si falta alguna, el arranque **aborta** nombrando la versión (fallo ruidoso, no silencio).
///
/// El SQL de las migraciones puede llevar el parámetro `:hub_id` (lo usa v1 para sellar el
/// hub_id del despliegue en las filas existentes).
pub async fn apply(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    ensure_control_table(db).await?;
    let applied = max_applied_version(db).await?;
    let registered = registered_versions(db).await?;

    let mut prev = 0i64;
    for m in MIGRATIONS {
        // Defensa: el slice debe ir en orden estrictamente creciente (detecta un duplicado o un
        // desorden al editar el catálogo embebido).
        debug_assert!(
            m.version > prev,
            "migraciones de sistema desordenadas en v{}",
            m.version
        );
        prev = m.version;

        if registered.contains(&m.version) {
            continue; // registrada de verdad (idempotencia por identidad, no por umbral).
        }

        // Versión del catálogo NO registrada, pero ≤ máximo aplicado: incoherencia. Sin esta
        // guarda se saltaría en silencio y el hub arrancaría sin la tabla (hub#573).
        if m.version <= applied {
            return Err(crate::errors::RuntimeError::Other(format!(
                "migración de sistema v{} (`{}`) no registrada pero su versión es ≤ el máximo \
                 aplicado (v{}): el catálogo embebido y el esquema del hub están incoherentes \
                 (probable colisión de versión entre ramas paralelas, o un renumerado que dejó \
                 esta migración por debajo del máximo). Renumerar a v{} NO arregla un hub ya \
                 desplegado: hay que aplicar su SQL a mano y registrarla, o restaurar el hub \
                 desde un backup coherente.",
                m.version,
                m.name,
                applied,
                next_catalogue_version()
            )));
        }

        let sql = m.postgres;

        // Migración + registro en la MISMA transacción. `execute_tx` aplica cada sentencia con los
        // mismos params (`:hub_id`); las sentencias sin `:hub_id` lo ignoran sin problema.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        let mut ops: Vec<(String, Params)> = split_statements(sql)
            .into_iter()
            .map(|stmt| (stmt, p.clone()))
            .collect();

        let mut record = Params::new();
        record.insert("version".into(), json!(m.version));
        record.insert("name".into(), json!(m.name));
        record.insert("applied_at".into(), json!(now_rfc3339()));
        ops.push((
            "INSERT INTO _hub_system_migrations (version, name, applied_at) \
             VALUES (:version, :name, :applied_at)"
                .to_string(),
            record,
        ));

        db.execute_tx(&ops).await?;
    }

    // Puesta a punto de las estaciones de impresión **de este hub** (hub#457). Va aquí y no dentro
    // de la v47 porque una migración se registra por BASE DE DATOS y este paso es por HUB: en la BD
    // compartida legacy (pre-ADR-0201) el segundo hub no vería nunca la siembra. Es idempotente y
    // barato (cuatro filas como mucho), y siembra **solo si el hub no tiene ninguna** — un
    // comerciante que borró `bar` no se lo encuentra de vuelta mañana.
    crate::print_stations::ensure_stations(db, hub_id).await?;
    // …y el mapa `documentType → estación` de este hub (hub#987). **Después** de las estaciones, no
    // antes: una ruta apunta al `id` de una estación, así que sembrarla primero la dejaría colgando
    // en el primer arranque. Misma razón que arriba para vivir aquí y no dentro de la v50: la
    // migración se registra por BASE DE DATOS y esto es por HUB. Siembra **por hueco** (no «solo si
    // no hay ninguna») para que un `documentType` nuevo de una versión futura llegue a su estación
    // en un hub que ya existía, en vez de fallar abierto para siempre.
    crate::print_routes::ensure_routes(db, hub_id).await?;
    Ok(())
}

/// La siguiente versión libre del catálogo (máximo + 1), para sugerirla en el mensaje de aborto
/// de hub#573. Ojo: esto NO es una recomendación de renumerar — renumerar no arregla un hub ya
/// desplegado, solo evita que la colisión vuelva a pasar. El mensaje lo deja claro.
fn next_catalogue_version() -> i64 {
    MIGRATIONS.iter().map(|m| m.version).max().unwrap_or(0) + 1
}

/// Versiones registradas en `_hub_system_migrations` (las que de verdad se aplicaron). A
/// diferencia de [`max_applied_version`], esta es la **identidad** de lo aplicado, no solo el
/// techo — y es lo que hace que la guarda de hub#573 distinga «ya hecha» de «saltada en silencio».
async fn registered_versions(db: &dyn DatabaseAdapter) -> Result<Vec<i64>> {
    let res = db
        .query("SELECT version FROM _hub_system_migrations", &Params::new())
        .await?;
    Ok(res
        .rows
        .iter()
        .filter_map(|r| r["version"].as_i64())
        .collect())
}

/// Versión máxima de migración de sistema ya aplicada (0 si ninguna).
async fn max_applied_version(db: &dyn DatabaseAdapter) -> Result<i64> {
    let res = db
        .query("SELECT version FROM _hub_system_migrations", &Params::new())
        .await?;
    let max = res
        .rows
        .iter()
        .filter_map(|r| r["version"].as_i64())
        .max()
        .unwrap_or(0);
    Ok(max)
}

/// Parte un batch SQL en sentencias individuales (separa por `;`, descarta vacías). El SQL de
/// migración aquí es DDL simple sin literales con `;` embebidos, así que un split por `;` basta
/// (igual que el resto de batches del runtime). Cada sentencia se ejecuta en la tx de la migración.
fn split_statements(sql: &str) -> Vec<String> {
    sql.split(';')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .map(|s| format!("{s};"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrations_are_strictly_increasing() {
        let mut prev = 0i64;
        for m in MIGRATIONS {
            assert!(m.version > prev, "v{} fuera de orden", m.version);
            prev = m.version;
        }
    }

    /// **El número de una migración de sistema NO es cosmético (hub#341 vs hub#316).** [`apply`]
    /// compara contra el **máximo** aplicado, así que una migración numerada por debajo de él se
    /// salta **EN SILENCIO**: el hub arranca creyendo que está al día y le falta la tabla. No
    /// falla, no avisa. Dos ramas paralelas eligieron el mismo `version: 14` y, de mergearse tal
    /// cual, la segunda en llegar habría desaparecido en los hubs que ya hubieran pasado por la
    /// primera.
    ///
    /// Este test fija el invariante desde el lado del hub ya desplegado: con todas las migraciones
    /// ANTERIORES ya aplicadas, un arranque nuevo **sí** aplica `print_queue`. Si alguien la
    /// renumera por debajo de otra, aquí revienta (la tabla no existiría) en vez de en producción.
    ///
    /// El hub se para **justo antes** de la cola, no «en todas menos esta»: registrar también las
    /// posteriores subiría el máximo aplicado por encima de la v18 y el test se saltaría a sí mismo
    /// —exactamente el fallo que vigila— en cuanto llegase una migración más (pasó con la v19).
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_print_queue() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let print_queue = MIGRATIONS
            .iter()
            .find(|m| m.name == "print_queue")
            .expect("la cola de impresión sigue en el catálogo");
        hub_deployed_through(&db, print_queue.version - 1).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            print_queue.version - 1,
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        // La cola existe: la migración NO se saltó por llegar «por debajo» del máximo aplicado.
        // (Se inserta con la forma de HOY —documento estructurado, v24— porque `apply` corre el
        // catálogo ENTERO: la columna `html` con la que nació la v18 ya no existe al terminar.)
        db.execute_batch(
            "INSERT INTO _print_queue (hub_id, job_id, role, document_type, document, created_at) \
             VALUES ('h1', 'j1', 'receipt', 'receipt', '{\"receipt_id\":\"T-1\"}', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
    }

    /// El mismo invariante para la **v25** (hub#501): un hub que ya pasó por todo lo anterior **sí**
    /// recibe las columnas del documento estructurado. Si alguien la renumera por debajo del máximo
    /// se saltaría en silencio y el hub arrancaría con una cola que `enqueue` no puede escribir —
    /// con el tique fallando en el sitio más caro, el mostrador.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_structured_document_columns() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let structured = MIGRATIONS
            .iter()
            .find(|m| m.name == "print_queue_structured_document")
            .expect("el documento estructurado sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(structured.version)).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            previous_version_of(structured.version),
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        db.execute_batch(
            "INSERT INTO _print_queue (hub_id, job_id, role, document_type, document, created_at) \
             VALUES ('h1', 'j1', 'receipt', 'receipt', '{\"receipt_id\":\"T-1\"}', '2026-01-01T00:00:00Z');",
        )
        .await
        .expect("la cola acepta el documento estructurado");
    }

    /// **Un trabajo encolado en el formato retirado muere con su motivo, no en silencio.**
    ///
    /// Sin esto, un `pending` heredado se lo llevaría un host que no tiene con qué renderizarlo:
    /// cinco entregas quemadas y un `dead` con un error que no explica nada. Aquí muere una vez y la
    /// fila dice qué hacer. Y el vecino **estructurado sigue vivo durante todo el proceso**: si la
    /// migración se llevase por delante la cola entera, este test lo vería.
    #[tokio::test]
    async fn a_job_queued_in_the_retired_html_format_is_dead_lettered_with_its_reason() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let structured = MIGRATIONS
            .iter()
            .find(|m| m.name == "print_queue_structured_document")
            .expect("el documento estructurado sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(structured.version)).await;
        // Dos trabajos del formato viejo (uno esperando, otro ya reclamado) y uno TERMINAL, que no
        // debe tocarse: un tique ya impreso no se «mata».
        db.execute_batch(
            "INSERT INTO _print_queue (hub_id, job_id, role, html, status, created_at) VALUES \
               ('h1', 'j-pending',  'receipt', '<p>t</p>', 'pending',  '2026-01-01T00:00:00Z'), \
               ('h1', 'j-printing', 'kitchen', '<p>o</p>', 'printing', '2026-01-01T00:00:01Z'), \
               ('h1', 'j-done',     'receipt', '<p>d</p>', 'done',     '2026-01-01T00:00:02Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();

        let rows = db
            .query(
                "SELECT job_id, status, last_error FROM _print_queue WHERE hub_id = 'h1' ORDER BY job_id",
                &Params::new(),
            )
            .await
            .unwrap();
        let by_id = |id: &str| {
            rows.rows
                .iter()
                .find(|r| r["job_id"] == json!(id))
                .unwrap_or_else(|| panic!("{id} sigue en la cola: morir no es desaparecer"))
                .clone()
        };
        for id in ["j-pending", "j-printing"] {
            let row = by_id(id);
            assert_eq!(row["status"], json!("dead"), "{id} no se puede imprimir");
            assert!(
                row["last_error"]
                    .as_str()
                    .unwrap_or_default()
                    .contains("hub#501"),
                "la fila dice POR QUÉ murió y qué hacer: {}",
                row["last_error"]
            );
        }
        assert_eq!(
            by_id("j-done")["status"],
            json!("done"),
            "un tique que ya salió por la impresora no se re-mata"
        );

        // Y la cola sigue siendo una cola: lo estructurado entra con normalidad.
        db.execute_batch(
            "INSERT INTO _print_queue (hub_id, job_id, role, document_type, document, created_at) \
             VALUES ('h1', 'j-new', 'receipt', 'receipt', '{\"receipt_id\":\"T-1\"}', '2026-01-02T00:00:00Z');",
        )
        .await
        .unwrap();
    }

    /// 🔒 **La v25 puede RE-EJECUTARSE sobre su propio resultado** (regla hub#342/#483). El `UPDATE`
    /// del dead-letter es la parte delicada: acotado a `document_type = ''`, que **ninguna** fila
    /// nueva puede cumplir, así que un segundo pase no puede matar un tique legítimo que esté
    /// esperando. Esto es lo que revienta si alguien afloja esa condición.
    #[tokio::test]
    async fn the_structured_document_migration_can_run_a_second_time() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        hub_deployed_through(&db, MIGRATIONS.last().expect("catálogo no vacío").version).await;
        db.execute_batch(
            "INSERT INTO _print_queue (hub_id, job_id, role, document_type, document, status, created_at) \
             VALUES ('h1', 'j-waiting', 'receipt', 'receipt', '{\"receipt_id\":\"T-1\"}', 'pending', '2026-01-02T00:00:00Z');",
        )
        .await
        .unwrap();
        let structured = MIGRATIONS
            .iter()
            .find(|m| m.name == "print_queue_structured_document")
            .expect("el documento estructurado sigue en el catálogo");

        let mut hub = Params::new();
        hub.insert("hub_id".into(), json!("hub-test"));
        for stmt in split_statements(structured.postgres) {
            db.execute(&stmt, &hub)
                .await
                .expect("la v25 tiene que poder correr sobre un esquema que ya la tiene");
        }

        let row = db
            .query(
                "SELECT status FROM _print_queue WHERE job_id = 'j-waiting'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            row.rows[0]["status"],
            json!("pending"),
            "un segundo pase no puede matar un tique que está esperando de verdad"
        );
    }

    /// El mismo invariante para la **v27** (hub#549): un hub que ya pasó por todo lo anterior **sí**
    /// recibe las tablas del perfil fiscal. Si alguien la renumera por debajo del máximo se saltaría
    /// **en silencio** y ese hub arrancaría sin perfil — es decir, sin nadie en el core que sepa que
    /// debe VeriFactu, que es exactamente el agujero que ADR-0273 cierra.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_fiscal_profile() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let fiscal = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_fiscal_profile")
            .expect("el perfil fiscal sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(fiscal.version)).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            previous_version_of(fiscal.version),
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        db.execute_batch(
            "INSERT INTO _hub_fiscal_profile (hub_id, country_code, fiscal_system, status) \
             VALUES ('h1', 'ES', 'verifactu', 'UNCONFIGURED');",
        )
        .await
        .expect("el perfil fiscal existe tras el arranque");
        let seeded = db
            .query(
                "SELECT regime_key FROM _hub_fiscal_regime_registry WHERE country_code = 'ES'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            seeded.rows.len(),
            1,
            "el registro de regímenes nace con su única fila: ES → verifactu"
        );
        assert_eq!(seeded.rows[0]["regime_key"], json!("verifactu"));
    }

    /// 🔒 **La v27 puede RE-EJECUTARSE sobre su propio resultado** (regla hub#342/#483). Lo delicado
    /// aquí es el `INSERT` del seed: sin `ON CONFLICT DO NOTHING` un segundo pase revienta con un
    /// 23505 y se lleva por delante la suite de otro — `tests/access_email_backfill.rs` rebobina el
    /// control a `version >= 19` y arrastra con él **todas** las posteriores, ésta incluida.
    #[tokio::test]
    async fn the_fiscal_profile_migration_can_run_a_second_time() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        hub_deployed_through(&db, MIGRATIONS.last().expect("catálogo no vacío").version).await;
        let fiscal = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_fiscal_profile")
            .expect("el perfil fiscal sigue en el catálogo");

        let mut hub = Params::new();
        hub.insert("hub_id".into(), json!("hub-test"));
        for stmt in split_statements(fiscal.postgres) {
            db.execute(&stmt, &hub)
                .await
                .expect("la v27 tiene que poder correr sobre un esquema que ya la tiene");
        }

        let seeded = db
            .query(
                "SELECT regime_key FROM _hub_fiscal_regime_registry WHERE country_code = 'ES'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            seeded.rows.len(),
            1,
            "el segundo pase no duplica el régimen de España"
        );
    }

    /// El mismo invariante para la v19 (hub#436): un hub que ya pasó por todo lo anterior **sí**
    /// recibe el backfill del email de acceso. Es el test que revienta si alguien la renumera por
    /// debajo del máximo — donde se saltaría en silencio y las filas seguirían sin revocarse.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_access_email_backfill() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let backfill = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_user_access_email_backfill")
            .expect("el backfill sigue en el catálogo");
        hub_deployed_through(&db, backfill.version - 1).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            backfill.version - 1,
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );
        // Una fila escrita por el alta anterior a hub#356: el email solo en el perfil.
        db.execute_batch(
            "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
               VALUES ('u1', 'hub-test', 'Ana Soto', '', 'admin', NULL, 1, '2026-08-01T10:00:00Z', '');\
             INSERT INTO hub_user_profile \
               (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
               VALUES ('hub-test', 'u1', 'Ana', 'Soto', 'ana@example.com', '', '2026-08-01T10:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();

        let row = db
            .query(
                "SELECT email FROM hub_user WHERE id = 'u1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            row.rows[0]["email"],
            json!("ana@example.com"),
            "el email llegó a la columna por la que se administra el ACCESO"
        );
    }

    /// El mismo invariante para la v21 (hub#470): un hub que ya pasó por todo lo anterior **sí**
    /// recibe la columna del TIPO de certificado. Es el test que revienta si alguien la renumera por
    /// debajo del máximo —donde se saltaría en silencio— y el hub elegiría la puerta de la AEAT con
    /// una columna que no existe.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_certificate_type_column() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let certificate_type = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_certificate_type")
            .expect("la columna del tipo sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(certificate_type.version)).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            previous_version_of(certificate_type.version),
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        // La columna existe, y **vacía**: nada rellena a ciegas el tipo del certificado que ese hub
        // ya tenía (adivinar de qué tipo es el certificado de alguien es lo que la v19 se negó a
        // hacer con su email — hub#436). Quien lo resuelve es `certificate::slot_type`, leyendo el
        // contenedor.
        db.execute_batch(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES ('h1', 'delegated', 'REVS', 'pw', '2026-01-01T00:00:00Z', 'cloud');",
        )
        .await
        .unwrap();
        let row = db
            .query(
                "SELECT certificate_type FROM _hub_certificate WHERE hub_id = 'h1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            row.rows[0]["certificate_type"],
            json!(""),
            "la columna nace vacía: el tipo no se deduce del slot, que es justo el defecto de hub#470"
        );
    }

    /// 🔒 **La v21 puede RE-EJECUTARSE sobre su propio resultado.** Regla nueva (hub#342/#483): una
    /// migración que no era idempotente tumbó 15 tests de otra suite con un `42P07`, y en producción
    /// sería un arranque fallido en vez de un no-op. El `IF NOT EXISTS` es lo que la cumple, y esto
    /// es lo que revienta si alguien lo quita.
    ///
    /// Solo la v21, a propósito: el catálogo histórico **no** es re-ejecutable (la v1 ya falla con
    /// un `42701` al añadir `hub_module.hub_id` por segunda vez) y arreglarlo entero es otra tarea.
    /// La regla vale de aquí en adelante, y aquí es donde empieza.
    #[tokio::test]
    async fn the_certificate_type_migration_can_run_a_second_time() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        hub_deployed_through(&db, MIGRATIONS.last().expect("catálogo no vacío").version).await;
        let certificate_type = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_certificate_type")
            .expect("la columna del tipo sigue en el catálogo");

        let mut hub = Params::new();
        hub.insert("hub_id".into(), json!("hub-test"));
        for stmt in split_statements(certificate_type.postgres) {
            db.execute(&stmt, &hub)
                .await
                .expect("la v21 tiene que poder correr sobre un esquema que ya la tiene");
        }
    }

    /// El mismo invariante para el **registro de hosts de impresión** (hub#342, v22). Se repite a
    /// propósito en vez de generalizarse a todo el catálogo: es la trampa que ya se cobró cuatro
    /// renumeraciones (hub#316, hub#317 y esta misma dos veces — nació v19 y chocó con hub#436,
    /// pasó a v20 y hub#470 metió una v21 antes, dejándola por DEBAJO del máximo: libre pero
    /// inalcanzable). Cada rama nueva en paralelo vuelve a exponerse a ella.
    ///
    /// Se para **justo antes** de la suya, con `hub_deployed_through` (que corre el SQL de verdad,
    /// no solo lo declara): así el test no puede saltarse a sí mismo cuando llegue la v23.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_print_host_registry() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let print_host = MIGRATIONS
            .iter()
            .find(|m| m.name == "print_host")
            .expect("el registro de hosts sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(print_host.version)).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            previous_version_of(print_host.version),
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        db.execute_batch(
            "INSERT INTO _print_host (hub_id, device_id, role, registered_at, last_seen_at) \
             VALUES ('h1', 'till-1', 'kitchen', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
    }

    /// **La v22 se puede RE-EJECUTAR sobre una base donde su tabla ya existe.**
    ///
    /// El control guarda *versiones*, no esquema, así que cualquier cosa que borre filas de
    /// `_hub_system_migrations` hace que `apply` vuelva a lanzar el SQL contra objetos que ya
    /// están. No es hipotético: `tests/access_email_backfill.rs` rebobina `version >= 19` para
    /// re-ejecutar el backfill de hub#436, y se lleva por delante **toda** migración posterior —
    /// esta. Con un `CREATE TABLE` a secas el segundo pase muere con 42P07 y tumba 15 tests de esa
    /// suite; con `IF NOT EXISTS` es una no-op silenciosa.
    ///
    /// A diferencia del test hermano de la v21, este rebobina **el registro** y vuelve a llamar a
    /// `apply` —el camino real— en vez de relanzar el SQL a mano, y comprueba además que la fila
    /// que el negocio ya tenía configurada **sigue ahí**: re-aplicar no puede recrear la tabla
    /// vacía y llevarse por delante qué caja imprime lo de cocina.
    #[tokio::test]
    async fn the_print_host_registry_can_be_applied_twice() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        // Una fila real: el segundo pase no puede perderla ni pisarla.
        db.execute_batch(
            "INSERT INTO _print_host (hub_id, device_id, role, label, registered_at, last_seen_at) \
             VALUES ('h1', 'till-1', 'kitchen', 'Mostrador', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        // El rebobinado que hace la suite de hub#436: se borra el REGISTRO, no la tabla.
        let print_host = MIGRATIONS
            .iter()
            .find(|m| m.name == "print_host")
            .expect("el registro de hosts sigue en el catálogo");
        let mut p = Params::new();
        p.insert("version".into(), json!(print_host.version));
        db.execute(
            "DELETE FROM _hub_system_migrations WHERE version >= :version",
            &p,
        )
        .await
        .unwrap();

        apply(&db, "hub-test")
            .await
            .expect("la v22 se re-aplica sobre su propia tabla sin romper");

        let rows = db
            .query(
                "SELECT label FROM _print_host WHERE device_id = 'till-1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1, "re-aplicar no recrea la tabla vacía");
        assert_eq!(
            rows.rows[0]["label"],
            json!("Mostrador"),
            "ni pisa lo que el negocio ya tenía configurado"
        );
    }

    /// El mismo invariante para el **device-trust por hub** (hub#489, v23): un hub que ya pasó por
    /// todo lo anterior **sí** recibe la columna `hub_id`. Es el test que revienta si alguien la
    /// renumera por debajo del máximo —v15 y v20 están libres y son **inalcanzables**—, donde se
    /// saltaría en silencio y la tabla seguiría siendo terreno común entre inquilinos.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_device_tenancy_column() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let scoped = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_trusted_device_hub_scoped")
            .expect("el device-trust por hub sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(scoped.version)).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            previous_version_of(scoped.version),
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        // La columna existe **y es la clave**: la MISMA tablet cabe dos veces si son dos negocios,
        // y no cabe dos veces dentro del mismo (la PK pasó de `device_id` a `(hub_id, device_id)`).
        db.execute_batch(
            "INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at) \
               VALUES ('hub-a', 'tablet-1', 'Ana', '2026-01-01T00:00:00Z');\
             INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at) \
               VALUES ('hub-b', 'tablet-1', 'Bruno', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
        let duplicated = db
            .execute_batch(
                "INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at) \
                   VALUES ('hub-a', 'tablet-1', 'Ana otra vez', '2026-01-02T00:00:00Z');",
            )
            .await;
        assert!(
            duplicated.is_err(),
            "dentro de un hub el dispositivo sigue siendo único: la PK es compuesta, no ausente"
        );
    }

    /// El mismo invariante para el **recibo de la elevación** (hub#362, v24): un hub que ya pasó
    /// por todo lo anterior **sí** recibe la tabla. Es el test que revienta si alguien la renumera
    /// por debajo del máximo —v15 y v20 están libres y son **inalcanzables**—, donde se saltaría
    /// EN SILENCIO: el hub arrancaría creyéndose al día, y la primera acción que un encargado
    /// aprobase moriría con un 42P01… o, peor, si algún día alguien "arregla" eso tragándose el
    /// error, se ejecutaría sin dejar rastro. Que es exactamente lo que hub#362 existe para evitar.
    #[tokio::test]
    async fn a_hub_already_migrated_still_receives_the_elevation_audit() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let audit = MIGRATIONS
            .iter()
            .find(|m| m.name == "elevation_audit")
            .expect("el recibo de la elevación sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(audit.version)).await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            previous_version_of(audit.version),
            "el hub se para JUSTO antes: si el fixture ya la aplicase, este test no probaría nada"
        );

        apply(&db, "hub-test").await.unwrap();

        // Las dos atribuciones, en la misma fila: quién estaba en la caja y quién lo autorizó.
        db.execute_batch(
            "INSERT INTO _elevation_audit (id, hub_id, command, permission, created_by, \
             approved_by, payload_fingerprint, created_at) \
             VALUES ('e1', 'h1', 'till.sale.void', 'till.void_sale', 'u-cashier', 'u-manager', \
             'abc123', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
    }

    /// **La v24 se puede RE-EJECUTAR sobre una base donde su tabla ya existe.**
    ///
    /// El control guarda *versiones*, no esquema: cualquier cosa que borre filas de
    /// `_hub_system_migrations` hace que [`apply`] vuelva a lanzar el SQL contra objetos que ya
    /// están (`tests/access_email_backfill.rs` rebobina `version >= 19` y se lleva por delante
    /// **toda** migración posterior — esta). Con un `CREATE TABLE` a secas el segundo pase muere
    /// con 42P07 y tumba 15 tests de esa suite (hub#483); con `IF NOT EXISTS` es una no-op.
    ///
    /// Y comprueba lo que en una tabla de auditoría es la mitad importante: re-aplicar **no puede
    /// recrear la tabla vacía**. Un registro de quién aprobó qué que se borra solo al rebobinar
    /// una migración no es un registro de nada.
    #[tokio::test]
    async fn the_elevation_audit_can_be_applied_twice() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        db.execute_batch(
            "INSERT INTO _elevation_audit (id, hub_id, command, permission, created_by, \
             approved_by, payload_fingerprint, created_at) \
             VALUES ('e1', 'h1', 'till.sale.void', 'till.void_sale', 'u-cashier', 'u-manager', \
             'abc123', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        let audit = MIGRATIONS
            .iter()
            .find(|m| m.name == "elevation_audit")
            .expect("el recibo de la elevación sigue en el catálogo");
        let mut p = Params::new();
        p.insert("version".into(), json!(audit.version));
        db.execute(
            "DELETE FROM _hub_system_migrations WHERE version >= :version",
            &p,
        )
        .await
        .unwrap();

        apply(&db, "hub-test")
            .await
            .expect("la v24 se re-aplica sobre su propia tabla sin romper");

        let rows = db
            .query(
                "SELECT approved_by FROM _elevation_audit WHERE id = 'e1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1, "re-aplicar no recrea la tabla vacía");
        assert_eq!(
            rows.rows[0]["approved_by"],
            json!("u-manager"),
            "ni pierde quién aprobó: una auditoría que se borra sola no es una auditoría"
        );
    }

    /// 🔴 **La decisión de la v23: la confianza que la BD no puede atribuir NO se le regala a
    /// nadie** (hub#489).
    ///
    /// Una fila anterior a la columna no dice de qué hub es. Sellarla con `:hub_id` —lo que hizo la
    /// v1 con `hub_module`— se la daría al hub que **arranque primero**, porque el control
    /// `_hub_system_migrations` tampoco es per-hub y la migración corre UNA vez por base de datos.
    /// En una BD compartida eso es regalarle a un negocio la tablet de confianza del vecino: el
    /// backfill a ciegas de hub#436, otra vez. Lo que se pierde por el lado conservador es
    /// **fricción** (un login online devuelve la fila, ya con su hub); lo que se perdería por el
    /// otro es **autorización**, y eso no se deshace.
    #[tokio::test]
    async fn the_trust_a_shared_database_cannot_attribute_is_not_handed_to_whoever_boots_first() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let scoped = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_trusted_device_hub_scoped")
            .expect("el device-trust por hub sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(scoped.version)).await;
        // La forma pre-v23: filas sin hub. Una es de quien va a arrancar y la otra del vecino, y
        // desde la tabla **no hay forma de saber cuál es cuál** — que es justo el punto.
        db.execute_batch(
            "INSERT INTO hub_trusted_device (device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
               VALUES ('till-1', 'Caja 1', '2026-08-01T09:00:00Z', 'shared', '', '');\
             INSERT INTO hub_trusted_device (device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
               VALUES ('tablet-of-the-neighbour', 'Marta Ruiz', '2026-08-02T10:00:00Z', 'personal', \
                       '2026-08-02T11:00:00Z', 'hub_user:admin');",
        )
        .await
        .unwrap();

        apply(&db, "hub-a").await.unwrap();

        let rows = db
            .query(
                "SELECT hub_id, device_id FROM hub_trusted_device ORDER BY device_id",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            rows.rows.len(),
            0,
            "ni una fila se selló con `hub-a`: la del vecino tampoco, y no había forma de \
             distinguirlas — se van las dos y se vuelven a ganar con un login online"
        );
    }

    /// **La v23 se puede RE-EJECUTAR sobre una base que ya la tiene** (regla de hub#342/#483).
    ///
    /// El control guarda *versiones*, no esquema: `tests/access_email_backfill.rs` rebobina
    /// `version >= 19` y se lleva por delante toda migración posterior — esta. Sin `IF NOT EXISTS`
    /// en el `ADD COLUMN` y sin el par `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`, el segundo
    /// pase muere (42701/42P16) y tumba la suite entera.
    ///
    /// Y comprueba lo que de verdad importa del segundo pase: que el `DELETE` del centinela
    /// **no toca confianza viva**. Solo puede alcanzar `hub_id = ''`, que el runtime no escribe
    /// nunca (`Runtime::hub_scope`).
    #[tokio::test]
    async fn the_device_tenancy_migration_can_be_applied_twice() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        // Una tablet de confianza de verdad, con su modo: el segundo pase no puede perderla.
        db.execute_batch(
            "INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
               VALUES ('hub-test', 'tablet-1', 'Ana Soto', '2026-08-01T09:00:00Z', 'personal', \
                       '2026-08-01T10:00:00Z', 'hub_user:admin');",
        )
        .await
        .unwrap();

        // El rebobinado que hace la suite de hub#436: se borra el REGISTRO, no la tabla.
        let scoped = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_trusted_device_hub_scoped")
            .expect("el device-trust por hub sigue en el catálogo");
        let mut p = Params::new();
        p.insert("version".into(), json!(scoped.version));
        db.execute(
            "DELETE FROM _hub_system_migrations WHERE version >= :version",
            &p,
        )
        .await
        .unwrap();

        apply(&db, "hub-test")
            .await
            .expect("la v23 se re-aplica sobre su propia columna sin romper");

        let rows = db
            .query(
                "SELECT hub_id, label, mode FROM hub_trusted_device WHERE device_id = 'tablet-1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1, "re-aplicar no se lleva la confianza viva");
        assert_eq!(rows.rows[0]["hub_id"], json!("hub-test"));
        assert_eq!(
            rows.rows[0]["mode"],
            json!("personal"),
            "ni el modo que un administrador ya había decidido"
        );
    }

    #[test]
    fn split_statements_keeps_each_terminated() {
        let stmts = split_statements("CREATE TABLE IF NOT EXISTS a (x);  DROP TABLE b; ");
        assert_eq!(stmts, vec!["CREATE TABLE IF NOT EXISTS a (x);", "DROP TABLE b;"]);
    }

    /// The user-activity mark needs a table of its own (hub#670): kept only in memory it died with
    /// the process, and with blue/green (ADR-0269) the process dies on every update. The row is
    /// what stops the Cloud's inactivity clock (ADR-0175) from deleting a free hub at 120 days.
    ///
    /// Re-executable on purpose (`CREATE TABLE IF NOT EXISTS`): a rewind of the control table must
    /// not blow up the second pass, and must not lose a mark that is already there (hub#483).
    #[tokio::test]
    async fn apply_creates_the_activity_table_and_can_run_twice_without_losing_the_mark() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        let activity = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_activity")
            .expect("the activity table is in the catalogue");
        assert!(
            max_applied_version(&db).await.unwrap() >= activity.version,
            "the activity migration must be registered"
        );

        db.execute_batch(
            "INSERT INTO _hub_activity (hub_id, last_activity_at, last_reported_at, updated_at) \
             VALUES ('hub-test', '2026-08-10T09:00:00Z', NULL, '2026-08-10T09:00:00Z');",
        )
        .await
        .unwrap();

        // The rewind the suite of hub#436 does: the RECORD is deleted, not the table.
        let mut p = Params::new();
        p.insert("version".into(), json!(activity.version));
        db.execute(
            "DELETE FROM _hub_system_migrations WHERE version >= :version",
            &p,
        )
        .await
        .unwrap();
        apply(&db, "hub-test")
            .await
            .expect("the activity migration re-applies over its own table");

        let rows = db
            .query(
                "SELECT last_activity_at FROM _hub_activity WHERE hub_id = 'hub-test'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1, "re-applying must not drop the mark");
        assert_eq!(rows.rows[0]["last_activity_at"], json!("2026-08-10T09:00:00Z"));
    }

    #[tokio::test]
    async fn apply_creates_trusted_device_table_v2() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        // El baseline v0 de identity/módulos no crea hub_trusted_device; la migración v2 sí.
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        // hub_session baseline (v0): la migración v8 (device_id) lo ALTERa, como el boot real
        // (`ensure_system_tables`) hace identity::ensure_tables antes de apply.
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        // La tabla existe (insert/select sin error) y la migración v2 quedó registrada.
        db.execute_batch(
            "INSERT INTO hub_trusted_device (device_id, label, trusted_at) \
             VALUES ('d1', 'Caja', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 2,
            "v2 registrada"
        );

        // Re-aplicar es idempotente (no re-crea la tabla → no falla por 'table exists').
        apply(&db, "hub-test").await.unwrap();
    }

    #[tokio::test]
    async fn apply_creates_hub_settings_table_v4() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        // hub_session baseline (v0): la migración v8 (device_id) lo ALTERa, como el boot real
        // (`ensure_system_tables`) hace identity::ensure_tables antes de apply.
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        // La tabla `hub_settings` existe (insert/select sin error) y la migración v4 quedó registrada.
        db.execute_batch(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
             VALUES ('hub-test', 'currency', 'EUR', '2026-01-01T00:00:00Z', 'hub_user:1');",
        )
        .await
        .unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 4,
            "v4 registrada"
        );

        // Re-aplicar es idempotente.
        apply(&db, "hub-test").await.unwrap();
    }

    #[tokio::test]
    async fn apply_adds_device_id_column_to_hub_session_v8() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        // Baseline v0: hub_module (necesaria para v1) + hub_session SIN device_id (identity v0).
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        // Sesión legacy YA existente (BD que sobrevive a un update): sin la columna device_id.
        db.execute_batch(
            "INSERT INTO hub_session (token, hub_id, user_id, created_at, expires_at) \
             VALUES ('legacy', 'hub-test', 'u1', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 8,
            "v8 registrada"
        );

        // La fila legacy sobrevive con device_id = NULL (columna nullable, ADITIVA).
        let legacy = db
            .query(
                "SELECT device_id FROM hub_session WHERE token = 'legacy'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(legacy.rows.len(), 1, "la sesión legacy sigue existiendo");
        assert_eq!(
            legacy.rows[0]["device_id"],
            serde_json::Value::Null,
            "device_id NULL en la legacy"
        );

        // Y una sesión nueva puede persistir device_id.
        db.execute_batch(
            "INSERT INTO hub_session (token, hub_id, user_id, created_at, expires_at, device_id) \
             VALUES ('t2', 'hub-test', 'u1', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z', 'dev-A');",
        )
        .await
        .unwrap();
        let row = db
            .query(
                "SELECT device_id FROM hub_session WHERE token = 't2'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(row.rows[0]["device_id"], json!("dev-A"));

        // Idempotente: re-aplicar NO re-ALTERa (no falla por 'duplicate column').
        apply(&db, "hub-test").await.unwrap();
    }

    #[tokio::test]
    async fn apply_adds_email_column_to_hub_user_v9() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        // Baseline v0: hub_module (necesaria para v1) + hub_user SIN email (identity v0).
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        // Usuario legacy YA existente (BD que sobrevive a un update): sin la columna email.
        db.execute_batch(
            "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-legacy', 'hub-test', 'Ada', '', 'owner', 'cloud-1', 1, '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 9,
            "v9 registrada"
        );

        // La fila legacy sobrevive con email = '' (columna con default, ADITIVA).
        let legacy = db
            .query(
                "SELECT email FROM hub_user WHERE id = 'u-legacy'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(legacy.rows.len(), 1, "el usuario legacy sigue existiendo");
        assert_eq!(legacy.rows[0]["email"], json!(""), "email '' en el legacy");

        // Y una fila nueva puede persistir + buscarse por email (lookup del enlace JWT→hub_user).
        db.execute_batch(
            "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
             VALUES ('u2', 'hub-test', 'Beto', '', 'employee', NULL, 1, '2026-01-01T00:00:00Z', 'beto@bar.com');",
        )
        .await
        .unwrap();
        let row = db
            .query(
                "SELECT id FROM hub_user WHERE email = 'beto@bar.com'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(row.rows[0]["id"], json!("u2"));

        // Idempotente: re-aplicar NO re-ALTERa (no falla por 'duplicate column').
        apply(&db, "hub-test").await.unwrap();
    }

    /// Role stored for a `hub_user`, read straight from the database.
    async fn stored_role(db: &dyn DatabaseAdapter, id: &str) -> String {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let res = db
            .query("SELECT role FROM hub_user WHERE id = :id", &p)
            .await
            .unwrap();
        res.rows[0]["role"].as_str().unwrap().to_string()
    }

    #[tokio::test]
    async fn apply_renames_the_legacy_owner_role_to_admin_v12() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        // A hub deployed BEFORE hub#349: the creator was seeded with `owner`, and the gate only
        // treated it as an administrator because `is_admin_role` said so. The rename must reach
        // those rows, whatever the casing, and must not touch anybody else.
        db.execute_batch(
            "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-owner', 'hub-test', 'Boss', '', 'owner', 'cloud-1', 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-shout', 'hub-test', 'Shout', '', 'OWNER', NULL, 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-cash', 'hub-test', 'Marta', '', 'cashier', NULL, 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-gone', 'hub-test', 'Baja', '', 'owner', NULL, 0, '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 12,
            "v12 registrada"
        );

        assert_eq!(
            stored_role(&db, "u-owner").await,
            "admin",
            "el creador legacy pasa a `admin`, que concede exactamente lo mismo"
        );
        assert_eq!(
            stored_role(&db, "u-shout").await,
            "admin",
            "el gate compara sin mayúsculas: la migración también"
        );
        assert_eq!(
            stored_role(&db, "u-gone").await,
            "admin",
            "también las filas inactivas: una reincorporación no puede resucitar el rol viejo"
        );
        assert_eq!(
            stored_role(&db, "u-cash").await,
            "cashier",
            "no toca ningún otro rol"
        );

        // Idempotente: re-aplicar no vuelve a correr el UPDATE ni cambia nada.
        apply(&db, "hub-test").await.unwrap();
        assert_eq!(stored_role(&db, "u-owner").await, "admin");
        assert_eq!(stored_role(&db, "u-cash").await, "cashier");
    }

    #[tokio::test]
    async fn apply_creates_user_profile_tables_v7() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        // hub_session baseline (v0): la migración v8 (device_id) lo ALTERa, como el boot real
        // (`ensure_system_tables`) hace identity::ensure_tables antes de apply.
        crate::identity::ensure_tables(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        db.execute_batch(
            "INSERT INTO hub_user_profile \
             (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
             VALUES ('hub-test', 'u1', 'Ada', 'Lovelace', 'ada@example.test', '', '2026-01-01');\
             INSERT INTO hub_user_pref \
             (hub_id, user_id, language, theme_mode, theme_palette, updated_at) \
             VALUES ('hub-test', 'u1', 'en', 'dark', 'ocean', '2026-01-01');",
        )
        .await
        .unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 7,
            "v7 registrada"
        );
        apply(&db, "hub-test").await.unwrap();
    }

    /// A hub deployed BEFORE hub#316: `_hub_certificate` in its v6 shape (singleton, PK `hub_id`)
    /// with the certificate its owner uploaded in Ajustes → Negocio, and every migration up to v13
    /// already registered. Reproduces the only state v14 has to survive — an ALTER cannot be tested
    /// against a table the same run has just created in its post-migration shape.
    ///
    /// `hub_trusted_device` (v2) belongs to that state too: this fixture jumps straight from v13 to
    /// the end of the catalogue, so **every** later migration runs over it, and one that ALTERs the
    /// device-trust table (v17, hub#357) would otherwise fail against a hub that never had one —
    /// a hub that has never existed, since v2 creates it for everybody.
    async fn hub_deployed_before_the_slots(db: &dyn DatabaseAdapter) {
        hub_deployed_through(db, 13).await;
    }

    /// Un hub **realmente** desplegado hasta la migración `upto`: el baseline v0 más el SQL de cada
    /// migración hasta esa versión, aplicado de verdad y registrado.
    ///
    /// Los fixtures de aquí abajo **declaraban** aplicadas unas versiones sin correr su SQL, y era
    /// inofensivo mientras ninguna migración posterior leyera esas tablas. La v19 (hub#436) lee
    /// `hub_user`, cuya columna `email` solo existe porque corrió la v9: un fixture que miente sobre
    /// el esquema convierte un fallo de la migración en un test que pasa por el motivo equivocado.
    /// Se replican, pues, de verdad.
    /// La versión del catálogo **inmediatamente anterior** a `version`.
    ///
    /// No es `version - 1`, y la diferencia importa: el catálogo tiene **huecos a propósito** (la
    /// v15, que nadie debe rellenar, y la v20, que quedó libre cuando hub#342 se renumeró a v22 tras
    /// entrar hub#470). Restar uno haría que el fixture se parase en un número que no existe y el
    /// `assert` de «justo antes» fallaría comparando contra un máximo que nunca se aplicó.
    ///
    /// Lo introdujo hub#470 inline; se factoriza aquí porque los dos tests de guarda lo necesitan y
    /// el siguiente que añada una migración lo necesitará también.
    fn previous_version_of(version: i64) -> i64 {
        MIGRATIONS
            .iter()
            .map(|m| m.version)
            .filter(|v| *v < version)
            .max()
            .expect("hay migraciones anteriores")
    }

    async fn hub_deployed_through(db: &dyn DatabaseAdapter, upto: i64) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        ensure_control_table(db).await.unwrap();
        for m in MIGRATIONS.iter().filter(|m| m.version <= upto) {
            run_and_record(db, m).await;
        }
    }

    /// Aplica **una** migración del catálogo por su `name` (SQL + registro), como haría [`apply`]
    /// al llegar a ella. Es lo que permite parar un fixture EN una migración concreta para medir su
    /// efecto, en vez de correr el catálogo entero y medir el de la última.
    ///
    /// Por `name` y no por número a propósito: el número es un accidente del orden de merge (esta
    /// tabla lo ha visto renumerarse cuatro veces), el nombre es el contrato.
    async fn apply_one(db: &dyn DatabaseAdapter, name: &str) {
        let m = MIGRATIONS
            .iter()
            .find(|m| m.name == name)
            .unwrap_or_else(|| panic!("`{name}` sigue en el catálogo"));
        run_and_record(db, m).await;
    }

    /// El SQL de `m` y su fila de control, en la misma transacción — igual que [`apply`].
    async fn run_and_record(db: &dyn DatabaseAdapter, m: &SystemMigration) {
        let mut hub = Params::new();
        hub.insert("hub_id".into(), json!("hub-test"));
        let mut ops: Vec<(String, Params)> = split_statements(m.postgres)
            .into_iter()
            .map(|stmt| (stmt, hub.clone()))
            .collect();
        let mut record = Params::new();
        record.insert("version".into(), json!(m.version));
        record.insert("name".into(), json!(m.name));
        record.insert("applied_at".into(), json!(now_rfc3339()));
        ops.push((
            "INSERT INTO _hub_system_migrations (version, name, applied_at) \
             VALUES (:version, :name, :applied_at)"
                .to_string(),
            record,
        ));
        db.execute_tx(&ops).await.unwrap();
    }

    /// The certificate a deployed hub already had is the BUSINESS's own one, and v14 must say so.
    ///
    /// The default of the new column is the whole safety of this migration: sealed as `delegated`,
    /// a hub in production would suddenly hold «ERPlora's certificate» — dropped from its own
    /// backup and exposed to a central rotation it never asked for.
    #[tokio::test]
    async fn the_certificate_a_deployed_hub_already_had_becomes_its_own_slot_v14() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        hub_deployed_before_the_slots(&db).await;
        db.execute_batch(
            "INSERT INTO _hub_certificate (hub_id, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES ('hub-test', 'TEVHQUNZ', 'pw', '2026-01-01T00:00:00Z', 'hub_user:admin');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 14,
            "v14 registrada"
        );

        let row = db
            .query(
                "SELECT kind, pkcs12_b64 FROM _hub_certificate WHERE hub_id = 'hub-test'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(row.rows.len(), 1, "la fila legacy sobrevive");
        assert_eq!(
            row.rows[0]["kind"],
            json!("own"),
            "sellada como PROPIA del negocio"
        );
        assert_eq!(
            row.rows[0]["pkcs12_b64"],
            json!("TEVHQUNZ"),
            "sus bytes intactos"
        );

        // Idempotente: re-aplicar no re-ALTERa (no falla por 'duplicate column').
        apply(&db, "hub-test").await.unwrap();
    }

    /// After v14 the two slots are two ROWS of the same hub: the PK is `(hub_id, kind)`, so storing
    /// the delegated certificate cannot evict the business's own one (nor the other way round).
    #[tokio::test]
    async fn after_v14_both_slots_fit_in_the_same_hub() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        hub_deployed_before_the_slots(&db).await;
        apply(&db, "hub-test").await.unwrap();

        db.execute_batch(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES ('hub-test', 'own', 'T1dO', 'pw1', '2026-01-01T00:00:00Z', 'hub_user:admin');\
             INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES ('hub-test', 'delegated', 'REVM', 'pw2', '2026-01-02T00:00:00Z', 'cloud');",
        )
        .await
        .unwrap();

        let rows = db
            .query(
                "SELECT kind FROM _hub_certificate WHERE hub_id = 'hub-test' ORDER BY kind",
                &Params::new(),
            )
            .await
            .unwrap();
        let kinds: Vec<&str> = rows
            .rows
            .iter()
            .filter_map(|r| r["kind"].as_str())
            .collect();
        assert_eq!(kinds, vec!["delegated", "own"], "los dos slots conviven");
    }

    /// v17 (hub#357): los dispositivos de confianza que YA existen heredan el modo **estricto**.
    ///
    /// Es toda la seguridad de esta migración. `personal` significa «sin pinpad, sesión larga»: si
    /// el default fuese ese, cada TPV de mostrador ya enrolado de la flota amanecería sin pedir
    /// quién está detrás de la caja, y nadie lo habría decidido. Lo que se hereda es la fricción,
    /// nunca su ausencia.
    ///
    /// Se para **en la v17** en vez de correr el catálogo entero, y el segundo acto dice por qué:
    /// la v23 (hub#489) se lleva esa misma fila, porque no dice de qué hub es. Las dos cosas son
    /// ciertas y ninguna tapa a la otra — el modo que hereda mientras existe, y que deja de existir.
    #[tokio::test]
    async fn the_devices_a_deployed_hub_already_trusted_inherit_the_strict_mode_v17() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        // Un hub anterior a la v17: la tabla del device-trust (v2) SIN las columnas del modo.
        hub_deployed_through(&db, 16).await;
        db.execute_batch(
            "INSERT INTO hub_trusted_device (device_id, label, trusted_at) \
             VALUES ('till-1', 'Caja 1', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply_one(&db, "hub_trusted_device_mode").await;
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            17,
            "el hub llega EXACTAMENTE a la v17: es su efecto lo que se mide"
        );

        let row = db
            .query(
                "SELECT mode, label FROM hub_trusted_device WHERE device_id = 'till-1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(row.rows.len(), 1, "el dispositivo de confianza sobrevive");
        assert_eq!(
            row.rows[0]["mode"],
            json!("shared"),
            "hereda la fricción, no su ausencia"
        );
        assert_eq!(row.rows[0]["label"], json!("Caja 1"), "su etiqueta intacta");

        // Segundo acto: el resto del catálogo. La v23 (hub#489) retira esa confianza en vez de
        // sellarla con el hub que arranque — ver
        // `the_trust_a_shared_database_cannot_attribute_is_not_handed_to_whoever_boots_first`.
        apply(&db, "hub-test").await.unwrap();
        let after = db
            .query(
                "SELECT device_id FROM hub_trusted_device",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            after.rows.len(),
            0,
            "la fila que no nombra hub deja de conceder nada; se recupera con un login online"
        );

        // Idempotente: re-aplicar no re-ALTERa (no falla por 'duplicate column').
        apply(&db, "hub-test").await.unwrap();
    }

    /// hub#573: a system migration whose version is ≤ the max applied, but which is **not
    /// registered** as applied, is an **incoherent catalogue** — not "already done". Two parallel
    /// branches that picked the same number (or a migration that landed below the max after a
    /// renumber) leave exactly this state: the row is in the embedded catalogue, the hub's max is
    /// above it, but its `_hub_system_migrations` row never got written because the old `apply`
    /// skipped it in silence.
    ///
    /// Before this fix `apply` treated `version <= max` as "done" and `continue`d — the hub booted
    /// believing it was up to date while missing the table. After: it **aborts** and names the
    /// version, turning a silent skip into a loud failure that a test or a boot log catches.
    #[tokio::test]
    async fn apply_aborts_if_a_catalogue_version_below_the_max_is_not_registered() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        // A hub deployed through v13 (baseline + v1..v13), all genuinely applied and registered.
        hub_deployed_before_the_slots(&db).await;
        assert_eq!(max_applied_version(&db).await.unwrap(), 13);

        // Now bump the recorded max to 15 WITHOUT registering v14 — the exact state a skipped
        // migration leaves: a row above v14 is recorded, v14 is in the catalogue, but v14's own
        // registration never happened (simulating a parallel-branch collision or a renumber).
        let mut p = Params::new();
        p.insert("version".into(), json!(15));
        p.insert("name".into(), json!("bogus_skip_above_14"));
        p.insert("applied_at".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO _hub_system_migrations (version, name, applied_at) \
             VALUES (:version, :name, :applied_at)",
            &p,
        )
        .await
        .unwrap();
        assert_eq!(max_applied_version(&db).await.unwrap(), 15);

        // v14 is in the catalogue and its version (14) is ≤ the recorded max (15), but it is NOT
        // registered. `apply` must REFUSE to boot — not silently skip v14 and continue.
        let err = apply(&db, "hub-test").await.unwrap_err();
        let msg = err.to_string().to_lowercase();
        assert!(
            msg.contains("14"),
            "el error nombra la versión perdida (v14); fue: {msg}"
        );
        assert!(
            !msg.contains("ok") && err.to_string() != "",
            "es un error real, no un silencio"
        );
    }

    /// The catalogue has **gaps by design** (v15, v20, v24 were left free by renumbers and must
    /// never be reused). hub#573's fix must not treat a gap as a missing migration: a version that
    /// is simply absent from the catalogue is not "unregistered", it is "does not exist". Only a
    /// version that IS in the catalogue but missing from `_hub_system_migrations` (while below the
    /// max) is the incoherence that aborts the boot.
    #[test]
    fn known_gaps_in_the_catalogue_are_documented_not_filled() {
        let versions: Vec<i64> = MIGRATIONS.iter().map(|m| m.version).collect();
        // Strictly increasing (no duplicates) — the existing guard, restated.
        let mut prev = 0i64;
        for &v in &versions {
            assert!(v > prev, "v{v} duplicada o desordenada");
            prev = v;
        }
        // The historical gaps. Documented here so a new gap is noticed: adding to this list is a
        // conscious act (you renumbered and left a hole), NOT an accident. If a gap appears that is
        // not in this list, someone added a migration out of order — investigate before listing it.
        let known_gaps: Vec<i64> = vec![15, 20, 24];
        let actual_gaps: Vec<i64> = (1..=*versions.last().unwrap())
            .filter(|v| !versions.contains(v))
            .collect();
        assert_eq!(
            actual_gaps, known_gaps,
            "gap nuevo en el catálogo: si lo dejaste a propósito al renumerar, añádelo a `known_gaps`; \
             si no, es un fallo de orden"
        );
    }

    /// **hub#483 — the whole catalogue is re-runnable.** `_hub_system_migrations` records versions
    /// applied, not schema. Anything that wipes rows from it (a fixture rewinding, a restored backup
    /// with control behind schema, a partial import) makes `apply` re-run the SQL against a base
    /// where the objects already exist. Without `IF NOT EXISTS`, the boot dies on `42P07` instead of
    /// converging — and dies with a Postgres error, not a message that explains anything.
    ///
    /// This test fixes the property for the ENTIRE catalogue, not one migration at a time: apply it
    /// all, wipe every control row, re-apply, and require green. A new migration that forgets
    /// `IF NOT EXISTS` fails here in CI, not in a fixture that belongs to somebody else.
    #[tokio::test]
    async fn the_whole_catalogue_can_be_re_applied_over_existing_schema() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        // Full baseline + the whole catalogue, genuinely applied once.
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        ensure_control_table(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() > 0,
            "el catálogo tiene migraciones y se aplicaron"
        );

        // Wipe ALL control rows → `apply` sees a max of 0 and re-runs every migration. With the
        // objects already in the schema, a `CREATE TABLE` without `IF NOT EXISTS` dies on 42P07.
        db.execute_batch("DELETE FROM _hub_system_migrations;").await.unwrap();
        assert_eq!(
            max_applied_version(&db).await.unwrap(),
            0,
            "borrado el control, el máximo vuelve a 0 → apply re-corre el catálogo entero"
        );

        // Re-applying over the existing schema must converge, not abort. Today this fails on the
        // first `CREATE TABLE` without `IF NOT EXISTS`.
        apply(&db, "hub-test").await.expect(
            "re-aplicar el catálogo sobre un esquema ya creado no debe fallar: cada CREATE/ALTER \
             necesita IF NOT EXISTS (hub#483)"
        );
        // And it leaves the control table populated again — a re-run is a real apply, not a no-op
        // that silently skipped everything.
        assert!(
            max_applied_version(&db).await.unwrap() > 0,
            "tras re-aplicar, el control vuelve a registrar las versiones"
        );
    }
    /// **v42 sella el hub en la identidad ya desplegada, y no pierde a nadie** (hub#497).
    ///
    /// Las filas que existían no dicen de qué hub son. v23 resolvió eso en `hub_trusted_device`
    /// **borrándolas** —lo perdido era una confianza que se recupera con un login—; aquí no se
    /// puede: son personas, y su historial cuelga de su id. Se sellan con el `hub_id` del
    /// despliegue, que desde ADR-0201 es un hecho (cada hub es dueño de su base) y no una
    /// conjetura.
    ///
    /// El baseline v0 ya crea la columna, así que un hub **ya desplegado** se simula quitándola:
    /// es exactamente la forma que tienen esos hubs.
    #[tokio::test]
    async fn la_v42_sella_el_hub_en_la_identidad_ya_desplegada_sin_perder_a_nadie() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let v42 = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_identity_hub_scoped")
            .expect("la identidad por hub sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(v42.version)).await;
        db.execute_batch(
            "ALTER TABLE hub_user DROP COLUMN hub_id;\
             ALTER TABLE hub_session DROP COLUMN hub_id;",
        )
        .await
        .unwrap();

        // Una persona y su sesión abierta, de antes de que la columna existiera.
        db.execute_batch(
            "INSERT INTO hub_user (id, name, pin_hash, role, is_active, created_at) \
               VALUES ('u-1', 'Ana', '', 'admin', 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_session (token, user_id, created_at, expires_at) \
               VALUES ('t-1', 'u-1', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-a").await.unwrap();

        // Nadie se borró, y ahora cada fila dice de quién es.
        let stamped = db
            .query(
                "SELECT (SELECT count(*) FROM hub_user WHERE hub_id = 'hub-a') AS users, \
                        (SELECT count(*) FROM hub_session WHERE hub_id = 'hub-a') AS sessions",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(stamped.rows[0]["users"].as_i64(), Some(1), "Ana sigue ahí");
        assert_eq!(
            stamped.rows[0]["sessions"].as_i64(),
            Some(1),
            "y sigue con la sesión que tenía abierta: migrar no echa a nadie del hub"
        );

        // Y la sesión ya solo vale en su hub — que es lo que la columna existe para poder decir.
        assert!(crate::identity::resolve_session(&db, "hub-a", "t-1")
            .await
            .unwrap()
            .is_some());
        assert!(
            crate::identity::resolve_session(&db, "hub-b", "t-1")
                .await
                .unwrap()
                .is_none(),
            "el token sellado para hub-a no abre otro hub"
        );
    }

    /// Re-ejecutable (regla hub#342/#483): el segundo pase es un no-op, no un error. Los fixtures
    /// que rebobinan el control por versión vuelven a pasar por aquí, y una migración que reventase
    /// al repetirse se llevaría por delante la suite de otro.
    #[tokio::test]
    async fn la_v42_se_puede_aplicar_dos_veces() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let v42 = MIGRATIONS
            .iter()
            .find(|m| m.name == "hub_identity_hub_scoped")
            .expect("la identidad por hub sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(v42.version)).await;
        db.execute_batch(
            "ALTER TABLE hub_user DROP COLUMN hub_id;\
             ALTER TABLE hub_session DROP COLUMN hub_id;",
        )
        .await
        .unwrap();

        apply_one(&db, "hub_identity_hub_scoped").await;
        // El mismo SQL otra vez, tal cual lo ejecutaría `apply`.
        for statement in split_statements(v42.postgres) {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!("hub-a"));
            db.execute(&statement, &p)
                .await
                .unwrap_or_else(|e| panic!("`{statement}` no es re-ejecutable: {e}"));
        }
    }

    /// **v46 sella el hub en los marcadores de idempotencia que ya existían** (hub#735).
    ///
    /// `_event_delivery` la crea el baseline v0 (`outbox::ensure_tables`), así que un hub **ya
    /// desplegado** se simula quitándole la columna: es exactamente la forma que tiene hoy. Lo que
    /// se comprueba es lo que importa de un marcador — que **sigue ahí**: perder uno no libera
    /// espacio, hace que un listener vuelva a correr y que un evento produzca un segundo run.
    #[tokio::test]
    async fn la_v46_sella_el_hub_en_los_marcadores_ya_escritos_sin_perder_ninguno() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let v46 = MIGRATIONS
            .iter()
            .find(|m| m.name == "event_delivery_hub_scoped")
            .expect("el marcador por hub sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(v46.version)).await;
        crate::outbox::ensure_tables(&db).await.unwrap();
        db.execute_batch("ALTER TABLE _event_delivery DROP COLUMN hub_id;")
            .await
            .unwrap();
        // Dos marcadores de antes de que la columna existiera: el de un listener de módulo y el
        // sintético de un disparador de flujo.
        db.execute_batch(
            "INSERT INTO _event_delivery (event_id, listener_command, delivered_at) VALUES \
               ('evt-1', 'inventory._restock_on_void', '2026-01-01T00:00:00Z'), \
               ('evt-1', '_flow:trigger-9', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-a").await.unwrap();

        let rows = db
            .query(
                "SELECT count(*) AS c FROM _event_delivery WHERE hub_id = 'hub-a'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            rows.rows[0]["c"].as_i64(),
            Some(2),
            "los dos marcadores siguen ahí, y ahora dicen de qué hub son"
        );
    }

    /// Re-ejecutable (regla hub#342/#483): el segundo pase es un no-op, no un error.
    #[tokio::test]
    async fn la_v46_se_puede_aplicar_dos_veces() {
        use erplora_db::testutil::fresh_db;
        let db = fresh_db().await;
        let v46 = MIGRATIONS
            .iter()
            .find(|m| m.name == "event_delivery_hub_scoped")
            .expect("el marcador por hub sigue en el catálogo");
        hub_deployed_through(&db, previous_version_of(v46.version)).await;
        crate::outbox::ensure_tables(&db).await.unwrap();
        db.execute_batch("ALTER TABLE _event_delivery DROP COLUMN hub_id;")
            .await
            .unwrap();

        apply_one(&db, "event_delivery_hub_scoped").await;
        for statement in split_statements(v46.postgres) {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!("hub-a"));
            db.execute(&statement, &p)
                .await
                .unwrap_or_else(|e| panic!("`{statement}` no es re-ejecutable: {e}"));
        }
    }
}

#[cfg(test)]
mod kind_contract_tests {
    use super::*;

    /// **Cada migración de sistema hace lo que su `kind` dice.**
    ///
    /// Esto es lo que impide que la próxima entre destruyendo algo sin decirlo: quien añada un
    /// `DROP COLUMN` marcándolo `expand` no llega a mergear. Y es el eslabón que hace seguro el
    /// auto-rollback (saas#1246) — sin él, revertir el binario sobre un esquema adelantado falla
    /// **en silencio**.
    #[test]
    fn every_system_migration_does_what_its_kind_says() {
        for migration in MIGRATIONS {
            if let Err(error) = crate::migration_guard::kind_matches(migration.postgres, migration.kind) {
                panic!(
                    "v{} `{}`: {error}\n\
                     Si de verdad no admite vuelta atrás, márcala `Kind::Contract` y añádela al \
                     inventario de abajo — no la disfraces de aditiva.",
                    migration.version, migration.name
                );
            }
        }
    }

    /// **El inventario: qué versiones NO admiten vuelta atrás.**
    ///
    /// Seis. La issue decía «al menos dos» (las PK de `hub_module` y de `_hub_certificate`) y se
    /// dejaba las dos peores:
    ///
    /// - **v23** hace `DELETE FROM` — **borra datos**, no solo esquema;
    /// - **v25** hace `DROP COLUMN` — el binario anterior usaba esa columna.
    ///
    /// Las dos `SET NOT NULL` (v42, v46) están aquí por el mismo motivo por los dos lados: revertir
    /// el binario deja una columna obligatoria que el código anterior no escribe, así que sus
    /// `INSERT` fallan. Y en el despliegue start-first (ADR-0269) eso también dura lo que tarda el
    /// contenedor viejo en morir: sus escrituras fallan y **hacen rollback** —ni entrega a medias
    /// ni marcador huérfano—, y la fila del outbox se reintenta con backoff. Es la alternativa
    /// segura frente a un `DEFAULT ''`, que dejaría marcadores sin dueño que el lector scopeado no
    /// vería nunca y que chocarían con la PK para siempre.
    ///
    /// Sirve para dos cosas: un rollback **por debajo** de estas versiones no es seguro, y este
    /// test se rompe si alguien añade una quinta sin mirarlo.
    #[test]
    fn the_inventory_of_versions_that_cannot_be_rolled_back() {
        let no_vuelta: Vec<i64> = MIGRATIONS
            .iter()
            .filter(|m| m.kind == Kind::Contract)
            .map(|m| m.version)
            .collect();

        assert_eq!(
            no_vuelta,
            vec![1, 14, 23, 25, 42, 46],
            "cambió el inventario de migraciones sin vuelta atrás. Si es una nueva: revisa que \
             de verdad haga falta, porque cada una es una versión por debajo de la cual el \
             rollback deja de ser seguro."
        );
    }

    /// Y el catálogo sigue siendo estrictamente creciente, con sus huecos.
    ///
    /// Los huecos (v15, v20, v24) son reales y correctos: una versión reservada y descartada no se
    /// reutiliza **nunca** — hacerlo aplicaría un SQL distinto en hubs que ya registraron ese
    /// número y no volverían a mirarlo.
    #[test]
    fn the_catalogue_only_grows() {
        let mut previous = 0;
        for migration in MIGRATIONS {
            assert!(
                migration.version > previous,
                "v{} rompe el orden del catálogo",
                migration.version
            );
            previous = migration.version;
        }
        // 38 = 27 + las cinco del kernel de automatización (v31–v35, hub#661) + `_flow_secrets`
        // (v36, hub#662) + `_flow_triggers.tz` (v37, hub#731) + `_flow_approvals` (v38, hub#665) +
        // `_hub_activity` (v39, hub#670) + `_update_history` (v40, hub#564) + `hub_module_package`
        // (v41, hub#571) + `hub_identity_hub_scoped` (v42, hub#497) + el otorgamiento de
        // representación en el perfil fiscal (v43, hub#817).
        // El número está a mano a propósito: añadir una migración de sistema tiene
        // que ser un gesto CONSCIENTE, y este assert es lo que obliga a mirar el catálogo entero
        // antes de tocarlo — que es justo lo que evita que dos ramas en vuelo pidan el mismo
        // número, como pasó en esta ola: hub#731 y hub#665 pidieron las dos el v37; hub#670,
        // hub#564 y hub#571 pidieron las tres el v39. Y `hub_identity_hub_scoped` (v42, hub#497)
        // se llevó el 42 que había pedido el otorgamiento de representación, que pasó al v43.
        // + `hub_trusted_device_name` (v44, hub#494): el nombre que le pone el NEGOCIO al
        // dispositivo. + `flow_approval_on_expire` (v45, hub#972): qué le pasa al run cuando su
        // aprobación caduca, escrito en la fila. + `event_delivery_hub_scoped` (v46, hub#735): el
        // marcador de idempotencia también dice de qué hub es — nació como v45 y el rebase lo
        // destapó como conflicto contra hub#972, que es exactamente para lo que sirve tener el
        // número a mano. Ojo a la distancia entre 43 entradas y la v46 — **el número es declarado,
        // no la posición**: faltan la 15, la 20 y la 24, así que contar entradas para elegir el
        // siguiente número da un choque, no un hueco.
        // + `print_stations` (v47, hub#457): las estaciones de impresión pasan a ser filas con id,
        // y la cola y el registro de hosts apuntan a ellas por `station_id` en vez de comparar una
        // cadena. Solo DDL — la siembra por hub vive en `print_stations::ensure_stations`, que
        // corre desde `apply` en cada arranque porque una migración se registra por BASE DE DATOS
        // y esto hace falta por HUB.
        // + `hub_user_badge_credential` (v48, hub#658): la placa de empleado, hermana del PIN, y la
        // traza de con qué se probó la identidad. Tomó el **48** dejando libre el 47 a propósito,
        // porque hub#457 iba a por él en la misma tanda — y en efecto lo cogió y se mergeó antes,
        // así que el hueco duró lo que duró el rebase. Es la lección de la v46 (que nació como v45 y
        // chocó) aplicada **por delante** en vez de por detrás: un hueco no se puede coger por
        // accidente, un número repetido sí, y ese aborta el arranque de un hub ya desplegado.
        // + `flow_approval_generic_decision` (v49, hub#950): `_flow_approvals` deja de ser solo
        // «lo que propuso un modelo» y gana `kind`, la pregunta ya templada (`title`/`summary`),
        // el rol que puede contestarla, el comentario de quien decidió y `on_reject`. Se
        // generaliza la fila; no se bifurca la tabla.
        // + `print_routes` (v50, hub#987): el mapa `documentType → estación`, la otra mitad del
        // diagrama que la v47 dejó a medias — el módulo dice QUÉ imprime y el hub decide DÓNDE sale.
        // Solo DDL, y por el mismo motivo que la v47: la siembra por hub vive en
        // `print_routes::ensure_routes`, que corre desde `apply` **después** de `ensure_stations`
        // (una ruta apunta al `id` de una estación). Al escribirla el máximo era la v48 en
        // `origin/develop` y en TODAS las ramas remotas — recomprobado contra el conjunto, no solo
        // contra develop, que es donde el recuento a mano se ha equivocado antes.
        // + `fiscal_regime_simplified_limit` (v51, hub#297): el techo de la factura simplificada
        // baja a la fila del régimen que lo impone (`_hub_fiscal_regime_registry`), porque es un
        // dato del mismo tipo que el régimen y no un `match` sobre el país compilado en el runtime.
        // `0` = «este régimen no pone techo», y el `UPDATE` de siembra lleva guarda `= 0` para que
        // un rearranque no le pise al comerciante un valor que él hubiera movido. Al escribirla el
        // máximo era la v50 en `origin/develop` y en TODAS las ramas remotas, y también en los 10
        // worktrees locales de la flota — que es donde vive el número que el remoto aún no ha visto.
        // + `public_claim` (v52, hub#963; nació v51 y se movió en el rebase: hub#297 se llevó la 51): las dos tablas de la ÚNICA puerta del hub que contesta a
        // alguien sin sesión — el cliente que se lleva el tique y quiere su factura. Se guarda el
        // HASH del localizador, nunca el localizador: un volcado de la tabla no puede entregar
        // todos los tiques abiertos del negocio. Al escribirla el máximo era la v50 en
        // `origin/develop` y en TODAS las ramas remotas, recomprobado contra el conjunto.
        // + `flow_run_waits` (v53, hub#951): las OTRAS salidas de un `delay` — los eventos que
        // cancelan un run dormido y los que mueven su instante. Tabla nueva + un índice PARCIAL
        // (`WHERE status = 'armed'`), porque el cotejo corre en el camino caliente de cada evento
        // entregado. Su número se movió DOS veces (v39 en la decisión → v51 al implementarla →
        // v53 cuando hub#1000 se llevó la v51 y hub#1001 la v52), que es justo por qué se
        // recomprueba en el rebase y no al escribir. El hueco de la v52 es de hub#1001 y tiene que
        // entrar ANTES: rellenar un hueco por DEBAJO del máximo ya aplicado aborta el arranque.
        // + `print_queue_discard` (v54, hub#1108): las tres columnas del SELLO de un descarte
        // (`discarded_at`/`discarded_by`/`discard_reason`) en `_print_queue`. Solo `ALTER … ADD
        // COLUMN IF NOT EXISTS`, re-ejecutable: retirar un tique que nadie va a imprimir **nunca**
        // borra la fila —es la única prueba de que existió— y una fila cerrada sin autor ni motivo
        // haría invisible justo lo que pasó. Mismas columnas y mismos tipos que hub#660/hub#955
        // pusieron en `_event_outbox`, porque es el mismo gesto sobre la otra cola durable. Al
        // escribirla el máximo era la v53 en `origin/develop` y en TODAS las ramas remotas.
        assert_eq!(MIGRATIONS.len(), 51, "el catálogo cambió de tamaño");
    }
}
