//! **La aritmética del dinero de ERPlora. Una vez, aquí.**
//!
//! El dinero es un entero de **CÉNTIMOS** (ADR-0007). Ésta es la única implementación de su
//! aritmética, y la enlaza en build el handler WASM de cada módulo. No es un módulo instalable:
//! los handlers corren en sandbox y no pueden llamar código Rust de otro módulo, y además el dinero
//! **no es opcional** — si un hub pudiera desinstalarlo, `sales` dejaría de sumar. Mismo criterio
//! que «el asistente es core, no un módulo» (ADR-0033).
//!
//! # Por qué existe
//!
//! Antes esto vivía copiado en **7 handlers**. Los cinco `round_cents` de `sales`, `kitchen`,
//! `invoice`, `cart_checkout` y `services` eran **byte a byte idénticos** (half-even sobre `f64`) y
//! `pricing` iba por su cuenta (`rust_decimal`, HALF_UP). Nadie decidió mal el redondeo: **cada uno
//! lo decidió por su cuenta**. Con la aritmética copiada 7 veces, cambiar el modo significaba tocar
//! 7 ficheros y confiar en que nadie se desviara. Ahora es [`ROUNDING`], y es una constante.
//!
//! # Las tres magnitudes, que NO son la misma
//!
//! * **Money** — un importe. Céntimos, **entero**: el céntimo es la unidad mínima, medio céntimo no
//!   existe. → [`Cents`]
//! * **Rate** — una tasa (%). **Lleva decimales**: el 12,5 % existe. Multiplicada por dinero
//!   *produce* dinero; no *es* dinero.
//! * **Quantity** — una cantidad. **Lleva decimales**: 1,5 kg existe.
//!
//! Confundirlas es lo que produjo los bugs de ×100 (ADR-0123), así que aquí van con tipos distintos.
//!
//! # Nada de `f64`
//!
//! Los cálculos intermedios sí son fraccionarios (el 10 % de 1493 cts son 149,3) y se hacen con
//! `rust_decimal` — decimal **exacto**, no binario. El `f64` de antes obligaba a comparar con un
//! épsilon (`(diff - 0.5).abs() < 1e-9`) para *simular* el half-even: un parche sobre un tipo que ni
//! siquiera puede representar 0,1. Y no cuesta tamaño — el wasm de `pricing` **con** `rust_decimal`
//! (191 KB) pesa **menos** que el de `sales` **con** `f64` (263 KB).

use rust_decimal::prelude::{FromPrimitive, ToPrimitive};
use rust_decimal::{Decimal, RoundingStrategy};
use serde_json::Value;

/// Un importe: **entero de UNIDADES MÍNIMAS de la moneda del hub**.
///
/// NO son «céntimos»: la unidad mínima depende de la moneda (ISO-4217). `1499` son 14,99 € en EUR,
/// pero **1499 ¥** en JPY (0 decimales) y 1,499 KWD (3 decimales). El entero no significa nada sin
/// su moneda — ver [`crate::currency`].
pub type Minor = i64;

/// Alias histórico de [`Minor`]. El nombre mentía en cuanto el hub salía del euro.
#[deprecated(note = "usa `Minor`: la unidad mínima no siempre es el céntimo (JPY tiene 0 decimales)")]
pub type Cents = Minor;

/// **El modo de redondeo del sistema. Uno solo, y vive aquí.** (ADR-0123 §4)
///
/// **HALF_UP** (redondeo comercial: la mitad justa va hacia arriba).
///
/// Ninguna norma española fija el modo de redondeo de la cuota de IVA — verificado por ausencia en
/// LIVA (Ley 37/1992), RD 1619/2012, RD 1007/2023 y Orden HAC/1177/2024; y el TJUE (C-484/06,
/// C-302/07) lo deja a cada Estado, opción que España **no ha ejercido**. Pero la **única regla de
/// redondeo monetario escrita en Derecho español** es half-up: art. 11 de la Ley 46/1998 del euro
/// («si el resultado se sitúa exactamente en la mitad, el redondeo se efectuará a la cifra
/// superior»). Es lo que espera un auditor y lo que el cliente ve en el ticket.
///
/// Half-even (bancario), que es lo que hacían 5 handlers, **es legal** —nada lo prohíbe— pero se
/// aparta de ese criterio sin comprar nada: la AEAT tolera **±10 €** en `cuota = base × tipo`, así
/// que el sesgo estadístico da igual. Lo que importa aquí es **determinismo y coherencia**.
pub const ROUNDING: RoundingStrategy = RoundingStrategy::MidpointAwayFromZero;

