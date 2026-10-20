// The rules of the options sheet of the till (SALE-F11; Modifiers' MODIFIER-F06, «Contrato con Ventas»), kept
// pure: what a tap does in each kind of group, the ids the line carries and when «Add» waits. As the market's
// tills do it (Square, Toast, Lightspeed): a group of one swaps (the new choice takes the old one out; the same
// one tapped again leaves), a group with a ceiling fills up and then refuses the next tap saying which group is
// full, one without a ceiling never fills, an option that may be repeated has a counter. The sheet never closes
// on its own. The money shown is a preview: Modifiers values the line on the server and the browser only sends
// the ids.
/** What the rules read of a group: Modifiers' groups of a product and Menus' courses of a menu (SALE-F12) both
 *  are one. */
export interface ChoiceGroup {
  readonly id: string;
  readonly min_choices: number;
  /** 0 = no ceiling. */
  readonly max_choices: number;
  readonly allow_repeat: boolean;
  readonly options: readonly { readonly id: string; readonly price_delta: number; readonly is_default?: boolean }[];
}

export interface Choice {
  /** The ids chosen, in the order chosen; a repeated option appears once per time. */
  readonly picks: readonly string[];
  /** The group whose ceiling refused the last tap, if it did. */
  readonly refused: string | null;
}

export interface Rule {
  key: 'sale.pos.options.choose' | 'sale.pos.options.upTo' | 'sale.pos.options.optional';
  n: number;
}

/** «Choose N» when required (N, its minimum), «Up to N» with a ceiling, «Optional» otherwise. */
export function ruleOf(group: ChoiceGroup): Rule {
  if (group.min_choices > 0) return { key: 'sale.pos.options.choose', n: group.min_choices };
  if (group.max_choices > 0) return { key: 'sale.pos.options.upTo', n: group.max_choices };
  return { key: 'sale.pos.options.optional', n: 0 };
}

/** The sheet as it opens: each group's defaults chosen, in the catalogue's order. */
export function initialChoice(groups: readonly ChoiceGroup[]): Choice {
  return { picks: groups.flatMap((group) => group.options.filter((option) => option.is_default).map((option) => option.id)), refused: null };
}

export function chosenIds(choice: Choice): string[] {
  return [...choice.picks];
}

export function countOf(choice: Choice, optionId: string): number {
  return choice.picks.filter((id) => id === optionId).length;
}

function countIn(choice: Choice, group: ChoiceGroup): number {
  const ids = new Set(group.options.map((option) => option.id));
  return choice.picks.filter((id) => ids.has(id)).length;
}

/** One time less of `optionId` (the last time it was chosen). */
export function unchoose(choice: Choice, optionId: string): Choice {
  const at = choice.picks.lastIndexOf(optionId);
  if (at < 0) return choice;
  return { picks: [...choice.picks.slice(0, at), ...choice.picks.slice(at + 1)], refused: null };
}

/** A tap on `optionId` of `group`: swap in a group of one, add (or count up) below the ceiling, take it out
 *  again when it was chosen and cannot be repeated; at the ceiling the tap is refused, naming the group. */
export function choose(choice: Choice, group: ChoiceGroup, optionId: string): Choice {
  const chosen = countOf(choice, optionId) > 0;
  if (group.max_choices === 1) {
    const ids = new Set(group.options.map((option) => option.id));
    const others = choice.picks.filter((id) => !ids.has(id));
    return { picks: chosen ? others : [...others, optionId], refused: null };
  }
  if (chosen && !group.allow_repeat) return unchoose(choice, optionId);
  if (group.max_choices > 0 && countIn(choice, group) >= group.max_choices) return { picks: choice.picks, refused: group.id };
  return { picks: [...choice.picks, optionId], refused: null };
}

/** The first group short of its minimum or over its ceiling: «Add» waits for it. */
export function missingGroup(groups: readonly ChoiceGroup[], choice: Choice): ChoiceGroup | null {
  return (
    groups.find((group) => {
      const count = countIn(choice, group);
      return count < group.min_choices || (group.max_choices > 0 && count > group.max_choices);
    }) ?? null
  );
}

/** What the choices add to the product's price, in cents, signs and repeats counted (a preview). */
export function addedCents(groups: readonly ChoiceGroup[], choice: Choice): number {
  const delta = new Map(groups.flatMap((group) => group.options.map((option) => [option.id, option.price_delta] as const)));
  return choice.picks.reduce((sum, id) => sum + (delta.get(id) ?? 0), 0);
}
