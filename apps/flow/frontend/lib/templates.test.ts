// The gallery's cards (WORKBOOK FLOW-F04): ten ready-made automations by sector, each built in the
// owner's language, born paused, with what it asks permission to do; a card whose event or actions this
// business does not have is hidden and the apps it needs are named; a card the business already has
// says how it is.
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { CatalogOut, FlowOut } from '../operations';
import type { Phrasing } from './phrasing';
import { alreadyFires, buildDocument, cardGrants, existingFor, missingApps, runnable, templateById, TEMPLATES, templatesOf } from './templates';

function phrasing(locale: 'en' | 'es' = 'en'): Phrasing {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  const g = i18n.global as unknown as { t: (key: string, named?: Record<string, unknown>) => string; te: (key: string) => boolean };
  return { t: (key, named) => (named ? g.t(key, named) : g.t(key)), te: (key) => g.te(key), locale };
}

const EVERYTHING: CatalogOut = {
  events: [
    'customer.customer.created',
    'sale.sale.completed',
    'staff.member.created',
    'cash_register.session.closed',
    'verifactu.record.rejected',
    'appointment.appointment.marked_no_show',
    'reservation.reservation.created',
  ].map((name) => ({ name, app: name.split('.')[0], app_name: name })),
  actions: ['task.task.create', 'customer.note.add'].map((name) => ({
    name,
    kind: 'command' as const,
    app: name.split('.')[0],
    app_name: name,
    description: '',
    fields: [],
    outputs: [],
  })),
};

const flow = (over: Partial<FlowOut>): FlowOut =>
  ({
    id: 'f1',
    name: 'Mine',
    enabled: true,
    trigger: { kind: 'event', event: 'customer.customer.created' },
    steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }],
    grants: ['task.task.create'],
    required_grants: ['task.task.create'],
    missing_grants: [],
    ...over,
  }) as FlowOut;

