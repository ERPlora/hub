//! **Las normas que escribe el CLIENTE** (ERPlora/hub#1701, ADR-0476).
//!
//! Doc de diseño: `architecture/hub/policies.md`. El orden as-built de los gates del embudo vive
//! en `architecture/hub/runtime-dispatcher.md` §2.0 y **no se copia aquí** — se referencia, que es
//! justo la guardia anti-regresión que architecture#733 puso después de que ADR-0476 lo escribiese
//! de memoria y lo publicase invertido.
//!
//! # Las tres piezas
//!
//! 1. **El módulo declara el punto de control**, por convención de carpeta:
//!    `<módulo>/policies/<nombre>.checkpoint.json`. Ni una clave nueva del manifest: la raíz es
//!    `additionalProperties: false` (ADR-0286) y una clave nueva le pondría suelo de versión de hub
//!    a todo módulo que la declarase (mismo razonamiento que `flows/`, ADR-0463).
//! 2. **El dueño escribe la norma** en `_policy`, con el lenguaje de condiciones **ya congelado**
//!    de los flujos ([`crate::flows::Condition`], nueve operadores en AND, conjunto cerrado). No se
//!    estrena DSL.
//! 3. **El runtime la aplica** en un punto exacto del embudo, [`enforce`], llamado desde
//!    [`crate::commands::execute_at`] después del bloque de schema y antes de la bifurcación de
//!    tier.
//!
//! # Por qué [`enforce`] NO recibe la base de datos
//!
//! No es un olvido: es la guarda de **coste acotado** escrita en el sistema de tipos. El gate corre
//! en **cada** command, y una lectura por command se paga en cada venta —además de retener el
//! guard compartido del runtime, que es justo (`crates/server/src/boot.rs`), así que un lector lento
//! deja esperando al escritor pendiente y a los lectores de detrás. Que la firma no tenga `db` hace
//! **imposible** añadir I/O aquí de paso; las filas llegan de [`PolicyIndex`], un mapa en memoria
//! que se refresca al arrancar y en cada escritura del CRUD.
//!
//! # Fallo CERRADO, y por qué no se hereda el del vecino
//!
//! `protects` —el gate de al lado— degrada **abierto**, y para su caso es correcto: una caja que
//! deja de cobrar por una lectura rota es peor fallo que una venta que se cuela. Una política es lo
//! contrario: existe para **impedir**, así que degradarla abierta en silencio la convierte en
//! decoración. Aquí lo que no se puede evaluar **DENIEGA** (`policies.md` §6.1).
//!
//! 🔴 Y el hecho ausente se detecta **comprobando presencia ANTES de evaluar**, nunca leyendo el
//! resultado de la evaluación: [`crate::flows::Condition::matches`] devuelve un `bool` pelado y un
//! camino ausente da `false`, **el mismo valor** que «la condición no casaba». Un gate que actuase
//! sobre ese `bool` no podría distinguirlos, y como una política es «si casa → `block`», el hecho
//! ausente haría que **no dispare y el command pase**: fail-open mudo por la puerta de atrás.
use std::collections::{BTreeMap, HashMap};
use std::path::Path;
use std::sync::RwLock;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::resolve_path;
use crate::flows::Condition;
use crate::manifest::Manifest;
use crate::registry::{new_id, now_rfc3339};

/// Sufijo de los documentos de la carpeta `policies/`.
const CHECKPOINT_SUFFIX: &str = ".checkpoint.json";

/// El documento no se puede leer del paquete.
pub const DISCARD_UNREADABLE_DOCUMENT: &str = "unreadable_document";
/// El documento no se lee como JSON, o sus campos no tienen la forma del contrato.
pub const DISCARD_INVALID_DOCUMENT: &str = "invalid_document";
/// El `command` no lo declara el manifest de este módulo.
pub const DISCARD_COMMAND_NOT_DECLARED: &str = "command_not_declared";
/// El `command` es de OTRO módulo. Un módulo solo habla en su namespace (hub#139, hub#351); parar
/// los commands de otro ya tiene su puerta declarada y consentida, y es `protects` (hub#775).
pub const DISCARD_FOREIGN_COMMAND: &str = "foreign_command";
/// El command no declara schema de payload, así que no hay `facts` que pueda aportar.
pub const DISCARD_COMMAND_WITHOUT_SCHEMA: &str = "command_without_schema";
/// Un `fact` cuya raíz el schema del command no declara. **Esta es la válvula** que hace segura la
/// denegación fail-closed del gate: se ve al instalar, no en mitad de una venta.
pub const DISCARD_FACT_NOT_DECLARED: &str = "fact_not_declared";
/// Un `fact` que no es un camino punteado del lenguaje congelado (`lines[].x`, `a..b`, vacío).
pub const DISCARD_INVALID_FACT_PATH: &str = "invalid_fact_path";
/// El checkpoint no declara ningún `fact`: no hay nada sobre lo que razonar.
pub const DISCARD_NO_FACTS: &str = "no_facts";
/// Un `outcome` fuera del vocabulario cerrado (`block`, `elevate:<permiso>`).
pub const DISCARD_UNKNOWN_OUTCOME: &str = "unknown_outcome";
/// El checkpoint no declara ningún `outcome`.
pub const DISCARD_NO_OUTCOMES: &str = "no_outcomes";
/// Otro checkpoint del módulo ya se enganchó a ese command.
pub const DISCARD_DUPLICATE_COMMAND: &str = "duplicate_command";

