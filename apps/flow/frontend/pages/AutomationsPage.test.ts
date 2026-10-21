// «Automations» (WORKBOOK FLOW-F01 to F08): «New automation» on top; the assistant's drafts; «Your
// automations» only when there is one; the gallery always below, which a link can open on a card; a
// card used opens the new automation on its Permissions; the app off or no permission replace it all.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import type { FlowOut } from '../operations';
import { click, errorFrame, mountFlow, OWNER, page, settle } from '../__tests__/mount-flow';
import DraftTray from '../components/DraftTray.vue';
import FlowList from '../components/FlowList.vue';
import FlowGallery from '../components/FlowGallery.vue';
import QuestionInbox from '../components/QuestionInbox.vue';
import AutomationsPage from './AutomationsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const CATALOG = { events: [], actions: [] };
const flow = (id: string, over: Partial<FlowOut> = {}) => ({ id, name: id, enabled: false, missing_grants: [], trigger: { kind: 'manual' }, steps: [], ...over }) as FlowOut;

async function setup(path = '/flow/automations', all: FlowOut[] = []) {
  const m = await mountFlow(AutomationsPage, { path, answers: { '/api/flow/catalog': [200, CATALOG] } });
  await m.live();
  await settle();
  await m.result('flow.flow.list', page(all, all.length, 100), { limit: 100 });
  return m;
}

describe('AutomationsPage', () => {
  it('sits under «Automations» with «New automation», the drafts and the gallery', async () => {
    const m = await setup();
    expect(m.wrapper.findComponent(AppPage).props('title')).toBe('Automations');
    expect(m.wrapper.findComponent(DraftTray).exists()).toBe(true);
    expect(m.wrapper.findComponent(FlowGallery).props('catalog')).toEqual(CATALOG);
    await click(m.find('flow-new').element);
    await settle();
    expect(m.router.currentRoute.value.path).toBe('/flow/automations/new');
  });

  it('«Your automations» shows only when there is one', async () => {
    const empty = await setup();
    expect(empty.wrapper.findComponent(FlowList).exists()).toBe(false);
    const some = await setup('/flow/automations', [flow('f1')]);
    expect(some.wrapper.findComponent(FlowList).props('allTotal')).toBe(1);
    expect(some.wrapper.findComponent(FlowGallery).props('flows')).toEqual([flow('f1')]);
  });

  it('a card used opens the new automation on its Permissions; a row, on its steps', async () => {
    const m = await setup('/flow/automations', [flow('f1')]);
    m.wrapper.findComponent(FlowGallery).vm.$emit('created', flow('f9'));
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/flow/automations/f9?tab=permissions');
    m.wrapper.findComponent(FlowList).vm.$emit('open', flow('f1'));
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/flow/automations/f1');
  });

  it('a link opens its card only once what is above the gallery is painted, so it stays in view (FLOW-F05)', async () => {
    const m = await setup('/flow/automations?template=noShow', [flow('f1')]);
    const gallery = () => m.wrapper.findComponent(FlowGallery).props('openCard');
    expect(gallery()).toBeNull();
    m.wrapper.findComponent(DraftTray).vm.$emit('ready');
    await settle();
    expect(gallery()).toBeNull();
    m.wrapper.findComponent(FlowList).vm.$emit('ready');
    await settle();
    expect(gallery()).toBe('noShow');
  });

  it('a link opens its card of the gallery; the guide is a page of its own', async () => {
    const m = await setup('/flow/automations?template=noShow');
    expect(m.wrapper.findComponent(FlowGallery).props('openCard')).toBeNull();
    m.wrapper.findComponent(DraftTray).vm.$emit('ready');
    await settle();
    expect(m.wrapper.findComponent(FlowGallery).props('openCard')).toBe('noShow');
    m.wrapper.findComponent(FlowGallery).vm.$emit('guide');
    await settle();
    expect(m.router.currentRoute.value.path).toBe('/flow/guide');
  });

  it('the app off replaces it all with its notice', async () => {
    const m = await mountFlow(AutomationsPage, { answers: { '/api/flow/catalog': [200, CATALOG] } });
    const call = await m.live();
    call.push(errorFrame(m.subId('flow.flow.list', { limit: 100 }), 'app_inactive'));
    await settle();
    expect(m.find('flow-page-inactive').exists()).toBe(true);
    expect(m.wrapper.findComponent(FlowGallery).exists()).toBe(false);
  });
});

describe('AutomationsPage: review 2026-10-15, item 5', () => {
  it('a catalog that could not be read is said, with «Retry»', async () => {
    const m = await mountFlow(AutomationsPage, { answers: { '/api/flow/catalog': [500, { error: { code: 'internal_error', message: 'Internal error' } }] } });
    await m.live();
    await settle();
    expect(m.find('flow-catalog-error').text()).toContain('What automations can use here could not be read.');
    m.answerBy({ '/api/flow/catalog': [200, CATALOG] });
    await click(m.find('flow-catalog-retry').element);
    await settle();
    expect(m.find('flow-catalog-error').exists()).toBe(false);
    expect(m.wrapper.findComponent(FlowGallery).props('catalog')).toEqual(CATALOG);
  });

  // FLOW-F29: «Waiting for your answer» sits on top for whoever runs the business; a manager or an employee, who
  // may only answer, sees only it (no list, no gallery, no «New automation»).
  it('«Waiting for your answer» on top, and all a person who only answers sees', async () => {
    const m = await setup();
    expect(m.wrapper.findComponent(QuestionInbox).props('alone')).toBe(false);
    const answerer = await mountFlow(AutomationsPage, { session: { ...OWNER, permissions: ['flow.answer'] } });
    await answerer.live();
    await settle();
    expect(answerer.wrapper.findComponent(QuestionInbox).props('alone')).toBe(true);
    expect(answerer.params('flow.flow.list')).toEqual([]);
    expect(answerer.wrapper.findComponent(FlowGallery).exists()).toBe(false);
    expect(answerer.find('flow-new').exists()).toBe(false);
  });
});