describe('the gallery', () => {
  it('has seven cards for any business, two for hair and beauty and one for bars and restaurants', () => {
    expect(TEMPLATES).toHaveLength(10);
    expect(templatesOf('any').map((card) => card.id)).toEqual([
      'welcome',
      'bigSaleNote',
      'bigSaleTask',
      'newStaff',
      'cashClose',
      'fiscalRejected',
      'weekReview',
    ]);
    expect(templatesOf('beauty').map((card) => card.id)).toEqual(['morning', 'noShow']);
    expect(templatesOf('food').map((card) => card.id)).toEqual(['bigParty']);
    expect(templateById('noShow')?.sector).toBe('beauty');
    expect(templateById('nothing')).toBeUndefined();
  });

  it('builds each card in the owner language, paused, and asks only for what its steps run', () => {
    const welcome = buildDocument(templateById('welcome')!, phrasing('es'));
    expect(welcome).toEqual({
      name: 'Dar la bienvenida a un cliente nuevo',
      enabled: false,
      trigger: { kind: 'event', event: 'customer.customer.created' },
      steps: [
        { id: 's1', kind: 'delay', seconds: 86400 },
        { id: 's2', kind: 'command', operation: 'task.task.create', params: { title: 'Dar la bienvenida al cliente nuevo', priority: 'medium' } },
      ],
    });
    expect(cardGrants(templateById('bigSaleNote')!)).toEqual(['customer.note.add']);
    const note = buildDocument(templateById('bigSaleNote')!, phrasing());
    expect(note.steps[0]).toEqual({ id: 's1', kind: 'condition', when: { 'input.customer_id': { exists: true }, 'input.total': { gte: 10000 } } });
    expect(note.steps[1]).toMatchObject({ params: { customer_id: 'input.customer_id', content: 'Big sale', author_name: 'Automations' } });
    const weekly = buildDocument(templateById('weekReview')!, phrasing());
    expect(weekly.trigger).toEqual({ kind: 'schedule', every: 'week', weekday: 4, time: '18:00' });
    const party = buildDocument(templateById('bigParty')!, phrasing());
    expect(party.steps[1]).toMatchObject({ params: { description: 'People: {{input.party_size}} · {{input.date}} {{input.time}}' } });
    const bigSale = buildDocument(templateById('bigSaleTask')!, phrasing());
    expect(bigSale.trigger).toEqual({ kind: 'event', event: 'sale.sale.completed', filter: { 'input.total': { gt: 10000 } } });
    expect(bigSale.steps[0]).toMatchObject({ params: { title: 'Thank the customer of a big sale {{input.sale_number}}' } });
  });

  it('every card is built with no permissions and nothing on', () => {
    for (const card of TEMPLATES) {
      const doc = buildDocument(card, phrasing());
      expect(doc.enabled, card.id).toBe(false);
      expect(doc.name, card.id).not.toMatch(/^flow\./);
      expect(cardGrants(card).length, card.id).toBeGreaterThan(0);
    }
  });

  it('hides a card whose event or actions this business does not have, and says which apps they need', () => {
    expect(TEMPLATES.every((card) => runnable(card, EVERYTHING))).toBe(true);
    const withoutTasks: CatalogOut = { ...EVERYTHING, actions: EVERYTHING.actions.filter((action) => action.app !== 'task') };
    expect(TEMPLATES.filter((card) => runnable(card, withoutTasks)).map((card) => card.id)).toEqual(['bigSaleNote']);
    const withoutVerifactu: CatalogOut = { ...EVERYTHING, events: EVERYTHING.events.filter((event) => event.app !== 'verifactu') };
    expect(missingApps(TEMPLATES, withoutVerifactu)).toEqual(['verifactu']);
    expect(missingApps(TEMPLATES, withoutTasks)).toEqual(['task']);
    expect(missingApps(TEMPLATES, EVERYTHING)).toEqual([]);
  });

  it('has a word for every app a card may need, so the hidden ones never name an app by its internal name (hub#476)', () => {
    const needed = missingApps(TEMPLATES, { events: [], actions: [] });
    expect(needed).toEqual(expect.arrayContaining(['task', 'verifactu', 'reservation']));
    // Read from each catalog itself: the Spanish one falls back to the English word, which would hide a missing one.
    for (const [locale, words] of [['en', en.flow.gallery.apps], ['es', es.flow.gallery.apps]] as const) {
      const named: Record<string, string> = words;
      expect(needed.filter((app) => !named[app]?.trim()), locale).toEqual([]);
    }
  });

  it('knows when the business already has a card, and how it is', () => {
    const welcome = templateById('welcome')!;
    const p = phrasing();
    expect(existingFor(welcome, [flow({})], p)?.id).toBe('f1');
    expect(existingFor(welcome, [flow({ steps: [] })], p)).toBeUndefined();
    const weekly = templateById('weekReview')!;
    expect(existingFor(weekly, [flow({ name: 'Review the week on Friday', trigger: { kind: 'schedule', every: 'week', weekday: 4, time: '18:00' } })], p)?.id).toBe(
      'f1',
    );
  });

  it('a card on the clock is known by its schedule and its actions, whatever it is called (flows#68)', () => {
    const weekly = templateById('weekReview')!;
    const morning = templateById('morning')!;
    const onFridays = { kind: 'schedule' as const, every: 'week' as const, weekday: 4, time: '19:30' };
    // Renamed, or made in Spanish and looked at in English: still the business's own.
    expect(existingFor(weekly, [flow({ name: 'Viernes: repaso', trigger: onFridays })], phrasing())?.id).toBe('f1');
    expect(existingFor(weekly, [flow({ name: 'Repasar la semana el viernes', trigger: onFridays })], phrasing())?.id).toBe('f1');
    // Every day is another card; without its actions it is not this one.
    expect(existingFor(weekly, [flow({ name: 'Mine', trigger: { kind: 'schedule', every: 'day', time: '18:00' } })], phrasing())).toBeUndefined();
    expect(existingFor(morning, [flow({ name: 'Mine', trigger: { kind: 'schedule', every: 'day', time: '08:30' }, steps: [] })], phrasing())).toBeUndefined();
    expect(existingFor(morning, [flow({ name: 'Mine', trigger: { kind: 'schedule', every: 'day', time: '08:30' } })], phrasing())?.id).toBe('f1');
  });

  it('warns that another automation already starts with the same thing', () => {
    const welcome = templateById('welcome')!;
    expect(alreadyFires(welcome, [flow({ name: 'Mine', steps: [] })])?.name).toBe('Mine');
    expect(alreadyFires(welcome, [flow({ enabled: false })])).toBeUndefined();
    expect(alreadyFires(templateById('weekReview')!, [flow({})])).toBeUndefined();
  });
});

describe('the words of the cards (flows#164)', () => {
  it('every datum a card fills or reads has its word in Spanish', () => {
    const p = phrasing('es');
    const words = (es as { flow: { fields: Record<string, string> } }).flow.fields;
    for (const card of TEMPLATES) {
      const { trigger, steps } = card.build(p);
      const names = new Set<string>();
      const read = (value: unknown): void => {
        if (typeof value !== 'string') return;
        for (const match of value.matchAll(/(?:^|\{\{\s*)(?:input|steps\.\w+)\.(\w+)/g)) names.add(match[1]);
      };
      if (trigger.kind === 'event') for (const path of Object.keys(trigger.filter ?? {})) read(path);
      for (const step of steps) {
        if (step.kind === 'condition') for (const path of Object.keys(step.when)) read(path);
        if (step.kind === 'command' || step.kind === 'query') {
          for (const [name, value] of Object.entries(step.params)) {
            names.add(name);
            read(value);
          }
        }
      }
      for (const name of names) expect(words[name], `${card.id}: ${name}`).toBeTruthy();
    }
  });
});
