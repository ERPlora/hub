// The gallery's cards (WORKBOOK FLOW-F04): ten ready-made automations by sector, the old module's
// (`ui/lib/templates.ts`) on this Hub's events and actions. Each card is built in the owner's language
// and born paused and ungranted; it is offered only when this business has its event and its actions
// (the catalog of the active apps), and the apps that would bring back a hidden one are named.
// The card that answered WhatsApp messages returns when the WhatsApp inbox declares its event.
import type { CatalogOut, Condition, FlowOut, Step, Trigger } from '../operations';
import { type FlowDocument, requiredGrants } from './document';
import type { Phrasing } from './phrasing';

export type Sector = 'any' | 'beauty' | 'food';

export interface FlowTemplate {
  id: string;
  sector: Sector;
  /** Registered in the shell (ION_ICONS); the old ones wait in UI-REQUESTS.md. */
  icon: string;
  /** Whether the card asks the owner to decide something (`flow.gallery.cards.<id>.blank`). */
  blank: boolean;
  build(p: Phrasing): { trigger: Trigger; steps: Step[] };
}

const T = (id: string, key: string, p: Phrasing): string => p.t(`flow.gallery.cards.${id}.${key}`);

function task(id: string, p: Phrasing, priority: string, more: Record<string, unknown> = {}, stepId = 's1'): Step {
  return { id: stepId, kind: 'command', operation: 'task.task.create', params: { title: T(id, 'task', p), priority, ...more } };
}

const event = (name: string, filter?: Condition): Trigger => (filter ? { kind: 'event', event: name, filter } : { kind: 'event', event: name });

export const TEMPLATES: readonly FlowTemplate[] = [
  {
    id: 'welcome',
    sector: 'any',
    icon: 'ion:person-add-outline',
    blank: true,
    build: (p) => ({
      trigger: event('customer.customer.created'),
      steps: [{ id: 's1', kind: 'delay', seconds: 86400 }, task('welcome', p, 'medium', {}, 's2')],
    }),
  },
  {
    id: 'bigSaleNote',
    sector: 'any',
    icon: 'ion:create-outline',
    blank: true,
    build: (p) => ({
      trigger: event('sale.sale.completed'),
      steps: [
        { id: 's1', kind: 'condition', when: { 'input.customer_id': { exists: true }, 'input.total': { gte: 10000 } } },
        {
          id: 's2',
          kind: 'command',
          operation: 'customer.note.add',
          params: { customer_id: 'input.customer_id', content: T('bigSaleNote', 'note', p), author_name: p.t('flow.gallery.author') },
        },
      ],
    }),
  },
  {
    id: 'bigSaleTask',
    sector: 'any',
    icon: 'ion:cash-outline',
    blank: true,
    build: (p) => ({
      trigger: event('sale.sale.completed', { 'input.total': { gt: 10000 } }),
      steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: `${T('bigSaleTask', 'task', p)} {{input.sale_number}}`, priority: 'high' } }],
    }),
  },
  {
    id: 'newStaff',
    sector: 'any',
    icon: 'ion:people-outline',
    blank: true,
    build: (p) => ({
      trigger: event('staff.member.created'),
      steps: [task('newStaff', p, 'high', { description: T('newStaff', 'description', p) })],
    }),
  },
  {
    id: 'cashClose',
    sector: 'any',
    icon: 'ion:file-tray-outline',
    blank: true,
    build: (p) => ({
      trigger: event('cash_register.session.closed'),
      steps: [task('cashClose', p, 'high', { description: T('cashClose', 'description', p) })],
    }),
  },
  {
    id: 'fiscalRejected',
    sector: 'any',
    icon: 'ion:alert-circle-outline',
    blank: true,
    build: (p) => ({
      trigger: event('verifactu.record.rejected'),
      steps: [task('fiscalRejected', p, 'urgent', { description: T('fiscalRejected', 'description', p) })],
    }),
  },
  {
    id: 'weekReview',
    sector: 'any',
    icon: 'ion:speedometer-outline',
    blank: true,
    build: (p) => ({
      trigger: { kind: 'schedule', every: 'week', weekday: 4, time: '18:00' },
      steps: [task('weekReview', p, 'medium', { description: T('weekReview', 'description', p) })],
    }),
  },
  {
    id: 'morning',
    sector: 'beauty',
    icon: 'ion:sunny-outline',
    blank: true,
    build: (p) => ({ trigger: { kind: 'schedule', every: 'day', time: '09:00' }, steps: [task('morning', p, 'high')] }),
  },
  {
    id: 'noShow',
    sector: 'beauty',
    icon: 'ion:notifications-outline',
    blank: false,
    build: (p) => ({ trigger: event('appointment.appointment.marked_no_show'), steps: [task('noShow', p, 'urgent')] }),
  },
  {
    id: 'bigParty',
    sector: 'food',
    icon: 'ion:people-outline',
    blank: true,
    build: (p) => ({
      trigger: event('reservation.reservation.created'),
      steps: [
        { id: 's1', kind: 'condition', when: { 'input.party_size': { gte: 6 } } },
        task('bigParty', p, 'high', { description: `${T('bigParty', 'people', p)}: {{input.party_size}} · {{input.date}} {{input.time}}` }, 's2'),
      ],
    }),
  },
];