/// Un punto de control declarado por un módulo: dónde puede el dueño poner una norma, y con qué
/// datos puede razonar.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct PolicyCheckpoint {
    /// `<módulo>/<nombre>` — el nombre estable con el que una fila de `_policy` lo referencia. La
    /// misma forma que `_flow.template_ref` (v60), y por el mismo motivo: es lo que el módulo ya
    /// sabe de sí mismo y no cambia entre releases suyas.
    pub id: String,
    pub module_id: String,
    /// El command que este checkpoint gatea. Del propio módulo, siempre.
    pub command: String,
    /// Los hechos con los que se puede razonar: caminos punteados dentro del payload del command,
    /// **ya validado, defaulteado y coercionado** (el gate corre después de ese bloque).
    pub facts: Vec<String>,
    /// El vocabulario que este checkpoint admite. `block` · `elevate:<permiso>`.
    pub outcomes: Vec<String>,
}

/// Lo que la carpeta `policies/` aportó y lo que **no**, con su motivo (mismo contrato que
/// [`crate::manifest::FlowTemplateScan`], hub#1649: best-effort no es mudo).
#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct CheckpointScan {
    pub checkpoints: Vec<PolicyCheckpoint>,
    pub discards: Vec<CheckpointDiscard>,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct CheckpointDiscard {
    /// El nombre del documento (el trozo antes de `.checkpoint.json`).
    pub name: String,
    pub code: String,
    pub detail: String,
}

impl CheckpointScan {
    pub fn is_empty(&self) -> bool {
        self.checkpoints.is_empty() && self.discards.is_empty()
    }

    fn discard(&mut self, name: &str, code: &'static str, detail: String) {
        self.discards.push(CheckpointDiscard {
            name: name.to_string(),
            code: code.to_string(),
            detail,
        });
    }
}

/// El documento tal cual viaja en el paquete.
#[derive(serde::Deserialize)]
struct CheckpointDoc {
    command: String,
    #[serde(default)]
    facts: Vec<String>,
    #[serde(default)]
    outcomes: Vec<String>,
}

