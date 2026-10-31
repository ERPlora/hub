// Words for what an automation does (WORKBOOK «Cómo son las páginas»): the events and actions of the
// active apps, its trigger, its steps, a condition, a wait and each line of a run's history, never a
// technical name where a phrase exists. Hand-written phrases for the known ones, composed for the rest.
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { CatalogOut, LogEntry, Step } from '../operations';
import { dataChoices } from './document';
import {
  actionLabel,
  describeClause,
  describeDelay,
  describeLog,
  describeStep,
  describeTrigger,
  eventLabel,
  fieldLabel,
  pathLabel,
  runStatusPill,
  statePill,
  type Phrasing,
} from './phrasing';

function phrasing(locale: 'en' | 'es' = 'en'): Phrasing {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  const g = i18n.global as unknown as { t: (key: string, named?: Record<string, unknown>) => string; te: (key: string) => boolean };
  return { t: (key, named) => (named ? g.t(key, named) : g.t(key)), te: (key) => g.te(key), locale };
}

const CATALOG = {
  events: [
    { name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' },
    { name: 'customer.group.deleted', app: 'customer', app_name: 'Customers' },
  ],
  actions: [
    { name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: ['id', 'number'] },
    { name: 'reservation.waitlist.convert', kind: 'command', app: 'reservation', app_name: 'Reservations', description: '', fields: [], outputs: [] },
    { name: 'customer.customer.detail', kind: 'query', app: 'customer', app_name: 'Customers', description: '', fields: [], outputs: ['name'] },
  ],
} as CatalogOut;

describe('events and actions in words', () => {
  it('every event and action of the Hub today has its phrase in Spanish, never English words (flows#41)', () => {
    const p = phrasing('es');
    expect(eventLabel('cart_checkout.cart.abandoned', CATALOG, p)).toBe('se abandona un carrito');
    expect(eventLabel('kitchen.ticket.ready', CATALOG, p)).toBe('una comanda está lista');
    expect(actionLabel('table.session.open', CATALOG, p)).toBe('Abrir una mesa');
    expect(actionLabel('reservation.waitlist.convert', CATALOG, phrasing())).toBe('Give a table to somebody on the waiting list');
    const flow = (es as { flow: { events: Record<string, string>; actions: Record<string, string> } }).flow;
    expect(Object.keys(flow.events).length).toBeGreaterThan(300);
    expect(Object.keys(flow.actions).length).toBeGreaterThan(450);
  });

  it('a known event has its phrase, in each language', () => {
    expect(eventLabel('sale.sale.completed', CATALOG, phrasing())).toBe('a sale is charged');
    expect(eventLabel('sale.sale.completed', CATALOG, phrasing('es'))).toBe('se cobra una venta');
  });

  it('another one is composed from its app, its subject and what happened', () => {
    // An event born after these words were written (none of the Hub's today) is composed.
    expect(eventLabel('customer.badge.deleted', CATALOG, phrasing())).toBe('Customers: badge deleted');
    expect(eventLabel('customer.badge.deleted', CATALOG, phrasing('es'))).toBe('Customers: badge borrado');
    // An app the catalog does not name is left out: never its internal name.
    expect(eventLabel('spa.sauna.overheated', CATALOG, phrasing())).toBe('Sauna overheated');
  });

  it('an app it cannot name yet is left out, never its internal name; with its catalog, its visible name', () => {
    // The editor at 390 painted «Look up: Read · whatsapp_inbox (message)» while its catalog was still on its way
    // (the catalog it sees then is none): the same with one that could not be read or an app that is not on.
    const read: Step = { id: 's1', kind: 'query', operation: 'whatsapp_inbox.message.get', params: {} };
    expect(describeStep(read, [read], null, phrasing())).toBe('Look up: Read (message)');
    expect(actionLabel('whatsapp_inbox.message.get', CATALOG, phrasing('es'))).toBe('Leer (message)');
    expect(eventLabel('whatsapp_inbox.message.flagged', null, phrasing())).toBe('Message flagged');
    const inbox = { ...CATALOG, events: [...CATALOG.events, { name: 'whatsapp_inbox.message.received', app: 'whatsapp_inbox', app_name: 'WhatsApp inbox' }] } as CatalogOut;
    expect(describeStep(read, [read], inbox, phrasing())).toBe('Look up: Read · WhatsApp inbox (message)');
  });

  it('a known action has its phrase; another says its verb, app and subject', () => {
    expect(actionLabel('task.task.create', CATALOG, phrasing())).toBe('Create a task');
    expect(actionLabel('task.task.create', CATALOG, phrasing('es'))).toBe('Crear una tarea');
    expect(actionLabel('reservation.waitlist.promote', CATALOG, phrasing())).toBe('promote · Reservations (waitlist)');
    expect(actionLabel('reservation.waitlist_badge.create', CATALOG, phrasing('es'))).toBe('Crear · Reservations (waitlist badge)');
  });

  it('a field has its word or is made readable', () => {
    expect(fieldLabel('title', phrasing('es'))).toBe('Título');
    expect(fieldLabel('party_size', phrasing())).toBe('Party size');
    expect(fieldLabel('some_new_field', phrasing())).toBe('Some new field');
  });

  it('the data the Hub offers today are named in Spanish with the screen in Spanish (flows#164)', () => {
    const p = phrasing('es');
    expect(fieldLabel('customer_phone', p)).toBe('Teléfono del cliente');
    expect(fieldLabel('sale_number', p)).toBe('Número de venta');
    expect(fieldLabel('party_size', p)).toBe('Personas');
    expect(fieldLabel('assigned_to_id', p)).toBe('Asignada a');
    expect(fieldLabel('appointment_id', phrasing())).toBe('Appointment');
    // The day and the hour an appointment or a reservation leaves ready to say: its words, never «Start date label».
    expect(fieldLabel('start_date_label', p)).toBe('Fecha de inicio, en texto');
    expect(fieldLabel('date_label', p)).toBe('Fecha, en texto');
    expect(fieldLabel('start_date_label', phrasing())).toBe('Start date, as text');
    // Every word of the dictionary has its Spanish, and the Spanish is never the English left as is.
    const words = (es as { flow: { fields: Record<string, string> } }).flow.fields;
    expect(Object.keys(words).length).toBeGreaterThan(1100);
  });

  it('names every datum the editor’s own steps leave, in both languages (FLOW-F11)', () => {
    // A call, a question, a step skipped by «Only if…» and one that failed and carried on (`dataChoices`).
    // What the modules' actions, reads and events bring is checked by tests/test_field_words.py.
    const runIf = { 'input.total': { gt: 1 } };
    const call: Step = { id: 's1', kind: 'http', method: 'GET', url: 'https://api.example.com', headers: {}, body: '', timeout: 10, run_if: runIf, on_error: 'continue' };
    const question: Step = { id: 's2', kind: 'ask', title: 'Refund?', details: '', role: '', hours: 24, on_no: 'stop', on_timeout: 'no', run_if: runIf };
    const names = dataChoices([call, question], 2, null, CATALOG).map((choice) => choice.path.split('.').at(-1) ?? '');
    expect(names).toEqual(expect.arrayContaining(['status', 'body', 'approved', 'expired', 'note', 'answered_by', 'skipped', 'failed', 'error_code']));
    // Each catalogue on its own: `te` falls back to English, so it would not see a word missing in Spanish.
    for (const [locale, catalogue] of [['en', en], ['es', es]] as const) {
      const words = (catalogue as { flow: { fields: Record<string, string> } }).flow.fields;
      for (const name of names) expect(words[name]?.trim(), `${locale}: ${name}`).toBeTruthy();
    }
  });

  it('a path says where it comes from', () => {
    const steps: Step[] = [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }];
    expect(pathLabel('input.customer_name', steps, CATALOG, phrasing())).toBe('Customer name');
    expect(pathLabel('input.customer.name', steps, CATALOG, phrasing())).toBe('Customer › Name');
    expect(pathLabel('steps.s1.number', steps, CATALOG, phrasing())).toBe('1. Create a task › Number');
    expect(pathLabel('steps.s9.id', steps, CATALOG, phrasing())).toBe('steps.s9.id');
  });
});

