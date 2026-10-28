// The card of a write the assistant wants to run (BASE-G115, G116), as the server describes it (`base.assistant.turn`'s
// `confirm`, base/assistant.py `card`): its action by its verb and its app by its name, never the operation's id; each
// datum in words — an amount the schema says is in cents, in the business's currency (gh:hub#1045) or, in a preview,
// the one its read answers, and, when it says it is signed (a difference), with its sign as Cash register writes it, a
// yes or no, a dash for nothing, a list by how many. A normal write is one line; a dangerous one, every datum and what
// to type.
import en from '../locale/en.json';
import { formatValue, type Money } from './home';

export interface AssistantField {
  name: string;
  label: string;
  kind: 'text' | 'money' | 'bool' | 'list' | 'object' | 'empty';
  value: unknown;
  /** An amount its app declares signed (Cash register's difference): «+» over, «-» short, none at zero. */
  signed?: boolean;
  /** The currency of an amount of a preview, as its read answers it (an invoice keeps the one it was issued in);
   *  none = the business's, the card's own. */
  money?: Money | null;
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
  /** The business's currency for its amounts (gh:hub#1045). */
  money?: Money | null;
  /** What a dangerous write will do, as the read its app declares answers it for this person (BASE-F98); none when
   *  its app declares no preview. */
  preview?: AssistantField[] | null;
}

type Translate = (key: string, values?: Record<string, unknown>) => string;

export interface CardFormat {
  locale: string;
  money?: Money;
  t: Translate;
}

/** The verb of each action a card or a receipt names (`base.assistant.card.actions.<action>`, base's catalogue): one
 *  per action of every write the assistant may run (guardrail: base/tests/test_assistant.py); another one is «Do
 *  this». */
const ACTIONS: Readonly<Record<string, string>> = en.base.assistant.card.actions;

export function actionKey(action: string): string {
  return `base.assistant.card.actions.${Object.hasOwn(ACTIONS, action) ? action : 'other'}`;
}

/** The platform's screens a receipt names by their key (`base.assistant.screens.<key>`, base's catalogue: the names
 *  the server gives them, base/assistant.py `SCREEN_NAMES`). */
const SCREENS: Readonly<Record<string, string>> = en.base.assistant.screens;

export function screenKey(screen: string | undefined): string | null {
  return screen && Object.hasOwn(SCREENS, screen) ? `base.assistant.screens.${screen}` : null;
}

/** The data a card names itself in the person's language (`base.assistant.card.fields.<name>`); another, by the
 *  label the server gives it in that language (base/assistant.py `_label`). */
const FIELDS = [
  'name', 'price', 'amount', 'note', 'notes', 'status', 'email', 'phone', 'quantity', 'qty', 'description',
  'duration_minutes', 'date', 'time', 'starts_at', 'ends_at', 'customer_id', 'reason', 'id', 'ids', 'title', 'category',
  'app',
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
    case 'money': {
      const text = formatValue(field.value, 'currency', format.locale, field.money ?? format.money);
      return field.signed && Number(field.value) > 0 ? `+${text}` : text;
    }
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

/** A dangerous write's data, one line each: its name in the person's language (or the server's label) and its value
 *  in words. What it sends and what it will do (its preview) are said alike. */
export function fieldLines(fields: readonly AssistantField[], format: CardFormat): string[] {
  return fields.map((field) => {
    const key = fieldLabelKey(field.name);
    return `${key ? format.t(key) : field.label}: ${fieldText(field, format)}`;
  });
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
