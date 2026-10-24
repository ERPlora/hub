// The card of a write the assistant wants to run (BASE-G115, G116), as the server describes it (`base.assistant.turn`'s
// `confirm`, base/assistant.py `card`): its action by its verb and its app by its name, never the operation's id; each
// datum in words — an amount the schema says is in cents, in the business's currency (gh:hub#1045), a yes or no, a
// dash for nothing, a list by how many. A normal write is one line; a dangerous one, every datum and what to type.
import { formatValue, type Money } from './home';

export interface AssistantField {
  name: string;
  label: string;
  kind: 'text' | 'money' | 'bool' | 'list' | 'object' | 'empty';
  value: unknown;
}

export interface AssistantCard {
  operation: string;
  app: string;
  app_name: string;
  action: string;
  risk: 'normal' | 'high';
  fields: AssistantField[];
  count: number | null;
  confirm_word: string;
  blocked: boolean;
}

type Translate = (key: string, values?: Record<string, unknown>) => string;

export interface CardFormat {
  locale: string;
  money?: Money;
  t: Translate;
}

/** The verbs a card names (`base.assistant.card.actions.<verb>`); another one is «Do this». */
const VERBS = [
  'create', 'add', 'update', 'set', 'delete', 'remove', 'void', 'refund', 'cancel', 'close', 'open', 'confirm',
  'complete', 'issue', 'send', 'import', 'move', 'assign', 'archive', 'restore', 'approve', 'reject', 'enable', 'disable',
];

export function actionKey(action: string): string {
  const verb = VERBS.find((known) => action === known || action.endsWith(`_${known}`) || action.startsWith(`${known}_`));
  return `base.assistant.card.actions.${verb ?? 'other'}`;
}

/** The data a card names in the person's language (`base.assistant.card.fields.<name>`); another, by its title. */
const FIELDS = [
  'name', 'price', 'amount', 'note', 'notes', 'status', 'email', 'phone', 'quantity', 'qty', 'description',
  'duration_minutes', 'date', 'time', 'starts_at', 'ends_at', 'customer_id', 'reason', 'id', 'ids', 'title', 'category',
];

export function fieldLabelKey(name: string): string | null {
  return FIELDS.includes(name) ? `base.assistant.card.fields.${name}` : null;
}

function compact(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value !== 'object') return String(value);
  if (Array.isArray(value)) return value.map(compact).join(', ');
  return Object.entries(value as Record<string, unknown>)
    .map(([key, inner]) => `${key}: ${compact(inner)}`)
    .join(' · ');
}

export function fieldText(field: AssistantField, format: CardFormat): string {
  switch (field.kind) {
    case 'empty':
      return '—';
    case 'money':
      return formatValue(field.value, 'currency', format.locale, format.money);
    case 'bool':
      return format.t(field.value ? 'base.assistant.card.yes' : 'base.assistant.card.no');
    case 'list':
      return format.t('base.assistant.card.items', { count: Array.isArray(field.value) ? field.value.length : 0 });
    case 'object':
      return compact(field.value);
    default:
      return String(field.value);
  }
}

/** A normal write in one line: its first three data, the empty ones left out. */
export function cardLine(card: AssistantCard, format: CardFormat): string {
  return card.fields
    .filter((field) => field.kind !== 'empty')
    .slice(0, 3)
    .map((field) => fieldText(field, format))
    .join(' · ');
}

/** Whether `typed` is what the card asks, as `ConfirmDialog` (which asks it) and the server compare it: spaces around
 *  and case ignored, accents not; a normal write asks nothing; a blocked one, never. */
export function typedMatches(card: AssistantCard, typed: string): boolean {
  if (card.blocked) return false;
  return card.confirm_word === '' || typed.trim().toLocaleLowerCase() === card.confirm_word.toLocaleLowerCase();
}
