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
        postgres: "\
ALTER TABLE hub_api_key ADD COLUMN rate_limit_per_minute INTEGER NOT NULL DEFAULT 60;\
CREATE TABLE hub_api_key_rate_window (\
  api_key_id TEXT PRIMARY KEY, window_epoch_minute BIGINT NOT NULL, request_count BIGINT NOT NULL);",
    },
    // ── v11 — ADR-0049: entrada/salida webhook ─────────────────────────────────────────────
    // El receipt evita repetir un command cuando el emisor reintenta el mismo envelope. Los
    // secretos de salida se cifran con HUB_SECRETS_KEY; el Outbox reintenta por destino.
    SystemMigration {
        version: 11,
        name: "integration_webhooks",
        postgres: "\
CREATE TABLE hub_webhook_receipt (\
  hub_id TEXT NOT NULL, api_key_id TEXT NOT NULL, request_id TEXT NOT NULL, command TEXT NOT NULL, request_hash TEXT NOT NULL, \
  status TEXT NOT NULL DEFAULT 'processing', response_json TEXT, created_at TEXT NOT NULL, \
  completed_at TEXT, PRIMARY KEY (hub_id, api_key_id, request_id));\
CREATE TABLE hub_webhook_subscription (\
  id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, url TEXT NOT NULL, \
  events_json TEXT NOT NULL DEFAULT '[]', secret_encrypted TEXT NOT NULL, \
  status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', \
  last_delivery_at TEXT);\
CREATE INDEX IF NOT EXISTS ix_hub_webhook_subscription_hub \
  ON hub_webhook_subscription (hub_id, status);",
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
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        // Sesión legacy YA existente (BD que sobrevive a un update): sin la columna device_id.
        db.execute_batch(
            "INSERT INTO hub_session (token, user_id, created_at, expires_at) \
             VALUES ('legacy', 'u1', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();
        assert!(max_applied_version(&db).await.unwrap() >= 8, "v8 registrada");

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
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        // Usuario legacy YA existente (BD que sobrevive a un update): sin la columna email.
        db.execute_batch(
            "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at) \
             VALUES ('u-legacy', 'Ada', '', 'owner', 'cloud-1', 1, '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        apply(&db, "hub-test").await.unwrap();
        assert!(max_applied_version(&db).await.unwrap() >= 9, "v9 registrada");

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
}
