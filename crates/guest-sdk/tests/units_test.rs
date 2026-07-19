//! Contrato de la CANTIDAD (ADR-0147).
//!
//! Una cantidad es un **valor decimal exacto expresado en una unidad de medida**. No es «un entero
//! de unidades mínimas»: 0,5 kg *es* medio kilo. El entero es solo cómo se persiste.
//!
//! * **Representación** — punto fijo con **escala GLOBAL de 6 decimales**, igual en SQLite y en
//!   Postgres. Nunca `REAL`/`FLOAT`/`DOUBLE`: `2.675 == 2.6749999999999998` y
//!   `8 % 1.6 = 1.5999999999999996` son la clase de problema que esto no gestiona, sino que no tiene.
//! * **Incremento** — el escalón permitido de la unidad (pieza `1`, kg `0,001`, hora `0,25`). Es una
//!   **validación**, no una instrucción de redondeo.
//! * **Factor** — fracción EXACTA `numerador/denominador` (1 t = 1000/1 kg · 1 min = 1/60 h), nunca
//!   un decimal aproximado.
//! * **Precio** — importe entero por una **cantidad de precio** (modelo `KPEIN` de SAP): «0,37 € por
//!   100 ud», no 0,0037 €/ud. El dinero sigue siendo entero de la unidad mínima (ADR-0123).
//!
//! Nada de `major`/`minor` en cantidades: ese vocabulario es del dinero, y mezclarlo fue justo el
//! error de la primera versión de este contrato.

use erplora_guest_sdk::units::{
    calculate_line_amount, convert_quantity_exact, format_quantity, parse_quantity,
    validate_increment, validate_unit_config, ConversionFactor, QuantityError, QuantityIncrement,
    QuantityValue, QUANTITY_SCALE,
};

/// Cantidad literal en unidades enteras (2 ud → 2_000_000).
fn q(units: i64) -> QuantityValue {
    QuantityValue::from_raw(units * QUANTITY_SCALE)
}

const INC_MILESIMA: QuantityIncrement = QuantityIncrement { value: 1_000 }; // 0,001
const INC_PIEZA: QuantityIncrement = QuantityIncrement { value: QUANTITY_SCALE }; // 1
const INC_CUARTO: QuantityIncrement = QuantityIncrement { value: 250_000 }; // 0,25

// ── 1. Representación exacta ────────────────────────────────────────────────────────────
#[test]
fn media_racion_de_gambas_se_representa_exactamente() {
    // El caso que abrió todo esto: `as_i64(0.5)` daba 0 y el stock no se descontaba.
    let medio_kilo = parse_quantity("0.5").expect("0,5 es una cantidad válida");
    assert_eq!(medio_kilo.raw(), 500_000);
    assert_eq!(format_quantity(medio_kilo), "0.5");

    let dos_y_medio = parse_quantity("2.5").unwrap();
    assert_eq!(dos_y_medio.raw(), 2_500_000);
    assert_eq!(format_quantity(dos_y_medio), "2.5");
}

#[test]
fn dos_canas_son_dos() {
    let dos = parse_quantity("2").unwrap();
    assert_eq!(dos.raw(), 2_000_000);
    assert_eq!(format_quantity(dos), "2", "una cantidad entera se pinta sin decimales de adorno");
}

#[test]
fn mas_decimales_que_la_escala_global_se_rechazan() {
    // Séptimo decimal: no cabe en la escala. Aceptarlo y truncar sería reabrir la puerta.
    let r = parse_quantity("0.1234567");
    assert!(matches!(r, Err(QuantityError::NotRepresentable { .. })), "{r:?}");
}

// ── 2. El incremento es VALIDACIÓN, no redondeo ─────────────────────────────────────────
#[test]
fn veinte_minutos_contra_incrementos_de_cuarto_de_hora_se_rechaza() {
    // ADR-0147 §2.2: redondear 20 min a 15 o 30 modificaría CALLADAMENTE lo trabajado, el importe
    // y las estadísticas. Se rechaza y se nombra el problema.
    let veinte_min_en_horas = parse_quantity("0.333333").unwrap();
    let r = validate_increment(veinte_min_en_horas, INC_CUARTO);
    assert!(matches!(r, Err(QuantityError::OffGrid { .. })), "{r:?}");
}

