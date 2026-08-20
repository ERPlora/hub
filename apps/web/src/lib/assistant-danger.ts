// Cuánto se le pide al usuario antes de dejar que el asistente destruya algo (hub#1042).
//
// La pasada de QA pidió «borra todas las citas de la agenda». No se borró ninguna — pero no por un
// control: el modelo improvisó una negativa y un turno después listó `bulk_delete` entre sus
// propias tools. Que no se borrara nada era una propiedad emergente de su criterio. Y el producto
// además LE MINTIÓ al usuario sobre sus defensas, que es peor que no tenerlas: quien lee «es una
// protección intencional» deja de tener cuidado.
//
// `ai.risk` lo declara el módulo y ya viaja hasta la tarjeta. Esto es la política que lo usa, y
// vive en el CORE: el módulo dice cuánto daño hace, el core decide cuánta fricción pone. Así el
// core no necesita saber qué es una cita.
//
// Las dos formas salen del mercado (tabla en la issue): la confirmación ESCRITA es el patrón de
// GitHub para borrar un repositorio, y enseñar el número afectado ANTES es lo que hacen BC (panel
// con las líneas resueltas, con `Delete Line` / `Discard` / `Keep it`) y SAP Joule (tarjeta con
// los datos y salida a Confirmar · Editar · Descartar).

export interface Confirmation {
  /** `click` = la tarjeta de siempre · `typed` = hay que escribir · `refuse` = no desde el chat. */
  kind: 'click' | 'typed' | 'refuse';
  /** Cuántos registros caen, cuando se puede saber. */
  affected?: number;
  /** Lo que el usuario tiene que escribir para que se ejecute. */
  expected?: string;
}

/** El array más largo del payload: el conjunto que la llamada nombra explícitamente. */
function largestSet(args: Record<string, unknown>): number | undefined {
  const sizes = Object.values(args ?? {})
    .filter((v): v is unknown[] => Array.isArray(v))
    .map((v) => v.length);
  return sizes.length > 0 ? Math.max(...sizes) : undefined;
}

export function confirmationFor(call: { risk?: string; args: Record<string, unknown> }): Confirmation {
  const { risk, args } = call;

  if (risk === 'bulk_destructive') {
    const affected = largestSet(args);
    // Un masivo cuyo payload NO nombra el conjunto (un filtro, un «todas») no se puede contar, y
    // una tarjeta que no dice cuántas caen es la que el dueño aprueba sin saber qué aprueba. No se
    // ofrece el atajo: se manda a la pantalla, que sí las enseña. Un conjunto vacío tampoco pasa —
    // que no borre nada no lo vuelve correcto, significa que no sabemos qué iba a borrar.
    if (!affected) return { kind: 'refuse' };
    // Se escribe el NÚMERO, no una palabra. «BORRAR» se teclea sin mirar; un número obliga a leer
    // la frase donde está, que es justo la que dice cuántas son.
    return { kind: 'typed', affected, expected: String(affected) };
  }

  if (risk === 'destructive') return { kind: 'typed', expected: undefined };

  // Ausente o `normal`: la tarjeta de siempre. La inmensa mayoría del catálogo no declara `risk`
  // todavía, y exigir texto escrito para crear un servicio enseñaría a teclear sin leer — que es
  // exactamente cómo una confirmación deja de confirmar nada.
  return { kind: 'click' };
}
