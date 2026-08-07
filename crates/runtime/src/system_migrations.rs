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
        // Postgres: añade la columna nullable, sella el hub_id del despliegue en las filas
        // existentes (UPDATE con `:hub_id`, bind seguro — no se mete un parámetro en un DEFAULT
        // de DDL, que Postgres rechazaría en sentencia preparada), luego la pone NOT NULL y
        // recompone la PK a `(hub_id, module_id)`.
        postgres: "\
ALTER TABLE hub_module ADD COLUMN hub_id TEXT;\
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
        postgres: "\
CREATE TABLE hub_trusted_device (\
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
        postgres: "\
CREATE TABLE hub_api_key (\
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
        postgres: "\
CREATE TABLE hub_settings (\
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
        postgres: "\
CREATE TABLE _module_capability_grants (\
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
        postgres: "\
CREATE TABLE _hub_certificate (\
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
        postgres: "\
CREATE TABLE hub_user_profile (\
  hub_id TEXT NOT NULL, user_id TEXT NOT NULL, first_name TEXT NOT NULL DEFAULT '', \
  last_name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', \
  avatar_path TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id, user_id));\
CREATE TABLE hub_user_pref (\
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
        postgres: "ALTER TABLE hub_session ADD COLUMN device_id TEXT;",
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
        postgres: "\
ALTER TABLE hub_user ADD COLUMN email TEXT NOT NULL DEFAULT '';\
CREATE INDEX IF NOT EXISTS ix_hub_user_email ON hub_user (email);",
    },
    // ── v10 — #42: cuota durable de API keys ────────────────────────────────────────────────
    SystemMigration {
        version: 10,
        name: "api_key_rate_limit",
        postgres:
            "\
ALTER TABLE hub_api_key ADD COLUMN rate_limit_per_minute INTEGER NOT NULL DEFAULT 60;\
CREATE TABLE hub_api_key_rate_window (\
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
        postgres: "ALTER TABLE hub_user ADD COLUMN cloud_revoked_at TEXT NOT NULL DEFAULT '';",
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
        postgres: "\
CREATE TABLE hub_role_activation (\
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
        postgres: "\
ALTER TABLE _hub_certificate ADD COLUMN kind TEXT NOT NULL DEFAULT 'own';\
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
        postgres: "ALTER TABLE _hub_certificate ADD COLUMN cert_version BIGINT;",
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
        postgres: "\
ALTER TABLE hub_trusted_device ADD COLUMN mode TEXT NOT NULL DEFAULT 'shared';\
ALTER TABLE hub_trusted_device ADD COLUMN mode_set_at TEXT NOT NULL DEFAULT '';\
ALTER TABLE hub_trusted_device ADD COLUMN mode_set_by TEXT NOT NULL DEFAULT '';",
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
        postgres: "\
CREATE TABLE _print_queue (\
  hub_id TEXT NOT NULL, job_id TEXT NOT NULL, seq BIGSERIAL NOT NULL, \
  role TEXT NOT NULL, html TEXT NOT NULL, format TEXT NOT NULL DEFAULT 'receipt', \
  status TEXT NOT NULL DEFAULT 'pending', attempts BIGINT NOT NULL DEFAULT 0, \
  claimed_by TEXT NOT NULL DEFAULT '', lease_expires_at TEXT NOT NULL DEFAULT '', \
  last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, completed_at TEXT, \
  PRIMARY KEY (hub_id, job_id));\
CREATE INDEX ix_print_queue_next ON _print_queue (hub_id, role, status, seq);\
CREATE INDEX ix_print_queue_lease ON _print_queue (hub_id, status, lease_expires_at);",
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
/// El SQL de las migraciones puede llevar el parámetro `:hub_id` (lo usa v1 para sellar el
/// hub_id del despliegue en las filas existentes).
pub async fn apply(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    ensure_control_table(db).await?;
    let applied = max_applied_version(db).await?;

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

        if m.version <= applied {
            continue; // ya aplicada en un arranque previo (idempotente).
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
    Ok(())
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
        db.execute_batch(
            "INSERT INTO _print_queue (hub_id, job_id, role, html, created_at) \
             VALUES ('h1', 'j1', 'receipt', '<p>t</p>', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
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
            "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
               VALUES ('u1', 'Ana Soto', '', 'admin', NULL, 1, '2026-08-01T10:00:00Z', '');\
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

    #[test]
    fn split_statements_keeps_each_terminated() {
        let stmts = split_statements("CREATE TABLE a (x);  DROP TABLE b; ");
        assert_eq!(stmts, vec!["CREATE TABLE a (x);", "DROP TABLE b;"]);
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
            "INSERT INTO hub_session (token, user_id, created_at, expires_at) \
             VALUES ('legacy', 'u1', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z');",
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
            "INSERT INTO hub_session (token, user_id, created_at, expires_at, device_id) \
             VALUES ('t2', 'u1', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z', 'dev-A');",
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
            "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-legacy', 'Ada', '', 'owner', 'cloud-1', 1, '2026-01-01T00:00:00Z');",
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
            "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
             VALUES ('u2', 'Beto', '', 'employee', NULL, 1, '2026-01-01T00:00:00Z', 'beto@bar.com');",
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
            "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-owner', 'Boss', '', 'owner', 'cloud-1', 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-shout', 'Shout', '', 'OWNER', NULL, 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-cash', 'Marta', '', 'cashier', NULL, 1, '2026-01-01T00:00:00Z');\
             INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-gone', 'Baja', '', 'owner', NULL, 0, '2026-01-01T00:00:00Z');",
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
    async fn hub_deployed_through(db: &dyn DatabaseAdapter, upto: i64) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        ensure_control_table(db).await.unwrap();
        let mut hub = Params::new();
        hub.insert("hub_id".into(), json!("hub-test"));
        for m in MIGRATIONS.iter().filter(|m| m.version <= upto) {
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

        apply(&db, "hub-test").await.unwrap();
        assert!(
            max_applied_version(&db).await.unwrap() >= 17,
            "v17 registrada"
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

        // Idempotente: re-aplicar no re-ALTERa (no falla por 'duplicate column').
        apply(&db, "hub-test").await.unwrap();
    }
}
