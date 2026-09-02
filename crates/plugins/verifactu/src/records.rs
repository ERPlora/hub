//! Record creation: invoice types, amount audit, chaining — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

pub(crate) const INVOICE_TYPES: [&str; 8] = ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"];

/// Tipos que exigen el bloque `Destinatarios` en el XML: sin destinatario identificado la AEAT
/// los rechaza con el error **1189**.
pub(crate) const TYPES_REQUIRING_RECIPIENT: [&str; 6] = ["F1", "F3", "R1", "R2", "R3", "R4"];

/// Estados de registro que **siguen siendo eslabón** de la cadena.
///
/// Solo `rejected` deja de serlo: la AEAT no lo tiene, así que su huella no existe para Hacienda
/// y encadenar ahí garantiza que también rechacen al siguiente — un fallo puntual se convierte
/// en una cadena que ya no avanza sola (hub#287, mismo defecto confirmado en el SaaS).
///
/// Lo que está **en vuelo** (`pending`, `retry`, `error` — encolado en contingencia con backoff)
/// sí encadena: ese registro se transmitirá con la huella que ya calculó, y saltárselo
/// bifurcaría la cadena.
pub fn is_chainable_status(status: &str) -> bool {
    status != "rejected"
}

/// Tipo de factura efectivo según haya o no **destinatario identificado**.
///
/// Una F1 exige el bloque `Destinatarios`; sin NIF de cliente el XML sale sin él y la AEAT lo
/// rechaza con **1189**, después de que el registro haya consumido su número en la cadena. Una
/// venta a consumidor final sin NIF es justo el supuesto de la **simplificada (F2)**.
///
/// Una rectificativa sin NIF **no** es una simplificada: es una rectificativa **de** simplificada
/// (**R5**). Degradarla a F2 declararía una venta donde hay una devolución.
///
/// Se resuelve **antes** de encadenar porque el tipo entra en el cálculo de la huella.
///
/// ⚠️ **Degradar es correcto; hacerlo en silencio no** (hub#1104). Esta función decide el tipo y
/// nada más — quien la llama compara el resultado con lo declarado y lleva la diferencia a
/// [`RecordInput::downgraded_from`], que es lo que hace que el hecho se vea: un evento
/// `invoice_type_downgraded` con severidad `warning` y, si la F2 fabricada rompiese el techo
/// §15.8, un rechazo antes de gastar el número de cadena.
pub(crate) fn resolve_invoice_type(declared: &str, recipient_nif: &str) -> String {
    if !recipient_nif.trim().is_empty() || !TYPES_REQUIRING_RECIPIENT.contains(&declared) {
        return declared.to_string();
    }
    match declared {
        "R1" | "R2" | "R3" | "R4" => "R5".to_string(),
        _ => "F2".to_string(),
    }
}

/// Tipos que **no admiten un total negativo**: F1, F2 y F3 documentan una venta. Lo negativo es
/// una RECTIFICATIVA (R1…R5), que es el camino legal de una devolución y sí puede serlo.
///
/// Espejo exacto de `invoice.NON_NEGATIVE_TYPES` y de la restricción
/// `ck_verifactu_record_ordinary_total_not_negative` del módulo. **De esta regla** —el signo— sí
/// miden lo mismo las tres puertas; la de la cuota contra su tipo no puede (ver
/// [`line_rate_tolerance_cents`]), y decir lo contrario fue el error que devolvió hub#1180 con
/// cambios.
pub(crate) const NON_NEGATIVE_TYPES: [&str; 3] = ["F1", "F2", "F3"];

/// Tolerancia, en céntimos, al contrastar la cuota de una entrada del desglose contra su propio
/// tipo — **en función de cuántas líneas de factura se agregaron en ella**.
///
/// # Why it CANNOT be a fixed number
///
/// ⚠️ **`invoice` no longer emits this.** Since ADR-0405 §Decisión 4 (`invoice` v1.2.27,
/// `invoice#65`, now closed) `build_invoice` closes the quota **once per fiscal key**
/// (`money::percent_of(Σbase, rate)`), so what it emits today *does* satisfy `cuota = base × tipo`
/// and its own audit tolerance is **1 cent per key**. The old `e.quota += main_quota` — deliberate
/// but undocumented — is exactly what that ADR removed.
///
/// This gate stays per-line permissive anyway, and not out of inertia: it reads rows it did not
/// produce.
///
///   * **Invoices already sealed** before v1.2.27 carry the per-line breakdown and are chained
///     into the AEAT fingerprint, so they cannot be reinterpreted (same reason `aeat::desglose`
///     still reads both generations of `tax_breakdown`).
///   * **The verbatim F3.** An F3 substituting an F2 copies the ticket's own figures, quota per
///     line included — `invoice.audit` itself keeps `e.lines.max(1)` for `Closing::Verbatim`.
///     Tightening here would reject a document `invoice` legitimately emits **today**.
///   * **`sales`** still closes its header with `percent_of(Σbase)` in tax-included mode, up to one
///     cent per key away from the document (ADR-0405 names this and leaves it).
///
/// Tightening this to a fixed cent would therefore not enforce ADR-0405 — it would only refuse a
/// fiscal record for documents that are correct. The rule this gate exists to catch is the forged
/// quota, and the second ceiling below is what catches it.
///
/// The historical measurement that set this shape: with a fixed 1,5-cent tolerance, four lines of
/// 0,50 € at 21 % — `round_half_up(10,5) = 11` four times → `base 200 / cuota 44`, where 21 % of
/// 200 is 42 — were left **with no fiscal record at all**. With twelve lines at 10 % it reached
/// **one in three** tickets. Measured in the review of hub#1180; `invoice` stopped producing that
/// shape in ADR-0405, but the rows it already produced are still out there.
///
/// # Por qué `+ 0.5`
///
/// `invoice.audit` compara contra `money::percent_of` (ya redondeado) y aquí se compara contra el
/// valor **sin redondear**, que dista hasta medio céntimo de aquél. Con ese medio céntimo esta
/// puerta **nunca es más estricta** que la de `invoice`: si `invoice` lo emitió, aquí pasa.
///
/// # El conteo
///
/// `lines` es el número de líneas de la **factura entera**, que es lo que se puede leer de una vez
/// (`ingest_invoice`); `invoice.audit` usa el de **cada entrada**, que es menor o igual. Usar el
/// total es por tanto igual de permisivo o más, nunca menos — que es el lado seguro. `None`
/// (nadie sabe cuántas líneas hay: `records.create`, cuyo esquema ni siquiera admite desglose)
/// cae a **una**, la factura de una sola línea.
///
/// # Y el segundo techo: el que también sabe medir la TABLA
///
/// El `CHECK` del módulo no puede contar líneas —la fila guarda el desglose, no el documento—, así
/// que desde `015_quota_rate_check_needs_the_line_count.sql` mide otra cosa que sí es row-local:
/// que la cuota no se aleje de lo que su tipo justifica **más que ese mismo importe, más un
/// céntimo** (o sea, que no lo doble). Es demostrablemente inofensivo para el redondeo por línea
/// —`|Σq − Σe| ≤ 0,5 × líneas ≤ |e| + 1` en las 420.000 combinaciones legítimas comprobadas— y
/// caza igual el caso del QA (99,99 € donde el tipo justifica 1,14 €).
///
/// Se aplica **el menor de los dos**, y no por cinturón y tirantes: así este motor es siempre
/// **igual o más estricto** que la tabla, y un registro no puede pasar por aquí para morir un
/// `INSERT` después con un error crudo de Postgres — que es justo lo que hub#1103 vino a evitar.
pub(crate) fn line_rate_tolerance_cents(lines: Option<i64>, expected_cents: f64) -> f64 {
    let by_lines = lines.unwrap_or(1).max(1) as f64 + 0.5;
    let by_magnitude = expected_cents.abs() + 1.0;
    by_lines.min(by_magnitude)
}

