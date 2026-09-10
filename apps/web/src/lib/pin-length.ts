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
 * Lo que vale la respuesta de un hub sobre su longitud de PIN: el valor si es una de las dos que
 * ofrece el mercado, y `fallback` para cualquier otra cosa (ausente, `'6'`, 5, `null`).
 *
 * El conjunto es CERRADO a propósito, y aquí importa más que en la mayoría de normalizaciones: el
 * teclado **envía en el último círculo**, así que la longitud no decide cuántos puntos se pintan
 * sino cuándo se manda el PIN. Una longitud que nadie puede teclear deja el teclado esperando un
 * dígito que no llega — una caja que no abre.
 */
export function normalizePinLength(value: unknown, fallback: number = DEFAULT_PIN_LENGTH): number {
  if (PIN_LENGTHS.includes(value as (typeof PIN_LENGTHS)[number])) return value as number;
  return PIN_LENGTHS.includes(fallback as (typeof PIN_LENGTHS)[number])
    ? fallback
    : DEFAULT_PIN_LENGTH;
}

/** La longitud vigente: la del hub si es una de las dos, el default si no hay o no se entiende. */
export const hubPinLength = computed<number>(() => normalizePinLength(hubSettings.value?.pin_length));
