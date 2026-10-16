// What the display remembers between updates (KITCHEN-F10, F16): the tickets it already showed — so it
// rings for a new one or one just rushed, never for what was on the board when it opened — and the
// station this device works at (Toast, Square and Fresh pin a screen to its station).
import type { Priority, TicketOut } from '../operations';

/** Where the station of this device is kept (`''`: every station; `none`; or a station's id). */
export const STATION_KEY = 'kitchen.display.station';

export interface Arrivals {
  /** Ring now: a ticket appeared, or one turned rush. */
  ring: boolean;
  /** What the board shows now: id → priority. */
  known: Map<string, Priority>;
}

/** Compares the tickets being cooked with what the board already knew (`undefined`: the first result). */
export function arrivals(known: Map<string, Priority> | undefined, cooking: readonly TicketOut[]): Arrivals {
  const now = new Map(cooking.map((ticket) => [ticket.id, ticket.priority] as const));
  if (known === undefined) return { ring: false, known: now };
  const ring = cooking.some((ticket) => {
    const before = known.get(ticket.id);
    return before === undefined || (ticket.priority === 'rush' && before !== 'rush');
  });
  return { ring, known: now };
}

export function rememberedStation(): string {
  try {
    return globalThis.localStorage?.getItem(STATION_KEY) ?? '';
  } catch {
    return '';
  }
}

export function rememberStation(station: string): void {
  try {
    if (station) globalThis.localStorage?.setItem(STATION_KEY, station);
    else globalThis.localStorage?.removeItem(STATION_KEY);
  } catch {
    // A browser that keeps nothing (private mode): the station is chosen every time, as before.
  }
}
