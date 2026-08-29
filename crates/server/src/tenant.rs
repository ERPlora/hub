//! Gateway multi-tenant compartido — el tier "cloud compartido" de ADR-0005 (hub#24).
//!
//! El `erplora-server` se despliega como **UN** servicio para **N** organizaciones (no un
//! contenedor por hub) que frontea las **Aurora por-org** (privadas). Es el hub cloud de **una**
//! org (Axum → su Aurora) generalizado a **N** orgs.
//!
//! Pieza central de este módulo: un **mapa de runtimes por organización**. Cada org tiene su
//! propio [`Runtime`] —que a su vez encapsula su propio `PgPool` (vía `PgAdapter`) **y** su
//! `hub_id`—, así que el aislamiento entre orgs es **estructural**: nunca se comparte conexión ni
//! adaptador entre orgs, y un token de la org A no tiene ningún camino hacia el pool de la org B.
//!
//! Resolución `org → runtime` (cada petición):
//!   1. La identidad de la petición (`hub_id`) sale de la auth ya existente (`X-Hub-Id` inyectado
//!      por el despliegue, no spoofable; ver `auth.rs`). En el tier compartido el gateway **mapea**
//!      ese `hub_id` a su organización y al DSN de su Aurora vía un [`OrgResolver`].
//!   2. Se busca/crea el [`Runtime`] de esa org en el mapa (lazy, con límite de pools).
//!   3. El handler ejecuta `execute_query`/`execute_command` sobre **ese** runtime: el gate de
//!      permisos, el scoping `hub_id` y `requires_primary`/`requires_cloud` siguen aplicándose
//!      **server-side** (los aporta el propio `Runtime`, no cambian aquí).
//!
//! What this module does **NOT** decide (still open — see [`EnvOrgResolver`]): the **secret/DSN
//! format per org** and **how the server discovers the orgs and their `database_name`**. ADR-0005
//! puts Django in the control plane (it provisions the org's DB and issues the token) but does not
//! close how the DSN reaches the gateway. That is parameterized behind the [`OrgResolver`] trait,
//! with a minimal environment-backed resolver ([`EnvOrgResolver`]) standing in until the real
//! mechanism is chosen.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use erplora_db::PgAdapter;
use erplora_runtime::Runtime;
use tokio::sync::RwLock as RuntimeLock;

use crate::state::SharedRuntime;

/// Identificador de organización (frontera de datos en ERPlora: una BD por org, §2.5). Newtype
/// sobre `String` para no confundirlo con un `hub_id` (varios hubs comparten la BD de una org).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct OrgId(pub String);

impl OrgId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Descriptor de la BD de una organización: a qué org pertenece un `hub_id` y con qué DSN se
/// conecta su Aurora por-org. Lo produce el [`OrgResolver`].
#[derive(Debug, Clone)]
pub struct OrgDescriptor {
    /// Organización dueña del `hub_id` (frontera de datos).
    pub org_id: OrgId,
    /// DSN Postgres de la Aurora de **esta** org (`postgres://user:pass@host:5432/org_abc…`).
    /// Secreto: vive solo aquí (server-side), nunca viaja al navegador.
    pub dsn: String,
}

