// «Waiting for your answer» (WORKBOOK FLOW-F29; the old module's flows-f24): every question an automation asked and
// waits on that this person may answer, live — its words, who it was asked of, what a no and silence do —,
// a note, and «Approve» or «No». A refusal (too late, someone already answered, paused…) stays on its card.
import { describe, expect, it, vi } from 'vitest';

import type { QuestionOut } from '../operations';
import { click, errorFrame, ionValue, mountFlow, settle } from '../__tests__/mount-flow';
import QuestionInbox from './QuestionInbox.vue';

const mocks = vi.hoisted(() => ({ toastSuccess: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess: mocks.toastSuccess }));

const OP = 'flow.question.list';
const Q: QuestionOut = {
  id: 'q1',
  flow_id: 'f1',
  flow_name: 'Refunds',
  run_id: 'r1',
  title: 'Refund 12,50 € to Ana?',
  details: 'Sale 0042',
  role: 'manager',
  on_no: 'stop',
  on_timeout: 'no',
  expires_at: '2026-10-16T12:00:00+02:00',
  created_at: '2026-10-15T12:00:00+02:00',
  action: '',
  fields: [],
};

/** The change the assistant wants (FLOW-F38), its data as the server says them for whoever reads it (BASE-F97 step 2):
 *  a moment and a record already in words; an amount in cents, a yes or no and a list as such. */
const CHANGE: QuestionOut = {
  ...Q,
  id: 'q2',
  role: '',
  title: 'The assistant wants to change something in «Appointments»',
  action: 'Book an appointment',
  details: 'I will book Ana.',
  fields: [
    { name: 'start', label: 'Starts at', kind: 'text', value: 'Nov 2, 2026, 10:00 AM' },
    { name: 'services', label: 'Services', kind: 'list', value: [{}] },
    { name: 'price_cents', label: 'Price', kind: 'money', value: 1500 },
    { name: 'urgent', label: 'Urgent', kind: 'bool', value: true },
    { name: 'customer_id', label: 'Customer', kind: 'text', value: 'Ana López' },
    { name: 'notes', label: 'Notes', kind: 'empty', value: '' },
  ],
};

async function setup(rows: QuestionOut[] = [Q], props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountFlow(QuestionInbox, { props, locale });
  await m.live();
  await m.result(OP, { rows });
  return m;
}

/** The lines of a question's data, as the card shows them. */
function data(m: Awaited<ReturnType<typeof setup>>, id: string): string[] {
  return m.find(`flow-question-data-${id}`).findAll('li').map((line) => line.text());
}