/// Margen al comparar dos importes que son **enteros de céntimos** viajando en `f64`.
pub(crate) const CENT_EPSILON: f64 = 0.5;

/// Una línea del desglose reducida a lo único que la auditoría necesita. Importes en CÉNTIMOS.
pub(crate) struct AuditLine {
    rate: f64,
    base: f64,
    quota: f64,
    surcharge_rate: f64,
    surcharge_quota: f64,
    has_surcharge: bool,
}

/// Lee el `tax_breakdown` en sus DOS generaciones (el mismo par que entiende `aeat::desglose`, y
/// por el mismo motivo: las facturas ya emitidas están encadenadas en la huella y no se pueden
/// reinterpretar). Un desglose ilegible devuelve la lista vacía — ahí no hay nada declarado que
/// contrastar y juzga el `tax_rate` de la fila.
pub(crate) fn audit_lines(tax_breakdown: &str) -> Vec<AuditLine> {
    let mut lines = Vec::new();
    match serde_json::from_str::<Json>(tax_breakdown) {
        // Formato nuevo: una entrada por clave fiscal completa.
        Ok(Json::Array(entries)) => {
            for e in &entries {
                if !e.is_object() {
                    continue;
                }
                lines.push(AuditLine {
                    rate: num_field(e, "rate", 0.0),
                    base: num_field(e, "base", 0.0),
                    quota: num_field(e, "quota", 0.0),
                    surcharge_rate: num_field(e, "surcharge_rate", 0.0),
                    surcharge_quota: num_field(e, "surcharge_quota", 0.0),
                    has_surcharge: e.get("surcharge_rate").is_some()
                        || e.get("surcharge_quota").is_some(),
                });
            }
        }
        // Formato viejo: clave = tipo, `{base, tax}`, todo venta nacional sujeta y no exenta.
        Ok(Json::Object(map)) => {
            for (rate, amounts) in map {
                let Ok(rate) = rate.trim().parse::<f64>() else {
                    continue;
                };
                lines.push(AuditLine {
                    rate,
                    base: num_field(&amounts, "base", 0.0),
                    quota: num_field(&amounts, "tax", 0.0),
                    surcharge_rate: 0.0,
                    surcharge_quota: 0.0,
                    has_surcharge: false,
                });
            }
        }
        _ => {}
    }
    lines
}