/// Errores del gateway multi-tenant. Se mapean a `4xx/5xx` en los handlers.
#[derive(Debug, thiserror::Error)]
pub enum TenantError {
    /// El `hub_id` de la petición no pertenece a ninguna org conocida → **se rechaza** (no se cae a
    /// ninguna BD por defecto). Es la primera barrera anti-cross-org.
    #[error("organización desconocida para hub_id={0}")]
    UnknownOrg(String),
    /// Se alcanzó el límite de pools por proceso (back-pressure): no se crea uno nuevo.
    #[error("límite de pools por organización alcanzado ({0})")]
    PoolLimit(usize),
    /// Fallo al abrir el pool de la org (DSN inválido, Aurora caída…).
    #[error("no se pudo conectar a la BD de la org: {0}")]
    Connect(#[from] erplora_db::DbError),
}

/// Resuelve `hub_id → OrgDescriptor` (org + DSN). Es el **seam** donde entra el mecanismo real de
/// descubrimiento de orgs (plano de control de Django, Secrets Manager, env…), que es **decisión
/// del humano**. El gateway solo necesita: dado el `hub_id` (no spoofable) de la petición, ¿de qué
/// org es y cuál es el DSN de su Aurora? `None` ⇒ org desconocida ⇒ la petición se rechaza.
pub trait OrgResolver: Send + Sync {
    fn resolve(&self, hub_id: &str) -> Option<OrgDescriptor>;
}

/// Resolvedor **mínimo** por entorno (placeholder del mecanismo real). Lee un mapa estático
/// `hub_id → (org_id, dsn)` cargado al arrancar. Pensado para tests y un primer despliegue; **no**
/// es el sistema de descubrimiento definitivo.
///
/// OPEN: how the gateway discovers the orgs and their `database_name`/DSN. The options ADR-0005
/// leaves open (Django in the control plane): (a) a Django control endpoint the gateway queries
/// and caches (`GET /api/v1/orgs/{hub_id}/db/` → short-lived signed DSN); (b) Secrets Manager per
/// org (`erplora/org/{org_id}/dsn`); (c) per-org env at boot. The exact secret/DSN format and the
/// refresh path (credential rotation) are part of that same decision; until it is taken, this is
/// parameterized behind [`OrgResolver`].
pub struct EnvOrgResolver {
    /// `hub_id → descriptor`. Inmutable tras construcción (un refresco vivo sería otro trabajo).
    map: HashMap<String, OrgDescriptor>,
}

impl EnvOrgResolver {
    /// Construye desde un mapa explícito (tests / arranque controlado).
    pub fn new(map: HashMap<String, OrgDescriptor>) -> Self {
        Self { map }
    }
}

impl OrgResolver for EnvOrgResolver {
    fn resolve(&self, hub_id: &str) -> Option<OrgDescriptor> {
        self.map.get(hub_id).cloned()
    }
}

/// Límite por defecto de pools (orgs) cacheados a la vez en un proceso. Conservador: ADR-0005 dice
/// "un solo servicio para muchas orgs", pero cada pool consume conexiones a su Aurora; el techo real
/// lo fija el humano por capacidad del proceso. Configurable por `HUB_MAX_ORG_POOLS`.
pub const DEFAULT_MAX_ORG_POOLS: usize = 256;

/// Fábrica de runtimes por org. Permite inyectar un constructor en tests (dos SQLite simulando dos
/// orgs) sin tocar Postgres real. En producción el factory por defecto abre un [`PgAdapter`].
pub type RuntimeFactory = Arc<
    dyn Fn(&OrgDescriptor) -> futures_util::future::BoxFuture<'static, Result<Runtime, TenantError>>
        + Send
        + Sync,
>;

/// Mapa de runtimes por organización + resolución `hub_id → org → runtime`.
///
/// Cada entrada es un [`SharedRuntime`] (mismo patrón que el `AppState` single-tenant: lectores en
/// paralelo, escritor exclusivo — hub#978). El lock es por-org, así que orgs distintas no se
/// bloquean entre sí. El mapa va tras un `RwLock` (lecturas concurrentes baratas: el caso común es
/// "el pool ya existe").
pub struct TenantRouter {
    resolver: Arc<dyn OrgResolver>,
    pools: RwLock<HashMap<OrgId, SharedRuntime>>,
    factory: RuntimeFactory,
    max_pools: usize,
}

impl TenantRouter {
    /// Crea el router con el factory de producción (abre un [`PgAdapter`] por org). El `Runtime` de
    /// cada org se fija con **su** `hub_id`… ojo: en BD compartida por org, el `hub_id` concreto de
    /// la fila lo aporta el `RequestContext` de cada petición (auth), no el runtime; el `hub_id` del
    /// runtime solo scopea el estado de módulos/sistema. Por eso el factory por defecto siembra el
    /// runtime con el `hub_id` de la petición que lo creó — ver [`resolve_runtime`].
    pub fn new(resolver: Arc<dyn OrgResolver>) -> Self {
        Self::with_factory(resolver, default_pg_factory(), max_pools_from_env())
    }

    /// Variante con factory + límite explícitos (tests: factory SQLite de dos orgs simuladas).
    pub fn with_factory(
        resolver: Arc<dyn OrgResolver>,
        factory: RuntimeFactory,
        max_pools: usize,
    ) -> Self {
        Self {
            resolver,
            pools: RwLock::new(HashMap::new()),
            factory,
            max_pools,
        }
    }

    /// Nº de pools (orgs) activos ahora mismo.
    pub fn pool_count(&self) -> usize {
        self.pools.read().map(|m| m.len()).unwrap_or(0)
    }

