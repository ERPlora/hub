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
};

async function setup(rows: QuestionOut[] = [Q], props: Record<string, unknown> = {}) {
  const m = await mountFlow(QuestionInbox, { props });
  await m.live();
  await m.result(OP, { rows });
  return m;
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