/// **Nada aritméticamente imposible se sella** (hub#1103).
///
/// Este motor es el último eslabón antes de Hacienda: calcula la huella SHA-256, gasta un número
/// de secuencia, encadena y encola para la AEAT. Aceptaba los importes que le dieran. Una pasada
/// de QA selló un registro que declaraba `rate 21.0` con una cuota de 99,99 € sobre una base de
/// 5,45 €, y otro con base y cuota negativas en un alta ordinaria: los dos viajaron VERBATIM al
/// `CuotaTotal` y al `ImporteTotal` que se remiten.
///
/// # Por qué aquí, si el módulo ya lo comprueba en la tabla
///
/// `013_arithmetic_integrity.sql` (verifactu#53) puso tres `CHECK` en `verifactu_record`, y esa es
/// la guarda que ninguna puerta puede saltarse. Pero una violación de `CHECK` llega como un error
/// crudo de Postgres: **sin código de dominio, sin motivo legible y después** de haber leído el
/// ancla de la cadena. Este control se adelanta a ese punto y da el motivo con su código, que es
/// lo que la issue pedía dejar «en `verifactu.events.list`». *(No puede ser una FILA de evento: el
/// rechazo revierte su propia transacción y el evento se iría con ella. El motivo viaja en el
/// error, que es lo que ve el llamante y lo que registra el runtime.)*
///
/// And there is one thing the table **cannot** check and this can: how many invoice lines were
/// aggregated into each breakdown entry. Rows whose quota was rounded per line — everything sealed
/// before `invoice` v1.2.27, and the verbatim F3 to this day — do not satisfy `cuota = base × tipo`
/// exactly, so no fixed tolerance works on them: the 1,5-cent one behind `013` was rejecting
/// legitimate multi-line tickets (verifactu#60). Since ADR-0405 `invoice` closes the key once and
/// no longer BUILDS that shape, but this gate reads rows it did not build. The two gates measure
/// **different things on purpose**, and this one is always the stricter of the two: see
/// [`line_rate_tolerance_cents`].
///
/// # Qué se comprueba, y qué NO
///
///   * **la cuota contra SU tipo declarado** — sí, y es la única que caza el caso del QA:
///     `base + cuota = total` cuadra igual (545 + 9999 = 10544 es internamente consistente). Con
///     la tolerancia que impone el redondeo por línea de `invoice`, ni un céntimo menos
///     ([`line_rate_tolerance_cents`]): una guarda que rechaza una mesa de doce no es una guarda,
///     es una caja que no factura.
///   * **la cuota contra `quantity × unit_price`** — NO, y no es un olvido: `sales` prorratea el
///     descuento DENTRO de la línea y deja `unit_price` en el bruto. Esa comparación rechazaría
///     toda venta con descuento y toda invitación (razonado en `invoice#50`).
///   * **el desglose contra la cabecera** (`Σ bases`, `Σ cuotas`) y **`base + cuota = total`** —
///     sí. Es exactamente el cruce que hace la AEAT, y es la mitad que la tabla dejó fuera a
///     propósito porque en SQL no cabía sin una función.
///   * **`total ≤ 0`** — NO: `< 0`. Un tique 100 % invitado suma 0,00 € honestamente y sigue
///     siendo una venta que necesita su F2. El criterio de aceptación de hub#1103 pedía `≤ 0` y
///     contradecía lo ya decidido en `invoice#50`; manda lo decidido.
///
/// Devuelve `Some(mensaje)` —con el código de dominio delante— cuando el registro no se puede
/// sellar.
pub(crate) fn audit_amounts(r: &RecordInput) -> Option<String> {
    // Una anulación no lleva importes: no hay nada que cuadrar.
    if r.record_type != "alta" {
        return None;
    }

    let lines = audit_lines(&r.tax_breakdown);
    let mut declared_base = 0.0;
    let mut declared_quota = 0.0;

    for line in &lines {
        declared_base += line.base;
        declared_quota += line.quota + line.surcharge_quota;

        let expected = line.base * line.rate / 100.0;
        let tolerance = line_rate_tolerance_cents(r.line_count, expected);
        if (line.quota - expected).abs() > tolerance {
            return Some(format!(
                "quota_rate_mismatch: el desglose declara {} de cuota sobre una base de {} al {} %, \
                 y ese tipo justifica {expected:.2} (tolerancia {tolerance} céntimos, el redondeo \
                 por línea de una factura de {} línea(s)). Cobrar un importe y declarar otro es lo \
                 que rompe el cruce de la AEAT",
                line.quota, line.base, line.rate, r.line_count.unwrap_or(1)
            ));
        }
        if line.has_surcharge {
            let expected_surcharge = line.base * line.surcharge_rate / 100.0;
            let tolerance = line_rate_tolerance_cents(r.line_count, expected_surcharge);
            if (line.surcharge_quota - expected_surcharge).abs() > tolerance {
                return Some(format!(
                    "quota_rate_mismatch: el desglose declara {} de recargo de equivalencia sobre \
                     una base de {} al {} %, y ese tipo justifica {expected_surcharge:.2} \
                     (tolerancia {tolerance} céntimos)",
                    line.surcharge_quota, line.base, line.surcharge_rate
                ));
            }
        }
    }

    if lines.is_empty() {
        // Sin desglose legible (facturas anteriores al campo, rectificativas que lo dejan vacío, o
        // un `records.create` que no lo manda) solo queda el `tax_rate` de la fila. Tolerancia: un
        // céntimo de redondeo más el error que introduce guardar el tipo EFECTIVO con dos
        // decimales — sin ese margen una factura grande se rechazaría por la precisión de su
        // propio tipo. Mismo margen que `ck_verifactu_record_quota_matches_row_rate`.
        let expected = r.base_amount * r.tax_rate / 100.0;
        let tolerance = 1.0 + (r.base_amount.abs() * 0.00005).ceil();
        if (r.tax_amount - expected).abs() > tolerance {
            return Some(format!(
                "quota_rate_mismatch: la fila declara {} de cuota sobre una base de {} al {} %, y \
                 ese tipo justifica {expected:.2} (tolerancia {tolerance} céntimos)",
                r.tax_amount, r.base_amount, r.tax_rate
            ));
        }
    } else if (declared_base - r.base_amount).abs() > CENT_EPSILON
        || (declared_quota - r.tax_amount).abs() > CENT_EPSILON
    {
        return Some(format!(
            "totals_mismatch: la cabecera declara base {} y cuota {}, y su propio desglose suma \
             base {declared_base} y cuota {declared_quota}. `CuotaTotal` tiene que ser la suma de \
             las cuotas declaradas",
            r.base_amount, r.tax_amount
        ));
    }

    if (r.base_amount + r.tax_amount - r.total_amount).abs() > CENT_EPSILON {
        return Some(format!(
            "totals_mismatch: la cabecera declara base {} + cuota {} y un total de {}, que es lo \
             que viaja como `ImporteTotal`",
            r.base_amount, r.tax_amount, r.total_amount
        ));
    }

    if NON_NEGATIVE_TYPES.contains(&r.invoice_type.as_str())
        && (r.total_amount < -CENT_EPSILON || r.base_amount + r.tax_amount < -CENT_EPSILON)
    {
        return Some(format!(
            "negative_total: una factura de tipo {} no puede totalizar {}: un importe negativo es \
             una rectificativa (R1…R5), no una ordinaria",
            r.invoice_type, r.total_amount
        ));
    }

    None
}

