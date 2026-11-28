// The values of a closed list an action takes (a task's priority, the channel of an order), in words: what the step's
// form offers and what «Try it» says it would send (WORKBOOK FLOW-F11, F13). The catalog gives each value as the
// action keeps it («high»); the screen never shows that. A country is named by the browser, a weekday as the trigger
// names it, the order of a list by the datum it sorts by and its direction, a status by the words of the app for the
// thing it is the status of (`flow.statuses.<app>__<entity>`), and every other value by `flow.choices.<field>`.
import type { FieldOut } from '../operations';
import { fieldLabel, type Phrasing } from './phrasing';

/** Which closed list a value is of: the field `field` of the action `action` («task.task.create»). */
export interface ChoiceOf {
  action: string;
  field: string;
}

const COUNTRIES: ReadonlySet<string> = new Set(['country', 'country_code']);
const WEEKDAYS: ReadonlySet<string> = new Set(['day_of_week', 'weekday']);

const capitalize = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

/** The key a value has in the catalogues: a path cannot hold a «/» («image/png»). */
const valueKey = (value: string): string => value.replaceAll('/', '_');

function country(code: string, p: Phrasing): string {
  try {
    return new Intl.DisplayNames([p.locale], { type: 'region' }).of(code) ?? code;
  } catch {
    // Not a region code the browser knows: it is said as it came.
    return code;
  }
}

/** «Created at, descending»: a list sorted by a datum, `-` before it for the other way round. */
function order(value: string, p: Phrasing): string {
  const descending = value.startsWith('-');
  return p.t(`flow.choiceOrder.${descending ? 'desc' : 'asc'}`, { field: fieldLabel(descending ? value.slice(1) : value, p) });
}

/** The words of a value without a rule of its own: a status of its app, the field's, a number as it is. */
function worded({ action, field }: ChoiceOf, value: string, p: Phrasing): string {
  const [app = '', entity = ''] = action.split('.');
  const status = `flow.statuses.${app}__${entity}.${valueKey(value)}`;
  if (field === 'status' && p.te(status)) return p.t(status);
  const own = `flow.choices.${field}.${valueKey(value)}`;
  if (p.te(own)) return p.t(own);
  return /^\d+$/.test(value) ? value : capitalize(value.replaceAll('_', ' '));
}

/** How the screen names `value` of the closed list `of`. */
export function choiceLabel(of: ChoiceOf, value: string, p: Phrasing): string {
  const { field } = of;
  if (COUNTRIES.has(field)) return country(value, p);
  if (WEEKDAYS.has(field) && p.te(`flow.trigger.weekdays.${value}`)) return capitalize(p.t(`flow.trigger.weekdays.${value}`));
  if (field === 'sort') return order(value, p);
  return worded(of, value, p);
}

/** What a closed list offers, in its order: every value with its words, but the empty one (leaving it out says it). */
export function choiceOptions(action: string, field: FieldOut, p: Phrasing): { value: string; label: string }[] {
  return field.choices.filter((value) => value !== '').map((value) => ({ value, label: choiceLabel({ action, field: field.name }, value, p) }));
}