/// Redondea a **céntimo entero**. Es el único punto del sistema donde el dinero pierde precisión.
pub fn round(x: Decimal) -> Minor {
    x.round_dp_with_strategy(0, ROUNDING).to_i64().unwrap_or(0)
}

/// Lee un **importe** del payload de un comando.
///
/// Con los schemas ya en `"type": "integer"` (ADR-0123) esto es casi una formalidad, pero acepta un
/// string de entero por robustez y, si se cuela un decimal por otra vía, lo **redondea** en vez de
/// truncarlo: un importe no puede valer menos en silencio.
pub fn from_json(v: &Value, default: Minor) -> Minor {
    match v {
        Value::Number(n) => n
            .as_i64()
            .or_else(|| n.as_f64().and_then(Decimal::from_f64).map(round))
            .unwrap_or(default),
        Value::String(s) => s
            .trim()
            .parse::<i64>()
            .ok()
            .or_else(|| s.trim().parse::<Decimal>().ok().map(round))
            .unwrap_or(default),
        _ => default,
    }
}

/// Lee una **tasa o una cantidad** (que NO son dinero) del payload.
///
/// Van por su propia puerta justamente para que nadie las pase por [`from_json`]: redondear un
/// 21,5 % a `22` es el bug que ADR-0123 persigue.
pub fn rate_from_json(v: &Value, default: Decimal) -> Decimal {
    match v {
        Value::Number(n) => n.as_f64().and_then(Decimal::from_f64).unwrap_or(default),
        Value::String(s) => s.trim().parse::<Decimal>().unwrap_or(default),
        _ => default,
    }
}

/// **Frontera 1 de 2: lo que teclea un humano → unidades mínimas.**
///
/// `decimals` son los de **la moneda del hub** ([`crate::currency::decimals_for`]), no un 2 fijo:
/// en JPY son **0** (1999 se teclea y se guarda como `1999` yenes, no como `199900`) y en KWD son
/// **3**. Un `* 100` clavado aquí cobra 100 veces mal en cuanto el hub sale del euro — y la app es
/// gratuita, así que sale.
///
/// Redondea (HALF_UP) a la unidad mínima: teclear más decimales de los que la moneda admite no
/// trunca en silencio. En `Decimal` es exacto; en `f64` no lo era (`0.29 * 100 = 28.999…` → 28).
pub fn major_to_minor(amount: Decimal, decimals: u32) -> Minor {
    round(amount * pow10(decimals))
}

/// **Frontera 2 de 2: unidades mínimas → lo que se le pinta a un humano.**
///
/// En EUR divide entre 100; en **JPY no divide** (la unidad mínima ES el yen); en KWD divide entre
/// 1000. Devuelve `Decimal` —no `f64`— para que el formateador no reintroduzca el error binario.
pub fn minor_to_major(amount: Minor, decimals: u32) -> Decimal {
    Decimal::from(amount) / pow10(decimals)
}

/// `10^n` como `Decimal` exacto (n ≤ 4 por ISO-4217; se capa por seguridad).
fn pow10(n: u32) -> Decimal {
    Decimal::from(10_i64.pow(n.min(9)))
}

/// La frontera euros→céntimos de siempre, para la moneda de 2 decimales.
///
/// **Prefiere [`major_to_minor`]** con los decimales de la moneda del hub: esta función asume EUR y
/// es exactamente la suposición que rompe en un hub en yenes. Se mantiene por comodidad en los
/// sitios donde la moneda es EUR **por contrato** (p. ej. la fiscalidad española de VeriFactu).
pub fn euros_to_cents(euros: Decimal) -> Minor {
    major_to_minor(euros, 2)
}

/// `precio × cantidad`. La cantidad es fraccionable (1,5 kg); el resultado es dinero → céntimo entero.
pub fn mul_qty(price: Minor, qty: Decimal) -> Minor {
    round(Decimal::from(price) * qty)
}

/// El `pct` % de un importe: descuentos, y la cuota de un IVA **no** incluido.
pub fn percent_of(amount: Minor, pct: Decimal) -> Minor {
    round(Decimal::from(amount) * pct / Decimal::from(100))
}