describe('QuestionInbox', () => {
  it('shows each question with who it was asked of and what a no and silence do', async () => {
    const m = await setup();
    expect(m.find('flow-question-title-q1').text()).toBe('Refund 12,50 € to Ana?');
    expect(m.find('flow-question-q1').text()).toContain('Sale 0042');
    expect(m.find('flow-question-q1').text()).toContain('Refunds');
    expect(m.find('flow-question-who-q1').text()).toBe('Asked of the managers. Whoever runs the business can answer too.');
    expect(m.find('flow-question-silence-q1').text()).toBe('If nobody answers before Oct 16, 2026, 12:00 PM, it counts as a no.');
    expect(m.find('flow-question-no-q1').text()).toBe('A no stops the automation here.');
    const own = await setup([{ ...Q, role: '', on_no: 'continue', on_timeout: 'continue' }]);
    expect(own.find('flow-question-who-q1').text()).toBe('Asked of whoever runs the business.');
    expect(own.find('flow-question-silence-q1').text()).toContain('the automation carries on anyway');
    expect(own.find('flow-question-no-q1').text()).toBe('After a no, the automation carries on.');
  });

  it("says each datum of the assistant's change in words, as its card in the chat does (FLOW-F38)", async () => {
    const m = await setup([CHANGE]);
    await m.result('base.business.get', { currency: 'EUR', currency_decimals: 2 });
    expect(m.find('flow-question-q2').text()).toContain('I will book Ana.');
    expect(data(m, 'q2')).toEqual([
      'Starts at: Nov 2, 2026, 10:00 AM',
      'Services: 1 item',
      'Price: €15.00',
      'Urgent: Yes',
      'Customer: Ana López',
    ]);
    const shown = m.find('flow-question-q2').text();
    for (const raw of ['[{}]', '1500', 'true']) expect(shown).not.toContain(raw);
  });

  it("says them in the reader's language, the business's currency included", async () => {
    // The server says each datum, and names it, in the reader's language; the card's own words are base's.
    const fields = [
      { name: 'start', label: 'Inicio', kind: 'text', value: '2 nov 2026, 10:00' },
      { name: 'services', label: 'Servicios', kind: 'list', value: [{}] },
      { name: 'price_cents', label: 'Precio', kind: 'money', value: 1500 },
      { name: 'urgent', label: 'Urgente', kind: 'bool', value: true },
      { name: 'customer_id', label: 'Cliente', kind: 'text', value: 'Ana López' },
    ] satisfies QuestionOut['fields'];
    const m = await setup([{ ...CHANGE, fields }], {}, 'es');
    await m.result('base.business.get', { currency: 'EUR', currency_decimals: 2 });
    expect(data(m, 'q2')).toEqual([
      'Inicio: 2 nov 2026, 10:00',
      'Servicios: 1 elemento',
      'Precio: 15,00\u00a0€',
      'Urgente: Sí',
      'Cliente: Ana López',
    ]);
  });

  it('a question with no change of the assistant lists no data', async () => {
    const m = await setup();
    expect(m.find('flow-question-data-q1').exists()).toBe(false);
  });

  it("says the action the assistant wants first, right under the card's title (FLOW-F29, FLOW-F38)", async () => {
    // The server names it as the History does, in the reader's language: a cancellation reads «Cancel a reservation»,
    // never only «… wants to change something».
    const m = await setup([CHANGE]);
    const action = m.find('flow-question-action-q2');
    expect(action.text()).toBe('Book an appointment');
    const order = m.find('flow-question-q2').element.children;
    const at = (testid: string) => [...order].findIndex((child) => child.getAttribute('data-testid') === testid);
    expect(at('flow-question-action-q2')).toBe(at('flow-question-title-q2') + 1);
    expect(at('flow-question-action-q2')).toBeLessThan(at('flow-question-data-q2'));
    const es = await setup([{ ...CHANGE, title: 'El asistente quiere cambiar algo en «Citas»', action: 'Reservar una cita' }], {}, 'es');
    expect(es.find('flow-question-action-q2').text()).toBe('Reservar una cita');
  });

  it('a question an automation step asks says no action of the assistant', async () => {
    const m = await setup();
    expect(m.find('flow-question-action-q1').exists()).toBe(false);
  });

  it('approves with a note', async () => {
    mocks.toastSuccess.mockClear();
    const m = await setup();
    m.answerBy({ '/api/flow/questions/answer': [200, { id: 'q1', run_id: 'r1', status: 'succeeded' }] });
    await ionValue(m.find('flow-question-note-q1').element, 'ok, go', 'ionInput');
    await click(m.find('flow-question-yes-q1').element);
    await settle();
    expect(m.sent().filter((call) => call.path === '/api/flow/questions/answer').map((call) => call.body)).toEqual([{ id: 'q1', approve: true, note: 'ok, go' }]);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Approved: the automation carries on.');
  });

  it('answers no', async () => {
    mocks.toastSuccess.mockClear();
    const m = await setup();
    m.answerBy({ '/api/flow/questions/answer': [200, { id: 'q1', run_id: 'r1', status: 'cancelled' }] });
    await click(m.find('flow-question-reject-q1').element);
    await settle();
    expect(m.sent().filter((call) => call.path === '/api/flow/questions/answer').map((call) => call.body)).toEqual([{ id: 'q1', approve: false, note: '' }]);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Answered no.');
  });

  it('a refusal stays on its card, worded by the server', async () => {
    const m = await setup();
    m.answerBy({ '/api/flow/questions/answer': [409, { error: { code: 'flow.question_expired', message: 'Too late: nobody answered it in time, so it was closed. Nothing was done.' } }] });
    await click(m.find('flow-question-yes-q1').element);
    await settle();
    expect(m.find('flow-question-problem-q1').text()).toBe('Too late: nobody answered it in time, so it was closed. Nothing was done.');
    expect(m.find('flow-question-q1').exists()).toBe(true);
  });

  it('without questions it hides, or says so when it is all the page shows', async () => {
    const hidden = await setup([]);
    expect(hidden.find('flow-inbox').exists()).toBe(false);
    const alone = await setup([], { alone: true });
    expect(alone.find('flow-inbox-empty').text()).toBe('Nothing is waiting for your answer.');
  });

  it('says when it is loading and when it could not be read', async () => {
    const m = await mountFlow(QuestionInbox, { props: { alone: true } });
    const call = await m.live();
    expect(m.find('flow-inbox-loading').exists()).toBe(true);
    call.push(errorFrame(m.subId(OP), 'internal_error'));
    await settle();
    expect(m.find('flow-inbox-error').text()).toContain('It could not be read right now. Try again in a moment.');
  });
});