/// Recompone un registro **rechazado** sobre el último eslabón que la AEAT sí tiene.
///
/// Cambia `previous_hash`, el número de secuencia y —por tanto— la propia huella. Reescribir el
/// registro localmente es legítimo *precisamente* porque la AEAT lo rechazó: nunca entró en la
/// cadena oficial. Lo que no vale es reenviarlo colgando de la huella equivocada.
///
/// Devuelve el registro recompuesto (para reconstruir el XML) y la intención que lo persiste.
/// El `xml_content` se limpia: el XML archivado corresponde al eslabón viejo y un reintento
/// posterior debe regenerarlo, no reenviar el que ya rechazaron.
pub fn rechain_record(
    record: &Json,
    anchor: &aeat::ConsultRecord,
    sequence_number: i64,
) -> (Json, Operation) {
    let previous_hash = chain::normalize_hash(&anchor.record_hash);
    let mut rechained = record.clone();
    let record_hash = if str_field(record, "record_type") == "anulacion" {
        chain::anulacion_hash(
            &str_field(record, "issuer_nif"),
            &str_field(record, "invoice_number"),
            &str_field(record, "invoice_date"),
            &previous_hash,
            &str_field(record, "generation_timestamp"),
        )
    } else {
        chain::alta_hash(
            &str_field(record, "issuer_nif"),
            &str_field(record, "invoice_number"),
            &str_field(record, "invoice_date"),
            &str_field(record, "invoice_type"),
            num_field(record, "tax_amount", 0.0) / 100.0,
            num_field(record, "total_amount", 0.0) / 100.0,
            &previous_hash,
            &str_field(record, "generation_timestamp"),
        )
    };
    if let Some(m) = rechained.as_object_mut() {
        m.insert("previous_hash".into(), json!(previous_hash));
        m.insert("record_hash".into(), json!(record_hash));
        m.insert("sequence_number".into(), json!(sequence_number));
        m.insert("is_first_record".into(), json!(0));
        m.insert("xml_content".into(), json!(""));
    }
    let record_id = str_field(record, "id");
    let intent = op(
        "verifactu._rechain_record",
        json!({
            "record_id": record_id,
            "sequence_number": sequence_number,
            "previous_hash": previous_hash,
            "record_hash": record_hash,
        }),
    );
    (rechained, intent)
}

/// Generates the chained fiscal record (alta/anulación): chain anchor per
/// `(hub_id, issuer_nif, environment)`, SHA-256 fingerprint (exact AEAT formats), `qr_url`,
/// and the INSERT record(pending) + event intentions (see [`build_record_output`]).
///
/// Sequence atomicity: the anchor is read before computing, and the unique index
/// `uq_verifactu_record_hub_seq (hub_id, issuer_nif, environment, sequence_number)` closes
/// the TOCTOU window — if two creates race, the second INSERT violates the index and ITS
/// whole transaction rolls back (no chain fork).
pub(crate) async fn create_record(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;

    // Validación del payload (espejo de schemas/record_create.json).
    let record_type = str_field(&payload, "record_type");
    if record_type != "alta" && record_type != "anulacion" {
        return Err(VerifactuError::Payload("record_type debe ser alta|anulacion".into()).into());
    }
    let issuer_nif = str_field(&payload, "issuer_nif");
    let issuer_name = str_field(&payload, "issuer_name");
    let invoice_number = str_field(&payload, "invoice_number");
    let invoice_date = str_field(&payload, "invoice_date");
    let invoice_type = str_field(&payload, "invoice_type");
    for (name, v) in [
        ("issuer_nif", &issuer_nif),
        ("issuer_name", &issuer_name),
        ("invoice_number", &invoice_number),
        ("invoice_date", &invoice_date),
    ] {
        if v.is_empty() {
            return Err(VerifactuError::Payload(format!("falta {name}")).into());
        }
    }
    if !INVOICE_TYPES.contains(&invoice_type.as_str()) {
        return Err(VerifactuError::Payload("invoice_type debe ser F1-F3|R1-R5".into()).into());
    }
    if chrono::NaiveDate::parse_from_str(&invoice_date, "%Y-%m-%d").is_err() {
        return Err(VerifactuError::Payload("invoice_date debe ser YYYY-MM-DD".into()).into());
    }

    build_record_output(
        host,
        &ctx,
        RecordInput {
            record_type,
            issuer_nif,
            issuer_name,
            invoice_number,
            invoice_date,
            invoice_type,
            // El esquema de `records.create` (`additionalProperties: false`) no admite
            // `tax_breakdown`, así que por esta puerta no llega desglose que contrastar y no hay
            // líneas que contar: manda la regla del `tax_rate` de la fila.
            line_count: None,
            // El command público declara el tipo que quiere y no se le toca: aquí no hay
            // degradación que anotar (la resuelve `ingest_invoice`, que sí conoce al destinatario).
            downgraded_from: String::new(),
            description: str_field(&payload, "description"),
            base_amount: num_field(&payload, "base_amount", 0.0),
            tax_rate: num_field(&payload, "tax_rate", 21.0),
            tax_breakdown: str_field(&payload, "tax_breakdown"),
            tax_amount: num_field(&payload, "tax_amount", 0.0),
            total_amount: num_field(&payload, "total_amount", 0.0),
            invoice_id: payload.get("invoice_id").cloned().unwrap_or(Json::Null),
            recipient_nif: str_field(&payload, "recipient_nif"),
            recipient_name: str_field(&payload, "recipient_name"),
            // Sustitución (F3): el caller manual puede pasarlos; normalmente vacíos.
            substitutes_number: str_field(&payload, "substitutes_number"),
            substitutes_date: str_field(&payload, "substitutes_date"),
            substitutes_nif: str_field(&payload, "substitutes_nif"),
            // Rectificación (R1-R5, hub#1023). `rectification_type` vacío = lo deriva el XML de
            // si vienen o no los importes rectificados; explícito (`S`/`I`) manda sobre él.
            rectifies_number: str_field(&payload, "rectifies_number"),
            rectifies_date: str_field(&payload, "rectifies_date"),
            rectifies_nif: str_field(&payload, "rectifies_nif"),
            rectification_type: str_field(&payload, "rectification_type"),
            rectified_base_amount: optional_cents(&payload, "rectified_base_amount"),
            rectified_tax_amount: optional_cents(&payload, "rectified_tax_amount"),
            rectified_surcharge_amount: optional_cents(&payload, "rectified_surcharge_amount"),
        },
    )
    .await
}