/// El importe de una **línea**: `precio × cantidad − descuento`, con **un solo redondeo**, al final.
///
/// Redondear el unitario ya descontado y multiplicar después daría otro número (0,99 € × 3 con un
/// 33 % de descuento: 199 cts haciéndolo bien, 198 redondeando antes). El céntimo se pierde una vez
/// y solo una: aquí.
pub fn line_amount(unit_price: Minor, qty: Decimal, discount_pct: Decimal) -> Minor {
    let factor = Decimal::ONE - discount_pct / Decimal::from(100);
    round(Decimal::from(unit_price) * qty * factor)
}

/// **IVA INCLUIDO** (el caso del TPV B2C, art. 88.Uno LIVA): del total que paga el cliente, saca
/// `(base, cuota)`.
///
/// La **cuota va POR DIFERENCIA** (`total − base`), no redondeando `base × tipo` por separado: así
/// `base + cuota` es **exactamente** lo cobrado, al céntimo. Redondeando las dos por separado, a
/// veces sumarían un céntimo de más o de menos que lo que hay en el cajón.
pub fn split_tax_included(total: Minor, rate_pct: Decimal) -> (Minor, Minor) {
    let divisor = Decimal::ONE + rate_pct / Decimal::from(100);
    if divisor.is_zero() {
        return (total, 0);
    }
    let base = round(Decimal::from(total) / divisor);
    (base, total - base)
}

/// El **desglose por TIPO IMPOSITIVO** — lo que acaba en el XML de VeriFactu.
///
/// Acumula el importe de cada línea **sin redondear la cuota**, y la calcula y redondea **una sola
/// vez por tipo**, al cerrar. Redondear por línea y sumar acumula error (lo que censura el TEAC,
/// RG 2233/2022) y, sobre todo, **el XML no tiene dónde meterlo**: `DetalleDesglose` es por tipo
/// impositivo (máx. 12), no por artículo.
///
/// # Dos modos, porque hay dos formas de vender
///
/// * [`TaxBreakdown::new`] — **IVA NO incluido** (B2B, factura): el precio de línea es la **base** y
///   el impuesto se suma encima. `cuota = round(base × tipo)`, `total = base + cuota`.
/// * [`TaxBreakdown::tax_included`] — **IVA INCLUIDO** (TPV B2C, art. 88.Uno LIVA): el precio de
///   línea **es lo que paga el cliente**, y la base se saca de dentro. `base = round(total/(1+tipo))`
///   y `cuota = total − base` → **lo cobrado no se mueve ni un céntimo** por culpa del redondeo.
///
/// El modo es del desglose entero, no de cada `add`: mezclarlos daría un desglose sin sentido.
#[derive(Debug, Default, Clone)]
pub struct TaxBreakdown {
    /// `true` = lo acumulado son TOTALES con IVA dentro; `false` = son BASES imponibles.
    included: bool,
    /// `(tipo, importe acumulado)`, en orden de aparición → salida determinista.
    lines: Vec<(Rate, Money)>,
}

impl TaxBreakdown {
    /// **IVA NO incluido**: lo que se acumula son BASES imponibles.
    pub fn new() -> Self {
        Self::default()
    }

    /// **IVA INCLUIDO**: lo que se acumula son TOTALES (lo que paga el cliente).
    pub fn tax_included() -> Self {
        Self { included: true, lines: Vec::new() }
    }

    /// Suma el importe de una línea al tipo que le toque. **No redondea la cuota**: eso pasa al
    /// cerrar, una vez por tipo. Según el modo, `amount` es una base o un total con IVA dentro.
    pub fn add(&mut self, rate: Rate, amount: Money) {
        match self.lines.iter_mut().find(|(r, _)| *r == rate) {
            Some((_, acc)) => *acc = *acc + amount,
            None => self.lines.push((rate, amount)),
        }
    }

    /// Cierra el desglose: `(tipo, base, cuota)` por tipo, con la cuota redondeada **una vez**.
    pub fn close(&self) -> Vec<(Rate, Money, Money)> {
        self.lines
            .iter()
            .map(|(rate, amount)| {
                if self.included {
                    let (base, tax) = amount.split_tax_included(*rate);
                    (*rate, base, tax)
                } else {
                    (*rate, *amount, amount.percent_of(*rate))
                }
            })
            .collect()
    }

