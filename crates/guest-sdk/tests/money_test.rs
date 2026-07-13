//! Contrato de la ARITMÉTICA DEL DINERO de ERPlora (ADR-0123). Una sola implementación, aquí.
//!
//! Antes esto vivía copiado en **7 handlers**. Los cinco `round_cents` de `sales`, `kitchen`,
//! `invoice`, `cart_checkout` y `services` eran **byte a byte idénticos** (half-even sobre `f64`) y
//! `pricing` iba por su cuenta (`rust_decimal`, HALF_UP). Nadie decidió mal el redondeo: es que
//! **cada uno lo decidió por su cuenta**. Estos tests fijan el contrato único.
//!
//! Las dos cosas que cambian respecto a lo que hacía `sales`, y que son la razón de ser de esto:
//!
//! 1. **HALF_UP, no half-even.** Ninguna norma española fija el modo (LIVA, RD 1619/2012,
//!    RD 1007/2023 y Orden HAC/1177/2024 no lo mencionan; el TJUE lo deja a cada Estado y España no
//!    ejerció la opción). La **única** regla de redondeo monetario escrita en Derecho español es
//!    half-up: art. 11 de la Ley 46/1998 del euro.
//! 2. **La cuota se redondea UNA vez por TIPO IMPOSITIVO, no por línea.** Es la única granularidad
//!    que el XML de VeriFactu sabe representar (`DetalleDesglose` es por tipo, máx. 12 — no hay
//!    detalle por artículo), y el TEAC (RG 2233/2022) censura el redondeo producto a producto.

use erplora_guest_sdk::money::{
    from_json, mul_qty, percent_of, rate_from_json, round, split_tax_included, Minor, TaxBreakdown,
};
use rust_decimal::Decimal;
use rust_decimal_macros::dec;
use serde_json::json;

// ── El redondeo: UN modo, y es HALF_UP ──────────────────────────────────────────────────
#[test]
fn redondea_half_up_no_half_even() {
    // Aquí es donde se separa de lo que hacían los 5 handlers viejos: con la fracción justo en el
    // medio, half-even va "al par" (0,5→0 · 2,5→2) y half-up siempre hacia arriba.
    assert_eq!(round(dec!(0.5)), 1);
    assert_eq!(round(dec!(1.5)), 2);
    assert_eq!(round(dec!(2.5)), 3, "half-even habría dicho 2");
    assert_eq!(round(dec!(149.3)), 149);
    assert_eq!(round(dec!(149.5)), 150);
}

#[test]
fn el_medio_centimo_negativo_se_aleja_del_cero() {
    assert_eq!(round(dec!(-0.5)), -1);
    assert_eq!(round(dec!(-2.5)), -3);
}

// ── El dinero entra ENTERO; una tasa NO ─────────────────────────────────────────────────
#[test]
fn from_json_lee_centimos_enteros() {
    assert_eq!(from_json(&json!(1493), 0), 1493);
    assert_eq!(from_json(&json!("1493"), 0), 1493);
    assert_eq!(from_json(&json!(null), 7), 7, "ausente → el default");
}

#[test]
fn from_json_redondea_un_decimal_colado_en_vez_de_truncarlo() {
    // El schema ya lo rechaza (`"type": "integer"`, ADR-0123), pero si algo se cuela por otra vía
    // que no acabe valiendo MENOS en silencio, que es como se pierde dinero.
    assert_eq!(from_json(&json!(149.6), 0), 150);
}

#[test]
fn una_tasa_conserva_sus_decimales() {
    // Pasar un 21,5 % por la función del DINERO lo dejaría en 22 %. Una tasa no es dinero.
    assert_eq!(rate_from_json(&json!(21.5), Decimal::ZERO), dec!(21.5));
    assert_eq!(rate_from_json(&json!(10), Decimal::ZERO), dec!(10));
}

// ── precio × cantidad (la cantidad SÍ es fraccionable) ──────────────────────────────────
#[test]
fn multiplica_por_una_cantidad_fraccionable() {
    assert_eq!(mul_qty(240, dec!(1.5)), 360, "1,5 kg a 2,40 €/kg");
    assert_eq!(mul_qty(121, dec!(3)), 363, "3 cafés de 1,21 €");
    assert_eq!(mul_qty(1000, dec!(0.333)), 333, "0,333 kg a 10 €/kg");
}

