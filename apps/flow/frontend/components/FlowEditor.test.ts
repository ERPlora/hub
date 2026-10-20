// The editor of an automation (WORKBOOK «Editor de automatización»; FLOW-F09 to F16, F18): its head —
// name, Active/Paused, switch, «Try it», «Run now», «Save» — and four tabs: Steps (the trigger card, the
// column of steps, the buttons to add), Try it, Permissions and History. Saving sends the whole
// document; the server's refusals show next to their step; a draft of the assistant shows its box.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CatalogOut, DraftOut, FlowOut } from '../operations';
import { click, ionChecked, ionValue, mountFlow, settle } from '../__tests__/mount-flow';
import { emptyDocument, fromFlow } from '../lib/document';
import FieldPicker from './FieldPicker.vue';
import FlowEditor from './FlowEditor.vue';
import HistoryPanel from './HistoryPanel.vue';
import PermissionsPanel from './PermissionsPanel.vue';
import StepNode from './StepNode.vue';
import TestPanel from './TestPanel.vue';
import TriggerCard from './TriggerCard.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), toastSuccess: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess: mocks.toastSuccess }));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
afterEach(() => {
  mocks.confirm.mockReset();
  mocks.toastSuccess.mockClear();
});

const CATALOG: CatalogOut = {
  events: [{ name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' }],
  actions: [
    {
      name: 'task.task.create',
      kind: 'command',
      app: 'task',
      app_name: 'Tasks',
      description: '',
      fields: [{ name: 'title', type: 'string', required: true, description: '', choices: [] }],
      outputs: ['id', 'number'],
    },
  ],
};

const FLOW: FlowOut = {
  id: 'f1',
  name: 'Big sale',
  enabled: false,
  trigger: { kind: 'event', event: 'sale.sale.completed' },
  steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Thank them' } }],
  grants: [],
  required_grants: ['task.task.create'],
  missing_grants: ['task.task.create'],
  version: 1,
  next_fire_at: null,
  created_at: '2026-10-15T10:00:00+02:00',
  updated_at: '2026-10-15T10:00:00+02:00',
  created_by: '',
  updated_by: '',
  last_run: null,
};

const BASE_ANSWERS: Record<string, [number, unknown]> = {
  '/api/flow/catalog': [200, CATALOG],
  '/api/flow/events/sample': [200, { found: true, event: 'sale.sale.completed', at: '2026-10-15T09:00:00+02:00', payload: { total: 12500, customer_name: 'Ana' } }],
};

async function setup(props: Record<string, unknown>, answers: Record<string, [number, unknown]> = {}) {
  const m = await mountFlow(FlowEditor, { props: { tab: 'steps', draft: null, ...props }, answers: { ...BASE_ANSWERS, ...answers } });
  await settle();
  const sentTo = (path: string) => m.sent().filter((call) => call.path === path);
  return { ...m, sentTo };
}

describe('FlowEditor: a new automation', () => {
  it('starts untitled, paused, by hand and without steps', async () => {
    const s = await setup({ flow: null, initial: emptyDocument() });
    expect((s.find('flow-editor-name').element as unknown as { placeholder: string }).placeholder).toBe('Untitled automation');
    expect(s.find('flow-editor-state').text()).toBe('Paused');
    expect(s.wrapper.findComponent(TriggerCard).props('modelValue')).toEqual({ kind: 'manual' });
    expect(s.find('flow-editor-nosteps').text()).toBe('No steps yet. Add the first thing this automation should do.');
    expect(s.find('flow-editor-run').exists()).toBe(false);
  });

  it('opened right after being created, it says «Saved.» (FLOW-F09)', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW), savedNow: true });
    expect(s.find('flow-editor-notice').text()).toBe('Saved.');
  });

  it('«Save» says its word, never an empty button (flows#144)', async () => {
    const s = await setup({ flow: null, initial: emptyDocument() });
    expect(s.find('flow-editor-save').text()).toBe('Save');
  });

  it('adds steps with the four buttons, open, and saves the whole document', async () => {
    const s = await setup({ flow: null, initial: emptyDocument() }, { '/api/flow/flows': [201, { ...FLOW, id: 'f9' }] });
    for (const kind of ['command', 'query', 'condition', 'delay']) await click(s.find(`flow-editor-add-${kind}`).element);
    expect(s.wrapper.findAllComponents(StepNode).map((node) => [node.props('step').kind, node.props('open')])).toEqual([
      ['command', false],
      ['query', false],
      ['condition', false],
      ['delay', true],
    ]);
    await ionValue(s.find('flow-editor-name').element, 'Weekly', 'ionInput');
    await click(s.find('flow-editor-save').element);
    await settle();
    const [created] = s.sentTo('/api/flow/flows');
    expect(created.body).toMatchObject({ name: 'Weekly', trigger: { kind: 'manual' } });
    expect(created.body).not.toHaveProperty('enabled');
    expect((created.body as { steps: unknown[] }).steps).toHaveLength(4);
    expect(s.wrapper.emitted('saved')).toEqual([[{ ...FLOW, id: 'f9' }]]);
    expect(s.find('flow-editor-notice').text()).toBe('Saved.');
  });

  it('a draft of the assistant shows its box and what it could not decide, and is used when saved', async () => {
    const draft = { id: 'd1', name: 'Call them', notes: ['I guessed the time.'], definition: { steps: [] } } as unknown as DraftOut;
    const s = await setup({ flow: null, initial: { ...emptyDocument(), name: 'Call them' }, draft }, { '/api/flow/flows': [201, FLOW] });
    expect(s.find('flow-editor-draft').text()).toContain('This is a draft the assistant wrote.');
    expect(s.find('flow-editor-draft').text()).toContain('I guessed the time.');
    await click(s.find('flow-editor-save').element);
    await settle();
    expect(s.sentTo('/api/flow/flows')[0].body).toMatchObject({ draft_id: 'd1', name: 'Call them' });
  });
});

