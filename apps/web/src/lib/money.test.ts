// hub#1090: el separador de millares del dinero. CLDR deja SIN agrupar los importes de 4 dígitos
// en español (`minimumGroupingDigits=2` → «1234,56 €»), pero la regla vinculante del CLAUDE.md
// raíz (estudio de mercado en la issue: Odoo, Dynamics BC, Shopify, WooCommerce, Holded, glibc,
// Excel y el comercio español agrupan desde 4) es agrupar SIEMPRE desde 4 dígitos: «1.234,56 €».
// En una columna de importes alineada a la derecha, 1234,56 y 12.345,60 no alinean sus separadores
// — el listado queda ilegible justo donde se revisa lo que sale del banco.
//
// `useGrouping: true` es la forma booleana del `'always'` de MDN (esta app tipa contra lib ES2022,
// donde la unión de strings aún no existe): fuerza el grupo aunque el locale prefiera lo contrario.
import { describe, expect, it } from 'vitest';

import { formatAmount, formatMoney } from './money';

// CLDR pone un ESPACIO INSEPARABLE (U+00A0) entre la cifra y el € en español — no un espacio
// normal. Pincharlo como código point evita el clásico «en mi editor se ve igual».
const NBSP = ' ';

describe('formatMoney — el separador de millares (hub#1090)', () => {
  it('es agrupa DESDE 4 dígitos, contra el minimumGroupingDigits=2 del CLDR', () => {
    expect(formatMoney(123456, { locale: 'es' })).toBe(`1.234,56${NBSP}€`);
  });

  it('es sigue agrupando de 5 en adelante (lo que ya hacía bien)', () => {
    expect(formatMoney(1234567, { locale: 'es' })).toBe(`12.345,67${NBSP}€`);
    expect(formatMoney(10011050, { locale: 'es' })).toBe(`100.110,50${NBSP}€`);
  });

  it('en agrupa desde 4 dígitos con coma (como ya hacía)', () => {
    expect(formatMoney(123456, { locale: 'en' })).toBe('€1,234.56');
  });

  it('los importes de 3 dígitos siguen sin llevar separador', () => {
    expect(formatMoney(10495, { locale: 'es' })).toBe(`104,95${NBSP}€`);
  });

  it('maximumFractionDigits se sigue respetando CON el grupo', () => {
    expect(formatMoney(123456, { locale: 'es', maximumFractionDigits: 0 })).toBe(`1.235${NBSP}€`);
  });

  it('la moneda cero-decimales no pinta decimales y también agrupa (JPY)', () => {
    // hub#2391: the scale is the one of the PAINTED currency (JPY → 0 decimals), not the hub's
    // (EUR here). The previous version of this case pinned 12345000 → 123450 ¥, i.e. ÷100 on a
    // currency without cents — the very bug of hub#2391.
    expect(formatMoney(123450, { currency: 'JPY', locale: 'es' })).toContain('123.450');
    expect(formatMoney(123450, { currency: 'JPY', locale: 'es' })).not.toContain(',');
  });
});

describe('formatMoney — the minor units belong to the painted currency (hub#2391)', () => {
  // No hub settings → the hub works in EUR (2 decimals).
  it('JPY on a euro hub is not divided by 100', () => {
    expect(formatMoney(1999, { currency: 'JPY', locale: 'en' })).toBe('¥1,999');
  });

  it('KWD on a euro hub keeps its three decimals', () => {
    expect(formatMoney(12345, { currency: 'KWD', locale: 'en' })).toBe(`KWD${NBSP}12.345`);
  });

  it('without currency, the hub currency and its scale', () => {
    expect(formatMoney(1999, { locale: 'en' })).toBe('€19.99');
  });
});

describe('formatAmount — mismas reglas en unidades mayores', () => {
  it('es agrupa desde 4 dígitos (KPIs del dashboard, totales del Cloud)', () => {
    expect(formatAmount(1234.5, { locale: 'es' })).toBe(`1.234,50${NBSP}€`);
  });

  it('es agrupa los millones igual que los millares', () => {
    expect(formatAmount(1234567.89, { locale: 'es' })).toBe(`1.234.567,89${NBSP}€`);
  });
});