    /// Resuelve el [`Runtime`] de la org dueña del `hub_id` de la petición, creando su pool bajo
    /// demanda. **Rechaza** (`UnknownOrg`) si el `hub_id` no mapea a ninguna org → un token cuyo
    /// `hub_id` no esté registrado jamás toca una BD. Como cada org tiene su propio runtime/pool, un
    /// `hub_id` de la org A solo puede resolver al runtime de A: el acceso cruzado es imposible por
    /// construcción (no hay ruta de A al pool de B).
    pub async fn resolve_runtime(&self, hub_id: &str) -> Result<SharedRuntime, TenantError> {
        let desc = self
            .resolver
            .resolve(hub_id)
            .ok_or_else(|| TenantError::UnknownOrg(hub_id.to_string()))?;

        // Camino rápido: el pool de la org ya existe (lectura compartida).
        if let Some(rt) = self
            .pools
            .read()
            .ok()
            .and_then(|m| m.get(&desc.org_id).cloned())
        {
            return Ok(rt);
        }

        // Camino lento: crear el pool de la org (escritura exclusiva). Re-chequea por si otra tarea
        // lo creó mientras esperábamos el lock (doble-check), y aplica el límite de pools.
        let rt = (self.factory)(&desc).await?;
        let rt = Arc::new(RuntimeLock::new(rt));
        let mut map = self.pools.write().expect("pools RwLock envenenado");
        if let Some(existing) = map.get(&desc.org_id) {
            return Ok(existing.clone());
        }
        if map.len() >= self.max_pools {
            return Err(TenantError::PoolLimit(self.max_pools));
        }
        map.insert(desc.org_id.clone(), rt.clone());
        Ok(rt)
    }
}

/// Lee el límite de pools del entorno (`HUB_MAX_ORG_POOLS`), con [`DEFAULT_MAX_ORG_POOLS`] de
/// fallback.
fn max_pools_from_env() -> usize {
    std::env::var("HUB_MAX_ORG_POOLS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_MAX_ORG_POOLS)
}

/// Factory de producción: abre un [`PgAdapter`] (un `PgPool`) contra el DSN de la org y construye un
/// [`Runtime`] sembrado con el `hub_id` del descriptor de la org. El tuning del pool (max_connections
/// por plan, TLS require, timeouts de failover de Aurora) está pendiente en `crates/db` (§8).
fn default_pg_factory() -> RuntimeFactory {
    Arc::new(|desc: &OrgDescriptor| {
        let dsn = desc.dsn.clone();
        let hub_id = desc.org_id.0.clone();
        Box::pin(async move {
            let db = PgAdapter::connect(&dsn).await?;
            // El `hub_id` del runtime scopea el estado de módulos/sistema; el `hub_id` de cada fila
            // de negocio lo aporta el `RequestContext` de la petición (auth, no spoofable).
            Ok(Runtime::with_hub_id(Box::new(db), hub_id))
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;
    use erplora_runtime::RequestContext;
    use serde_json::{json, Map};

    /// Factory de test: cada org tiene su **propio** SQLite en memoria (dos pools independientes)
    /// → simula dos Aurora por-org sin Postgres real. La tabla `t` lleva `hub_id` (contrato §2.5).
    fn sqlite_factory() -> RuntimeFactory {
        Arc::new(|desc: &OrgDescriptor| {
            let hub_id = desc.org_id.0.clone();
            Box::pin(async move {
                let db = fresh_db().await;
                let rt = Runtime::with_hub_id(Box::new(db), hub_id);
                Ok(rt)
            })
        })
    }

    fn two_org_resolver() -> Arc<dyn OrgResolver> {
        let mut map = HashMap::new();
        // hub-a1 pertenece a org-a; hub-b1 a org-b. El DSN es irrelevante para el factory SQLite.
        map.insert(
            "hub-a1".to_string(),
            OrgDescriptor {
                org_id: OrgId("org-a".into()),
                dsn: "sqlite::memory:".into(),
            },
        );
        map.insert(
            "hub-b1".to_string(),
            OrgDescriptor {
                org_id: OrgId("org-b".into()),
                dsn: "sqlite::memory:".into(),
            },
        );
        Arc::new(EnvOrgResolver::new(map))
    }

    /// Crea la tabla `t` (con `hub_id`) en el runtime y registra una fila marcada con `marker`.
    async fn seed(rt: &SharedRuntime, hub_id: &str, marker: &str) {
        let rt = rt.read().await;
        let db = rt.db_for_test();
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY, hub_id TEXT, marker TEXT);",
        )
        .await
        .unwrap();
        let mut p = Map::new();
        p.insert("id".into(), json!(marker));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("marker".into(), json!(marker));
        db.execute(
            "INSERT INTO t (id, hub_id, marker) VALUES (:id, :hub_id, :marker)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn rows_for(rt: &SharedRuntime, hub_id: &str) -> Vec<String> {
        let rt = rt.read().await;
        let db = rt.db_for_test();
        let mut p = Map::new();
        p.insert("hub_id".into(), json!(hub_id));
        let res = db
            .query("SELECT marker FROM t WHERE hub_id = :hub_id", &p)
            .await
            .unwrap();
        res.rows
            .iter()
            .map(|r| r["marker"].as_str().unwrap().to_string())
            .collect()
    }

    /// Criterio de aceptación 1: un `hub_id` de org A solo accede a la BD de A; un intento con un
    /// `hub_id` desconocido se **rechaza** (no se cae a ninguna BD).
    #[tokio::test]
    async fn org_a_token_never_touches_org_b_db() {
        let router = TenantRouter::with_factory(two_org_resolver(), sqlite_factory(), 32);

        // Dos orgs servidas por el MISMO router (un solo proceso) → criterio de aceptación 3.
        let rt_a = router.resolve_runtime("hub-a1").await.unwrap();
        let rt_b = router.resolve_runtime("hub-b1").await.unwrap();
        assert_eq!(router.pool_count(), 2, "un pool por org");

        // Cada org siembra su propia fila en su propia BD.
        seed(&rt_a, "hub-a1", "dato-de-A").await;
        seed(&rt_b, "hub-b1", "dato-de-B").await;

        // La BD de A solo ve datos de A; la de B solo los de B. Pools independientes ⇒ aislamiento.
        assert_eq!(
            rows_for(&rt_a, "hub-a1").await,
            vec!["dato-de-A".to_string()]
        );
        assert_eq!(
            rows_for(&rt_b, "hub-b1").await,
            vec!["dato-de-B".to_string()]
        );
        // El dato de B NO existe en la BD de A (ni con su propio hub_id ni con el de B).
        assert!(
            rows_for(&rt_a, "hub-b1").await.is_empty(),
            "A no debe ver filas de B"
        );

        // Un hub_id no registrado se rechaza: jamás llega a una BD.
        let cross = router.resolve_runtime("hub-desconocido").await;
        assert!(matches!(cross, Err(TenantError::UnknownOrg(_))));
    }

    /// Resolver es estable: dos peticiones de la misma org comparten el MISMO runtime/pool (no se
    /// abre un pool nuevo por petición). Aísla el caché del mapa de pools.
    #[tokio::test]
    async fn same_org_reuses_pool() {
        let router = TenantRouter::with_factory(two_org_resolver(), sqlite_factory(), 32);
        let r1 = router.resolve_runtime("hub-a1").await.unwrap();
        let r2 = router.resolve_runtime("hub-a1").await.unwrap();
        assert!(Arc::ptr_eq(&r1, &r2), "misma org ⇒ mismo pool cacheado");
        assert_eq!(router.pool_count(), 1);
    }

    /// El límite de pools aplica back-pressure: con un techo de 1, la segunda org distinta se
    /// rechaza con `PoolLimit` (no se desborda el proceso).
    #[tokio::test]
    async fn pool_limit_is_enforced() {
        let router = TenantRouter::with_factory(two_org_resolver(), sqlite_factory(), 1);
        router.resolve_runtime("hub-a1").await.unwrap();
        let second = router.resolve_runtime("hub-b1").await;
        assert!(matches!(second, Err(TenantError::PoolLimit(1))));
    }

    /// El gate de permisos sigue siendo server-side sobre el runtime resuelto: el `RequestContext`
    /// con el `hub_id` de la org A scopea la query a A. (El gate real de permisos por rol se prueba
    /// en `tests/http.rs::permission_denied_is_403`; aquí confirmamos que el contexto se construye
    /// con el hub_id correcto sobre el runtime correcto.)
    #[tokio::test]
    async fn request_context_scopes_to_resolved_org() {
        let router = TenantRouter::with_factory(two_org_resolver(), sqlite_factory(), 32);
        let rt_a = router.resolve_runtime("hub-a1").await.unwrap();
        let ctx = RequestContext::new("hub-a1".to_string(), "u1".to_string(), Vec::<String>::new());
        assert_eq!(ctx.hub_id, "hub-a1");
        // El runtime resuelto es el de la org A (su hub_id de despliegue).
        assert_eq!(rt_a.read().await.hub_id(), "org-a");
    }
}
