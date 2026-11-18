import { describe, expect, it } from 'vitest';

import type { AppHelp, HelpFlow } from '../operations-help';
import { flush, mountBase } from '../__tests__/mount-base';
import HelpFlowList from './HelpFlowList.vue';

const floor = { id: 'floor', title: 'Floor plan', path: '/table/floor-plan', text: 'Floor text' };
const tables = { id: 'tables', title: 'Tables', path: '/table/tables', text: 'Tables text' };

function flow(id: string, title: string, screens: string[], steps = 'Open a table'): HelpFlow {
  return { id, title, screens, steps, failure: id === 'seat' ? 'The table may have been taken.' : '' };
}

const help: AppHelp = {
  app: 'table', name: 'Tables', language: 'en', video: null, purpose: 'Purpose',
  screens: [floor, tables],
  flows: [flow('seat', 'Sentar un grupo', ['floor'], 'Elige los comensales'), flow('merge', 'Join checks', ['floor', 'tables'])],
};

async function setup(answer = help) {
  const m = await mountBase(HelpFlowList, { props: { help: answer, current: floor } });
  const el = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  async function search(value: string) {
    const input = el('help-flow-search');
    (input.element as HTMLElement & { value: string }).value = value;
    input.element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  return { ...m, el, search };
}

describe('HelpFlowList', () => {
  it('shows the current screen group first and repeats a shared flow under the other screen', async () => {
    const s = await setup();
    expect(s.wrapper.findAll('.help-flow-group__title').map((title) => title.text())).toEqual(['Floor plan', 'Tables']);
    expect(s.el('help-flow-floor-merge').exists()).toBe(true);
    expect(s.el('help-flow-tables-merge').exists()).toBe(true);
  });

  it('opens one flow at a time and reports the last expanded title', async () => {
    const s = await setup();
    await s.el('help-flow-floor-seat').trigger('click');
    expect(s.el('help-flow-floor-seat').attributes('aria-expanded')).toBe('true');
    expect(s.el('help-flow-content-floor-seat').text()).toContain('Elige los comensales');
    expect(s.el('help-flow-content-floor-seat').text()).toContain('If something goes wrong');
    await s.el('help-flow-floor-merge').trigger('click');
    expect(s.el('help-flow-floor-seat').attributes('aria-expanded')).toBe('false');
    expect(s.el('help-flow-floor-merge').attributes('aria-expanded')).toBe('true');
    expect(s.wrapper.emitted('expand')).toEqual([['Sentar un grupo'], ['Join checks']]);
  });

  it('filters titles and steps without accents, with an empty state and a clear button', async () => {
    const extra = Array.from({ length: 7 }, (_, index) => flow(`extra-${index}`, `Extra ${index}`, ['tables']));
    const s = await setup({ ...help, flows: [...help.flows, ...extra] });
    await s.search('comensal');
    expect(s.el('help-flow-floor-seat').exists()).toBe(true);
    expect(s.el('help-flow-floor-merge').exists()).toBe(false);
    await s.search('nothing-here');
    expect(s.el('help-flow-empty').text()).toContain('Nothing matches your search');
    await s.el('help-flow-clear').trigger('click');
    expect(s.el('help-flow-floor-seat').exists()).toBe(true);
    expect(s.el('help-flow-empty').exists()).toBe(false);
  });

  it('shows search only when the module has more than eight flows', async () => {
    const small = await setup();
    expect(small.el('help-flow-search').exists()).toBe(false);
    small.wrapper.unmount();
    const flows = Array.from({ length: 9 }, (_, index) => flow(`f${index}`, `Task ${index}`, ['floor']));
    const large = await setup({ ...help, flows });
    expect(large.el('help-flow-search').exists()).toBe(true);
    expect(large.el('help-flow-search').attributes('mode')).toBe('md');
  });

  it('does not show the search empty state when there are no flows and no query', async () => {
    const s = await setup({ ...help, flows: [] });
    expect(s.el('help-flow-empty').exists()).toBe(false);
    expect(s.wrapper.findAll('.help-flow-group')).toHaveLength(0);
  });

  it('shows an unlisted flow without a group heading when it is the only group', async () => {
    const s = await setup({ ...help, flows: [flow('orphan', 'Unlisted task', ['removed-screen'])] });
    expect(s.el('help-flow-unlisted-orphan').exists()).toBe(true);
    expect(s.wrapper.findAll('.help-flow-group__title')).toHaveLength(0);
  });
});
