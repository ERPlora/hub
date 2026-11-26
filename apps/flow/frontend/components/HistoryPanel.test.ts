// «History» (WORKBOOK FLOW-F16): what the automation did, the newest first and live, the ones that
// stopped by an error on top; each run says how it ended and when, opens to its steps in words, says
// why it failed and what to do, and its reference is copied for support. «See more» goes back further.
import { describe, expect, it, vi } from 'vitest';

import type { CatalogOut, RunOut, Step } from '../operations';
import { click, errorFrame, mountFlow, settle } from '../__tests__/mount-flow';
import HistoryPanel from './HistoryPanel.vue';

const toastSuccess = vi.hoisted(() => vi.fn<(message: string) => Promise<void>>(async () => undefined));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess }));
const confirm = vi.hoisted(() => vi.fn<(options: unknown) => Promise<boolean>>());
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm }),
}));

const OP = 'flow.run.list';
const CATALOG = { events: [], actions: [{ name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: [] }] } as unknown as CatalogOut;
const STEPS: Step[] = [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }];

const run = (id: string, over: Partial<RunOut> = {}): RunOut => ({
  id,
  flow_id: 'f1',
  flow_version: 1,
  status: 'succeeded',
  trigger_kind: 'event',
  event_name: 'customer.customer.created',
  input: {},
  step_index: 1,
  steps_total: 1,
  log: [{ step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'done', at: '2026-10-15T10:00:00+02:00' }],
  error_code: '',
  error_message: '',
  resume_at: null,
  started_at: '2026-10-15T10:00:00+02:00',
  finished_at: '2026-10-15T10:00:00+02:00',
  started_by: 'system',
  resumable: false,
  ...over,
});

const NOT_ALLOWED = 'It tried to do something you have not allowed it to do («Create a task»), so it stopped.';
const ADVICE = 'Open Permissions and allow what it needs.';
const FAILED = run('r2', {
  status: 'failed',
  error_code: 'flow.not_allowed',
  error_message: NOT_ALLOWED,
  log: [{ step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'failed', at: '2026-10-15T11:00:00+02:00', error: { code: 'flow.not_allowed', message: NOT_ALLOWED } }],
});

async function setup(rows: RunOut[], failed = 0, total = rows.length) {
  const m = await mountFlow(HistoryPanel, { props: { flowId: 'f1', steps: STEPS, catalog: CATALOG } });
  await m.live();
  await m.result(OP, { rows, total, limit: 20, offset: 0, failed });
  return m;
}

