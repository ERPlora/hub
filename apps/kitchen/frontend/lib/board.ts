// What the display remembers between updates (KITCHEN-F10, F16): the tickets it already showed — so it
// rings for a new one or one just rushed, never for what was on the board when it opened — and the
// station this device works at (Toast, Square and Fresh pin a screen to its station).
import type { ItemOut, Priority, TicketOut } from '../operations';

/** Where the station of this device is kept (`''`: every station; `none`; or a station's id). */
export const STATION_KEY = 'kitchen.display.station';

export interface Arrivals {
  /** Ring now: a ticket appeared, or one turned rush. */
  ring: boolean;
  /** What the board shows now, cooking or on the pass: id → priority. */
  known: Map<string, Priority>;
}

/** Compares the tickets being cooked with what the board already knew (`undefined`: the first result). The
 *  ones waiting on the pass (`ready`) count as known: one the pass recalls to the line is not a new ticket. */
export function arrivals(
  known: Map<string, Priority> | undefined,
  cooking: readonly TicketOut[],
  ready: readonly TicketOut[] = [],
): Arrivals {
  const now = new Map([...ready, ...cooking].map((ticket) => [ticket.id, ticket.priority] as const));
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

/** A menu of a ticket (KITCHEN-F06): its line of the check and its header. */
export interface MenuHead {
  lineId: string;
  name: string;
}

/** A run of dishes on a card: the dishes of one menu under its header, or one dish ordered on its own. */
export interface DishGroup {
  menu: MenuHead | null;
  items: ItemOut[];
}

/** The dishes of a ticket as the card paints them (kitchen#57): the consecutive dishes of a menu's line
 * under that menu, each other dish on its own. */
export function groupMenus(items: readonly ItemOut[]): DishGroup[] {
  const groups: DishGroup[] = [];
  for (const item of items) {
    const last = groups.at(-1);
    if (item.menu_line_id && last?.menu?.lineId === item.menu_line_id) last.items.push(item);
    else if (item.menu_line_id) groups.push({ menu: { lineId: item.menu_line_id, name: item.menu_name }, items: [item] });
    else groups.push({ menu: null, items: [item] });
  }
  return groups;
}
