// What the till shows while something it needs is on its way (its settings, a check opened by its address): a spinner,
// with its words when it has them; and once it failed, why, with the one button that gets the person out of it.
import { InlineFeedback } from '@erplora/ui/components';
import { IonSpinner } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import PosLoadState from './PosLoadState.vue';

async function setup(props: Record<string, unknown>) {
  return mountSale(PosLoadState, { props: { error: null, action: 'Retry', testid: 'pos-x', ...props } });
}

describe('PosLoadState', () => {
  it('while it loads, a spinner with its words, read out as a status', async () => {
    const m = await setup({ loading: 'Opening the check…' });
    const box = m.find('pos-x-loading');
    expect(box.attributes('role')).toBe('status');
    expect(box.findComponent(IonSpinner).exists()).toBe(true);
    expect(box.text()).toBe('Opening the check…');
    expect(m.find('pos-x-error').exists()).toBe(false);
  });

  it('without words, the spinner alone', async () => {
    const m = await setup({});
    expect(m.find('pos-x-loading').findComponent(IonSpinner).exists()).toBe(true);
    expect(m.find('pos-x-loading').text()).toBe('');
  });

  it('once it failed, why, as a danger notice with its button, which hands the choice up', async () => {
    const m = await setup({ error: 'That check is not open any more.', action: 'Continue', loading: 'Opening the check…' });
    expect(m.find('pos-x-loading').exists()).toBe(false);
    const notice = m.wrapper.findComponent(InlineFeedback);
    expect(notice.props('tone')).toBe('danger');
    expect(m.find('pos-x-error').text()).toContain('That check is not open any more.');
    expect(m.find('pos-x-action').text()).toBe('Continue');
    await click(m.find('pos-x-action').element);
    expect(m.wrapper.emitted('act')).toHaveLength(1);
  });
});