describe('HistoryPanel', () => {
  it('says «Loading…» as a status until the first runs are in, with the one LoadingNote of flow (hub#969)', async () => {
    const m = await mountFlow(HistoryPanel, { props: { flowId: 'f1', steps: STEPS, catalog: CATALOG } });
    await m.live();
    expect(m.find('flow-history-loading').text()).toBe('Loading…');
    expect(m.find('flow-history-loading').attributes('role')).toBe('status');
    await m.result(OP, { rows: [], total: 0, limit: 20, offset: 0, failed: 0 });
    expect(m.find('flow-history-loading').exists()).toBe(false);
  });

  it('follows the runs of the automation, twenty at a time', async () => {
    const m = await setup([]);
    expect(m.params(OP)).toEqual([{ flow_id: 'f1', limit: 20, offset: 0 }]);
    expect(m.find('flow-history-empty').text()).toBe('It has not run yet.');
  });

  it('a history that could not be read says the screen\'s sentence when the server did not word it', async () => {
    const m = await mountFlow(HistoryPanel, { props: { flowId: 'f1', steps: STEPS, catalog: CATALOG } });
    const call = await m.live();
    call.push(errorFrame(m.subId(OP, { flow_id: 'f1' }), 'internal_error'));
    await settle();
    expect(m.find('flow-history-error').text()).toContain('It could not be read right now. Try again in a moment.');
    expect(m.find('flow-history-error').text()).not.toContain('msg internal_error');
  });

  it('a refusal the server worded is shown as it came', async () => {
    const m = await mountFlow(HistoryPanel, { props: { flowId: 'f1', steps: STEPS, catalog: CATALOG } });
    const call = await m.live();
    call.push(errorFrame(m.subId(OP, { flow_id: 'f1' }), 'permission_denied'));
    await settle();
    expect(m.find('flow-history-error').text()).toContain('msg permission_denied');
  });

  it('puts the ones that stopped by an error on top, with how many', async () => {
    const m = await setup([run('r1'), FAILED], 1);
    expect(m.find('flow-history-attention').text()).toContain('Needs somebody');
    expect(m.find('flow-history-attention').text()).toContain('1 run stopped by a problem');
    const ids = m.wrapper.findAll('[data-testid^="flow-run-r"]').filter((el) => /^flow-run-r\d$/.test(el.attributes('data-testid') ?? '')).map((el) => el.attributes('data-testid'));
    expect(ids).toEqual(['flow-run-r2', 'flow-run-r1']);
  });

  it('says several stopped runs in the plural', async () => {
    const m = await setup([run('r1'), FAILED], 2);
    expect(m.find('flow-history-attention').text()).toContain('2 runs stopped by a problem');
  });

  it('a run says how it ended, why it failed and what to do', async () => {
    const m = await setup([FAILED], 1);
    const failed = m.find('flow-run-r2');
    expect(failed.text()).toContain('Stopped by an error');
    expect(m.find('flow-run-trouble-r2').text()).toContain(NOT_ALLOWED);
    expect(m.find('flow-run-trouble-r2').text()).toContain(ADVICE);
  });

  it('a run resumed and stopped again by a missing permission says what to do once, with its steps open', async () => {
    const failedAgain = { step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'failed', at: '2026-10-15T12:00:00+02:00', error: { code: 'flow.not_allowed', message: NOT_ALLOWED } } as const;
    const resumed = { step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'resumed', at: '2026-10-15T12:00:00+02:00', by: 'ana' } as const;
    const m = await setup([{ ...FAILED, log: [...FAILED.log, resumed, failedAgain] }], 1);
    await click(m.find('flow-run-toggle-r2').element);
    expect(m.find('flow-run-steps-r2').text()).toContain(`Create a task: ${NOT_ALLOWED}`);
    expect(m.find('flow-run-r2').text().split(ADVICE)).toHaveLength(2);
  });

  it('opens to its steps in words', async () => {
    const m = await setup([run('r1')]);
    expect(m.find('flow-run-steps-r1').exists()).toBe(false);
    await click(m.find('flow-run-toggle-r1').element);
    expect(m.find('flow-run-steps-r1').text()).toContain('Did: Create a task');
  });

  it('copies its reference for support', async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    toastSuccess.mockClear();
    const m = await setup([run('r1')]);
    await click(m.find('flow-run-copy-r1').element);
    await settle();
    expect(writeText).toHaveBeenCalledWith('r1');
    expect(toastSuccess).toHaveBeenCalledWith('Copied. Paste it if you ask us about this run.');
  });

  it('«See more» follows twenty more', async () => {
    const m = await setup([run('r1')], 0, 30);
    await click(m.find('flow-history-more').element);
    await m.reopen();
    expect(m.params(OP)).toEqual([{ flow_id: 'f1', limit: 40, offset: 0 }]);
  });

  // FLOW-F24: a run stopped by an error at a step resumes there, after a confirmation.
  it('a run that can be resumed offers it, asks first and resumes it at the step that failed', async () => {
    toastSuccess.mockClear();
    confirm.mockResolvedValue(true);
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    m.answerBy({ '/api/flow/runs/retry': [200, run('r2', { status: 'succeeded' })] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Resume it from the step that failed?', confirmLabel: 'Yes, resume it' }));
    expect(m.sent().filter((call) => call.path === '/api/flow/runs/retry').map((call) => call.body)).toEqual([{ id: 'r2' }]);
    expect(toastSuccess).toHaveBeenCalledWith('Resumed: it finished well.');
  });

  it('cancelling the question resumes nothing', async () => {
    confirm.mockResolvedValue(false);
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    expect(m.sent().filter((call) => call.path === '/api/flow/runs/retry')).toEqual([]);
  });

  it('a resumed run that stops again, or a refusal, is said next to the run', async () => {
    confirm.mockResolvedValue(true);
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    m.answerBy({ '/api/flow/runs/retry': [200, run('r2', { status: 'failed', error_message: 'Not allowed yet.' })] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    expect(m.find('flow-run-retry-problem-r2').text()).toBe('It was resumed and stopped by an error again: Not allowed yet.');
    m.answerBy({ '/api/flow/runs/retry': [409, { error: { code: 'flow.disabled', message: 'This automation is paused: turn it on to run it.' } }] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    expect(m.find('flow-run-retry-problem-r2').text()).toBe('This automation is paused: turn it on to run it.');
  });

  // The notice says what the resumed run is doing right now, as «Run now» does: a run still calling another system,
  // waiting for an answer or for the assistant has not finished.
  it.each([
    ['succeeded', 'command', 'done', 'Resumed: it finished well.'],
    ['succeeded', 'assistant', 'assistant_answered', 'Resumed: it finished well.'],
    ['stopped', 'condition', 'stopped', 'Resumed: it finished, the condition was not met.'],
    ['waiting', 'delay', 'waiting', 'Resumed: it is waiting. See how it goes here.'],
    ['calling', 'http', 'calling', 'Resumed: it is calling another system. See how it goes here.'],
    ['calling', 'assistant', 'thinking', 'Resumed: the assistant is on it. See how it goes here.'],
    ['asking', 'ask', 'asking', 'Resumed: it is waiting for an answer in “Waiting for your answer”.'],
  ] as const)('a run resumed that is now %s at a %s step says so', async (status, kind, outcome, notice) => {
    toastSuccess.mockClear();
    confirm.mockResolvedValue(true);
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    const log = [{ step: 's1', kind, outcome, at: '2026-10-15T12:00:00+02:00' }];
    m.answerBy({ '/api/flow/runs/retry': [200, run('r2', { status, log })] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    expect(toastSuccess.mock.calls).toEqual([[notice]]);
  });

  it('a run resumed that stops again at once has no «Resumed» notice, only why next to it', async () => {
    toastSuccess.mockClear();
    confirm.mockResolvedValue(true);
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    m.answerBy({ '/api/flow/runs/retry': [200, run('r2', { status: 'failed', error_message: 'Not allowed yet.' })] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(m.find('flow-run-retry-problem-r2').text()).toBe('It was resumed and stopped by an error again: Not allowed yet.');
  });

  it('a resumed run that ends later without an error says nothing of an error next to it', async () => {
    confirm.mockResolvedValue(true);
    const asking = run('r2', {
      status: 'asking',
      finished_at: null,
      log: [{ step: 's1', kind: 'ask', outcome: 'asking', at: '2026-10-15T12:00:00+02:00' }],
    });
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    m.answerBy({ '/api/flow/runs/retry': [200, asking] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    const answeredNo = { ...asking, status: 'cancelled' as const, error_code: 'flow.question_rejected', error_message: 'Cancelled: Ana answered no to «Book».' };
    await m.result(OP, { rows: [answeredNo], total: 1, limit: 20, offset: 0, failed: 0 }, {}, 2);
    expect(m.find('flow-run-trouble-r2').text()).toContain('Cancelled: Ana answered no to «Book».');
    expect(m.find('flow-run-retry-problem-r2').exists()).toBe(false);
  });

  it('a resumed call that fails again later says so next to the run, with why', async () => {
    confirm.mockResolvedValue(true);
    const calling = run('r2', {
      status: 'calling',
      finished_at: null,
      log: [{ step: 's1', kind: 'http', outcome: 'calling', host: 'qa.invalid', at: '2026-10-15T12:00:00+02:00' }],
    });
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    m.answerBy({ '/api/flow/runs/retry': [200, calling] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    await m.result(OP, { rows: [calling], total: 1, limit: 20, offset: 0, failed: 0 }, {}, 2);
    expect(m.find('flow-run-retry-problem-r2').exists()).toBe(false);
    const failedAgain = { ...calling, status: 'failed' as const, error_code: 'flow.http_timeout', error_message: 'It could not reach qa.invalid.', resumable: true };
    await m.result(OP, { rows: [failedAgain], total: 1, limit: 20, offset: 0, failed: 1 }, {}, 3);
    expect(m.find('flow-run-retry-problem-r2').text()).toBe('It was resumed and stopped by an error again: It could not reach qa.invalid.');
  });

  it('a resumed run that waits and stops by an error after the wait says so next to the run', async () => {
    confirm.mockResolvedValue(true);
    const waiting = run('r2', { status: 'waiting', finished_at: null, log: [{ step: 's1', kind: 'delay', outcome: 'waiting', at: '2026-10-15T12:00:00+02:00' }] });
    const m = await setup([{ ...FAILED, resumable: true }], 1);
    m.answerBy({ '/api/flow/runs/retry': [200, waiting] });
    await click(m.find('flow-run-retry-r2').element);
    await settle();
    const failedAgain = { ...waiting, status: 'failed' as const, error_code: 'flow.not_allowed', error_message: NOT_ALLOWED, resumable: true };
    await m.result(OP, { rows: [failedAgain], total: 1, limit: 20, offset: 0, failed: 1 }, {}, 2);
    expect(m.find('flow-run-retry-problem-r2').text()).toBe(`It was resumed and stopped by an error again: ${NOT_ALLOWED}`);
  });

  it('a run that stops by an error without being resumed here says nothing of a resume', async () => {
    const m = await setup([run('r4', { status: 'calling', finished_at: null })]);
    await m.result(OP, { rows: [run('r4', { status: 'failed', error_message: 'It could not reach qa.invalid.' })], total: 1, limit: 20, offset: 0, failed: 1 }, {}, 2);
    expect(m.find('flow-run-trouble-r4').text()).toContain('It could not reach qa.invalid.');
    expect(m.find('flow-run-retry-problem-r4').exists()).toBe(false);
  });

  it('a run that cannot be resumed offers nothing', async () => {
    const m = await setup([FAILED, run('r1')], 1);
    expect(m.find('flow-run-retry-r2').exists()).toBe(false);
    expect(m.find('flow-run-retry-r1').exists()).toBe(false);
  });

  it('says in its steps where it was resumed', async () => {
    const resumed = run('r3', {
      log: [
        { step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'failed', at: '2026-10-15T11:00:00+02:00', error: { code: 'flow.not_allowed', message: 'Not allowed.' } },
        { step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'resumed', at: '2026-10-15T12:00:00+02:00', by: 'ana' },
        { step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'done', at: '2026-10-15T12:00:00+02:00' },
      ],
    });
    const m = await setup([resumed]);
    await click(m.find('flow-run-toggle-r3').element);
    expect(m.find('flow-run-steps-r3').text()).toContain('Resumed here, from the step that had failed');
  });

  // FLOW-F26/F27: what to do when a call or a secret stopped the run.
  it('says what to do when a call or a secret stopped it', async () => {
    const codes: Record<string, string> = {
      'flow.http_blocked': 'Use the public address of the other system',
      'flow.http_status': 'Check in the other system why it refused',
      'flow.http_timeout': 'Try again later',
      'flow.secret_not_found': 'Save the secret again',
      'flow.secrets_key_missing': 'encryption key',
    };
    for (const [code, words] of Object.entries(codes)) {
      const m = await setup([run('r9', { status: 'failed', error_code: code, error_message: 'It stopped.' })]);
      expect(m.find('flow-run-trouble-r9').text()).toContain(words);
    }
  });
});