#[test]
fn veinte_minutos_con_unidad_base_minuto_se_acepta() {
    // La configuración correcta cuando el negocio trabaja en minutos: unidad base minuto,
    // incremento 1 min. Nada de almacenar 0,333333 h.
    assert!(validate_increment(q(20), INC_PIEZA).is_ok());
}

#[test]
fn medio_kilo_cae_en_la_rejilla_de_milesimas() {
    assert!(validate_increment(parse_quantity("0.5").unwrap(), INC_MILESIMA).is_ok());
    // Pero una diezmilésima no: la báscula da gramos, no décimas de gramo.
    let r = validate_increment(parse_quantity("0.5001").unwrap(), INC_MILESIMA);
    assert!(matches!(r, Err(QuantityError::OffGrid { .. })), "{r:?}");
}

#[test]
fn el_error_de_rejilla_dice_cual_es_el_incremento() {
    // Un «cantidad inválida» a secas no le sirve a nadie en barra. El error tiene que permitir
    // decir «20 minutos no vale en una unidad configurada en incrementos de 15 minutos».
    let Err(QuantityError::OffGrid { value, increment }) =
        validate_increment(parse_quantity("0.333333").unwrap(), INC_CUARTO)
    else {
        panic!("debe ser OffGrid");
    };
    assert_eq!(value, 333_333);
    assert_eq!(increment, 250_000);
}

// ── 3. Conversión con fracción exacta ───────────────────────────────────────────────────
#[test]
fn una_tonelada_son_mil_kilos_sin_perdida() {
    let a_kilos =
        convert_quantity_exact(q(1), ConversionFactor { numerator: 1000, denominator: 1 })
            .expect("1 t → kg es exacta");
    assert_eq!(a_kilos.raw(), 1000 * QUANTITY_SCALE);
}

#[test]
fn una_conversion_que_no_divide_exacta_se_rechaza() {
    // 20 min → h es 1/3 periódico: no es representable con 6 decimales. Truncar a 0,333333 metería
    // un error silencioso en el importe y en el stock.
    let r = convert_quantity_exact(q(20), ConversionFactor { numerator: 1, denominator: 60 });
    assert!(matches!(r, Err(QuantityError::InexactConversion { .. })), "{r:?}");
}

#[test]
fn media_hora_si_convierte_exacta_a_minutos() {
    let media_hora = parse_quantity("0.5").unwrap();
    let a_minutos =
        convert_quantity_exact(media_hora, ConversionFactor { numerator: 60, denominator: 1 })
            .expect("0,5 h → 30 min es exacta");
    assert_eq!(a_minutos.raw(), 30 * QUANTITY_SCALE);
}

#[test]
fn una_conversion_que_desborda_se_rechaza_en_vez_de_dar_la_vuelta() {
    let enorme = QuantityValue::from_raw(i64::MAX / 2);
    let r =
        convert_quantity_exact(enorme, ConversionFactor { numerator: 1_000_000, denominator: 1 });
    assert!(matches!(r, Err(QuantityError::Overflow)), "{r:?}");
}

// ── 4. Precio: dinero entero por cantidad de precio (KPEIN) ─────────────────────────────
#[test]
fn doce_euros_el_kilo_por_medio_kilo_son_seis_euros() {
    // price = 1200 céntimos POR 1 kg; se venden 0,5 kg.
    let importe = calculate_line_amount(1200, parse_quantity("0.5").unwrap(), q(1)).unwrap();
    assert_eq!(importe, 600, "6,00 €");
}