/// Lee `<dir>/policies/*.checkpoint.json` y devuelve lo que este hub va a ofrecer.
///
/// **Best-effort y no mudo**: un paquete de terceros roto no puede impedir que el hub levante (esto
/// corre en cada arranque por `rehydrate_installed`), pero lo descartado sale con su código.
///
/// El resultado va **ordenado por nombre de documento** para que dos arranques den lo mismo: de ahí
/// depende cuál de dos checkpoints sobre el mismo command sobrevive.
pub fn scan_checkpoints(dir: &Path, manifest: &Manifest) -> CheckpointScan {
    let mut scan = CheckpointScan::default();
    let Ok(entries) = std::fs::read_dir(dir.join("policies")) else {
        return scan;
    };

    // 1ª pasada: recoger los documentos por nombre. `BTreeMap` = orden estable por bytes, que es lo
    // que hace determinista el desempate de `DISCARD_DUPLICATE_COMMAND`.
    let mut docs: BTreeMap<String, std::path::PathBuf> = BTreeMap::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if let Some(stem) = name.strip_suffix(CHECKPOINT_SUFFIX) {
            if !stem.is_empty() {
                docs.insert(stem.to_string(), path);
            }
        }
    }

    // Cache de los schemas ya leídos: dos checkpoints del mismo command no releen el fichero.
    let mut schema_props: HashMap<String, Option<Vec<String>>> = HashMap::new();
    let mut taken: HashMap<String, String> = HashMap::new();

    for (name, path) in docs {
        let Ok(text) = std::fs::read_to_string(&path) else {
            scan.discard(
                &name,
                DISCARD_UNREADABLE_DOCUMENT,
                format!("`{name}{CHECKPOINT_SUFFIX}` no se puede leer del paquete"),
            );
            continue;
        };
        let doc = match serde_json::from_str::<CheckpointDoc>(&text) {
            Ok(doc) => doc,
            Err(err) => {
                scan.discard(
                    &name,
                    DISCARD_INVALID_DOCUMENT,
                    format!(
                        "`{name}{CHECKPOINT_SUFFIX}` no tiene la forma del contrato \
                         (`command`, `facts`, `outcomes`): {err}"
                    ),
                );
                continue;
            }
        };

        // (1) Namespace ANTES que nada: el `command` de otro módulo no es cosa de este documento,
        // y decirle «no lo declaras» sería mandarle a mirar el fichero equivocado.
        if !is_own_command(&manifest.id, &doc.command) {
            scan.discard(
                &name,
                DISCARD_FOREIGN_COMMAND,
                format!(
                    "`{}` es un command de otro módulo. Un checkpoint solo gatea commands de \
                     `{}`; para parar los de otro está `protects`, que el módulo protegido declara",
                    doc.command, manifest.id
                ),
            );
            continue;
        }
        let Some(command) = manifest.commands.get(&doc.command) else {
            scan.discard(
                &name,
                DISCARD_COMMAND_NOT_DECLARED,
                format!("`{}` no es un command de este manifest", doc.command),
            );
            continue;
        };

        // (2) El vocabulario de consecuencias, cerrado.
        if doc.outcomes.is_empty() {
            scan.discard(
                &name,
                DISCARD_NO_OUTCOMES,
                "un checkpoint sin `outcomes` no admite ninguna norma".to_string(),
            );
            continue;
        }
        if let Some(bad) = doc.outcomes.iter().find(|o| Outcome::parse(o).is_none()) {
            scan.discard(
                &name,
                DISCARD_UNKNOWN_OUTCOME,
                format!(
                    "`{bad}` no es una consecuencia del vocabulario cerrado: `block` o \
                     `elevate:<permiso>`"
                ),
            );
            continue;
        }

        // (3) Los hechos. La válvula de la denegación fail-closed: si el command no puede
        // aportarlos, se ve AQUÍ —al instalar— y no en mitad de una venta.
        if doc.facts.is_empty() {
            scan.discard(
                &name,
                DISCARD_NO_FACTS,
                "un checkpoint sin `facts` no da nada sobre lo que razonar".to_string(),
            );
            continue;
        }
        if let Some(bad) = doc.facts.iter().find(|f| !is_plain_path(f)) {
            scan.discard(
                &name,
                DISCARD_INVALID_FACT_PATH,
                format!(
                    "`{bad}` no es un camino punteado del lenguaje congelado de los flujos. El \
                     gate resuelve con `resolve_path`, que no entiende colecciones (`x[].y`): un \
                     hecho así no se podría leer NUNCA y la política denegaría siempre"
                ),
            );
            continue;
        }
        let props = schema_props
            .entry(doc.command.clone())
            .or_insert_with(|| command.schema.as_deref().and_then(|rel| schema_roots(dir, rel)));
        let Some(props) = props.as_ref() else {
            scan.discard(
                &name,
                DISCARD_COMMAND_WITHOUT_SCHEMA,
                format!(
                    "`{}` no declara un schema de payload legible, así que no hay `facts` que el \
                     command pueda aportar",
                    doc.command
                ),
            );
            continue;
        };
        if let Some(bad) = doc
            .facts
            .iter()
            .find(|f| !props.iter().any(|p| p == fact_root(f)))
        {
            scan.discard(
                &name,
                DISCARD_FACT_NOT_DECLARED,
                format!(
                    "`{bad}`: el schema de `{}` no declara `{}`. El gate DENIEGA si al ejecutar \
                     falta un hecho declarado, así que un hecho que el command no puede aportar se \
                     rechaza aquí y no en mitad de una venta",
                    doc.command,
                    fact_root(bad)
                ),
            );
            continue;
        }

        // (4) Un command, un gate. Si no, qué norma se aplica dependería del orden del directorio.
        if let Some(first) = taken.get(&doc.command) {
            scan.discard(
                &name,
                DISCARD_DUPLICATE_COMMAND,
                format!(
                    "`{}` ya lo gatea `{first}`. Dos checkpoints sobre el mismo command harían que \
                     la norma aplicada dependiese del orden del sistema de ficheros",
                    doc.command
                ),
            );
            continue;
        }
        taken.insert(doc.command.clone(), name.clone());
        scan.checkpoints.push(PolicyCheckpoint {
            id: format!("{}/{}", manifest.id, name),
            module_id: manifest.id.clone(),
            command: doc.command,
            facts: doc.facts,
            outcomes: doc.outcomes,
        });
    }
    scan
}

/// ¿`command` pertenece al namespace de `module_id`? Mismo criterio que el resto del kernel: el
/// nombre de un command empieza por el id de su módulo y un punto.
fn is_own_command(module_id: &str, command: &str) -> bool {
    command
        .strip_prefix(module_id)
        .is_some_and(|rest| rest.starts_with('.'))
}

/// La raíz de un camino punteado: `order.total` → `order`.
fn fact_root(fact: &str) -> &str {
    fact.split('.').next().unwrap_or(fact)
}

/// ¿Es un camino punteado que [`resolve_path`] sabe resolver? Sin segmentos vacíos y sin nada que
/// no sea una clave de objeto (los índices y las colecciones no los entiende el lenguaje).
fn is_plain_path(path: &str) -> bool {
    !path.is_empty()
        && path.split('.').all(|s| {
            !s.is_empty()
                && s.chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
        })
}

