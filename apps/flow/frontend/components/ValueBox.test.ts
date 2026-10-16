// One value composed of text the owner types and data they pick (WORKBOOK FLOW-F11): a picked datum is
// a pill with its words (never a path on screen), each piece of text its own box; «Insert data» asks
// the editor's one picker and adds what it answers.
import { describe, expect, it } from 'vitest';

import type { CatalogOut, Step } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import ValueBox from './ValueBox.vue';

const CATALOG = { events: [], actions: [{ name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: ['number'] }] } as unknown as CatalogOut;
const STEPS: Step[] = [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }];

async function setup(modelValue: unknown, pick: () => Promise<string | null> = async () => 'input.customer_name') {
  const m = await mountFlow(ValueBox, { props: { modelValue, label: 'Title', testid: 'vb', steps: STEPS, catalog: CATALOG, pick } });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  const texts = () => m.wrapper.findAll('[data-testid^="vb-text-"]').map((input) => (input.element as HTMLInputElement).value);
  const pills = () => m.wrapper.findAll('[data-testid^="vb-pill-"]').map((pill) => pill.text());
  return { ...m, emitted, texts, pills };
}

describe('ValueBox', () => {
  it('paints text and pills with their words, never the path', async () => {
    const s = await setup('Call {{input.customer_name}} about {{steps.s1.number}}');
    expect(s.find('vb-label').text()).toBe('Title');
    expect(s.pills()).toEqual(['Customer name', '1. Create a task › Number']);
    expect(s.texts()).toEqual(['Call ', ' about ', '']);
    expect(s.wrapper.text()).not.toContain('{{');
  });

  it('typing changes the value; a number is sent as one', async () => {
    const s = await setup('');
    const input = s.find('vb-text-0');
    (input.element as HTMLInputElement).value = '10000';
    await input.trigger('input');
    expect(s.emitted()).toEqual([10000]);
  });

  it('«Insert data» adds the picked datum: alone it keeps its type, with text it makes a sentence', async () => {
    const alone = await setup('');
    await click(alone.find('vb-insert').element);
    await settle();
    expect(alone.emitted()).toEqual(['input.customer_name']);
    const after = await setup('Call ');
    await click(after.find('vb-insert').element);
    await settle();
    expect(after.emitted()).toEqual(['Call {{input.customer_name}}']);
  });

  it('a pick that is cancelled changes nothing', async () => {
    const s = await setup('Hi', async () => null);
    await click(s.find('vb-insert').element);
    await settle();
    expect(s.emitted()).toEqual([]);
  });

  it('× takes a pill out and joins the text around it', async () => {
    const s = await setup('Call {{input.customer_name}} now');
    await click(s.find('vb-unpill-1').element);
    expect(s.emitted()).toEqual(['Call  now']);
  });

  it('shows the server’s refusal of this value', async () => {
    const m = await mountFlow(ValueBox, { props: { modelValue: '', label: 'Title', testid: 'vb', steps: [], catalog: null, pick: async () => null, errorText: 'Required.' } });
    expect(m.find('vb-error').text()).toBe('Required.');
  });
});
