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
 * Lo que pide un hub nuevo, y también lo que se supone mientras los settings no han llegado.
 *
 * **No cuatro**: un teclado que pinta cuatro casillas y luego rechaza el PIN es peor que uno que
 * espera, porque el error aparece en caja y con cola. Seis es lo que estrena un hub nuevo (Clover lo
 * exige a los comercios nuevos desde abril de 2026), así que es también la suposición honesta.
 */
export const DEFAULT_PIN_LENGTH = 6;

/** La longitud vigente: la del hub si es una de las dos, el default si no hay o no se entiende. */
export const hubPinLength = computed<number>(() => {
  const declared = hubSettings.value?.pin_length;
  return PIN_LENGTHS.includes(declared as (typeof PIN_LENGTHS)[number])
    ? (declared as number)
    : DEFAULT_PIN_LENGTH;
});