describe('the trigger', () => {
  it('in words, for each way of starting', () => {
    const p = phrasing();
    expect(describeTrigger({ kind: 'event', event: 'sale.sale.completed' }, CATALOG, p)).toBe('When a sale is charged');
    expect(describeTrigger({ kind: 'event', event: '' }, CATALOG, p)).toBe('Choose what has to happen for it to start');
    expect(describeTrigger({ kind: 'manual' }, CATALOG, p)).toBe('Only when you press Run');
    expect(describeTrigger({ kind: 'schedule', every: 'day', time: '09:00' }, CATALOG, p)).toBe('Every day at 09:00');
    expect(describeTrigger({ kind: 'schedule', every: 'week', weekday: 4, time: '18:00' }, CATALOG, p)).toBe('Every Friday at 18:00');
    expect(describeTrigger({ kind: 'schedule', every: 'month', day: 1, time: '08:30' }, CATALOG, p)).toBe('Every month on day 1 at 08:30');
    expect(describeTrigger({ kind: 'at', at: '2026-11-01T09:00:00+01:00' }, CATALOG, p)).toMatch(/^Once, on .*2026/);
    expect(describeTrigger({ kind: 'schedule', every: 'week', weekday: 4, time: '18:00' }, CATALOG, phrasing('es'))).toBe(
      'Todos los viernes a las 18:00',
    );
  });
});