/// Las propiedades de primer nivel del JSON Schema de un command. `None` si no hay schema legible o
/// si no declara `properties` — en los dos casos no hay nada contra lo que validar los `facts`.
fn schema_roots(dir: &Path, rel: &str) -> Option<Vec<String>> {
    let text = std::fs::read_to_string(dir.join(rel)).ok()?;
    let doc: Json = serde_json::from_str(&text).ok()?;
    let props = doc.get("properties")?.as_object()?;
    if props.is_empty() {
        return None;
    }
    Some(props.keys().cloned().collect())
}

/// La consecuencia que el dueño elige. **Vocabulario cerrado**: uno desconocido no se adivina.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    /// No dejar. Sale por el canal de errores de dominio (ADR-0205) con el mensaje del dueño.
    Block,
    /// Pedírselo al encargado. **Este core todavía no lo ejecuta** (hub#1708): se reconoce para que
    /// un checkpoint que lo declare no pierda su `block`, y escribir una política así se rechaza.
    Elevate(String),
}

impl Outcome {
    pub fn parse(raw: &str) -> Option<Self> {
        if raw == "block" {
            return Some(Outcome::Block);
        }
        raw.strip_prefix("elevate:")
            .filter(|p| !p.is_empty())
            .map(|p| Outcome::Elevate(p.to_string()))
    }

    pub fn as_str(&self) -> String {
        match self {
            Outcome::Block => "block".to_string(),
            Outcome::Elevate(p) => format!("elevate:{p}"),
        }
    }
}

/// `warn` avisa; `enforce` impide. La rampa obligatoria antes de poner una norma en vigor — lo que
/// Stripe Radar llama *Review*, y por el mismo motivo: una norma que bloquea mal en un TPV **para
/// la caja**, y el dueño la escribió sin poder probarla contra su día real.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Warn,
    Enforce,
}

impl Mode {
    pub fn parse(raw: &str) -> Option<Self> {
        match raw {
            "warn" => Some(Mode::Warn),
            "enforce" => Some(Mode::Enforce),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Mode::Warn => "warn",
            Mode::Enforce => "enforce",
        }
    }
}

/// Una norma del dueño tal y como está guardada, lista para evaluarse **sin tocar la BD**.
///
/// No lleva los `facts`: esos son del **checkpoint**, y el checkpoint vive en el paquete del
/// módulo. Leerlos del Registry en el momento de aplicar —en vez de congelarlos aquí al cargar—
/// es lo que hace que desinstalar el módulo deje de aplicar sus normas y reinstalarlo las vuelva a
/// poner en vigor, sin que nadie tenga que acordarse de refrescar nada.
#[derive(Debug, Clone)]
pub struct ActivePolicy {
    pub id: String,
    pub hub_id: String,
    pub checkpoint: String,
    /// `None` = la condición guardada no se puede leer con este core → **deniega** (fail-closed).
    pub condition: Option<Condition>,
    /// `None` = la consecuencia guardada no la sabe ejecutar este core → **deniega**.
    pub outcome: Option<Outcome>,
    pub message: String,
    pub mode: Mode,
}

/// Techo de normas por punto de control (guarda de **coste acotado**). El gate compara en memoria,
/// pero la comparación sigue siendo trabajo por command: sin techo, un hub con cien normas sobre
/// `sales.complete_sale` las paga en cada venta.
pub const MAX_POLICIES_PER_CHECKPOINT: usize = 20;

/// El índice en memoria del que lee [`enforce`]: `checkpoint → normas activas`.
///
/// Vive en el [`crate::registry::Registry`] por el mismo motivo por el que vive ahí `demo_hub`: es
/// la única autoridad que llega a `commands::execute_at` por **todos** los caminos (HTTP, API
/// pública, asistente, relay del outbox, scheduler) y que ningún llamador puede fabricar. Un
/// parámetro más de la firma sería una etiqueta que la próxima puerta nueva podría olvidarse de
/// poner, y olvidarla aquí es dejar el gate abierto.
///
/// 🔴 **Está indexado por CHECKPOINT y no por command, y eso no es un detalle.** Con un índice por
/// command, el mapa dependería de dos cosas que cambian por caminos distintos —las filas de
/// `_policy` y los módulos instalados—, así que habría que reconstruirlo también en `install`,
/// `update`, `activate`, `deactivate`, `uninstall` y la re-hidratación del arranque: **ocho sitios**
/// donde olvidarse de una línea deja normas sin aplicar sin decir nada. Indexado por checkpoint solo
/// depende de las filas, así que se refresca donde las filas cambian (el arranque y cada escritura
/// del CRUD) y el resto lo resuelve el Registry en el momento de aplicar.
#[derive(Debug, Default)]
pub struct PolicyIndex {
    by_checkpoint: RwLock<HashMap<String, Vec<ActivePolicy>>>,
}