describe('FlowEditor: a saved automation', () => {
  it('saves what changed as an update, and says when it is no longer dirty', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW) }, { '/api/flow/flows/update': [200, { ...FLOW, name: 'Bigger sale' }] });
    expect(s.wrapper.emitted('dirty')).toBeUndefined();
    await ionValue(s.find('flow-editor-name').element, 'Bigger sale', 'ionInput');
    expect(s.wrapper.emitted('dirty')?.at(-1)).toEqual([true]);
    await click(s.find('flow-editor-save').element);
    await settle();
    expect(s.sentTo('/api/flow/flows/update')[0].body).toEqual({
      id: 'f1',
      name: 'Bigger sale',
      trigger: { kind: 'event', event: 'sale.sale.completed' },
      steps: FLOW.steps,
    });
    expect(s.wrapper.emitted('dirty')?.at(-1)).toEqual([false]);
  });

  it('shows the server’s refusal next to its step', async () => {
    const s = await setup(
      { flow: FLOW, initial: fromFlow(FLOW) },
      { '/api/flow/flows/update': [422, { error: { code: 'invalid_payload', message: 'Choose what this step does.', fields: { 'steps.0.command.operation': 'Choose what this step does.' } } }] },
    );
    await click(s.find('flow-editor-save').element);
    await settle();
    expect(s.find('flow-editor-error').text()).toContain('Choose what this step does.');
    expect(s.wrapper.findComponent(StepNode).props('errors')).toEqual({ 'steps.0.operation': 'Choose what this step does.' });
    expect(s.wrapper.findComponent(StepNode).props('open')).toBe(true);
  });

  it('a save the Hub did not answer says so in words, never the technical text (hub#2320)', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW) }, { '/api/flow/flows/update': [502, { detail: 'Bad gateway' }] });
    await click(s.find('flow-editor-save').element);
    await settle();
    expect(s.find('flow-editor-error').text()).toContain('It could not be done right now. Try again in a moment.');
    expect(s.find('flow-editor-error').text()).not.toContain('Unexpected response');
  });

  it('turning it on warns of the permissions it lacks and that it was not tried', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW) });
    await ionChecked(s.find('flow-editor-enabled').element, true);
    expect(s.find('flow-editor-state').text()).toBe('Unfinished');
    expect(s.find('flow-editor-warning').text()).toContain('it still lacks the permissions it asks for');
    expect(s.find('flow-editor-warning').text()).toContain('You have not tried it yet');
  });

  it('«Run now» asks first, runs it for real and says so', async () => {
    const s = await setup({ flow: { ...FLOW, enabled: true }, initial: fromFlow({ ...FLOW, enabled: true }) }, { '/api/flow/flows/run': [200, { id: 'r1', status: 'succeeded' }] });
    mocks.confirm.mockResolvedValue(true);
    await click(s.find('flow-editor-run').element);
    await settle();
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Run it now?', confirmLabel: 'Yes, run it' }));
    expect(s.sentTo('/api/flow/flows/run')[0].body).toEqual({ id: 'f1' });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Run. See it in History.');
  });

  it('the four tabs: Steps, Try it, Permissions and History', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW) }, { '/api/flow/flows/test': [200, { sample: { found: false, event: '', at: null, payload: {} }, starts: true, trigger_failed: [], steps: [] }] });
    await click(s.find('flow-editor-test').element);
    expect(s.wrapper.findComponent(TestPanel).props()).toMatchObject({ flowId: 'f1' });
    await ionValue(s.find('flow-editor-tabs').element, 'permissions');
    expect(s.wrapper.findComponent(PermissionsPanel).props('flow')).toEqual(FLOW);
    await ionValue(s.find('flow-editor-tabs').element, 'history');
    expect(s.wrapper.findComponent(HistoryPanel).props('flowId')).toBe('f1');
  });

  it('«Insert data» offers what the last real event brought and what earlier steps leave', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow({ ...FLOW, steps: [...FLOW.steps, { id: 's2', kind: 'command', operation: 'task.task.create', params: { title: '' } }] }) });
    expect(s.sentTo('/api/flow/events/sample')[0].query).toEqual({ event: 'sale.sale.completed' });
    const picked = (s.wrapper.findAllComponents(StepNode)[1].props('pick') as () => Promise<string | null>)();
    await settle();
    const picker = s.wrapper.findComponent(FieldPicker);
    expect(picker.props('open')).toBe(true);
    expect(picker.props('choices').map((choice: { path: string }) => choice.path)).toEqual([
      'input.total',
      'input.customer_name',
      'steps.s1.id',
      'steps.s1.number',
    ]);
    picker.vm.$emit('pick', 'input.customer_name');
    await expect(picked).resolves.toBe('input.customer_name');
  });

  it('reorders the steps with the gesture', async () => {
    const two = { ...FLOW, steps: [...FLOW.steps, { id: 's2', kind: 'delay' as const, seconds: 60 }] };
    const s = await setup({ flow: two, initial: fromFlow(two) });
    const complete = vi.fn();
    s.find('flow-editor-steps').element.dispatchEvent(new CustomEvent('ionItemReorder', { detail: { from: 1, to: 0, complete }, bubbles: true }));
    await settle();
    expect(s.wrapper.findAllComponents(StepNode).map((node) => node.props('step').id)).toEqual(['s2', 's1']);
    expect(complete).toHaveBeenCalledWith(false);
  });
});