#[test]
fn un_precio_sub_centimo_se_expresa_como_importe_por_cien_unidades() {
    // 0,0037 €/ud no es un entero de céntimos → rompería el contrato del dinero. SAP lo resuelve
    // con KPEIN: se guarda «0,37 € por 100 ud» y se divide TARDE, al calcular el importe.
    let mil_unidades = calculate_line_amount(37, q(1000), q(100)).unwrap();
    assert_eq!(mil_unidades, 370, "1000 ud a 0,37 €/100 ud = 3,70 €");

    // Y una sola unidad redondea a 0 céntimos, que es lo correcto: no se puede cobrar 0,0037 €.
    assert_eq!(calculate_line_amount(37, q(1), q(100)).unwrap(), 0);
}

#[test]
fn el_importe_redondea_half_up_una_sola_vez() {
    // ADR-0123, y una sola vez POR LÍNEA antes de sumar — nunca al total (patrón Stripe).
    let importe = calculate_line_amount(3, parse_quantity("0.5").unwrap(), q(1)).unwrap();
    assert_eq!(importe, 2, "3 × 0,5 = 1,5 → HALF_UP → 2");
}

#[test]
fn el_calculo_del_importe_no_desborda_en_silencio() {
    // La operación intermedia va en i128; si aun así no cabe, se dice.
    let r = calculate_line_amount(i64::MAX, q(1_000_000), QuantityValue::from_raw(1));
    assert!(matches!(r, Err(QuantityError::Overflow)), "{r:?}");
}

// ── 5. La unidad se valida al CONFIGURARLA, no al vender ────────────────────────────────
#[test]
fn una_unidad_bien_configurada_se_acepta() {
    // Tonelada: incremento 0,001 t, factor 1000/1 hacia kg (base con incremento 0,001 kg).
    // 0,001 t × 1000 = 1 kg → representable y múltiplo del incremento base. ✔
    let r = validate_unit_config(
        INC_MILESIMA,
        ConversionFactor { numerator: 1000, denominator: 1 },
        INC_MILESIMA,
    );
    assert!(r.is_ok(), "{r:?}");
}

#[test]
fn una_unidad_cuyo_incremento_no_cae_en_la_base_se_rechaza_al_crearla() {
    // Hora con incremento 0,01 h sobre una base en minutos con incremento 1 min:
    // 0,01 h × 60 = 0,6 min ✘ — no es múltiplo de 1 min. Hay que cazarlo al configurar la unidad,
    // no al cerrar una venta con el cliente delante.
    let centesima_de_hora = QuantityIncrement { value: 10_000 }; // 0,01
    let r = validate_unit_config(
        centesima_de_hora,
        ConversionFactor { numerator: 60, denominator: 1 }, // h → min
        INC_PIEZA,                                          // base: 1 min
    );
    assert!(matches!(r, Err(QuantityError::InvalidIncrement { .. })), "{r:?}");
}

#[test]
fn una_unidad_cuyo_incremento_no_es_representable_se_rechaza() {
    // Incremento que al convertir a la base necesitaría más de 6 decimales.
    let r = validate_unit_config(
        QuantityIncrement { value: 1 }, // 0,000001
        ConversionFactor { numerator: 1, denominator: 60 },
        QuantityIncrement { value: 1 },
    );
    assert!(r.is_err(), "una unidad así no se puede usar: {r:?}");
}

// ── 6. Ida y vuelta ─────────────────────────────────────────────────────────────────────
#[test]
fn parsear_y_pintar_no_pierde_nada() {
    for texto in ["0.5", "2.5", "0.001", "1000", "0.25", "123.456789"] {
        let parsed = parse_quantity(texto).unwrap_or_else(|e| panic!("{texto}: {e:?}"));
        assert_eq!(format_quantity(parsed), texto, "ida y vuelta de {texto}");
    }
}

#[test]
fn una_cantidad_negativa_se_admite_porque_un_movimiento_de_stock_resta() {
    // El ledger guarda deltas firmados: una venta es un movimiento negativo.
    let salida = parse_quantity("-0.5").unwrap();
    assert_eq!(salida.raw(), -500_000);
    assert_eq!(format_quantity(salida), "-0.5");
}
