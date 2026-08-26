// Qué se está aprobando, en el idioma de quien lo aprueba (hub#1040).
//
// La tarjeta que confirma TODA escritura del asistente enseñaba el nombre técnico de la tool y el
// `JSON.stringify` de sus argumentos. Un dueño de peluquería tenía que aprobar
// `services.services.create` con `{"price_cents": 1500}` sin que en ningún sitio pusiera
// **15,00 €** — en el único punto del producto donde un humano podía cazar un error de ×100, y
// justo el único donde el importe no se presentaba en euros. El propio system prompt lo avisa:
// «a price written wrong by a factor of 100 is a real invoice at the wrong price, and the schema
// will not catch it».
//
// Dos decisiones que gobiernan este fichero:
//
// 1. **El dinero se marca, no se adivina.** Formatear por nombre («si acaba en `price`…») crearía
//    una mentira nueva el día que un porcentaje se pinte como importe. Quien sabe qué campo es
//    dinero es el JSON Schema del command, y el runtime lo manda resuelto (`money_fields`). Sin
//    marca, el valor se enseña tal cual: no saber es seguro, equivocarse no.
// 2. **Nunca el command crudo.** Es la decisión de hub#363 y la escalera que ya construyó
//    hub#579: la traducción que da el MÓDULO, o nada. `sales.void` es vocabulario nuestro, no del
//    mostrador.
import { formatMoney } from './money';
import { describeElevation, type ElevationCatalogueEntry } from './elevation-label';

export interface ConfirmField {
  key: string;
  /** Ya formateado para leer: importes en euros, booleanos en palabras, objetos compactados. */
  value: string;
  isMoney: boolean;
}

export interface ConfirmDescription {
  /** La acción en palabras del negocio. Vacío = el módulo no sabe nombrarla; la UI lo dice. */
  action: string;
  /** De qué app viene, localizado. Vacío = desconocido. */
  app: string;
  fields: ConfirmField[];
}

/** Un valor de argumento, legible. Nunca lanza: una tarjeta que no se pinta es una escritura a ciegas. */
function readable(value: unknown, isMoney: boolean): string {
  if (value === null || value === undefined) return '—';
  if (isMoney && typeof value === 'number' && Number.isFinite(value)) return formatMoney(value);
  if (typeof value === 'boolean') return value ? 'Sí' : 'No';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function describeToolCall(input: {
  command: string;
  args: Record<string, unknown>;
  moneyFields?: readonly string[];
  catalogue?: readonly ElevationCatalogueEntry[];
}): ConfirmDescription {
  const { command, args, moneyFields = [], catalogue = [] } = input;
  const money = new Set(moneyFields);

  // Orden estable: la misma acción produce la misma tarjeta. Una tarjeta que baraja sus campos
  // entre turnos es una tarjeta que se deja de leer.
  const fields = Object.keys(args ?? {})
    .sort()
    .map((key) => {
      const isMoney = money.has(key);
      return { key, value: readable(args[key], isMoney), isMoney };
    });

  const described = describeElevation({ command }, catalogue);
  return { action: described.action, app: described.moduleName, fields };
}
