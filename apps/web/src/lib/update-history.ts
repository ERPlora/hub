// Historial de actualizaciones del hub (hub#564, ADR-0269 §3.5).
//
// Actualizamos nosotros, siempre, sin preguntar y sin cortar el servicio. La contrapartida que le
// debemos al dueño es **transparencia**: puede no decidir *cuándo*, pero tiene derecho a saber
// *qué* le ha cambiado. Esto es solo la presentación de ese dato; quién decide qué se anota es el
// runtime, que lo escribe cuando la transición OCURRE (el estado actual no se puede restar de sí
// mismo para deducir un historial).
//
// La regla que carga con el valor no es «pintar una lista», es **solo lo que cambió**: un día sin
// actualizaciones no es una fila que diga «sin cambios», es nada.
//
// ⚠️ Esta pantalla es de SOLO LECTURA a propósito. El botón «Actualizar» del hub para el dueño se
// retiró (contradice ADR-0269) y esto no lo reintroduce: aquí no hay ninguna acción.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Una transición tal como la devuelve `GET /api/system/update-history`. */
export interface UpdateHistoryEntry {
  /** `hub` (el core) o `module`. Los dos van en la MISMA lista. */
  component: 'hub' | 'module' | string;
  /** `module_id`; vacío para el core. */
  id: string;
  /** El nombre que lee el dueño: «Inventario», no `inventory` (ADR-0254). */
  name: string;
  /** De dónde venía. Vacío solo en filas que no deberían llegar aquí. */
  from: string;
  /** A dónde fue. **Vacío = no quedó nada corriendo** (`outcome: 'lost'`). */
  to: string;
  outcome: 'updated' | 'rolled_back' | 'lost' | string;
  /**
   * El error de una vuelta atrás, verbatim. **No se pinta**: es texto de desarrollo y lo que el
   * dueño necesita leer es la frase («volvió a 1.1.3»), no el fallo de una migración. Viaja porque
   * es lo primero que preguntamos nosotros en una incidencia.
   */
  reason: string;
  /** Instante ISO-8601 en que ocurrió. */
  at: string;
}

/** Una entrada ya lista para pintar: la de arriba más su hora en local. */
export interface DisplayEntry extends UpdateHistoryEntry {
  time: string;
}

/** Un día con algo que contar. Los días sin cambios no producen grupo. */
export interface DayGroup {
  /** `YYYY-MM-DD` en hora local — la clave del `v-for`, estable y ordenable. */
  key: string;
  /** La fecha ya formateada. Vacía cuando es hoy o ayer: esos se nombran, no se fechan. */
  label: string;
  isToday: boolean;
  isYesterday: boolean;
  entries: DisplayEntry[];
}

/**
 * Lo que se lee en cada línea: **de → a**.
 *
 * Va el origen y no solo la versión nueva porque «Inventario 1.1.2» no dice nada y «1.1.1 → 1.1.2»
 * sí. Cuando no quedó nada corriendo (`to` vacío) se enseña solo de dónde venía: escribir una
 * versión de destino que no existe sería inventarse el dato en la única pantalla que existe
 * precisamente para no inventárselo.
 */
export function versionJump(entry: UpdateHistoryEntry): string {
  if (!entry.to) return entry.from;
  if (!entry.from) return entry.to;
  return `${entry.from} → ${entry.to}`;
}

/** `YYYY-MM-DD` del día LOCAL de una fecha (no UTC: el dueño vive en su huso, no en Greenwich). */
function localDayKey(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * Grupo al que van las entradas cuyo instante no se puede leer.
 *
 * No es una fecha, así que nunca coincide con el día de hoy ni con el de ayer, y **nunca** es
 * `Invalid Date`: pintar eso en la única pantalla que existe para no mentirle al dueño sería basura
 * con aspecto de dato. El hecho —«esto cambió, de aquí a aquí»— sigue siendo cierto aunque el
 * cuándo no se pueda leer, así que la entrada se conserva y lo que se calla es la hora.
 */
const UNDATED = '';

/**
 * Agrupa las entradas por día, lo más reciente primero.
 *
 * Solo hay grupo si ese día pasó algo: entre dos actualizaciones separadas por una semana no se
 * cuelan siete días vacíos. Hoy y ayer se **nombran** en vez de fecharse, porque «hoy» es lo que
 * alguien busca cuando algo dejó de funcionar esta mañana.
 */
export function groupByDay(
  entries: readonly UpdateHistoryEntry[],
  now: Date,
  locale: string,
): DayGroup[] {
  const todayKey = localDayKey(now);
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = localDayKey(yesterday);

  const byDay = new Map<string, DisplayEntry[]>();
  const sorted = [...entries].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));

  for (const entry of sorted) {
    const at = new Date(entry.at);
    const readable = !Number.isNaN(at.getTime());
    const key = readable ? localDayKey(at) : UNDATED;
    const time = readable ? at.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) : '';
    const bucket = byDay.get(key);
    if (bucket) bucket.push({ ...entry, time });
    else byDay.set(key, [{ ...entry, time }]);
  }

  return [...byDay.entries()].map(([key, dayEntries]) => {
    const named = key === todayKey || key === yesterdayKey || key === UNDATED;
    return {
      key,
      isToday: key === todayKey,
      isYesterday: key === yesterdayKey,
      label: named
        ? ''
        : new Date(dayEntries[0].at).toLocaleDateString(locale, {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
          }),
      entries: dayEntries,
    };
  });
}

/**
 * Lo que le hemos cambiado a este hub, últimamente.
 *
 * Devuelve `[]` si no se puede leer: un historial vacío y un historial que no se pudo pedir se ven
 * igual en pantalla —«no te hemos cambiado nada»— y eso es correcto, porque la alternativa sería
 * afirmar un cambio que no consta.
 */
export async function fetchUpdateHistory(locale: string): Promise<UpdateHistoryEntry[]> {
  const url = `${RUNTIME_URL}/api/system/update-history?locale=${encodeURIComponent(locale)}`;
  // NO lanza: la pantalla de Sistema se monta con esto en el `onMounted`, y una promesa rechazada
  // aquí tumbaría el resto del render por un dato secundario. Sin red no hay historial que enseñar,
  // que es exactamente lo que se pinta.
  try {
    const res = await fetch(url, { headers: runtimeHeaders() });
    if (!res.ok) return [];
    const env = (await res.json().catch(() => ({}))) as {
      ok?: boolean;
      data?: UpdateHistoryEntry[];
    };
    return env.ok && env.data ? env.data : [];
  } catch {
    return [];
  }
}