    /// Suma de las bases imponibles (ya extraídas, si el IVA iba incluido).
    pub fn total_base(&self) -> Money {
        self.close().iter().map(|(_, b, _)| *b).sum()
    }

    /// Suma de las cuotas, redondeadas una vez por tipo.
    pub fn total_tax(&self) -> Money {
        self.close().iter().map(|(_, _, t)| *t).sum()
    }

    /// `base + cuota`. Cuadra **por construcción** con lo que se declara a la AEAT — no se apoya en
    /// la tolerancia de ±10 €. Con IVA incluido, es **exactamente** lo que el cliente paga.
    pub fn total(&self) -> Money {
        self.close().iter().map(|(_, b, t)| *b + *t).sum()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════════════════
// LOS TRES TIPOS — que el COMPILADOR impida confundirlos
//
// [`Minor`] es un ALIAS de `i64`, y un alias **no protege de nada**: el compilador deja pasar tan
// tranquilo un stock, una cantidad o un tipo de IVA donde se espera un importe — son todos `i64`.
// O sea: el tipo NO impide el próximo bug de unidades, que es justamente la familia de bugs que
// ADR-0123 vino a matar (un descuento de «5» que resultaron ser 5 céntimos y no 5 €).
//
// `Money`, `Rate` y `Qty` son tipos DISTINTOS, así que la confusión pasa de ser un bug silencioso
// en producción a un error de compilación:
//
// ```compile_fail
// use erplora_guest_sdk::money::{Money, Rate};
// use rust_decimal::Decimal;
// let total = Money::from_minor(1000);
// let iva = Rate::from_percent(Decimal::from(21));
// let _ = total + iva;   // ← NO COMPILA: una tasa no es un importe
// ```
//
// Una `Rate` multiplicada por dinero **produce** dinero; no **es** dinero. Una `Qty`, igual.
// ═══════════════════════════════════════════════════════════════════════════════════════════

use std::iter::Sum;
use std::ops::{Add, Neg, Sub};

/// Un **importe**: entero de unidades mínimas de la moneda del hub.
///
/// No se puede sumar a una tasa ni a una cantidad — **el compilador no te deja**, y eso es todo el
/// propósito del tipo. Sumar dos importes, sí:
///
/// ```
/// use erplora_guest_sdk::money::Money;
/// let total = Money::from_minor(1493) + Money::from_minor(507);
/// assert_eq!(total.minor(), 2000);
/// ```
///
/// Sumarle una TASA, no. Esto **no compila** (y ese es justo el bug que ADR-0123 vino a matar):
///
/// ```compile_fail
/// use erplora_guest_sdk::money::{Money, Rate};
/// use rust_decimal::Decimal;
/// let total = Money::from_minor(1000);
/// let iva = Rate::from_percent(Decimal::from(21));
/// let _ = total + iva;   // ← error[E0308]: una tasa no es un importe
/// ```
///
/// Ni una CANTIDAD. Tampoco compila:
///
/// ```compile_fail
/// use erplora_guest_sdk::money::{Money, Qty};
/// use rust_decimal::Decimal;
/// let precio = Money::from_minor(240);
/// let peso = Qty::from_decimal(Decimal::from(2));
/// let _ = precio + peso;   // ← error[E0308]: una cantidad no es un importe
/// ```
///
/// Lo que SÍ se puede es multiplicar: una tasa o una cantidad **producen** dinero, no **son** dinero.
///
/// ```
/// use erplora_guest_sdk::money::{Money, Qty, Rate};
/// use rust_decimal::Decimal;
/// let precio = Money::from_minor(240);                       // 2,40 €/kg
/// let peso = Qty::from_decimal(Decimal::new(15, 1));         // 1,5 kg
/// assert_eq!(precio.mul(peso).minor(), 360);                 // 3,60 €
/// assert_eq!(Money::from_minor(1000).percent_of(Rate::from_percent(Decimal::from(21))).minor(), 210);
/// ```
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, PartialOrd, Ord)]
pub struct Money(Minor);

/// Una **tasa** (%): 21, 12,5, 5,2. Lleva decimales. **No es dinero.**
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, PartialOrd, Ord)]
pub struct Rate(Decimal);

/// Una **cantidad**: 3 cafés, 1,5 kg, 0,333 l. Lleva decimales. **No es dinero.**
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Qty(Decimal);

