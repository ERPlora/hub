// The lines of a run's History (WORKBOOK FLOW-F16), in words: each step by what it does, never by the id it has
// inside the automation, and a call or a request to the assistant said once, by how it went.
import { describe, expect, it } from 'vitest';

import { catalogNames, internalCodesIn } from '../__tests__/internal-codes';
import { TASK_CATALOG } from '../__tests__/mount-flow';
import { phrasingIn } from '../__tests__/phrasing';
import type { LogEntry, Step } from '../operations';
import { describeLog, historyLines, type LogWords } from './history';

const CATALOG = TASK_CATALOG;
const CALL: Step = { id: 's5', kind: 'http', method: 'POST', url: 'https://api.example.com/v1/x', headers: {}, body: '', timeout: 10 };
const STEPS: Step[] = [
  { id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' },
  { id: 's2', kind: 'condition', when: { 'input.total': { gte: 10000 } } },
  { id: 's3', kind: 'command', operation: 'task.task.create', params: {} },
  { id: 's4', kind: 'delay', seconds: 3600 },
  CALL,
  { id: 's6', kind: 'ask', title: 'Refund?', details: '', role: 'manager', hours: 24, on_no: 'stop', on_timeout: 'no' },
  { id: 's7', kind: 'assistant', prompt: 'Book Ana', tools: [], mode: 'ask', max_rounds: 6 },
];
const AT = '2026-10-15T10:00:00+02:00';
const words = (locale: 'en' | 'es' = 'en', steps: readonly Step[] = STEPS): LogWords => ({ steps, catalog: CATALOG, p: phrasingIn(locale, 'Europe/Madrid') });
const entry = (more: Partial<LogEntry>): LogEntry => ({ step: 's3', kind: 'command', outcome: 'done', at: AT, ...more }) as LogEntry;
const unreachable = { code: 'flow.http_unreachable', message: 'It could not reach «api.example.com», so it stopped.' };

describe('a line of the history', () => {
  it('in words, step by step', () => {
    const w = words();
    expect(describeLog(entry({ operation: 'task.task.create' }), w)).toBe('Did: Create a task');
    expect(describeLog(entry({ step: 's1', kind: 'query', outcome: 'found', count: 3 }), w)).toBe('Found 3');
    expect(describeLog(entry({ step: 's1', kind: 'query', outcome: 'not_found' }), w)).toBe('Found nothing, and carried on');
    expect(describeLog(entry({ step: 's2', kind: 'condition', outcome: 'passed' }), w)).toBe('The condition held');
    expect(describeLog(entry({ step: 's2', kind: 'condition', outcome: 'stopped', failed: [{ path: 'input.total', op: 'gte', value: 10000 }] }), w)).toBe(
      'It stopped here because this was not met: Total greater than or equal to 10000. That is the automation working.',
    );
    expect(describeLog(entry({ step: 's4', kind: 'delay', outcome: 'waited', seconds: 3600 }), w)).toBe('Waited 1 hour');
    expect(describeLog(entry({ operation: 'task.task.create', outcome: 'failed', error: { code: 'invalid_field', message: 'No such project.' } }), w)).toBe(
      'Create a task: No such project.',
    );
    expect(describeLog(entry({ operation: 'task.task.create', outcome: 'skipped', failed: [{ path: 'input.total', op: 'gte', value: 10000 }] }), w)).toBe(
      'Skipped: its “Only if…” did not hold (Total greater than or equal to 10000)',
    );
    expect(describeLog(entry({ operation: 'task.task.create', outcome: 'failed', continued: true, error: { code: 'flow.not_allowed', message: 'Not allowed.' } }), w)).toBe(
      'Create a task: Not allowed. It carried on with the next steps.',
    );
  });

  it('says what a call did', () => {
    const w = words();
    expect(describeLog({ step: 's5', kind: 'http', outcome: 'calling', host: 'api.example.com', at: AT }, w)).toBe('Calling api.example.com…');
    expect(describeLog({ step: 's5', kind: 'http', outcome: 'called', host: 'api.example.com', status: 201, at: AT }, w)).toBe('Called api.example.com: it answered 201');
  });

  it('says who was asked, who answered and what', () => {
    const w = words();
    const asked = { step: 's6', kind: 'ask', at: AT } as const;
    expect(describeLog({ ...asked, outcome: 'asking', role: 'manager', until: '2026-10-16T10:00:00+02:00' }, w)).toBe(
      'Asked the managers; waiting for an answer until Oct 16, 2026, 10:00 AM',
    );
    expect(describeLog({ ...asked, outcome: 'asking', role: '', until: AT }, w)).toContain('Asked whoever runs the business');
    expect(describeLog({ ...asked, outcome: 'answered', approved: true, by: 'Marta', note: 'ok' }, w)).toBe('Marta answered yes: “ok”');
    expect(describeLog({ ...asked, outcome: 'answered', approved: true, by: 'Marta', note: 'ok' }, words('es'))).toMatch(/: «ok»$/);
    expect(describeLog({ ...asked, outcome: 'answered', approved: false, by: 'Marta', note: '' }, w)).toBe('Marta answered no');
    expect(describeLog({ ...asked, outcome: 'expired' }, w)).toBe('Nobody answered in time');
  });

  it('tells what the assistant did (FLOW-F38)', () => {
    const w = words();
    const thought = (more: Partial<LogEntry>): LogEntry => entry({ step: 's7', kind: 'assistant', outcome: 'thinking', ...more });
    expect(describeLog(thought({}), w)).toBe('Asked the assistant; it answers in a moment.');
    expect(describeLog(thought({ outcome: 'assistant_used', operation: 'task.task.create', ok: true }), w)).toBe('The assistant used “Create a task”.');
    expect(describeLog(thought({ outcome: 'assistant_used', operation: 'task.task.create', ok: false }), w)).toBe('The assistant tried “Create a task”, which did not take it.');
    expect(describeLog(thought({ outcome: 'assistant_answered', text: 'Done' }), w)).toBe('The assistant answered: “Done”');
    expect(describeLog(thought({ outcome: 'assistant_proposed', operation: 'task.task.create', until: '2026-10-31T10:00:00Z' }), w)).toMatch(
      /^The assistant wants to “Create a task”: it waits for a yes until /,
    );
    const empty = thought({ outcome: 'assistant_pinned_empty', operation: 'reservation.reservation.cancel', fields: ['on_behalf_of'] });
    expect(describeLog(empty, w)).toBe('The assistant tried “Cancel a reservation”, but “On behalf of the customer”, fixed by this step, was empty: it was not done.');
    expect(describeLog(empty, words('es'))).toBe(
      'El asistente ha intentado «Anular una reserva», pero «En nombre del cliente», que fija este paso, estaba vacío: no se ha hecho.',
    );
  });
});

describe('a step that is not an action of the catalog, when it fails (hub#2586)', () => {
  const failed = entry({ step: 's5', kind: 'http', outcome: 'failed', error: unreachable });

  it('is named by what it does, never by its id', () => {
    expect(describeLog(failed, words())).toBe('Call api.example.com: It could not reach «api.example.com», so it stopped.');
    expect(describeLog({ ...failed, error: { ...unreachable, message: 'No ha podido llegar a «api.example.com», así que se ha parado.' } }, words('es'))).toBe(
      'Llamar a api.example.com: No ha podido llegar a «api.example.com», así que se ha parado.',
    );
    expect(describeLog(entry({ step: 's6', kind: 'ask', outcome: 'failed', error: { code: 'x', message: 'Nobody may answer it.' } }), words())).toBe('Ask: Refund?: Nobody may answer it.');
  });

  it('is named by its kind when the automation no longer has it', () => {
    expect(describeLog(failed, words('en', []))).toBe('Call another system: It could not reach «api.example.com», so it stopped.');
    expect(describeLog({ ...failed, host: 'api.example.com' }, words('es', []))).toMatch(/^Llamar a api\.example\.com: /);
  });
});

describe('the lines of a run', () => {
  const calling = entry({ step: 's5', kind: 'http', outcome: 'calling', host: 'api.example.com' });

  it('says a call once: while it goes on, and then how it went (hub#2586)', () => {
    const w = words();
    expect(historyLines([calling], w)).toEqual(['Calling api.example.com…']);
    expect(historyLines([calling, { ...calling, outcome: 'called', status: 201 }], w)).toEqual(['Called api.example.com: it answered 201']);
    expect(historyLines([calling, entry({ step: 's5', kind: 'http', outcome: 'failed', error: unreachable })], w)).toEqual([
      'Call api.example.com: It could not reach «api.example.com», so it stopped.',
    ]);
  });

  it('keeps each try of a resumed call, said by how it went', () => {
    const lines = historyLines(
      [calling, entry({ step: 's5', kind: 'http', outcome: 'failed', error: unreachable }), entry({ step: 's5', kind: 'http', outcome: 'resumed' }), calling, { ...calling, outcome: 'called', status: 200 }],
      words(),
    );
    expect(lines).toEqual(['Call api.example.com: It could not reach «api.example.com», so it stopped.', 'Resumed here, from the step that had failed', 'Called api.example.com: it answered 200']);
  });

  it('drops «it answers in a moment» once the assistant answered', () => {
    const thinking = entry({ step: 's7', kind: 'assistant', outcome: 'thinking' });
    expect(historyLines([thinking], words())).toEqual(['Asked the assistant; it answers in a moment.']);
    expect(historyLines([thinking, { ...thinking, outcome: 'assistant_answered', text: 'Done' }], words())).toEqual(['The assistant answered: “Done”']);
  });

  it('never shows an internal code, whatever a step did', () => {
    const outcomes: LogEntry['outcome'][] = ['done', 'found', 'not_found', 'passed', 'stopped', 'waiting', 'waited', 'failed', 'resumed', 'skipped', 'calling', 'called', 'asking', 'answered', 'expired', 'thinking', 'assistant_used', 'assistant_answered', 'assistant_proposed', 'assistant_pinned_empty'];
    for (const locale of ['en', 'es'] as const) {
      for (const step of [...STEPS, { id: 's9', kind: 'command', operation: '', params: {} } as Step]) {
        for (const outcome of outcomes) {
          const said = describeLog(entry({ step: step.id, kind: step.kind, outcome, error: { code: 'x', message: 'Broken.' }, host: 'api.example.com' }), words(locale));
          expect(internalCodesIn(said, catalogNames(CATALOG)), `${step.kind} ${outcome}: ${said}`).toEqual([]);
        }
      }
    }
  });
});