impl PolicyIndex {
    /// Sustituye el índice entero. Lo llama el arranque y **cada escritura del CRUD**: una norma que
    /// el dueño acaba de guardar tiene que estar en vigor en la siguiente venta, no en el próximo
    /// reinicio.
    pub fn replace(&self, by_checkpoint: HashMap<String, Vec<ActivePolicy>>) {
        match self.by_checkpoint.write() {
            Ok(mut guard) => *guard = by_checkpoint,
            // Un `RwLock` envenenado significa que un hilo entró en pánico con el guard cogido. No
            // hay estado que salvar aquí —el índice se reconstruye entero— así que se recupera en
            // vez de propagar el pánico al arranque.
            Err(poisoned) => *poisoned.into_inner() = by_checkpoint,
        }
    }

    /// Las normas de un punto de control. Vacío = no hay gate y no se paga nada.
    fn for_checkpoint<T>(&self, checkpoint: &str, f: impl FnOnce(&[ActivePolicy]) -> T) -> T {
        let guard = match self.by_checkpoint.read() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        f(guard.get(checkpoint).map(Vec::as_slice).unwrap_or(&[]))
    }

    /// Cuántas normas hay en vigor en total. Para `/readyz` y los tests; no está en el camino
    /// caliente.
    pub fn len(&self) -> usize {
        let guard = match self.by_checkpoint.read() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        guard.values().map(Vec::len).sum()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Código de dominio (ADR-0205) de una orden que una norma del negocio **impide**. Estable y
/// namespaced; el texto que lee la persona es el que escribió el dueño y viaja en `message`.
pub const ERR_BLOCKED: &str = "policy.blocked";
/// Falta un hecho que el checkpoint declara. **Deniega** — ver el §6.1 del doc.
pub const ERR_FACT_MISSING: &str = "policy.fact_missing";
/// La norma guardada nombra una consecuencia que este core no sabe ejecutar (p. ej. `elevate:` en
/// un hub que rodó atrás). **Deniega**: una política que no se puede aplicar no se ignora.
pub const ERR_OUTCOME_NOT_AVAILABLE: &str = "policy.outcome_not_available";
/// La condición guardada no se puede leer con este core. **Deniega**, por lo mismo.
pub const ERR_CONDITION_UNREADABLE: &str = "policy.condition_unreadable";

// ── Códigos de la puerta de ESCRITURA (el CRUD) ───────────────────────────────────────────────
/// No hay ninguna norma con ese id en este hub.
pub const ERR_NOT_FOUND: &str = "policy.not_found";
/// El punto de control ya tiene [`MAX_POLICIES_PER_CHECKPOINT`] normas.
pub const ERR_TOO_MANY: &str = "policy.too_many";
/// Ningún módulo instalado y activo ofrece ese punto de control.
pub const ERR_CHECKPOINT_NOT_FOUND: &str = "policy.checkpoint_not_found";
/// La condición nombra un dato que el checkpoint no declara como `fact`.
pub const ERR_FACT_NOT_DECLARED: &str = "policy.fact_not_declared";
/// El checkpoint no ofrece esa consecuencia.
pub const ERR_OUTCOME_NOT_OFFERED: &str = "policy.outcome_not_offered";
/// Un `block` sin mensaje sería una negativa muda.
pub const ERR_MESSAGE_REQUIRED: &str = "policy.message_required";
/// `mode` fuera de `warn`/`enforce`.
pub const ERR_UNKNOWN_MODE: &str = "policy.unknown_mode";
/// Una condición vacía casa SIEMPRE.
pub const ERR_EMPTY_CONDITION: &str = "policy.empty_condition";

fn domain(code: &str, message: String) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message,
    }
}

/// **El gate.** Corre en [`crate::commands::execute_at`] después del bloque de schema y antes de la
/// bifurcación de tier — ver `runtime-dispatcher.md` §2.0 para el orden completo y `policies.md`
/// §4.3 para por qué ese punto no es negociable.
///
/// Sin `db` a propósito: ver la nota de módulo. `payload` es el **ya validado, defaulteado y
/// coercionado**, que es lo que hace que un hecho ausente signifique de verdad «el módulo no lo
/// aportó» y no «el llamador lo omitió y el schema lo iba a rellenar».
///
/// Devuelve los veredictos de `mode: warn` —los que avisaron sin impedir— para que la rampa sea
/// observable sin que el gate escriba en la BD.
pub fn enforce(
    registry: &crate::registry::Registry,
    command: &str,
    payload: &Params,
    hub_id: &str,
) -> Result<Vec<Verdict>> {
    // Ningún módulo activo declara un punto de control sobre este command: no hay gate, y lo único
    // que se ha pagado es una búsqueda en un mapa.
    let Some(checkpoint) = registry.policy_checkpoint_for_command(command) else {
        return Ok(Vec::new());
    };
    registry.policies.for_checkpoint(&checkpoint.id, |policies| {
        if policies.is_empty() {
            return Ok(Vec::new());
        }
        let scope = Json::Object(payload.clone().into_iter().collect());
        let mut warned = Vec::new();
        for policy in policies {
            // Tenancy antes que nada: las normas son del hub que las escribió (contrato de fila).
            if policy.hub_id != hub_id {
                continue;
            }
            match evaluate(policy, &checkpoint.facts, &scope) {
                Some(refusal) if policy.mode == Mode::Enforce => return Err(refusal.into_error()),
                Some(refusal) => {
                    // `warn`: se registra y NUNCA impide. Es la rampa con la que el dueño ve qué
                    // se dispararía antes de ponerlo en vigor.
                    eprintln!(
                        "[policy] warn {} ({}) sobre `{command}`: {} — {}",
                        refusal.policy_id, refusal.checkpoint, refusal.code, refusal.message
                    );
                    warned.push(refusal);
                }
                None => {}
            }
        }
        Ok(warned)
    })
}