impl Money {
    pub const ZERO: Money = Money(0);

    /// Desde unidades mínimas (lo que hay en la columna `INTEGER`).
    pub const fn from_minor(m: Minor) -> Self {
        Money(m)
    }
    /// A unidades mínimas (lo que se bindea a la columna `INTEGER`).
    pub const fn minor(self) -> Minor {
        self.0
    }

    /// Lee un importe del payload de un comando (ver [`from_json`]).
    pub fn from_json(v: &Value, default: Minor) -> Self {
        Money(from_json(v, default))
    }

    /// **Frontera:** lo que teclea un humano → importe. `decimals` son los de la moneda del hub
    /// ([`crate::currency::decimals_for`]) — en JPY son 0, no 2.
    pub fn from_major(amount: Decimal, decimals: u32) -> Self {
        Money(major_to_minor(amount, decimals))
    }
    /// **Frontera:** importe → lo que se le pinta a un humano.
    pub fn to_major(self, decimals: u32) -> Decimal {
        minor_to_major(self.0, decimals)
    }

    /// El `r` % de este importe (descuento, o cuota de un IVA no incluido).
    pub fn percent_of(self, r: Rate) -> Self {
        Money(percent_of(self.0, r.0))
    }

    /// Este importe × una cantidad. Un precio unitario por 1,5 kg.
    pub fn mul(self, q: Qty) -> Self {
        Money(mul_qty(self.0, q.0))
    }

    /// El importe de una **línea**: `precio × cantidad − descuento`, con **un solo redondeo**.
    pub fn line(unit: Money, q: Qty, disc: Rate) -> Self {
        Money(line_amount(unit.0, q.0, disc.0))
    }

    /// **IVA incluido**: de lo que paga el cliente, saca `(base, cuota)`. La cuota va por diferencia,
    /// así que `base + cuota` es **exactamente** este importe.
    pub fn split_tax_included(self, r: Rate) -> (Money, Money) {
        let (b, t) = split_tax_included(self.0, r.0);
        (Money(b), Money(t))
    }

    /// Capa a `[0, max]`. Un descuento no puede dejar un total negativo.
    pub fn clamp_to(self, max: Money) -> Self {
        Money(self.0.clamp(0, max.0))
    }

    pub const fn is_zero(self) -> bool {
        self.0 == 0
    }
}

impl Rate {
    pub const ZERO: Rate = Rate(Decimal::ZERO);

    pub const fn from_percent(pct: Decimal) -> Self {
        Rate(pct)
    }
    pub const fn percent(self) -> Decimal {
        self.0
    }
    /// Lee una tasa del payload. **No** pasa por la puerta del dinero: un 21,5 % redondeado a 22
    /// sería el bug de siempre.
    pub fn from_json(v: &Value, default: Decimal) -> Self {
        Rate(rate_from_json(v, default))
    }
    /// A `f64`, que es como se guarda en SQL (columna `REAL`: una tasa NO es dinero).
    pub fn to_f64(self) -> f64 {
        self.0.to_f64().unwrap_or(0.0)
    }
}

impl Qty {
    pub const ONE: Qty = Qty(Decimal::ONE);

    pub const fn from_decimal(q: Decimal) -> Self {
        Qty(q)
    }
    pub const fn value(self) -> Decimal {
        self.0
    }
    pub fn from_json(v: &Value, default: Decimal) -> Self {
        Qty(rate_from_json(v, default))
    }
    /// A `f64`, que es como se guarda en SQL (columna `REAL`: una cantidad NO es dinero).
    pub fn to_f64(self) -> f64 {
        self.0.to_f64().unwrap_or(0.0)
    }
}

// Sumar y restar IMPORTES entre sí: sí. Sumarles una tasa o una cantidad: no compila.
impl Add for Money {
    type Output = Money;
    fn add(self, o: Money) -> Money {
        Money(self.0 + o.0)
    }
}
impl Sub for Money {
    type Output = Money;
    fn sub(self, o: Money) -> Money {
        Money(self.0 - o.0)
    }
}
impl Neg for Money {
    type Output = Money;
    fn neg(self) -> Money {
        Money(-self.0)
    }
}
impl Sum for Money {
    fn sum<I: Iterator<Item = Money>>(it: I) -> Money {
        Money(it.map(|m| m.0).sum())
    }
}