/// Un importe **opcional** en céntimos, tal cual venga: `Json::Null` cuando nadie lo escribió.
///
/// No se normaliza a `0`: en el bloque `ImporteRectificacion` la diferencia entre «no hay importe»
/// y «el importe es cero» es la diferencia entre no declarar el bloque y declarar a Hacienda que
/// se rectifica una base de cero euros (hub#324). Quien decide es `aeat::importe_rectificacion`.
pub(crate) fn optional_cents(payload: &Json, key: &str) -> Json {
    payload.get(key).cloned().unwrap_or(Json::Null)
}

// ── ingest_invoice: alta automática desde el módulo invoice ───────────────────

/// Campos fiscales ya resueltos para emitir un registro (compartido por `create_record` y
/// `ingest_invoice`). Importes en **céntimos** (ADR-0007); la huella/XML/QR convierten a euros.
pub(crate) struct RecordInput {
    pub(crate) record_type: String,
    pub(crate) issuer_nif: String,
    pub(crate) issuer_name: String,
    pub(crate) invoice_number: String,
    pub(crate) invoice_date: String,
    pub(crate) invoice_type: String,
    /// Cuántas **líneas** tiene la factura de la que sale este registro, cuando se sabe.
    ///
    /// Es el dato que hace juzgable la cuota del desglose: `invoice` redondea por línea y suma, así
    /// que la desviación admisible crece con el número de líneas (ver
    /// [`line_rate_tolerance_cents`]). `None` = nadie lo sabe, y entonces se juzga como una factura
    /// de una línea.
    pub(crate) line_count: Option<i64>,
    /// Tipo que **declaraba el documento** cuando `invoice_type` es el resultado de una
    /// degradación (hub#1104), y vacío cuando nadie degradó nada.
    ///
    /// No es decorativo: es lo que convierte la degradación en un hecho observable. Con él,
    /// [`build_record_output`] emite el evento `invoice_type_downgraded` y comprueba el techo
    /// §15.8 ANTES de gastar un número de cadena.
    pub(crate) downgraded_from: String,
    pub(crate) description: String,
    pub(crate) base_amount: f64,
    /// Tipo EFECTIVO (`cuota/base`). Ya NO es lo que se declara a la AEAT en factura mixta: el XML
    /// emite una línea `DetalleDesglose` por tipo real (ver `aeat::desglose`). Se conserva como
    /// columna de la fila —consultas, listados— y como fallback de facturas sin desglose.
    pub(crate) tax_rate: f64,
    /// Desglose REAL por tipo, tal cual lo escribe el módulo `invoice`:
    /// `{"21.00":{"base":1000,"tax":210},"10.00":{…}}` en céntimos. Es lo que la AEAT necesita para
    /// que un ticket de bar (caña 21% + tapa 10%) declare sus DOS tipos y no uno inventado.
    pub(crate) tax_breakdown: String,
    pub(crate) tax_amount: f64,
    pub(crate) total_amount: f64,
    pub(crate) invoice_id: Json,
    /// Destinatario (cliente) — obligatorio en el XML para F1/F3/R1-R4 (error AEAT 1189). Vacío
    /// para tiquets simplificados (F2). Se usa al construir el SOAP en la transmisión inline.
    pub(crate) recipient_nif: String,
    pub(crate) recipient_name: String,
    /// Factura SUSTITUIDA (F3 → F2, ADR-0140): nº+serie, fecha de expedición y NIF del emisor de la
    /// simplificada que esta factura completa sustituye. Alimentan el bloque XML `FacturasSustituidas`
    /// (XSD IDFacturaARType). Vacíos si el registro no es una sustitución (todo lo que no sea F3).
    pub(crate) substitutes_number: String,
    pub(crate) substitutes_date: String,
    pub(crate) substitutes_nif: String,
    /// Factura RECTIFICADA (R1-R5 → la original, hub#1023): nº+serie, fecha de expedición y NIF
    /// del emisor de la factura que esta rectificativa corrige. Alimentan el bloque XML
    /// `FacturasRectificadas` (XSD `IDFacturaARType`, el mismo shape que las sustituidas). Vacíos
    /// si el registro no rectifica nada, o si la rectificativa no identifica el original (una R5
    /// de un tique puede no hacerlo: el bloque es `minOccurs="0"`).
    pub(crate) rectifies_number: String,
    pub(crate) rectifies_date: String,
    pub(crate) rectifies_nif: String,
    /// `TipoRectificativa`: `S` sustitutiva · `I` por diferencias. **Vacío = lo deriva el XML**
    /// de si vienen o no los importes rectificados (`aeat::rectification_type`), que es la única
    /// lectura que admite el esquema. Un valor explícito manda sobre la derivación.
    pub(crate) rectification_type: String,
    /// `ImporteRectificacion` (solo en una `S`): base, cuota y —opcional— recargo **rectificados**,
    /// en CÉNTIMOS. `Json::Null` cuando no vienen: ahí «no hay importe» y «el importe es cero» son
    /// cosas distintas ante Hacienda, así que no se normalizan a `0` (hub#324).
    pub(crate) rectified_base_amount: Json,
    pub(crate) rectified_tax_amount: Json,
    pub(crate) rectified_surcharge_amount: Json,
}