/// Lo que una norma dictaminó. Se devuelve para que `warn` sea observable sin que el gate escriba
/// en la BD (guarda de coste acotado).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Verdict {
    pub policy_id: String,
    pub checkpoint: String,
    pub code: &'static str,
    pub message: String,
}

impl Verdict {
    fn into_error(self) -> RuntimeError {
        RuntimeError::Domain {
            code: self.code.to_string(),
            message: self.message,
        }
    }
}

/// `Some(v)` = esta norma dice que NO. `None` = deja pasar.
///
/// 🔴 El orden importa y es la mitad del arreglo: **primero la presencia de los hechos declarados**,
/// y solo después la condición. [`Condition::matches`] devuelve un `bool` pelado y un camino ausente
/// da `false`, exactamente igual que «no casaba»; leer ese `bool` para decidir haría que un hecho
/// ausente dejase pasar el command.
fn evaluate(policy: &ActivePolicy, facts: &[String], scope: &Json) -> Option<Verdict> {
    let refuse = |code: &'static str, message: String| {
        Some(Verdict {
            policy_id: policy.id.clone(),
            checkpoint: policy.checkpoint.clone(),
            code,
            message,
        })
    };
    for fact in facts {
        if resolve_path(fact, scope).filter(|v| !v.is_null()).is_none() {
            return refuse(
                ERR_FACT_MISSING,
                format!(
                    "la norma «{}» necesita `{fact}` y el comando no lo aporta",
                    policy.message
                ),
            );
        }
    }
    let Some(condition) = &policy.condition else {
        return refuse(
            ERR_CONDITION_UNREADABLE,
            format!("la norma «{}» no se puede leer con este core", policy.message),
        );
    };
    let Some(outcome) = &policy.outcome else {
        return refuse(
            ERR_OUTCOME_NOT_AVAILABLE,
            format!(
                "la norma «{}» pide una consecuencia que este hub no sabe aplicar",
                policy.message
            ),
        );
    };
    if !condition.matches(scope) {
        return None;
    }
    match outcome {
        Outcome::Block => refuse(ERR_BLOCKED, policy.message.clone()),
        // Un `elevate:` que llegó a la tabla (hub rodado atrás) no se ignora: deniega.
        Outcome::Elevate(_) => refuse(
            ERR_OUTCOME_NOT_AVAILABLE,
            format!(
                "la norma «{}» pide una consecuencia que este hub no sabe aplicar",
                policy.message
            ),
        ),
    }
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// La puerta de ESCRITURA: lo que el dueño guarda en `_policy`
// ─────────────────────────────────────────────────────────────────────────────────────────────

/// Una norma tal como la ve la API. `condition` viaja como documento, no como cadena: el llamador
/// mandó JSON y recibe JSON.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Policy {
    pub id: String,
    pub checkpoint: String,
    pub condition: Json,
    pub outcome: String,
    pub message: String,
    pub mode: String,
    pub is_active: bool,
    pub created_at: String,
    pub created_by: String,
    pub updated_at: String,
    pub updated_by: String,
}

/// Lo que carga un `POST`/`PUT`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NewPolicy {
    pub checkpoint: String,
    pub condition: Json,
    pub outcome: String,
    pub message: String,
    pub mode: String,
    #[serde(default = "default_true")]
    pub is_active: bool,
}

fn default_true() -> bool {
    true
}

const COLUMNS: &str = "id, checkpoint, condition, outcome, message, mode, is_active, \
                       created_at, created_by, updated_at, updated_by";

fn policy_row(row: &Json) -> Policy {
    let text = |k: &str| row.get(k).and_then(Json::as_str).unwrap_or("").to_string();
    Policy {
        id: text("id"),
        checkpoint: text("checkpoint"),
        // Una condición ilegible se devuelve como `null` en vez de reventar la lectura: la pantalla
        // del dueño tiene que poder ENSEÑAR la norma rara para que alguien la borre. El gate ya la
        // trata aparte, y denegando.
        condition: serde_json::from_str(&text("condition")).unwrap_or(Json::Null),
        outcome: text("outcome"),
        message: text("message"),
        mode: text("mode"),
        is_active: row
            .get("is_active")
            .and_then(Json::as_i64)
            .is_some_and(|v| v != 0),
        created_at: text("created_at"),
        created_by: text("created_by"),
        updated_at: text("updated_at"),
        updated_by: text("updated_by"),
    }
}

