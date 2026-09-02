//! Capacidad de host `host.print(job)` (hub#957): **el gemelo de [`crate::host_notify`]** para la
//! cola de impresión del hub (ADR-0196 §6).
//!
//! **Entrega vía Outbox (espejo de `outbox.rs`)**: un command de módulo NO encola inline. Emite un
//! evento `<algo>.print.due` cuyo payload es la intención `{jobId, role, documentType, document,
//! format}`; el runtime registra un **listener-host** sintético sobre ese evento y el **relay** lo
//! entrega con reintentos/backoff/dead-letter **gratis** (la misma máquina ya probada). Aquí no se
//! reimplementa nada de eso: solo se lee la intención del payload y se la pasa a
//! [`crate::print_queue::enqueue`], que es quien valida el vocabulario y guarda el trabajo.
//!
//! ## Por qué esta puerta y no otra (decisión de Ioan, 2026-08-15 — hub#957)
//!
//! Un flujo no podía sacar papel por ninguna vía: ni step, ni grant, ni command de módulo, ni
//! handler WASM (`_print_queue` es tabla de sistema). De las tres salidas posibles, la elegida es la
//! que **menos descongela** el core (ADR-0283 D1): no añade una familia de primitivas, añade un
//! **segundo consumidor** del mecanismo de listener-host que ADR-0012 ya estableció. El lenguaje del
//! flujo v1 (`command · condition · delay · http · ai · notify`) no se toca, y un flujo llega aquí
//! por la puerta que ya tiene: un step `command` ejecuta un command de un módulo, y ese command
//! emite el evento.
//!
//! ## Las puertas, y en qué se diferencian de las de `notify`
//!
//! 1. **Capability del módulo emisor** — `printer` declarada **y concedida** (ADR-0079,
//!    default-deny), exigida en [`crate::outbox`] antes de tocar la cola. Es la capability que ya
//!    existía (`CapabilityKind::Printer`, la que usa `printing`): no se inventa una nueva, porque
//!    lo que se concede es exactamente lo mismo que ya nombraba —«este módulo puede sacar papel»— y
//!    dos permisos para una sola cosa solo consiguen que el dueño conceda el que no era.
//! 2. **Atribución** — sin `module_id` en la fila de outbox no hay a quién exigirle la capability, y
//!    entonces no se imprime. Aquí **no hay cuarta puerta de flujo** (la que `notify` tiene para lo
//!    que encola el kernel, hub#821) a propósito: el kernel no emite nada acabado en `.print.due` —
//!    quien lo emite es siempre un módulo, con su nombre puesto.
//! 3. **Vocabulario cerrado** — el equivalente al «canal declarado» de `notify` lo aplica la propia
//!    cola: `documentType` se comprueba contra [`crate::print_queue::DOCUMENT_TYPES`] y `document`
//!    tiene que ser un objeto JSON acotado. Un tipo desconocido es un rechazo con motivo, no un
//!    tique en blanco.
//!
//! No hace falta el equivalente de la puerta 3 de `notify` (destinatario resuelto desde datos del
//! hub): un trabajo de impresión **no sale del hub**. Se guarda en `_print_queue` y lo recoge un
//! dispositivo del propio negocio que se registró como host de ese `role`. No hay exfiltración que
//! cerrar ni gasto por mensaje que acotar, que es lo que justificaba aquella puerta.
//!
//! ## Y no hace falta transporte
//!
//! `host.notify` es no-op sin `Registry::notify_transport` porque el envío externo depende de un
//! cliente que el host inyecta. Aquí el «transporte» es una tabla del propio hub, así que la
//! capacidad está **siempre** disponible: no hay configuración que pueda faltar, y un
//! `<algo>.print.due` en un hub recién arrancado encola igual.
use serde::Deserialize;
use serde_json::Value as Json;

use crate::errors::{Result, RuntimeError};
use crate::print_queue::{NewPrintJob, FORMAT_RECEIPT};

/// La intención de impresión que un command emite en el payload del evento `*.print.due`.
///
/// Los nombres van en camelCase porque son los de `NewPrintJob` —el productor que ya existe es el
/// shell (`apps/web/src/lib/print.ts`)—, y un módulo que quiera imprimir no debería tener que
/// aprender una segunda forma del mismo documento.
///
/// A diferencia de [`NewPrintJob`], **NO** lleva `deny_unknown_fields`: el payload de un evento
/// declarativo viaja con los parámetros de sistema que el runtime inyecta (`hub_id`,
/// `current_user_id`, `now`…), así que exigir un objeto exacto haría imposible el camino normal.
/// Es la misma tolerancia que tiene `NotifyIntent`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintIntent {
    /// Clave de idempotencia elegida por el emisor. Dos eventos con el mismo `jobId` son UN tique
    /// (`print_queue::enqueue` es `ON CONFLICT DO NOTHING`), así que la deduplicación que un flujo
    /// necesita no hay que construirla: basta con que la clave viaje en el payload.
    pub job_id: String,
    /// **Override de la estación, en deprecación** (hub#987). Ausente —lo normal ya— significa «lo
    /// decide el hub», y la cola lo resuelve del mapa `documentType → estación`.
    ///
    /// Que sea opcional importa más aquí que en el shell: un flujo lo escribe el comerciante en un
    /// editor, y pedirle que teclee el nombre de una impresora sería devolverle exactamente la
    /// cadena tecleada que hub#457 quitó de en medio. Un flujo dice `kitchen_order` y ya está.
    #[serde(default)]
    pub role: String,
    /// Qué documento es, del vocabulario cerrado de la cola.
    pub document_type: String,
    /// El documento, estructurado (hub#501: nunca HTML).
    pub document: Json,
    /// Formato de papel. Ausente = `receipt`, el mismo defecto que el shell.
    #[serde(default)]
    pub format: Option<String>,
}