// ── porcentajes ─────────────────────────────────────────────────────────────────────────
#[test]
fn calcula_un_porcentaje_de_un_importe() {
    assert_eq!(percent_of(1000, dec!(21)), 210);
    assert_eq!(percent_of(1493, dec!(10)), 149); // 149,3 → 149
    assert_eq!(percent_of(1495, dec!(10)), 150); // 149,5 → 150 (half-up)
}

// ── IVA INCLUIDO: la cuota va POR DIFERENCIA ────────────────────────────────────────────
#[test]
fn iva_incluido_base_mas_cuota_es_exactamente_lo_cobrado() {
    let (base, cuota) = split_tax_included(121, dec!(21));
    assert_eq!((base, cuota), (100, 21), "un café de 1,21 € con 21 % incluido");
    assert_eq!(base + cuota, 121, "lo que hay en el cajón debe cuadrar al céntimo");
}

#[test]
fn iva_incluido_cuadra_siempre_no_por_casualidad() {
    // Si base y cuota se redondearan por separado, a veces sumarían un céntimo de más o de menos
    // que lo cobrado. El contrato es que SIEMPRE sumen — por eso la cuota es `total − base`.
    for total in 1..=1000 {
        let (base, cuota) = split_tax_included(total, dec!(21));
        assert_eq!(base + cuota, total, "descuadre en {total} cts");
    }
    for total in 1..=1000 {
        let (base, cuota) = split_tax_included(total, dec!(10));
        assert_eq!(base + cuota, total, "descuadre al 10 % en {total} cts");
    }
}

// ── El desglose de la AEAT: UNA cuota por TIPO ──────────────────────────────────────────
#[test]
fn el_desglose_declara_una_base_y_una_cuota_por_tipo() {
    let mut b = TaxBreakdown::new();
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(333));
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(333));
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(333));

    let cerrado = b.close();
    assert_eq!(cerrado.len(), 1, "un solo DetalleDesglose por tipo impositivo");
    assert_eq!(cerrado[0], (Rate::from_percent(dec!(21)), Money::from_minor(999), Money::from_minor(210)));
}

#[test]
fn redondear_por_linea_y_por_tipo_DIFIEREN_y_manda_el_de_por_tipo() {
    // Esta es la razón de ser del cambio. Cuatro líneas de base 12 cts al 21 %:
    //   · por LÍNEA (lo que hacía sales): round(2,52) = 3, cuatro veces → 12 cts de cuota.
    //   · por TIPO   (lo que va al XML):  round(48 × 0,21) = round(10,08) → 10 cts.
    // Dos céntimos de diferencia, y el bueno es 10: es lo que se declara a la AEAT.
    let mut b = TaxBreakdown::new();
    for _ in 0..4 {
        b.add(Rate::from_percent(dec!(21)), Money::from_minor(12));
    }
    assert_eq!(b.total_base().minor(), 48);
    assert_eq!(b.total_tax().minor(), 10, "la cuota se calcula sobre la base AGREGADA");

    let por_linea: Minor = (0..4).map(|_| percent_of(12, dec!(21))).sum();
    assert_eq!(por_linea, 12, "esto es lo que salía antes");
    assert_ne!(por_linea, b.total_tax().minor(), "y por eso había que centralizarlo");
}

#[test]
fn varios_tipos_conviven_y_el_total_cuadra_por_construccion() {
    // El ticket de un bar: comida al 10 %, alcohol al 21 %.
    let mut b = TaxBreakdown::new();
    b.add(Rate::from_percent(dec!(10)), Money::from_minor(1000));
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(200));
    b.add(Rate::from_percent(dec!(10)), Money::from_minor(500));

    let cerrado = b.close();
    assert_eq!(cerrado.len(), 2, "un detalle por TIPO, no por línea");
    assert_eq!(cerrado[0], (Rate::from_percent(dec!(10)), Money::from_minor(1500), Money::from_minor(150)));
    assert_eq!(cerrado[1], (Rate::from_percent(dec!(21)), Money::from_minor(200), Money::from_minor(42)));

    assert_eq!(b.total_base().minor(), 1700);
    assert_eq!(b.total_tax().minor(), 192);
    assert_eq!(b.total().minor(), 1892, "base + cuota, sin depender de la tolerancia de ±10 € de la AEAT");
}