/// Chaining core: reads the `(hub_id, issuer_nif, environment)` anchor, computes the SHA-256
/// fingerprint (exact AEAT formats) + `qr_url`, and returns the INSERT record(pending) + event
/// intentions (plus the inline transmission when a certificate is available — module active =
/// always emit, ADR-0202 guard R3).
///
/// Environment scoping (ADR-0202 guard R4, hub#313): `production` and `testing` are two
/// parallel, independent chains. The anchor, the sequence and `PrimerRegistro` never cross
/// environments — switching the config toggle starts/resumes THAT environment's own chain.
///
/// Sequence atomicity: the anchor is read before computing, and the unique index
/// `uq_verifactu_record_hub_seq (hub_id, issuer_nif, environment, sequence_number)` closes the
/// TOCTOU window — if two creates race, the second INSERT violates the index and ITS whole
/// transaction rolls back (no chain fork).
pub(crate) async fn build_record_output(host: &dyn NativeHost, ctx: &Ctx, r: RecordInput) -> Result<Output> {
    // ADR-0202 §4.2 (phase 0, hub#312): `NumeroInstalacion` is this hub's UUID before the AEAT
    // and can never be reused — a record built under a slug or any non-UUID id would register a
    // bogus installation that Hacienda can neither reconcile nor keep unique. Hard fail, before
    // any sequence number is consumed.
    if uuid::Uuid::parse_str(&ctx.hub_id).is_err() {
        return Err(RuntimeError::Native(format!(
            "verifactu: context.hub_id {:?} is not a UUID — NumeroInstalacion must be the hub UUID",
            ctx.hub_id
        )));
    }
    // hub#1103: **nada aritméticamente imposible se sella**. Antes de leer el ancla y ANTES de
    // gastar un número de secuencia — un registro rechazado más tarde deja el hueco igual.
    if let Some(reason) = audit_amounts(&r) {
        return Err(VerifactuError::Payload(reason).into());
    }

    // hub#1104: una F1 sin destinatario se degrada a F2 para no morir con el 1189… pero una F2
    // por encima de 3.010,00 € muere con el §15.8, y esa la habríamos FABRICADO nosotros. El techo
    // se comprueba aquí, no en `xsd::validate_registro`, porque allí llega con la cadena ya gastada.
    if !r.downgraded_from.is_empty() && r.invoice_type == "F2" {
        let declared = r.base_amount + r.tax_amount;
        if declared > xsd::F2_CEILING_CENTS as f64 {
            return Err(VerifactuError::Payload(format!(
                "f2_limit_exceeded: la factura {} se declaró {} sin NIF de destinatario, y una \
                 simplificada F2 no puede pasar de {:.2} € (§15.8) sumando base y cuota; suma \
                 {:.2} €. Identifica al destinatario para poder emitirla como factura completa",
                r.invoice_number,
                r.downgraded_from,
                xsd::F2_CEILING_CENTS as f64 / 100.0,
                declared / 100.0,
            ))
            .into());
        }
    }

    // The record joins the chain of the hub's CURRENT config environment (guard R4). Read the
    // config BEFORE the anchor: the environment scopes every chain read below (and the QR host).
    let config = read_config(host, &ctx.hub_id).await?;
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    // Chain anchor: last CHAINABLE row for (hub_id, issuer_nif, environment). A `rejected`
    // record is not at the AEAT, so its fingerprint cannot be the next `previous_hash` —
    // chaining there guarantees another rejection and stalls the chain (`is_chainable_status`).
    let anchor = host
        .read(
            "SELECT record_hash, sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND is_deleted = 0 \
             AND status <> 'rejected' \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": r.issuer_nif,
                "environment": environment,
            })),
        )
        .await?;
    // The SEQUENCE, instead, counts ALL rows of the environment: a rejected record already
    // spent its number and the unique index `uq_verifactu_record_hub_seq` won't reuse it.
    let sequence_number = next_sequence(host, &ctx.hub_id, &r.issuer_nif, &environment).await?;
    let (previous_hash, is_first) = match anchor.first() {
        Some(row) => (str_field(row, "record_hash"), false),
        // Sin eslabón anterior que la AEAT reconozca, este SÍ es el primero: si lo único previo
        // fue un rechazo, Hacienda no tiene nada de este emisor.
        None => (String::new(), true),
    };

    // Huella (formatos AEAT exactos — chain.rs) + QR.
    // ⚠️ ADR-0007: los importes llegan/persisten en CÉNTIMOS (INTEGER), pero la huella y el
    // XML/QR de la AEAT exigen EUROS con 2 decimales. Se convierte céntimos→euros SOLO en el
    // límite de formateo fiscal; las columnas (`base/tax/total_amount`) siguen en céntimos.
    let generation_timestamp = ctx.now.clone();
    let tax_amount_eur = r.tax_amount / 100.0;
    let total_amount_eur = r.total_amount / 100.0;
    let record_hash = if r.record_type == "alta" {
        chain::alta_hash(
            &r.issuer_nif,
            &r.invoice_number,
            &r.invoice_date,
            &r.invoice_type,
            tax_amount_eur,
            total_amount_eur,
            &previous_hash,
            &generation_timestamp,
        )
    } else {
        chain::anulacion_hash(
            &r.issuer_nif,
            &r.invoice_number,
            &r.invoice_date,
            &previous_hash,
            &generation_timestamp,
        )
    };
    // The QR host depends on the environment (testing vs production), read above.
    let qr_url = chain::qr_url(
        &r.issuer_nif,
        &r.invoice_number,
        &r.invoice_date,
        total_amount_eur,
        &environment,
    );

    let ids = &ctx.new_ids;
    if ids.len() < 3 {
        return Err(RuntimeError::Native("context.new_ids insuficientes".into()));
    }
    // `ids[0..6]` ya están repartidos (registro, evento, la ranura reservada de la vieja cola y los
    // tres de la transmisión inline). El aviso de degradación estrena la séptima para no mover
    // ninguna de las anteriores de sitio.
    const DOWNGRADE_EVENT_ID_INDEX: usize = 6;
    if !r.downgraded_from.is_empty() && ids.len() <= DOWNGRADE_EVENT_ID_INDEX {
        return Err(RuntimeError::Native(
            "context.new_ids insuficientes para anotar la degradación de tipo".into(),
        ));
    }
    let record_id = ids[0].clone();

    let mut output = Output::new()
        .with_operation(op(
            "verifactu._insert_record",
            json!({
                "record_id": record_id,
                "record_type": r.record_type,
                "sequence_number": sequence_number,
                "invoice_id": r.invoice_id,
                "issuer_nif": r.issuer_nif,
                "issuer_name": r.issuer_name,
                "invoice_number": r.invoice_number,
                "invoice_date": r.invoice_date,
                "invoice_type": r.invoice_type,
                "description": r.description,
                "base_amount": r.base_amount,
                "tax_rate": r.tax_rate,
                "tax_breakdown": r.tax_breakdown,
                "tax_amount": r.tax_amount,
                "total_amount": r.total_amount,
                "previous_hash": previous_hash,
                "record_hash": record_hash,
                "is_first_record": if is_first { 1 } else { 0 },
                "generation_timestamp": generation_timestamp,
                "qr_url": qr_url,
                // Guard R4 (hub#313): explicit environment — the record joins the chain whose
                // anchor/sequence were read above; the SQL COALESCE fallback is only for older
                // engines that omit the param.
                "environment": environment,
                // F3 → FacturasSustituidas (ADR-0140): snapshot de la F2 sustituida para reconstruir
                // el XML en contingencia/reintento sin releer la factura. Vacíos si no es sustitución.
                "substitutes_number": r.substitutes_number,
                "substitutes_date": r.substitutes_date,
                "substitutes_nif": r.substitutes_nif,
                // R1-R5 → bloque rectificativo (hub#1023): mismo snapshot, mismo motivo. Un envío
                // diferido (registro creado sin certificado y remitido a mano después) reconstruye
                // el XML desde ESTA fila, así que lo que no esté aquí no llega a la AEAT.
                "rectifies_number": r.rectifies_number,
                "rectifies_date": r.rectifies_date,
                "rectifies_nif": r.rectifies_nif,
                "rectification_type": r.rectification_type,
                "rectified_base_amount": r.rectified_base_amount,
                "rectified_tax_amount": r.rectified_tax_amount,
                "rectified_surcharge_amount": r.rectified_surcharge_amount,
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ids[1],
                "record_id": record_id,
                "event_type": "record_created",
                "severity": "info",
                "message": format!("Registro {} #{sequence_number} de {} creado", r.record_type, r.invoice_number),
                "details": details_for("verifactu.record_created", json!({
                    "record_type": r.record_type,
                    "invoice_number": r.invoice_number,
                    "sequence_number": sequence_number,
                    "record_hash": record_hash,
                    "is_first_record": is_first,
                })),
                "timestamp": ctx.now,
            }),
        ));

    // hub#1104: **la degradación deja de ser muda.** Va como evento propio y no como un matiz del
    // `record_created` porque es un hecho distinto y con severidad distinta: quien filtre por
    // `warning` en la pantalla de eventos —o dispare un flujo con él— tiene que encontrarlo.
    if !r.downgraded_from.is_empty() {
        output = output.with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ids[DOWNGRADE_EVENT_ID_INDEX],
                "record_id": record_id,
                "event_type": EVENT_TYPE_INVOICE_TYPE_DOWNGRADED,
                "severity": "warning",
                "message": format!(
                    "La factura {} se declaró {} y se ha registrado como {}: sin NIF de \
                     destinatario la AEAT rechaza el tipo declarado (error 1189)",
                    r.invoice_number, r.downgraded_from, r.invoice_type
                ),
                "details": details_for("verifactu.invoice_type_downgraded", json!({
                    "invoice_number": r.invoice_number,
                    "declared": r.downgraded_from,
                    "effective": r.invoice_type,
                    "reason": REASON_MISSING_RECIPIENT,
                    "sequence_number": sequence_number,
                })),
                "timestamp": ctx.now,
            }),
        ));
    }

    // Module active = ALWAYS emit (ADR-0202 guard R3, verifactu#26): the `auto_transmit`
    // column was dropped in verifactu v1.5.2 — there is no deferred-transmission mode.
    // `ids[2]` stays reserved (it was the contingency queue id) so the transmit ids below
    // keep their positions.
    if let Some(cfg) = config.as_ref() {
        // Inline AEAT transmission on emit. Reuses `transmit_one`, which applies the result to
        // the record (accepted/rejected + CSV) and, on network failure, enqueues it in the
        // contingency queue with backoff. With NO transmission road at all (neither a core
        // certificate nor the fiscal gateway, hub#1432) → left `pending` (manual send later).
        // Intentions apply AFTER the record INSERT (Output order).
        if can_transmit(host, &ctx.hub_id, cfg).await? {
            let record_json = json!({
                "id": record_id,
                "record_type": r.record_type,
                "sequence_number": sequence_number,
                "issuer_nif": r.issuer_nif,
                "issuer_name": r.issuer_name,
                "invoice_number": r.invoice_number,
                "invoice_date": r.invoice_date,
                "invoice_type": r.invoice_type,
                "description": r.description,
                "tax_rate": r.tax_rate,
                "tax_breakdown": r.tax_breakdown,
                "base_amount": r.base_amount,
                "tax_amount": r.tax_amount,
                "total_amount": r.total_amount,
                "record_hash": record_hash,
                "previous_hash": previous_hash,
                "is_first_record": if is_first { 1 } else { 0 },
                "generation_timestamp": generation_timestamp,
                // Guard R4: `transmit_one` scopes its previous-link lookup by the record's
                // environment; the freshly built record carries the one resolved above.
                "environment": environment,
                "recipient_nif": r.recipient_nif,
                "recipient_name": r.recipient_name,
                "substitutes_number": r.substitutes_number,
                "substitutes_date": r.substitutes_date,
                "substitutes_nif": r.substitutes_nif,
                "rectifies_number": r.rectifies_number,
                "rectifies_date": r.rectifies_date,
                "rectifies_nif": r.rectifies_nif,
                "rectification_type": r.rectification_type,
                "rectified_base_amount": r.rectified_base_amount,
                "rectified_tax_amount": r.rectified_tax_amount,
                "rectified_surcharge_amount": r.rectified_surcharge_amount,
            });
            if let Ok((ops, events, _success)) =
                transmit_one(
                    host,
                    ctx,
                    &record_json,
                    cfg,
                    &ids[3],
                    &ids[4],
                    &ids[5],
                    // Alta recién creada: se remite en el momento, no sale de ninguna cola.
                    Remission::Punctual,
                )
                .await
            {
                for o in ops {
                    output = output.with_operation(o);
                }
                // A sale whose invoice the AEAT refused is the case verifactu#42 exists for: it
                // happens on the till, in front of nobody, and the audit row is on a screen.
                for e in events {
                    output = output.with_event(e);
                }
            }
        }
    }

    // El evento `verifactu.record.created` lo emite el `emit` declarado del command.
    Ok(output)
}

