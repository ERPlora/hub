// **La plantilla del tique: dónde se configura de verdad** (hub#761).
//
// Ajustes → Tiques enseñaba una fila pintada como botón —«Plantilla de tique · Configuración del
// recibo impreso y digital»— **sin `@click`**. No navegaba ni explicaba nada: un callejón sin salida
// en la configuración más básica de un TPV, y de las que el dueño busca el primer día.
//
// El motivo por el que se quedó muerta es real, no un olvido: **esa configuración no vive en el
// shell**. Cabecera y pie del tique, ancho de papel, auto-impresión y qué impresora lo saca son
// ajustes del módulo `printing`. El shell no puede tener su propia pantalla sin duplicar el módulo,
// así que lo único que le toca es **resolver a dónde llevar** — y decir la verdad cuando la app no
// está instalada, que es el caso que convertía la fila en un botón mudo.
//
// Se resuelve contra `moduleNav` (lo que el RUNTIME reporta instalado en `GET /api/navigation`), no
// contra una lista fija: un hub sin `printing` es normal, no un error.

/** El módulo que posee la plantilla del tique. Un solo sitio donde se nombra. */
export const RECEIPT_TEMPLATE_MODULE = 'printing';

/**
 * Ruta de la pantalla de ajustes del módulo: su PRIMERA entrada de navegación
 * (`erp-printing-settings`), que es la misma que su manifest declara en `setup.route`.
 */
const MODULE_SETTINGS_ROUTE = `/m/${RECEIPT_TEMPLATE_MODULE}/${RECEIPT_TEMPLATE_MODULE}`;

/** Dónde se instalan las apps. El destino honesto cuando la que hace falta no está. */
const APPS_ROUTE = '/apps';

/** Lo mínimo que hace falta de `moduleNav`: la ruta con que el shell monta cada módulo. */
export interface InstalledModule {
  path: string;
}

export interface ReceiptTemplateTarget {
  /** A dónde lleva la fila. Siempre hay destino: nunca se vuelve a quedar muda. */
  route: string;
  /** `true` si falta la app que configura el tique — la vista lo dice, no lo esconde. */
  missingApp: boolean;
}

/**
 * A dónde debe llevar «Plantilla de tique», según lo que este hub tenga instalado.
 *
 * Comparación **exacta** de la ruta del módulo, no por prefijo: `/m/printing_labels` no es
 * `/m/printing`, y con un `startsWith` un módulo de etiquetas haría creer al shell que la plantilla
 * ya se puede configurar — la fila volvería a llevar a una pantalla que no existe.
 */
export function receiptTemplateTarget(installed: InstalledModule[] | undefined): ReceiptTemplateTarget {
  const present = (installed ?? []).some((m) => m?.path === `/m/${RECEIPT_TEMPLATE_MODULE}`);
  return present
    ? { route: MODULE_SETTINGS_ROUTE, missingApp: false }
    : { route: APPS_ROUTE, missingApp: true };
}