export function templatesOf(sector: Sector): FlowTemplate[] {
  return TEMPLATES.filter((card) => card.sector === sector);
}

export function templateById(id: string): FlowTemplate | undefined {
  return TEMPLATES.find((card) => card.id === id);
}

export function cardName(card: FlowTemplate, p: Phrasing): string {
  return T(card.id, 'name', p);
}

/** The automation a card creates: its name, paused, its trigger and its steps. */
export function buildDocument(card: FlowTemplate, p: Phrasing): FlowDocument {
  return { name: cardName(card, p), enabled: false, ...card.build(p) };
}

/** What a card will ask permission to do: the operations of its steps. Read from a build in any
 *  language: the names do not depend on it. */
export function cardGrants(card: FlowTemplate): string[] {
  const neutral: Phrasing = { t: (key) => key, te: () => false, locale: 'en' };
  return requiredGrants(card.build(neutral).steps);
}

function cardEvent(card: FlowTemplate): string | null {
  const neutral: Phrasing = { t: (key) => key, te: () => false, locale: 'en' };
  const trigger = card.build(neutral).trigger;
  return trigger.kind === 'event' ? trigger.event : null;
}

/** The apps a card needs that are not in this business (by their label). */
function lacking(card: FlowTemplate, catalog: CatalogOut): string[] {
  const apps: string[] = [];
  const name = cardEvent(card);
  if (name && !catalog.events.some((candidate) => candidate.name === name)) apps.push(name.split('.')[0]);
  for (const operation of cardGrants(card)) {
    if (!catalog.actions.some((action) => action.name === operation)) apps.push(operation.split('.')[0]);
  }
  return apps;
}

/** Whether this business has the card's event and actions. */
export function runnable(card: FlowTemplate, catalog: CatalogOut): boolean {
  return lacking(card, catalog).length === 0;
}

/** The apps (labels, sorted) that would bring back the hidden cards. */
export function missingApps(cards: readonly FlowTemplate[], catalog: CatalogOut): string[] {
  return [...new Set(cards.flatMap((card) => lacking(card, catalog)))].sort();
}

/** The automation of the business that is this card: same event and its actions, or (a card on the
 *  clock) the same name. */
export function existingFor(card: FlowTemplate, flows: readonly FlowOut[], p: Phrasing): FlowOut | undefined {
  const name = cardEvent(card);
  const operations = cardGrants(card);
  return flows.find((flow) => {
    if (name) {
      const has = flow.steps.map((step) => ('operation' in step ? step.operation : ''));
      return flow.trigger.kind === 'event' && flow.trigger.event === name && operations.every((operation) => has.includes(operation));
    }
    return flow.name === cardName(card, p);
  });
}

/** Another automation, on, that already starts with the card's event. */
export function alreadyFires(card: FlowTemplate, flows: readonly FlowOut[]): FlowOut | undefined {
  const name = cardEvent(card);
  if (!name) return undefined;
  return flows.find((flow) => flow.enabled && flow.trigger.kind === 'event' && flow.trigger.event === name);
}
