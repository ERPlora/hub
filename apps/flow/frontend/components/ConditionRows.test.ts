// «Only continue if…» and «Only when…» (WORKBOOK FLOW-F10, F11): one row per comparison — Data, Is,
// Value —, every one must hold. The data are chosen from what the automation has; «present» asks
// yes or no; «one of» takes values separated by commas; a number typed is sent as one.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountFlow } from '../__tests__/mount-flow';
import ConditionRows from './ConditionRows.vue';

const CHOICES = [
  { path: 'input.total', group: 'input', example: 12500 },
  { path: 'input.customer_id', group: 'input', example: 'c-1' },
];

async function setup(modelValue: Record<string, Record<string, unknown>>, pick?: () => Promise<string | null>) {
  const m = await mountFlow(ConditionRows, { props: { modelValue, choices: CHOICES, steps: [], catalog: null, testid: 'cond', pick } });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  const el = (testid: string) => m.find(testid).element;
  return { ...m, emitted, el };
}

describe('ConditionRows', () => {
  it('paints one row per comparison, the data in words', async () => {
    const s = await setup({ 'input.total': { gte: 10000 } });
    expect((s.el('cond-path-0') as HTMLIonSelectElement & { value: string }).value).toBe('input.total');
    expect(s.find('cond-path-0').text()).toContain('Total');
    expect((s.el('cond-op-0') as unknown as { value: string }).value).toBe('gte');
    expect((s.el('cond-value-0') as unknown as { value: string }).value).toBe('10000');
  });

  it('a value typed is sent as a number when it is one, and the operator changes', async () => {
    const s = await setup({ 'input.total': { gte: 10000 } });
    await ionValue(s.el('cond-value-0'), '5000', 'ionInput');
    await ionValue(s.el('cond-op-0'), 'lt');
    expect(s.emitted()).toEqual([{ 'input.total': { gte: 5000 } }, { 'input.total': { lt: 5000 } }]);
  });

  it('«present» asks yes or no; «one of» takes a list', async () => {
    const s = await setup({ 'input.customer_id': { exists: true } });
    expect((s.el('cond-value-0') as unknown as { value: string }).value).toBe('true');
    await ionValue(s.el('cond-value-0'), 'false');
    await ionValue(s.el('cond-op-0'), 'in');
    await ionValue(s.el('cond-value-0'), 'a, b, 3', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ 'input.customer_id': { in: ['a', 'b', 3] } });
    expect(s.find('cond-hint-0').text()).toBe('Separate the values with commas.');
  });

  it('adds a row, which counts once its data is chosen, and removes one', async () => {
    const s = await setup({ 'input.total': { gte: 1 } });
    await click(s.el('cond-add'));
    expect(s.wrapper.findAll('[data-testid^="cond-row-"]')).toHaveLength(2);
    await ionValue(s.el('cond-path-1'), 'input.customer_id');
    expect(s.emitted().at(-1)).toEqual({ 'input.total': { gte: 1 }, 'input.customer_id': { eq: '' } });
    await click(s.el('cond-remove-0'));
    expect(s.emitted().at(-1)).toEqual({ 'input.customer_id': { eq: '' } });
  });

  it('compares with another datum: picked, shown in words as a pill and taken out again (hub#1712)', async () => {
    let asked = 0;
    const s = await setup({ 'input.total': { gte: 10000 } }, async () => {
      asked += 1;
      return 'input.customer_id';
    });
    await click(s.el('cond-insert-0'));
    expect(asked).toBe(1);
    expect(s.emitted().at(-1)).toEqual({ 'input.total': { gte: 'input.customer_id' } });
    expect(s.find('cond-pill-0').text()).toContain('Customer');
    expect(s.wrapper.find('[data-testid="cond-value-0"]').exists()).toBe(false);
    await click(s.el('cond-unpill-0'));
    expect(s.emitted().at(-1)).toEqual({ 'input.total': { gte: '' } });
    expect(s.wrapper.find('[data-testid="cond-value-0"]').exists()).toBe(true);
  });

  it('a datum it was saved with is a pill even without a picker; «present» and «one of» insert none', async () => {
    const s = await setup({ 'input.total': { eq: 'input.customer_id' }, 'input.customer_id': { exists: true } });
    expect(s.find('cond-pill-0').text()).toContain('Customer');
    expect(s.wrapper.find('[data-testid="cond-insert-0"]').exists()).toBe(false);
    const picking = await setup({ 'input.customer_id': { exists: true } }, async () => 'input.total');
    expect(picking.wrapper.find('[data-testid="cond-insert-0"]').exists()).toBe(false);
    await ionValue(picking.el('cond-op-0'), 'in');
    expect(picking.wrapper.find('[data-testid="cond-insert-0"]').exists()).toBe(false);
  });
});
