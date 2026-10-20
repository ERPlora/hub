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

const FAILED = run('r2', {
  status: 'failed',
  error_code: 'flow.not_allowed',
  error_message: 'It tried to do something you have not allowed it to do («task.task.create»), so it stopped.',
  log: [{ step: 's1', kind: 'command', operation: 'task.task.create', outcome: 'failed', at: '2026-10-15T11:00:00+02:00', error: { code: 'flow.not_allowed', message: 'Not allowed.' } }],
});

async function setup(rows: RunOut[], failed = 0, total = rows.length) {
  const m = await mountFlow(HistoryPanel, { props: { flowId: 'f1', steps: STEPS, catalog: CATALOG } });
  await m.live();
  await m.result(OP, { rows, total, limit: 20, offset: 0, failed });
  return m;
}

describe('HistoryPanel', () => {
  it('follows the runs of the automation, twenty at a time', async () => {
    const m = await setup([]);
    expect(m.params(OP)).toEqual([{ flow_id: 'f1', limit: 20, offset: 0 }]);
    expect(m.find('flow-history-empty').text()).toBe('It has not run yet.');
  });

  it('a history that could not be read says the screen\'s sentence when the server did not word it (hub#2320)', async () => {
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

  it('a run says how it ended, why it failed and what to do', async () => {
    const m = await setup([FAILED], 1);
    const failed = m.find('flow-run-r2');
    expect(failed.text()).toContain('Stopped by an error');
    expect(m.find('flow-run-trouble-r2').text()).toContain('It tried to do something you have not allowed it to do');
    expect(m.find('flow-run-trouble-r2').text()).toContain('Open Permissions and allow what it needs.');
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
});
