// One value composed of text the owner types and data they pick (WORKBOOK FLOW-F11): a picked datum is
// a pill with its words (never a path on screen), each piece of text its own box; «Insert data» asks
// the editor's one picker and adds what it answers.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountFlow, settle, TASK_CATALOG, TASK_STEPS } from '../__tests__/mount-flow';
import ValueBox from './ValueBox.vue';

async function setup(modelValue: unknown, pick: () => Promise<string | null> = async () => 'input.customer_name') {
  const m = await mountFlow(ValueBox, { props: { modelValue, label: 'Title', testid: 'vb', steps: TASK_STEPS, catalog: TASK_CATALOG, pick } });
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

  describe('a closed list (a task’s priority, hub#2729)', () => {
    const OPTIONS = [
      { value: 'low', label: 'Low' },
      { value: 'high', label: 'High' },
    ];
    async function choice(modelValue: unknown, pick: () => Promise<string | null> = async () => 'input.priority') {
      const m = await mountFlow(ValueBox, { props: { modelValue, label: 'Priority', testid: 'vb', steps: TASK_STEPS, catalog: TASK_CATALOG, pick, options: OPTIONS } });
      const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
      return { ...m, emitted };
    }

    it('is chosen by the words of its values, never typed as the action keeps them', async () => {
      const s = await choice('high');
      const select = s.find('vb-choice');
      expect((select.element as unknown as { value: string }).value).toBe('high');
      expect(select.findAll('ion-select-option').map((option) => [(option.element as unknown as { value: string }).value, option.text()])).toEqual([
        ['low', 'Low'],
        ['high', 'High'],
      ]);
      expect(s.wrapper.find('[data-testid="vb-text-0"]').exists()).toBe(false);
      await ionValue(select.element, 'low');
      expect(s.emitted()).toEqual(['low']);
    });

    it('takes a datum instead with «Insert data», shown as its pill until it is taken out', async () => {
      const empty = await choice('');
      await click(empty.find('vb-insert').element);
      await settle();
      expect(empty.emitted()).toEqual(['input.priority']);
      const picked = await choice('input.priority');
      expect(picked.wrapper.find('[data-testid="vb-choice"]').exists()).toBe(false);
      expect(picked.find('vb-pill-1').text()).toBe('Priority');
    });

    it('a value that is not one of the list is shown as it is, to be corrected', async () => {
      const s = await choice('High');
      expect(s.wrapper.find('[data-testid="vb-choice"]').exists()).toBe(false);
      expect((s.find('vb-text-0').element as HTMLInputElement).value).toBe('High');
    });
  });
});
