use crate::DbError;

/// Por qué falló al pedir el lock de migración.
#[derive(Debug)]
pub enum MigrationLockError {
    /// Otro arranque lo tiene y no lo soltó a tiempo. **No es un error transitorio que se reintente
    /// en bucle**: es la señal de que este arranque no debe seguir.
    Timeout { hub_id: String, waited_ms: u64 },
    Db(DbError),
}

impl std::fmt::Display for MigrationLockError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MigrationLockError::Timeout { hub_id, waited_ms } => write!(
                f,
                "no conseguí el lock de migración de '{hub_id}' en {waited_ms} ms: otro arranque \
                 del mismo hub lo tiene. No sigo: migrar en paralelo rompe el esquema."
            ),
            MigrationLockError::Db(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for MigrationLockError {}

impl From<DbError> for MigrationLockError {
    fn from(e: DbError) -> Self {
        MigrationLockError::Db(e)
    }
}

/// El lock tomado. **Se suelta al caer** — no hace falta llamar a nada.
///
/// Sostiene una **transacción propia** con `pg_advisory_xact_lock`, y ahí está todo el diseño:
///
/// - `pg_advisory_lock()` (el de sesión) sobre un **pool** es una trampa. sqlx coge una conexión,
///   ejecuta el lock y **devuelve la conexión al pool con el lock puesto**; el `unlock` posterior
///   sale por otra conexión y no libera nada, mientras la envenenada vuelve a circular. Con el lock
///   de transacción, vive y muere con ella.
/// - Un arranque que revienta a medias —panic, error, `?` a mitad— suelta la transacción, Postgres
///   la aborta y el lock se va con ella. **Nunca deja la base cerrada.**
/// - Retiene **una** conexión, no el pool: el resto del arranque sigue migrando por las demás.
pub struct MigrationLock {
    _tx: Option<sqlx::Transaction<'static, sqlx::Postgres>>,
}

impl MigrationLock {
    /// Un lock que no bloquea nada — para adaptadores donde no hay concurrencia que serializar
    /// (los fakes en memoria de los tests).
    pub fn noop() -> Self {
        Self { _tx: None }
    }

    /// Lo construye el adaptador que ya tiene la transacción con el lock puesto. El campo se queda
    /// privado: sacar la transacción de aquí soltaría el lock antes de tiempo, y esa es justo la
    /// clase de error que este tipo existe para hacer imposible.
    pub(crate) fn held(tx: sqlx::Transaction<'static, sqlx::Postgres>) -> Self {
        Self { _tx: Some(tx) }
    }
}

impl std::fmt::Debug for MigrationLock {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("MigrationLock")
    }
}

#[cfg(test)]
mod tests {
    // El lock que serializa el arranque que migra (hub#539).
    //
    // ## La trampa que estos tests existen para cazar
    //
    // `pg_advisory_lock()` es **de sesión**, y este adaptador habla con un **pool**. Tomarlo con un
    // `db.query("SELECT pg_advisory_lock(k)")` corriente parece funcionar y no funciona: sqlx coge una
    // conexión del pool, ejecuta, y **la devuelve al pool con el lock puesto**. El `unlock` posterior
    // sale por otra conexión y no libera nada — mientras tanto, esa conexión envenenada vuelve a
    // circular. En un test de una sola conexión eso pasa en verde.
    //
    // Por eso el guard sostiene una **transacción propia** con `pg_advisory_xact_lock`: el lock vive
    // y muere con ella, y soltarla —incluso por un panic— lo libera. El caso
    // `the_lock_really_blocks_a_second_boot` es el que distingue las dos implementaciones.

    use crate::DatabaseAdapter;
    use serde_json::json;


    /// Dos adaptadores contra **la misma** base, como los dos runtimes del solape blue/green.
    async fn two_adapters_on_one_database() -> (crate::PgAdapter, crate::PgAdapter) {
        crate::testutil::two_adapters_sharing_a_schema().await
    }

