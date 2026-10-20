// The page of a saved automation (`/flow/automations/:id`): follows it live and opens the editor on the
// tab of the link; one that does not exist says so; ← goes back to the list.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import type { FlowOut } from '../operations';
import { errorFrame, mountFlow, settle } from '../__tests__/mount-flow';
import FlowEditor from '../components/FlowEditor.vue';
import { markSaved } from '../lib/justSaved';
import FlowEditorPage from './FlowEditorPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const FLOW = { id: 'f1', name: 'Big sale', enabled: false, trigger: { kind: 'manual' }, steps: [], grants: [], missing_grants: [], required_grants: [] } as unknown as FlowOut;

async function setup(path = '/flow/automations/f1?tab=permissions') {
  const m = await mountFlow(FlowEditorPage, { path, answers: { '/api/flow/catalog': [200, { events: [], actions: [] }] } });
  const call = await m.live();
  return { ...m, call };
}

describe('FlowEditorPage', () => {
  it('follows the automation of the link and opens the editor on its tab', async () => {
    const s = await setup();
    expect(s.params('flow.flow.detail')).toEqual([{ id: 'f1' }]);
    expect(s.find('flow-editor-loading').exists()).toBe(true);
    await s.result('flow.flow.detail', FLOW);
    const editor = s.wrapper.findComponent(FlowEditor);
    expect(editor.props()).toMatchObject({ flow: FLOW, tab: 'permissions', draft: null });
    expect(editor.props('initial')).toEqual({ name: 'Big sale', enabled: false, trigger: { kind: 'manual' }, steps: [] });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Big sale');
  });

  it('just created, it opens saying «Saved.», once (FLOW-F09)', async () => {
    markSaved('f1');
    const s = await setup();
    await s.result('flow.flow.detail', FLOW);
    expect(s.wrapper.findComponent(FlowEditor).props('savedNow')).toBe(true);
    const again = await setup();
    await again.result('flow.flow.detail', FLOW);
    expect(again.wrapper.findComponent(FlowEditor).props('savedNow')).toBe(false);
  });

  it('one that does not exist says so', async () => {
    const s = await setup('/flow/automations/f9');
    s.call.push(errorFrame(s.subId('flow.flow.detail'), 'not_found'));
    await settle();
    expect(s.find('flow-editor-missing').text()).toContain('That automation does not exist in this business.');
  });

  it('← goes back to the list', async () => {
    const s = await setup();
    await s.result('flow.flow.detail', FLOW);
    s.wrapper.findComponent(FlowEditor).vm.$emit('back');
    await settle();
    expect(s.router.currentRoute.value.path).toBe('/flow/automations');
  });
});
