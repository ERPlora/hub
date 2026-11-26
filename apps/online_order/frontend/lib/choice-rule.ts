// How many of a group of choices the customer picks, said above its options: a dish's modifier group (a ceiling of 0
// is none) or a set menu's course. The key of its text and the numbers it names.

export type ChoiceRule = [key: string, named: Record<string, number>];

const RULE = 'online_order.menu.rule';

export function choiceRule(min: number, max: number): ChoiceRule {
  if (min === 0) return max === 0 ? [`${RULE}.optional`, {}] : [`${RULE}.optionalUpTo`, { max }];
  if (max === min) return [`${RULE}.exactly`, { min }];
  return max === 0 ? [`${RULE}.atLeast`, { min }] : [`${RULE}.between`, { min, max }];
}
