// The basket of a table's page: the dishes and set menus a customer adds before sending the order. Its total is the
// menu's prices as the page shows them; the order sends only ids, and the server prices it again.
import type { SendLineIn } from '../operations';

/** The most units of one line, as the server takes them. */
export const MAX_QUANTITY = 20;

/** An option of a dish, or a dish of a set menu, as picked: once per time it was picked. */
export interface BasketPick {
  id: string;
  name: string;
  price_delta: number;
}

export interface BasketLine {
  key: number;
  kind: 'dish' | 'menu';
  /** The dish's product or the set menu, by its id. */
  ref: string;
  name: string;
  price: number;
  picks: BasketPick[];
  quantity: number;
  notes: string;
}

export function addLine(lines: BasketLine[], line: Omit<BasketLine, 'key'>): BasketLine[] {
  const key = Math.max(0, ...lines.map((one) => one.key)) + 1;
  return [...lines, { ...line, key }];
}

export function unitPrice(line: Omit<BasketLine, 'key'>): number {
  return line.price + line.picks.reduce((sum, pick) => sum + pick.price_delta, 0);
}

export function basketTotal(lines: BasketLine[]): number {
  return lines.reduce((sum, line) => sum + unitPrice(line) * line.quantity, 0);
}

/** The line `key` with `quantity`; at zero it leaves the basket. */
export function setQuantity(lines: BasketLine[], key: number, quantity: number): BasketLine[] {
  if (quantity <= 0) return lines.filter((line) => line.key !== key);
  return lines.map((line) => (line.key === key ? { ...line, quantity } : line));
}

function counted(picks: BasketPick[]): { option_id: string; quantity: number }[] {
  const counts = new Map<string, number>();
  for (const pick of picks) counts.set(pick.id, (counts.get(pick.id) ?? 0) + 1);
  return [...counts].map(([option_id, quantity]) => ({ option_id, quantity }));
}

/** What the order sends: each dish with its options and each set menu with its dishes, by their ids. */
export function toSend(lines: BasketLine[]): SendLineIn[] {
  return lines.map(({ kind, ref, picks, quantity, notes }) =>
    kind === 'dish'
      ? { product_id: ref, option_ids: picks.map((pick) => pick.id), quantity, notes }
      : { combo_id: ref, choices: counted(picks), quantity, notes },
  );
}