// ── transmit_record (issue verifactu#3) ──────────────────────────────────────

#[cfg(test)]
mod audit_message_keys {
    //! Cada fila de auditoría del motor fiscal lleva un CÓDIGO, no solo una frase (hub#1178).
    //!
    //! Todo el corpus de `verifactu_event.message` nace en español y en duro, y la pantalla
    //! **Eventos** del módulo lo pinta tal cual: un hub en catalán, gallego o inglés lee su
    //! auditoría fiscal en castellano. Va contra ADR-0055/0199 y es la misma familia que hub#1190
    //! (la pantalla no puede traducir lo que llega como prosa).
    //!
    //! El canal decidido es el que hub#1103 ya empezó con `details.scope`: **un código estable
    //! dentro de `details`** (`message_key`, espacio `verifactu.`) más los datos que la frase
    //! necesita, y el catálogo `en`+`es` en quien la pinta. `message` se queda como el respaldo
    //! honesto que hoy se lee — cambiarlo a inglés ANTES de que el módulo traduzca pondría inglés
    //! delante de un usuario español, que es justo el defecto de hub#1190.
    //!
    //! Esta guarda es de patrón, no de punto: barre el FUENTE. Un evento nuevo escrito sin su
    //! clave falla aquí, en vez de descubrirse cuando alguien abra el hub en otro idioma.