describe('FlowEditor: review 2026-10-15', () => {
  it('the switch is saved by «set_enabled», after the document (item 3)', async () => {
    const s = await setup(
      { flow: null, initial: emptyDocument() },
      { '/api/flow/flows': [201, { ...FLOW, id: 'f9' }], '/api/flow/flows/set_enabled': [200, { ...FLOW, id: 'f9', enabled: true }] },
    );
    await ionChecked(s.find('flow-editor-enabled').element, true);
    await click(s.find('flow-editor-save').element);
    await settle();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/flow/catalog', undefined],
      ['/api/flow/flows', { name: '', trigger: { kind: 'manual' }, steps: [] }],
      ['/api/flow/flows/set_enabled', { id: 'f9', enabled: true }],
    ]);
    expect(s.wrapper.emitted('saved')?.at(-1)).toEqual([{ ...FLOW, id: 'f9', enabled: true }]);
  });

  it('a run by hand that stopped by an error says so, never «Run.» (item 11)', async () => {
    const on = { ...FLOW, enabled: true };
    const s = await setup(
      { flow: on, initial: fromFlow(on) },
      { '/api/flow/flows/run': [200, { id: 'r1', status: 'failed', error_message: 'It tried to do something you have not allowed it to do.' }] },
    );
    mocks.confirm.mockResolvedValue(true);
    await click(s.find('flow-editor-run').element);
    await settle();
    expect(s.find('flow-editor-error').text()).toBe('It ran and stopped by an error: It tried to do something you have not allowed it to do.');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it('with unsaved changes «Run now» waits for the save: it would run the saved version (item 11)', async () => {
    const on = { ...FLOW, enabled: true };
    const s = await setup({ flow: on, initial: fromFlow(on) });
    await ionValue(s.find('flow-editor-name').element, 'Changed', 'ionInput');
    expect((s.find('flow-editor-run').element as unknown as { disabled: boolean }).disabled).toBe(true);
    expect(s.find('flow-editor-run-hint').text()).toBe('Save it first: «Run now» runs what is saved.');
  });

  it('the permissions are read from what is saved, and ask to save the changes first (item 12)', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW) });
    await ionValue(s.find('flow-editor-tabs').element, 'permissions');
    expect(s.wrapper.findComponent(PermissionsPanel).props()).toMatchObject({ flow: FLOW, dirty: false });
    await ionValue(s.find('flow-editor-name').element, 'Changed', 'ionInput');
    expect(s.wrapper.findComponent(PermissionsPanel).props('dirty')).toBe(true);
  });

  it('a catalog that could not be read is said, with «Retry» (item 5)', async () => {
    const s = await setup({ flow: FLOW, initial: fromFlow(FLOW) }, { '/api/flow/catalog': [500, { error: { code: 'internal_error', message: 'Internal error' } }] });
    expect(s.find('flow-catalog-error').text()).toContain('What automations can use here could not be read.');
    expect(s.find('flow-catalog-error').text()).not.toContain('Internal error');
    s.answerBy({ ...BASE_ANSWERS });
    await click(s.find('flow-catalog-retry').element);
    await settle();
    expect(s.find('flow-catalog-error').exists()).toBe(false);
  });
});