    #[tokio::test]
    async fn the_lock_really_blocks_a_second_boot() {
        let (first, second) = two_adapters_on_one_database().await;

        let held = first.migration_lock("hub-1", 5_000).await.expect("el primero lo coge");

        // El segundo NO puede cogerlo mientras el primero lo tenga. Con un lock de sesión mal hecho
        // esto pasaría: el lock estaría en una conexión del pool y nadie lo estaría reteniendo.
        let blocked = second.migration_lock("hub-1", 250).await;
        assert!(
            matches!(blocked, Err(super::MigrationLockError::Timeout { .. })),
            "el segundo arranque tiene que esperar, no colarse: {blocked:?}"
        );

        drop(held);

        // Y en cuanto el primero suelta, el segundo entra.
        second
            .migration_lock("hub-1", 5_000)
            .await
            .expect("soltado el lock, el segundo entra");
    }

    /// Dos hubs distintos **no** se estorban: la clave sale del `hub_id`.
    ///
    /// Sin esto, una base compartida serializaría el arranque de hubs que no tienen nada que ver — y
    /// con la flota entera actualizándose a la vez, eso es una cola.
    #[tokio::test]
    async fn different_hubs_do_not_wait_for_each_other() {
        let (first, second) = two_adapters_on_one_database().await;

        let _held = first.migration_lock("hub-1", 5_000).await.expect("hub-1 lo coge");

        second
            .migration_lock("hub-2", 250)
            .await
            .expect("otro hub no tiene por qué esperar");
    }

    /// **El que espera no se cuelga para siempre.**
    ///
    /// Colgarse sería peor que fallar: el contenedor se quedaría arrancando, `/readyz` nunca daría
    /// `UP`, y Swarm esperaría a que expire `start_period` para revertir — cuando el diagnóstico
    /// («no consigo el lock») estaba disponible desde el segundo uno.
    #[tokio::test]
    async fn waiting_gives_up_instead_of_hanging_forever() {
        let (first, second) = two_adapters_on_one_database().await;
        let _held = first.migration_lock("hub-1", 5_000).await.unwrap();

        let started = std::time::Instant::now();
        let outcome = second.migration_lock("hub-1", 300).await;

        assert!(matches!(outcome, Err(super::MigrationLockError::Timeout { .. })));
        assert!(
            started.elapsed() < std::time::Duration::from_secs(5),
            "se rindió tarde: {:?}",
            started.elapsed()
        );
    }

    /// Soltar el guard libera el lock **aunque nadie llame a nada**: va atado a su transacción.
    ///
    /// Es lo que hace que un arranque que revienta a medias no deje la base cerrada para siempre.
    #[tokio::test]
    async fn dropping_the_guard_releases_the_lock() {
        let (first, second) = two_adapters_on_one_database().await;

        {
            let _held = first.migration_lock("hub-1", 5_000).await.unwrap();
        } // sale de scope sin release() explícito

        second
            .migration_lock("hub-1", 2_000)
            .await
            .expect("el guard suelta el lock al caer");
    }

    /// Con el lock puesto, el resto del arranque **sigue funcionando** por el pool.
    ///
    /// El guard retiene UNA conexión; si retuviera el pool entero, el arranque se bloquearía a sí mismo.
    #[tokio::test]
    async fn the_rest_of_the_boot_keeps_working_while_the_lock_is_held() {
        let (first, _second) = two_adapters_on_one_database().await;
        let _held = first.migration_lock("hub-1", 5_000).await.unwrap();

        first
            .execute_batch("CREATE TABLE lock_probe (id BIGINT)")
            .await
            .expect("el arranque sigue pudiendo migrar mientras sostiene su propio lock");

        let mut params = crate::Params::new();
        params.insert("id".into(), json!(1));
        first
            .execute("INSERT INTO lock_probe (id) VALUES (:id)", &params)
            .await
            .expect("y escribir");
    }
}
