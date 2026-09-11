// Cuántos dígitos pide el PIN de ESTE hub (hub#974).
//
// Decisión de mercado (9 referencias + foros, tabla en la issue): gana el modelo de Clover —
// longitud **fija por cuenta**, 4 o 6, con 6 en las altas nuevas. La uniformidad no es un capricho:
// es lo que permite que el teclado **envíe solo al último dígito**. Los productos que admiten
// longitud variable (Toast 3-8, Lightspeed K 4-6, Shopify 4-6) están obligados a poner un botón de
// confirmar, y un cajero que ficha decenas de veces al día paga ese toque extra decenas de veces al
// día. Cinco o siete dígitos no los ofrece nadie.
import { computed } from 'vue';

import { hubSettings } from './hub-settings';

/** Las dos longitudes que ofrece el mercado — espejo de `pin_policy::PIN_LENGTHS` del runtime. */
export const PIN_LENGTHS = [4, 6] as const;

/**
 * Lo que se supone mientras el hub no ha dicho nada: 4, espejo del default del runtime
 * (`pin_policy::DEFAULT_PIN_LENGTH`). Es compatibilidad — la longitud con la que se tecleaban todos
 * los PIN que hoy funcionan—, no la recomendación: **un hub nuevo se crea con 6**, y ese 6 lo
 * escribe el aprovisionamiento, que es el único que sabe que el hub es nuevo.
 */
export const DEFAULT_PIN_LENGTH = 4;

/**
 * What a hub's answer about its PIN length is worth: the value itself when it is one of the two the
 * market offers, and `fallback` for anything else (missing, `'6'`, 5, `null`).
 *
 * The set is CLOSED on purpose, and it matters more here than in most normalisations: the keypad
 * **submits on the last circle**, so the length does not decide how many dots are painted but when
 * the PIN is sent. A length nobody can type leaves the keypad waiting for a digit that never
 * arrives — a till that does not open.
 */
export function normalizePinLength(value: unknown, fallback: number = DEFAULT_PIN_LENGTH): number {
  if (PIN_LENGTHS.includes(value as (typeof PIN_LENGTHS)[number])) return value as number;
  return PIN_LENGTHS.includes(fallback as (typeof PIN_LENGTHS)[number])
    ? fallback
    : DEFAULT_PIN_LENGTH;
}

/** The length in force: this hub's when it is one of the two, the default when missing or unreadable. */
export const hubPinLength = computed<number>(() => normalizePinLength(hubSettings.value?.pin_length));
