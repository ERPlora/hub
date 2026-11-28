// What a screen of Automations must never show a person: the name an operation or an event has inside the Hub
// («task.task.create», «sale.sale.completed»), the id of a step («s4»), a name in snake case («in_progress»), the name
// of a permission to call another system («http:https://…») or the values of a closed list as they are kept
// («low, medium, high, urgent»). Each of them has its words. The tests of the screens and the browser walks of
// Automations share it, so a new screen or a new line that shows one fails, whatever the site.
import type { CatalogOut } from '../operations';

/** The internal names of a business's catalog. */
export interface CatalogNames {
  operations: readonly string[];
  events: readonly string[];
  /** The values of each closed list an action takes, as they are kept. */
  choiceLists: readonly (readonly string[])[];
}

/** A name of three dotted parts, as operations and events are named; a host («api.example.com») is one too. */
const DOTTED = /(?<![\p{L}\p{N}_.])[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2}(?![\p{L}\p{N}_]|\.[\p{L}\p{N}])/gu;
const STEP_ID = /(?<![\p{L}\p{N}_.-])s\d+(?![\p{L}\p{N}_])/gu;
const SNAKE = /(?<![\p{L}\p{N}_.@/-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\p{L}\p{N}_@])/gu;
const CALL_GRANT = /http:https?:\/\//gu;

export function catalogNames(catalog: CatalogOut): CatalogNames {
  return {
    operations: catalog.actions.map((action) => action.name),
    events: catalog.events.map((event) => event.name),
    choiceLists: catalog.actions.flatMap((action) => action.fields.filter((field) => field.choices.length > 1).map((field) => field.choices)),
  };
}

export function internalCodesIn(text: string, names: CatalogNames): string[] {
  const known = new Set([...names.operations, ...names.events]);
  const found: string[] = [];
  // A dotted name is internal if the catalog has it or a part of it is in snake case; a host is neither.
  const rest = text.replace(DOTTED, (name) => {
    if (!known.has(name) && !name.includes('_')) return name;
    found.push(name);
    return ' ';
  });
  for (const pattern of [STEP_ID, SNAKE, CALL_GRANT]) for (const match of rest.matchAll(pattern)) found.push(match[0]);
  for (const values of names.choiceLists) if (text.includes(values.join(', '))) found.push(values.join(', '));
  return [...new Set(found)];
}