    /// The engine sources — the truth about which events the engine writes. `lib.rs`
    /// is an index since hub#1405, so the sweep reads the split modules instead;
    /// `records.rs` goes LAST because the self-exclusion filter below cuts everything
    /// after this very mod's marker, and only `records.rs` contains it.
    fn engine_source() -> String {
        [
            include_str!("config.rs"),
            include_str!("diagnostics.rs"),
            include_str!("engine.rs"),
            include_str!("events.rs"),
            include_str!("ingest.rs"),
            include_str!("recovery.rs"),
            include_str!("transmission.rs"),
            include_str!("util.rs"),
            include_str!("validation.rs"),
            include_str!("records.rs"),
        ]
        .concat()
    }

    /// The command every audit row goes through.
    const INSERT_EVENT: &str = "\"verifactu._insert_event\"";

    #[test]
    fn every_verifactu_event_carries_a_stable_message_key_hub1178() {
        let source = engine_source();
        let sites: Vec<usize> = source
            .match_indices(INSERT_EVENT)
            .map(|(at, _)| at)
            .filter(|at| source[..*at].rfind("mod audit_message_keys").is_none())
            .collect();
        assert!(
            sites.len() >= 12,
            "el barrido encontró solo {} sitios de `verifactu._insert_event`: ha dejado de casar \
             con la forma del fichero",
            sites.len()
        );

        for at in sites {
            // El payload del evento va desde el nombre del command hasta su `timestamp`, que es la
            // última clave de todos ellos.
            let rest = &source[at..];
            let end = rest
                .find("\"timestamp\"")
                .expect("todo evento persiste su instante");
            let payload = &rest[..end];
            let line = source[..at].lines().count();
            assert!(
                payload.contains(&format!("details_{}(", "for")),
                "el evento de la línea {line} escribe su `details` sin clave de mensaje: la \
                 pantalla de Eventos solo podrá repetir la frase castellana del motor (hub#1178)"
            );
        }
    }

    /// Y la clave que se escribe es de VERDAD un código estable, no una frase disfrazada.
    #[test]
    fn a_message_key_is_a_stable_code_in_the_verifactu_namespace_hub1178() {
        // La aguja se compone en tiempo de ejecución para que ESTE fichero no la contenga
        // literalmente: si no, el barrido se contaría a sí mismo.
        let needle = format!("details_{}(", "for");
        // De cada llamada se leen TODAS las claves de su primer argumento: dos de los eventos
        // eligen la suya según el veredicto (`if valid { … } else { … }`), y las dos cuentan.
        let source = engine_source();
        let mut keys: Vec<&str> = Vec::new();
        for (at, _) in source.match_indices(needle.as_str()) {
            let rest = &source[at + needle.len()..];
            // El primer argumento acaba donde empieza el segundo: o el `json!` de los datos, o la
            // variable `details` que dos de los sitios ya tenían construida. Se toma el que llegue
            // antes; sin ninguno, un tramo corto acotado.
            let arg_end = [rest.find("json!"), rest.find("details,")]
                .into_iter()
                .flatten()
                .min()
                .unwrap_or(rest.len().min(400));
            let mut slice = &rest[..arg_end];
            while let Some(open) = slice.find('"') {
                let after = &slice[open + 1..];
                let close = match after.find('"') {
                    Some(i) => i,
                    None => break,
                };
                keys.push(&after[..close]);
                slice = &after[close + 1..];
            }
        }
        assert!(keys.len() >= 12, "solo {} claves encontradas", keys.len());
        for key in keys {
            assert!(
                key.starts_with("verifactu."),
                "`{key}` no está en el espacio de nombres del módulo"
            );
            assert!(
                key[10..]
                    .chars()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_'),
                "`{key}` no es un código estable (se esperaba `verifactu.<snake_case>`)"
            );
        }
    }
}