impl PrintIntent {
    /// Extrae la intención del payload de un evento `*.print.due`. `Err` si falta/!encaja.
    pub fn from_event_payload(payload: &erplora_db::Params) -> Result<PrintIntent> {
        let value = Json::Object(payload.clone());
        serde_json::from_value(value).map_err(|e| RuntimeError::InvalidPayload {
            name: "host.print".to_string(),
            detail: format!("intención de impresión inválida: {e}"),
        })
    }

    /// El trabajo tal y como lo recibe la cola. Todo lo que valida `print_queue::enqueue` —tipo de
    /// documento, forma y tamaño del documento, formato de papel— se valida **ahí** y no aquí: una
    /// segunda copia de esas reglas es una que se queda vieja.
    pub fn into_job(self) -> NewPrintJob {
        NewPrintJob {
            job_id: self.job_id,
            role: self.role,
            document_type: self.document_type,
            document: self.document,
            format: self.format.unwrap_or_else(|| FORMAT_RECEIPT.to_string()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::Params;
    use serde_json::json;

    fn intent_params() -> Params {
        let mut p = Params::new();
        p.insert("jobId".into(), json!("job-1"));
        p.insert("role".into(), json!("kitchen"));
        p.insert("documentType".into(), json!("kitchen_order"));
        p.insert("document".into(), json!({ "items": [] }));
        p
    }

    #[test]
    fn parses_intent_from_event_payload() {
        let intent = PrintIntent::from_event_payload(&intent_params()).unwrap();
        assert_eq!(intent.job_id, "job-1");
        assert_eq!(intent.role, "kitchen");
        assert_eq!(intent.document_type, "kitchen_order");
        assert_eq!(intent.format, None);
    }

    /// **Un flujo puede decir solo QUÉ imprime** (hub#987). Sin `role` la intención sigue siendo
    /// válida y llega a la cola con el override vacío, que es lo que hace que el mapa del hub
    /// resuelva la estación. Pedirle al comerciante que teclee el nombre de una impresora en el
    /// editor de flujos sería devolver la cadena tecleada que hub#457 quitó de en medio.
    #[test]
    fn an_intent_without_a_role_is_valid_and_lets_the_hub_route_it() {
        let mut p = intent_params();
        p.remove("role");

        let intent = PrintIntent::from_event_payload(&p).unwrap();

        assert_eq!(intent.role, "", "ausente y vacío son la misma cosa");
        assert_eq!(
            intent.into_job().role,
            "",
            "el override viaja vacío hasta la cola, que es quien consulta el mapa"
        );
    }

    /// El payload de un evento declarativo llega con los parámetros de sistema que el runtime
    /// inyecta (`hub_id`, `current_user_id`, `now`, `new_id`…). Si la intención los rechazara, el
    /// camino normal —un command que declara su `emit`— no podría imprimir nunca.
    #[test]
    fn tolerates_the_system_params_the_runtime_injects() {
        let mut p = intent_params();
        p.insert("hub_id".into(), json!("h1"));
        p.insert("current_user_id".into(), json!("u1"));
        p.insert("now".into(), json!("2026-08-15T10:00:00Z"));
        PrintIntent::from_event_payload(&p).unwrap();
    }

    #[test]
    fn rejects_a_payload_that_is_not_a_print_job() {
        let mut p = intent_params();
        p.remove("jobId");
        let err = PrintIntent::from_event_payload(&p).unwrap_err();
        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "got {err:?}"
        );
    }

    /// Sin `format` el trabajo sale en papel de tique, que es el defecto del shell; con él, manda
    /// lo que diga el emisor (y si es una palabra que la cola no conoce, lo rechaza la cola).
    #[test]
    fn the_default_paper_is_the_receipt_one() {
        let job = PrintIntent::from_event_payload(&intent_params())
            .unwrap()
            .into_job();
        assert_eq!(job.format, FORMAT_RECEIPT);

        let mut p = intent_params();
        p.insert("format".into(), json!("a4"));
        let job = PrintIntent::from_event_payload(&p).unwrap().into_job();
        assert_eq!(job.format, "a4");
    }
}