#[test]
fn un_desglose_vacio_no_revienta() {
    let b = TaxBreakdown::new();
    assert_eq!(b.close().len(), 0);
    assert_eq!(b.total().minor(), 0);
}

// ── El desglose tiene DOS modos, porque hay dos formas de vender ─────────────────────────
//
// · IVA NO incluido (B2B, factura): el precio es la BASE y el IVA se suma encima.
//     base = Σ líneas · cuota = round(base × tipo) · total = base + cuota
// · IVA INCLUIDO (TPV B2C, art. 88.Uno LIVA): el precio ES lo que paga el cliente, y la base se
//   saca de dentro.
//     total = Σ líneas · base = round(total / (1+tipo)) · cuota = total − base
//
// Mezclar los dos en el mismo acumulador daría un desglose sin sentido: por eso el modo es del
// desglose, no de cada `add`.
#[test]
fn iva_incluido_el_desglose_saca_la_base_de_dentro_y_el_total_no_se_mueve() {
    // Tres cervezas de 2,50 € (IVA 21 % YA incluido). El cliente paga 7,50 € y no un céntimo más.
    let mut b = TaxBreakdown::tax_included();
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(250));
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(250));
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(250));

    let cerrado = b.close();
    assert_eq!(cerrado.len(), 1);
    let (rate, base, cuota) = cerrado[0];
    assert_eq!(rate, Rate::from_percent(dec!(21)));
    assert_eq!((base + cuota).minor(), 750, "lo que el cliente paga NO puede cambiar por el redondeo");
    assert_eq!(b.total().minor(), 750);
    assert_eq!((base.minor(), cuota.minor()), (620, 130)); // 750 / 1,21 = 619,83… → 620; cuota = el resto
}

#[test]
fn iva_no_incluido_el_desglose_suma_el_impuesto_encima() {
    let mut b = TaxBreakdown::new();
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(1000)); // 10,00 € de BASE
    let cerrado = b.close();
    assert_eq!(cerrado[0], (Rate::from_percent(dec!(21)), Money::from_minor(1000), Money::from_minor(210)));
    assert_eq!(b.total().minor(), 1210, "aquí el total SÍ crece: el IVA va encima");
}

#[test]
fn el_ticket_de_un_bar_con_dos_tipos_e_iva_incluido_cuadra_al_centimo() {
    // Menú 12,00 € (10 %) + cerveza 2,50 € (21 %) + café 1,30 € (10 %). Total cobrado: 15,80 €.
    let mut b = TaxBreakdown::tax_included();
    b.add(Rate::from_percent(dec!(10)), Money::from_minor(1200));
    b.add(Rate::from_percent(dec!(21)), Money::from_minor(250));
    b.add(Rate::from_percent(dec!(10)), Money::from_minor(130));

    let cerrado = b.close();
    assert_eq!(cerrado.len(), 2, "un DetalleDesglose por tipo, no por artículo");
    assert_eq!(b.total().minor(), 1580, "el ImporteTotal es exactamente lo cobrado");
    // Y base+cuota de cada tipo suma su bruto: 1330 (10 %) + 250 (21 %) = 1580.
    assert_eq!((cerrado[0].1 + cerrado[0].2).minor(), 1330);
    assert_eq!((cerrado[1].1 + cerrado[1].2).minor(), 250);
}

// ── La frontera EUROS → CÉNTIMOS ────────────────────────────────────────────────────────
#[test]
fn euros_a_centimos_es_una_funcion_con_nombre_no_un_x100_suelto() {
    use erplora_guest_sdk::money::euros_to_cents;

    // Las denominaciones físicas de la caja son etiquetas en EUROS ("50", "0.50"): entran por aquí.
    assert_eq!(euros_to_cents(dec!(50)), 5000);
    assert_eq!(euros_to_cents(dec!(0.50)), 50);
    assert_eq!(euros_to_cents(dec!(0.01)), 1);
    // Y el céntimo no se pierde: en `f64`, 0.29 * 100 = 28.999… → 28. En Decimal, 29.
    assert_eq!(euros_to_cents(dec!(0.29)), 29);
    assert_eq!(euros_to_cents(dec!(2.20)), 220);
}

