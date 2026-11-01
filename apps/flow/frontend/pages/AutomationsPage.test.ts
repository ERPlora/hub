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
    // Hidden, not left out (one live stream, below): `display: none` until there is one.
    const shown = (m: Awaited<ReturnType<typeof setup>>) => (m.wrapper.findComponent(FlowList).element as HTMLElement).style.display !== 'none';
    expect(shown(empty)).toBe(false);
    const some = await setup('/flow/automations', [flow('f1')]);
    expect(shown(some)).toBe(true);
    expect(some.wrapper.findComponent(FlowList).props('allTotal')).toBe(1);
    expect(some.wrapper.findComponent(FlowGallery).props('flows')).toEqual([flow('f1')]);
  });

  // FIX-HUB-FLOW-ASSISTANT-STEP-ACTS-ON-ANOTHER-CUSTOMER-WITHOUT-ON-BEHALF-OF: the list of the automations used to
  // subscribe only once the count arrived, so the stream was closed (net::ERR_ABORTED) and opened again on every visit.
  it('opens one live stream for the whole page: the automations arriving reopen nothing', async () => {
    const m = await setup('/flow/automations', [flow('f1')]);
    await m.reopen();
    await settle();
    expect(m.net.streams.map((stream) => stream.aborted())).toEqual([false]);
    expect(m.params('flow.flow.list')).toHaveLength(2);
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
    expect(answerer.params('flow.recipe.list')).toEqual([]);
  });
});

describe('AutomationsPage: the ready-made automations the apps bring (FLOW-F33 to F36)', () => {
  it('a fix its app made never waits for the owner: nothing to press above «Your automations»', async () => {
    // FIX-HUB-FLOW-FACTORY-SAFETY-FIX-WAITS-FOR-THE-OWNERS-UPDATE: its app's condition already counts, so the old
    // «… starts in more cases than it should» with «Update it» would say what is no longer true.
    const m = await setup('/flow/automations', [flow('f1')]);
    const installed = { flow_id: 'f1', name: 'My gap', enabled: true, outdated: true, missing_grants: [], repair: { 'input.by_customer': { eq: true } } };
    const gap = {
      ref: 'appointment/customer_cancelled', app: 'appointment', app_name: 'Appointments', icon: 'ion:calendar-outline',
      id: 'customer_cancelled', name: 'Fill the gap when a customer cancels', summary: '', description: '',
      trigger: { kind: 'event', event: 'appointment.appointment.cancelled' }, steps: [], grants: [], installed,
    };
    await m.result('flow.recipe.list', { recipes: [gap], set_aside: [] });
    await settle();
    expect(m.wrapper.find('[data-testid=flow-repairs]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="flow-repair-appointment/customer_cancelled"]').exists()).toBe(false);
    expect(m.wrapper.text()).not.toContain('starts in more cases than it should');
  });
});

// FIX-HUB-FLOW-AUTOMATIONS-TITLE-CUT-ON-PHONE: on a phone «New automation», icon and words, took the bar and left
// the title as «A…». There it is its «+» alone, still named «New automation» (Material's top app bar, iOS's
// navigation bars); from a tablet on, its icon and its words, as before.
describe('AutomationsPage: «New automation» on a phone', () => {
  /** A window whose phone query answers `phone`, and can be resized. */
  function screenOf(phone: boolean) {
    const listeners = new Set<(event: { matches: boolean }) => void>();
    const query = {
      matches: phone,
      media: '(max-width: 767px)',
      addEventListener: (_: string, listener: (event: { matches: boolean }) => void) => listeners.add(listener),
      removeEventListener: (_: string, listener: (event: { matches: boolean }) => void) => listeners.delete(listener),
    };
    const spy = vi.spyOn(window, 'matchMedia').mockReturnValue(query as unknown as MediaQueryList);
    return {
      spy,
      listeners,
      resize(next: boolean) {
        query.matches = next;
        for (const listener of listeners) listener({ matches: next });
      },
    };
  }

  const words = (m: Awaited<ReturnType<typeof setup>>) => m.find('flow-new').text().trim();
  const iconSlot = (m: Awaited<ReturnType<typeof setup>>) => m.find('flow-new').find('[data-testid=flow-new-icon]').attributes('slot');

  it('on a phone it is its «+» alone, named «New automation», and still opens a new one', async () => {
    const screen = screenOf(true);
    try {
      const m = await setup();
      expect(words(m)).toBe('');
      expect(iconSlot(m)).toBe('icon-only');
      expect(m.find('flow-new').attributes('aria-label')).toBe('New automation');
      expect(m.find('flow-new').attributes('title')).toBe('New automation');
      await click(m.find('flow-new').element);
      await settle();
      expect(m.router.currentRoute.value.path).toBe('/flow/automations/new');
    } finally {
      screen.spy.mockRestore();
    }
  });

  it('from a tablet on, its icon and its words; turning the device changes it, and leaving lets the window go', async () => {
    const screen = screenOf(false);
    try {
      const m = await setup();
      expect(words(m)).toBe('New automation');
      expect(iconSlot(m)).toBe('start');
      expect(m.find('flow-new').attributes('aria-label')).toBe('New automation');
      expect(m.find('flow-new').attributes('title')).toBeUndefined();
      screen.resize(true);
      await settle();
      expect(words(m)).toBe('');
      expect(iconSlot(m)).toBe('icon-only');
      m.wrapper.unmount();
      expect(screen.listeners.size).toBe(0);
    } finally {
      screen.spy.mockRestore();
    }
  });

  it('in Spanish its name is «Nueva automatización»', async () => {
    const screen = screenOf(true);
    try {
      const m = await mountFlow(AutomationsPage, { locale: 'es', answers: { '/api/flow/catalog': [200, CATALOG] } });
      await m.live();
      await settle();
      await m.result('flow.flow.list', page([], 0, 100), { limit: 100 });
      expect(m.find('flow-new').attributes('aria-label')).toBe('Nueva automatización');
    } finally {
      screen.spy.mockRestore();
    }
  });
});