/// Comprueba una norma **antes** de guardarla, contra el punto de control que dice gatear.
///
/// Es la otra mitad del fallo cerrado: como una norma que no se puede evaluar DENIEGA, todo lo que
/// se pueda comprobar al escribirla se comprueba AQUÍ —en la pantalla donde el dueño la está
/// escribiendo— y no en mitad de una venta.
fn validate(registry: &crate::registry::Registry, new: &NewPolicy) -> Result<()> {
    let Some(mode) = Mode::parse(&new.mode) else {
        return Err(domain(
            ERR_UNKNOWN_MODE,
            format!("`{}` no es un modo: `warn` avisa y `enforce` impide", new.mode),
        ));
    };
    let Some(checkpoint) = registry.policy_checkpoint_for_id(&new.checkpoint) else {
        return Err(domain(
            ERR_CHECKPOINT_NOT_FOUND,
            format!(
                "ningún módulo instalado y activo ofrece el punto de control `{}`",
                new.checkpoint
            ),
        ));
    };
    // Un `block` mudo sería peor que no tener la función: la persona del mostrador tiene que poder
    // leer POR QUÉ no se la deja seguir. `warn` va por el mismo aro para que promover la norma a
    // `enforce` no sea el momento en que aparece el problema.
    if new.message.trim().is_empty() {
        return Err(domain(
            ERR_MESSAGE_REQUIRED,
            "una norma tiene que decir por qué impide lo que impide".to_string(),
        ));
    }
    // Una condición vacía casa SIEMPRE (es el default permisivo de los flujos). En una política eso
    // es una norma que bloquea el command entero sin decirlo, y el dueño la escribió creyendo que
    // filtraba algo.
    if new.condition.as_object().is_some_and(|o| o.is_empty()) {
        return Err(domain(
            ERR_EMPTY_CONDITION,
            "una condición vacía casaría con TODO: la norma impediría el comando entero".to_string(),
        ));
    }
    // El lenguaje congelado de los flujos, sin estrenar dialecto: un operador que no conoce devuelve
    // su propio `flow.*`.
    let condition = Condition::parse(&new.condition)?;
    // El checkpoint dice CON QUÉ DATOS se puede razonar. Una condición que nombra otra cosa lee
    // fuera del vocabulario que el módulo declaró — el mismo agujero que hub#662 cerró en los flujos.
    if let Some(unknown) = condition
        .0
        .keys()
        .find(|path| !checkpoint.facts.iter().any(|f| f == *path))
    {
        return Err(domain(
            ERR_FACT_NOT_DECLARED,
            format!(
                "`{unknown}` no es uno de los datos que `{}` ofrece para razonar ({})",
                checkpoint.id,
                checkpoint.facts.join(", ")
            ),
        ));
    }
    // La consecuencia, dos puertas distintas a propósito: una se arregla cambiando la norma y la
    // otra esperando una release, y decirle lo mismo a las dos dejaría al dueño sin saber cuál es.
    if !checkpoint.outcomes.iter().any(|o| o == &new.outcome) {
        return Err(domain(
            ERR_OUTCOME_NOT_OFFERED,
            format!(
                "`{}` no es una de las consecuencias que ofrece `{}` ({})",
                new.outcome,
                checkpoint.id,
                checkpoint.outcomes.join(", ")
            ),
        ));
    }
    match Outcome::parse(&new.outcome) {
        Some(Outcome::Block) => {}
        // `elevate:` está reconocido y todavía no se ejecuta (hub#1708). Se rechaza al escribir —en
        // vez de guardarse y denegar en caja— porque aquí sí hay alguien mirando la pantalla.
        _ => {
            return Err(domain(
                ERR_OUTCOME_NOT_AVAILABLE,
                format!(
                    "este hub todavía no sabe aplicar `{}`: por ahora una norma solo puede impedir",
                    new.outcome
                ),
            ))
        }
    }
    let _ = mode;
    Ok(())
}

/// Las normas de este hub, la recién borrada no.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<Policy>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            &format!(
                "SELECT {COLUMNS} FROM _policy \
                 WHERE hub_id = :hub_id AND deleted_at IS NULL ORDER BY created_at, id"
            ),
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(policy_row).collect())
}

pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<Policy> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    let res = db
        .query(
            &format!(
                "SELECT {COLUMNS} FROM _policy \
                 WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
            ),
            &p,
        )
        .await?;
    res.rows
        .first()
        .map(policy_row)
        .ok_or_else(|| domain(ERR_NOT_FOUND, format!("no hay ninguna norma `{id}` en este hub")))
}