describe('steps', () => {
  const p = phrasing();

  it('an action, a read, a condition and a wait', () => {
    expect(describeStep({ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }, [], CATALOG, p)).toBe('Create a task');
    expect(describeStep({ id: 's1', kind: 'command', operation: '', params: {} }, [], CATALOG, p)).toBe('Choose what this step does');
    expect(describeStep({ id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' }, [], CATALOG, p)).toBe(
      'Look up: Read a customer',
    );
    expect(describeStep({ id: 's2', kind: 'condition', when: { 'input.total': { gte: 10000 } } }, [], CATALOG, p)).toBe(
      'Total greater than or equal to 10000',
    );
    expect(describeStep({ id: 's2', kind: 'condition', when: {} }, [], CATALOG, p)).toBe('nothing yet');
    expect(describeStep({ id: 's3', kind: 'delay', seconds: 86400 }, [], CATALOG, p)).toBe('Wait 1 day');
  });

  it('a wait in its largest unit, singular or plural', () => {
    expect(describeDelay(7200, p)).toBe('Wait 2 hours');
    expect(describeDelay(60, phrasing('es'))).toBe('Esperar 1 minuto');
  });

  it('a comparison names its data, its operator and its value', () => {
    expect(describeClause({ path: 'input.customer_id', op: 'exists', value: true }, [], CATALOG, p)).toBe('Customer present: yes');
    expect(describeClause({ path: 'input.party_size', op: 'in', value: [6, 8] }, [], CATALOG, p)).toBe('Party size one of 6, 8');
  });

  it('a comparison with another datum names that datum, never its path (hub#1712)', () => {
    const clause = describeClause({ path: 'input.total', op: 'eq', value: 'input.customer_id' }, [], CATALOG, p);
    expect(clause).toContain('Customer');
    expect(clause).not.toContain('input.');
    expect(describeClause({ path: 'input.total', op: 'in', value: ['input.customer_id', 5] }, [], CATALOG, p)).not.toContain('input.');
  });
});

describe('pills', () => {
  it('a run says how it ended, with the tone of what it means', () => {
    const p = phrasing();
    expect(runStatusPill('succeeded', p)).toEqual({ tone: 'success', label: 'Finished well' });
    expect(runStatusPill('stopped', p)).toEqual({ tone: 'info', label: 'Finished: a condition did not hold' });
    expect(runStatusPill('failed', p)).toEqual({ tone: 'danger', label: 'Stopped by an error' });
    expect(runStatusPill('waiting', p)).toEqual({ tone: 'warning', label: 'Waiting' });
    expect(runStatusPill('cancelled', p)).toEqual({ tone: 'neutral', label: 'Cancelled' });
  });

  it('an automation is active, paused, or on without what it needs', () => {
    const p = phrasing();
    expect(statePill({ enabled: true, missing_grants: [] }, p)).toEqual({ tone: 'success', label: 'Active' });
    expect(statePill({ enabled: false, missing_grants: [] }, p)).toEqual({ tone: 'neutral', label: 'Paused' });
    expect(statePill({ enabled: true, missing_grants: ['task.task.create'] }, p)).toEqual({ tone: 'warning', label: 'Unfinished' });
  });
});

describe('a line of the history', () => {
  const steps: Step[] = [
    { id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' },
    { id: 's2', kind: 'condition', when: { 'input.total': { gte: 10000 } } },
    { id: 's3', kind: 'command', operation: 'task.task.create', params: {} },
    { id: 's4', kind: 'delay', seconds: 3600 },
  ];
  const entry = (more: Partial<LogEntry>): LogEntry => ({ step: 's3', kind: 'command', outcome: 'done', at: '2026-10-15T10:00:00+02:00', ...more });

  it('in words, step by step', () => {
    const p = phrasing();
    expect(describeLog(entry({ operation: 'task.task.create' }), steps, CATALOG, p)).toBe('Did: Create a task');
    expect(describeLog(entry({ step: 's1', kind: 'query', outcome: 'found', count: 3 }), steps, CATALOG, p)).toBe('Found 3');
    expect(describeLog(entry({ step: 's1', kind: 'query', outcome: 'not_found' }), steps, CATALOG, p)).toBe('Found nothing, and carried on');
    expect(describeLog(entry({ step: 's2', kind: 'condition', outcome: 'passed' }), steps, CATALOG, p)).toBe('The condition held');
    expect(
      describeLog(entry({ step: 's2', kind: 'condition', outcome: 'stopped', failed: [{ path: 'input.total', op: 'gte', value: 10000 }] }), steps, CATALOG, p),
    ).toBe('It stopped here because this was not met: Total greater than or equal to 10000. That is the automation working.');
    expect(describeLog(entry({ step: 's4', kind: 'delay', outcome: 'waited', seconds: 3600 }), steps, CATALOG, p)).toBe('Waited 1 hour');
    expect(
      describeLog(entry({ operation: 'task.task.create', outcome: 'failed', error: { code: 'invalid_field', message: 'No such project.' } }), steps, CATALOG, p),
    ).toBe('Create a task: No such project.');
    expect(
      describeLog(entry({ operation: 'task.task.create', outcome: 'skipped', failed: [{ path: 'input.total', op: 'gte', value: 10000 }] }), steps, CATALOG, p),
    ).toBe('Skipped: its «Only if…» did not hold (Total greater than or equal to 10000)');
    expect(
      describeLog(entry({ operation: 'task.task.create', outcome: 'failed', continued: true, error: { code: 'flow.not_allowed', message: 'Not allowed.' } }), steps, CATALOG, p),
    ).toBe('Create a task: Not allowed. It carried on with the next steps.');
  });
});

// FLOW-F27: what a call is called on the screen.
describe('a call in words', () => {
  const call: Step = { id: 's1', kind: 'http', method: 'GET', url: 'https://api.example.com/v1/x', headers: {}, body: '', timeout: 10 };

  it('names the call by its host, and its permission too', () => {
    const p = phrasing();
    expect(describeStep(call, [call], CATALOG, p)).toBe('Call api.example.com');
    expect(describeStep({ ...call, url: '' }, [call], CATALOG, p)).toBe('Call another system');
    expect(actionLabel('http:https://api.example.com', CATALOG, p)).toBe('Call api.example.com');
    expect(actionLabel('http:https://api.example.com', CATALOG, phrasing('es'))).toBe('Llamar a api.example.com');
  });

  it('names a secret, the key and what a call leaves', () => {
    const p = phrasing();
    expect(pathLabel('secret.STRIPE_KEY', [call], CATALOG, p)).toBe('Secret «STRIPE_KEY»');
    expect(pathLabel('run.idempotency_key', [call], CATALOG, p)).toBe('No-repeat key');
    expect(pathLabel('steps.s1.status', [call], CATALOG, p)).toBe('1. Call api.example.com › Status');
  });

  it('says in the history what the call did', () => {
    const p = phrasing();
    const at = '2026-10-15T10:00:00+02:00';
    expect(describeLog({ step: 's1', kind: 'http', outcome: 'calling', host: 'api.example.com', at }, [call], CATALOG, p)).toBe('Calling api.example.com…');
    expect(describeLog({ step: 's1', kind: 'http', outcome: 'called', host: 'api.example.com', status: 201, at }, [call], CATALOG, p)).toBe('Called api.example.com: it answered 201');
  });
});

// FLOW-F28 to F30: what a question is called, and what its run says.
describe('a question in words', () => {
  const question: Step = { id: 's1', kind: 'ask', title: 'Refund {{input.amount}}?', details: '', role: 'manager', hours: 24, on_no: 'stop', on_timeout: 'no' };

  it('names the step by its question', () => {
    const p = phrasing();
    // A datum in the question is named by its words, never by its path.
    expect(describeStep(question, [question], CATALOG, p)).toBe('Ask: Refund «Amount»?');
    expect(describeStep({ ...question, title: '' }, [question], CATALOG, p)).toBe('Ask someone first');
    expect(describeStep(question, [question], CATALOG, phrasing('es'))).toBe('Preguntar: Refund «Importe»?');
    expect(pathLabel('steps.s1.approved', [question], CATALOG, p)).toBe('1. Ask: Refund «Amount»? › Approved');
  });

  it('says in the history who was asked, who answered and what', () => {
    const p = phrasing();
    const at = '2026-10-15T10:00:00+02:00';
    expect(describeLog({ step: 's1', kind: 'ask', outcome: 'asking', role: 'manager', until: '2026-10-16T10:00:00+02:00', at }, [question], CATALOG, p)).toBe(
      'Asked the managers; waiting for an answer until Oct 16, 2026, 10:00 AM',
    );
    expect(describeLog({ step: 's1', kind: 'ask', outcome: 'asking', role: '', until: at, at }, [question], CATALOG, p)).toContain('Asked whoever runs the business');
    expect(describeLog({ step: 's1', kind: 'ask', outcome: 'answered', approved: true, by: 'Marta', note: 'ok', at }, [question], CATALOG, p)).toBe('Marta answered yes: «ok»');
    expect(describeLog({ step: 's1', kind: 'ask', outcome: 'answered', approved: false, by: 'Marta', note: '', at }, [question], CATALOG, p)).toBe('Marta answered no');
    expect(describeLog({ step: 's1', kind: 'ask', outcome: 'expired', at }, [question], CATALOG, p)).toBe('Nobody answered in time');
  });
});


describe('«Ask the assistant» in words (FLOW-F37, F38)', () => {
  const en = phrasing('en');
  const step: Step = { id: 's1', kind: 'assistant', prompt: 'Book Ana', tools: [], mode: 'ask', max_rounds: 6 };
  const entry = (more: Partial<LogEntry>): LogEntry => ({ step: 's1', kind: 'assistant', outcome: 'thinking', at: '2026-10-28T10:00:00Z', ...more }) as LogEntry;

  it('names the step by what it is asked', () => {
    expect(describeStep(step, [step], null, en)).toBe('Ask the assistant: Book Ana');
    expect(describeStep({ ...step, prompt: '' }, [step], null, en)).toBe('Ask the assistant');
  });

  it('a run that waits for the assistant says so, not that it calls another system', () => {
    expect(runStatusPill('calling', en, [entry({})])).toEqual({ tone: 'info', label: 'Waiting for the assistant' });
    // Between two turns (the assistant used a read and thinks again) it still waits for the assistant.
    expect(runStatusPill('calling', en, [entry({}), entry({ outcome: 'assistant_used', operation: 'task.task.list', ok: true })]).label).toBe('Waiting for the assistant');
    expect(runStatusPill('calling', en, [entry({ kind: 'http', outcome: 'calling' })]).label).toBe('Calling another system');
  });

  it('tells in the history what the assistant did', () => {
    expect(describeLog(entry({}), [step], null, en)).toBe('Asked the assistant; it answers in a moment.');
    expect(describeLog(entry({ outcome: 'assistant_used', operation: 'task.task.create', ok: true }), [step], null, en)).toBe('The assistant used «Create a task».');
    expect(describeLog(entry({ outcome: 'assistant_used', operation: 'task.task.create', ok: false }), [step], null, en)).toBe('The assistant tried «Create a task», which did not take it.');
    expect(describeLog(entry({ outcome: 'assistant_answered', text: 'Done' }), [step], null, en)).toBe('The assistant answered: «Done»');
    expect(describeLog(entry({ outcome: 'assistant_proposed', operation: 'task.task.create', until: '2026-10-31T10:00:00Z' }), [step], null, en)).toMatch(
      /^The assistant wants to «Create a task»: it waits for a yes until /,
    );
  });

  it('says a tool was not used because a datum the step fixes was empty, naming the datum', () => {
    // FIX-HUB-FLOW-ASSISTANT-STEP-ACTS-ON-ANOTHER-CUSTOMER-WITHOUT-ON-BEHALF-OF: nothing half done, and visible.
    const empty = entry({ outcome: 'assistant_pinned_empty', operation: 'reservation.reservation.cancel', fields: ['on_behalf_of'] });
    expect(describeLog(empty, [step], null, en)).toBe(
      'The assistant tried «Cancel a reservation», but «On behalf of the customer», fixed by this step, was empty: it was not done.',
    );
    expect(describeLog(empty, [step], null, phrasing('es'))).toBe(
      'El asistente ha intentado «Anular una reserva», pero «En nombre del cliente», que fija este paso, estaba vacío: no se ha hecho.',
    );
  });
});
