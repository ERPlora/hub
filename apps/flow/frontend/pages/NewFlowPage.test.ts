// The page of a new automation (`/flow/automations/new`): blank, or the assistant's draft of the link
// (`?draft=`) with its name, trigger and steps; a draft no longer waiting says so. Once saved, the
// address becomes the automation's, on the same tab.
import { describe, expect, it, vi } from 'vitest';

import type { DraftOut, FlowOut } from '../operations';
import { mountFlow, page, settle } from '../__tests__/mount-flow';
import FlowEditor from '../components/FlowEditor.vue';
import NewFlowPage from './NewFlowPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const DRAFT = {
  id: 'd1',
  name: 'Call who did not come',
  definition: { trigger: { kind: 'event', event: 'appointment.appointment.marked_no_show' }, steps: [{ id: 's1', kind: 'delay', seconds: 60 }] },
  notes: ['I guessed.'],
  status: 'pending',
} as unknown as DraftOut;

async function setup(path: string) {
  const m = await mountFlow(NewFlowPage, { path, answers: { '/api/flow/catalog': [200, { events: [], actions: [] }] } });
  // Only a draft is followed live; a blank automation opens no stream.
  if (path.includes('draft=')) await m.live();
  return m;
}

describe('NewFlowPage', () => {
  it('a blank automation', async () => {
    const m = await setup('/flow/automations/new');
    await settle();
    const editor = m.wrapper.findComponent(FlowEditor);
    expect(editor.props()).toMatchObject({ flow: null, draft: null });
    expect(editor.props('initial')).toEqual({ name: '', enabled: false, trigger: { kind: 'manual' }, steps: [] });
  });

  it('the assistant’s draft of the link, paused', async () => {
    const m = await setup('/flow/automations/new?draft=d1');
    expect(m.params('flow.draft.list')).toEqual([{ limit: 100 }]);
    await m.result('flow.draft.list', page([DRAFT], 1, 100));
    const editor = m.wrapper.findComponent(FlowEditor);
    expect(editor.props('draft')).toEqual(DRAFT);
    expect(editor.props('initial')).toEqual({
      name: 'Call who did not come',
      enabled: false,
      trigger: { kind: 'event', event: 'appointment.appointment.marked_no_show' },
      steps: [{ id: 's1', kind: 'delay', seconds: 60 }],
    });
  });

  it('a draft no longer waiting says so', async () => {
    const m = await setup('/flow/automations/new?draft=d9');
    await m.result('flow.draft.list', page([DRAFT], 1, 100));
    expect(m.find('flow-draft-gone').text()).toBe('That draft is no longer waiting.');
  });

  it('once saved, the address is the automation’s', async () => {
    const m = await setup('/flow/automations/new');
    await settle();
    m.wrapper.findComponent(FlowEditor).vm.$emit('saved', { id: 'f9' } as FlowOut);
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/flow/automations/f9');
  });
});
