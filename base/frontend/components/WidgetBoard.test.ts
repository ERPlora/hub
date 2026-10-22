// The Home's board (BASE-G166, BASE-G167): the panels this person may put (`base.widget.list`, live), the
// defaults until this browser chooses, and «Customize panel» (⋮): «Recommended», the active ones to reorder or
// remove and the available ones to add. The choice is kept in this browser (`dashboard-hub`).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WidgetDef } from '../operations';
import { errorFrame, flush, memoryStorage, mountBase, subId } from '../__tests__/mount-base';
import WidgetBoard from './WidgetBoard.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

function widget(key: string, fields: Partial<WidgetDef> = {}): WidgetDef {
  return {
    key,
    app: key.split('.')[0],
    title: `Panel ${key}`,
    icon: '',
    category: 'Demo',
    size: 'sm',
    default: false,
    kind: 'kpi',
    operation: 'demo.item.stats',
    params: {},
    map: { value: 'open' },
    options: {},
    component: null,
    refresh_on: [],
    live: true,
    ...fields,
  };
}

const CATALOGUE = [widget('a.one', { default: true }), widget('a.two'), widget('b.three', { default: true })];

/** WidgetPanel has its own tests: here only which panels, in which order. */
const PanelStub = { props: ['widget'], template: '<article data-testid="widget" :data-key="widget.key" />' };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountBase(WidgetBoard, { locale, stubs: { WidgetPanel: PanelStub } });
  const call = await m.live();
  const show = (widgets: WidgetDef[], rev?: number) => m.result(call, 'base.widget.list', { widgets }, rev);
  const panels = () => m.wrapper.findAll('[data-testid="widget"]').map((w) => w.attributes('data-key'));
  const inDoc = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const allInDoc = (id: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)];
  const stored = () => JSON.parse(localStorage.getItem('dashboard-hub') ?? 'null') as string[] | null;
  async function customize() {
    await m.wrapper.get('[data-testid="widgets-customize"]').trigger('click');
    await flush();
  }
  return { ...m, call, show, panels, inDoc, allInDoc, stored, customize };
}

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('WidgetBoard', () => {
  it('follows base.widget.list and says it is loading until it arrives', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('base.widget.list').map((sub) => sub.params)).toEqual([{}]);
    // Ionic's hydrated elements patch `textContent`: the markup is what the person sees.
    expect(s.wrapper.get('[data-testid="widgets-loading"]').html()).toContain('Loading widgets…');
    await s.show(CATALOGUE);
    expect(s.wrapper.find('[data-testid="widgets-loading"]').exists()).toBe(false);
  });

  it("puts the catalogue's defaults while this browser chose nothing", async () => {
    const s = await setup();
    await s.show(CATALOGUE);
    expect(s.panels()).toEqual(['a.one', 'b.three']);
  });

  it("keeps this browser's choice and its order, without the panels whose app is gone", async () => {
    localStorage.setItem('dashboard-hub', JSON.stringify(['b.three', 'gone.x', 'a.two']));
    const s = await setup();
    await s.show(CATALOGUE);
    expect(s.panels()).toEqual(['b.three', 'a.two']);
  });

  it('«Customize panel» lists the active ones and the available ones; adding one keeps it in this browser', async () => {
    const s = await setup('es');
    await s.show(CATALOGUE);
    expect(s.wrapper.get('[data-testid="widgets-customize"]').attributes('aria-label')).toBe('Personalizar panel');
    await s.customize();
    expect(s.allInDoc('widgets-active-item').map((el) => el.dataset.key)).toEqual(['a.one', 'b.three']);
    expect(s.allInDoc('widgets-available-item').map((el) => el.dataset.key)).toEqual(['a.two']);
    s.inDoc('widgets-add-a.two')!.click();
    await flush();
    expect(s.stored()).toEqual(['a.one', 'b.three', 'a.two']);
    expect(s.panels()).toEqual(['a.one', 'b.three', 'a.two']);
  });

  it('removing a panel takes it off the board; an empty board says how to add one', async () => {
    const s = await setup('es');
    await s.show(CATALOGUE);
    await s.customize();
    s.inDoc('widgets-remove-a.one')!.click();
    s.inDoc('widgets-remove-b.three')!.click();
    await flush();
    expect(s.stored()).toEqual([]);
    expect(s.panels()).toEqual([]);
    expect(s.wrapper.get('[data-testid="widgets-empty"]').text()).toBe('Panel vacío. Pulsa ⋮ para añadir widgets.');
  });

  it('dragging an active panel reorders the board', async () => {
    const s = await setup();
    await s.show(CATALOGUE);
    await s.customize();
    const complete = vi.fn();
    s.inDoc('widgets-active')!.dispatchEvent(new CustomEvent('ionItemReorder', { detail: { from: 1, to: 0, complete } }));
    await flush();
    expect(complete).toHaveBeenCalled();
    expect(s.stored()).toEqual(['b.three', 'a.one']);
    expect(s.panels()).toEqual(['b.three', 'a.one']);
  });

  it('«Recommended» goes back to the defaults', async () => {
    localStorage.setItem('dashboard-hub', JSON.stringify(['a.two']));
    const s = await setup();
    await s.show(CATALOGUE);
    await s.customize();
    s.inDoc('widgets-recommended')!.click();
    await flush();
    expect(s.stored()).toEqual(['a.one', 'b.three']);
  });

  it('«Close» closes the picker', async () => {
    const s = await setup();
    await s.show(CATALOGUE);
    await s.customize();
    s.inDoc('widgets-close')!.click();
    await flush();
    expect(s.inDoc('widgets-active')).toBeNull();
  });

  it('with no app offering panels the picker says so', async () => {
    const s = await setup('es');
    await s.show([]);
    await s.customize();
    expect(s.inDoc('widgets-none')!.textContent?.trim()).toBe('Ninguna app instalada ofrece widgets todavía.');
  });

  it('a failed read says so, with «Retry»', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'base.widget.list'), 'internal'));
    await flush();
    expect(s.wrapper.get('[data-testid="widgets-error"]').text()).toContain('Could not load the panels');
    expect(s.wrapper.find('[data-testid="widgets-retry"]').exists()).toBe(true);
  });
});