// ── El importe de una LÍNEA: precio × cantidad − descuento, con UN solo redondeo ─────────
#[test]
fn el_importe_de_linea_se_redondea_una_sola_vez() {
    use erplora_guest_sdk::money::line_amount;

    // 3 cafés de 1,21 €, sin descuento.
    assert_eq!(line_amount(121, dec!(3), Decimal::ZERO), 363);
    // 1,5 kg a 2,40 €/kg con 10 % de descuento: 240 × 1,5 × 0,9 = 324
    assert_eq!(line_amount(240, dec!(1.5), dec!(10)), 324);
    // Redondear el descuento ANTES de multiplicar daría otro número: es el error que evita.
    // 0,99 € × 3 con 33 % dto: exacto = 99 × 3 × 0,67 = 199,0 -> 199.
    // (Si se redondeara el unitario descontado: round(99×0,67)=round(66,33)=66 → 66×3 = 198.)
    assert_eq!(line_amount(99, dec!(3), dec!(33)), 199);
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// LOS NEWTYPES: que el COMPILADOR impida confundir las tres magnitudes
//
// `pub type Minor = i64` es un ALIAS, y un alias no protege de nada: el compilador deja pasar
// tranquilamente un stock, una cantidad o un tipo de IVA donde se espera dinero — son todos `i64`.
// O sea, el tipo que había NO impedía el siguiente bug de unidades, que es justo la familia de bugs
// que ADR-0123 vino a matar.
//
// `Money`, `Rate` y `Qty` son tipos DISTINTOS. `total + tax_rate` deja de compilar.
// ═══════════════════════════════════════════════════════════════════════════════════════
use erplora_guest_sdk::money::{Money, Qty, Rate};

#[test]
fn money_es_un_importe_y_sabe_sumarse_consigo_mismo() {
    let a = Money::from_minor(1493);
    let b = Money::from_minor(507);
    assert_eq!((a + b).minor(), 2000);
    assert_eq!((a - b).minor(), 986);
    assert_eq!(Money::ZERO.minor(), 0);
}

#[test]
fn una_tasa_multiplicada_por_dinero_PRODUCE_dinero_pero_no_ES_dinero() {
    let total = Money::from_minor(1000);
    let iva = Rate::from_percent(dec!(21));
    assert_eq!(total.percent_of(iva).minor(), 210);
}

#[test]
fn una_cantidad_multiplicada_por_un_precio_produce_dinero() {
    let precio = Money::from_minor(240); // 2,40 €/kg
    let peso = Qty::from_decimal(dec!(1.5)); // 1,5 kg
    assert_eq!(precio.mul(peso).minor(), 360);
}

#[test]
fn el_importe_de_linea_con_los_tres_tipos_en_su_sitio() {
    let unit = Money::from_minor(99);
    let qty = Qty::from_decimal(dec!(3));
    let disc = Rate::from_percent(dec!(33));
    assert_eq!(Money::line(unit, qty, disc).minor(), 199);
}

#[test]
fn el_iva_incluido_devuelve_DOS_importes_no_un_par_de_i64_sueltos() {
    let (base, cuota) = Money::from_minor(121).split_tax_included(Rate::from_percent(dec!(21)));
    assert_eq!((base.minor(), cuota.minor()), (100, 21));
    assert_eq!((base + cuota).minor(), 121);
}

#[test]
fn una_suma_de_importes_sigue_siendo_un_importe() {
    let lineas = [Money::from_minor(121), Money::from_minor(110), Money::from_minor(250)];
    let total: Money = lineas.into_iter().sum();
    assert_eq!(total.minor(), 481);
}

#[test]
fn la_frontera_de_la_moneda_esta_en_el_tipo() {
    // 19,99 en EUR (2 decimales) → 1999 unidades mínimas.
    assert_eq!(Money::from_major(dec!(19.99), 2).minor(), 1999);
    // 1999 en JPY (0 decimales) → 1999 unidades mínimas. NO 199900.
    assert_eq!(Money::from_major(dec!(1999), 0).minor(), 1999);
    assert_eq!(Money::from_minor(1999).to_major(0), dec!(1999));
}