pub async fn create(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &crate::registry::Registry,
    new: &NewPolicy,
    by: &str,
) -> Result<Policy> {
    validate(registry, new)?;
    // El techo se comprueba con la norma ya validada: una que además esté mal escrita merece que se
    // le diga qué está mal, no que el punto de control está lleno.
    let live = count_live(db, hub_id, &new.checkpoint).await?;
    if live >= MAX_POLICIES_PER_CHECKPOINT as i64 {
        return Err(domain(
            ERR_TOO_MANY,
            format!(
                "`{}` ya tiene {MAX_POLICIES_PER_CHECKPOINT} normas: el gate las compara en CADA \
                 comando, así que la siguiente se paga en cada venta",
                new.checkpoint
            ),
        ));
    }
    let id = new_id();
    let now = now_rfc3339();
    let mut p = bind(new, by);
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _policy (id, hub_id, checkpoint, condition, outcome, message, mode, \
                              is_active, created_at, created_by, updated_at, updated_by) \
         VALUES (:id, :hub_id, :checkpoint, :condition, :outcome, :message, :mode, \
                 :is_active, :now, :by, :now, :by)",
        &p,
    )
    .await?;
    get(db, hub_id, &id).await
}

pub async fn update(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    registry: &crate::registry::Registry,
    new: &NewPolicy,
    by: &str,
) -> Result<Policy> {
    validate(registry, new)?;
    get(db, hub_id, id).await?; // 404 antes de tocar nada, y acotado a este hub.
    // El techo NO se comprueba aquí: un `update` no añade una fila, y negarle al dueño editar el
    // texto de una de sus 20 normas porque «ya hay 20» sería dejarle sin poder arreglarlas.
    let mut p = bind(new, by);
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _policy SET checkpoint = :checkpoint, condition = :condition, outcome = :outcome, \
                            message = :message, mode = :mode, is_active = :is_active, \
                            updated_at = :now, updated_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    get(db, hub_id, id).await
}

/// Borrado **suave**: una norma que impidió una venta es parte de por qué esa venta no está, así
/// que la fila se marca y no se pierde.
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str, id: &str, by: &str) -> Result<()> {
    get(db, hub_id, id).await?;
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(by));
    db.execute(
        "UPDATE _policy SET deleted_at = :now, deleted_by = :by, updated_at = :now, \
                            updated_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

fn bind(new: &NewPolicy, by: &str) -> Params {
    let mut p = Params::new();
    p.insert("checkpoint".into(), json!(new.checkpoint));
    p.insert("condition".into(), json!(new.condition.to_string()));
    p.insert("outcome".into(), json!(new.outcome));
    p.insert("message".into(), json!(new.message));
    p.insert("mode".into(), json!(new.mode));
    p.insert("is_active".into(), json!(i64::from(new.is_active)));
    p.insert("by".into(), json!(by));
    p
}

async fn count_live(db: &dyn DatabaseAdapter, hub_id: &str, checkpoint: &str) -> Result<i64> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("checkpoint".into(), json!(checkpoint));
    let res = db
        .query(
            "SELECT COUNT(*) AS n FROM _policy \
             WHERE hub_id = :hub_id AND checkpoint = :checkpoint AND deleted_at IS NULL",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r.get("n"))
        .and_then(Json::as_i64)
        .unwrap_or(0))
}

/// Reconstruye el índice en memoria a partir de las filas VIVAS y ENCENDIDAS de este hub.
///
/// Lo llaman el arranque y **cada escritura** del CRUD. Una norma apagada (`is_active = 0`) o
/// borrada simplemente no entra: apagarla tiene que dejar de gatear en el comando siguiente, no en
/// el próximo reinicio.
///
/// Las filas que este core no entiende SÍ entran, con su hueco a `None`, porque el gate las trata
/// **denegando** (`policies.md` §6.1). Filtrarlas aquí sería el fail-open que el §6.1 cierra: una
/// norma que el hub no sabe leer desaparecería en silencio.
pub async fn load_index(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<HashMap<String, Vec<ActivePolicy>>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, checkpoint, condition, outcome, message, mode FROM _policy \
             WHERE hub_id = :hub_id AND deleted_at IS NULL AND is_active <> 0 \
             ORDER BY created_at, id",
            &p,
        )
        .await?;
    let mut by_checkpoint: HashMap<String, Vec<ActivePolicy>> = HashMap::new();
    for row in &res.rows {
        let text = |k: &str| row.get(k).and_then(Json::as_str).unwrap_or("").to_string();
        let checkpoint = text("checkpoint");
        // Un `mode` que no se entiende se trata como `enforce`, que es el lado seguro: la otra
        // opción —tratarlo como `warn`— convertiría una norma en vigor en un aviso mudo.
        let mode = Mode::parse(&text("mode")).unwrap_or(Mode::Enforce);
        let condition = serde_json::from_str::<Json>(&text("condition"))
            .ok()
            .and_then(|doc| Condition::parse(&doc).ok());
        by_checkpoint
            .entry(checkpoint.clone())
            .or_default()
            .push(ActivePolicy {
                id: text("id"),
                hub_id: hub_id.to_string(),
                checkpoint,
                condition,
                outcome: Outcome::parse(&text("outcome")),
                message: text("message"),
                mode,
            });
    }
    Ok(by_checkpoint)
}
