// TemplatePicker: the four designs as cards with a small drawing of each (CSS only, in the page's colours); one is
// chosen, picking another changes only the template (the content stays).
import { describe, expect, it } from 'vitest';

import { mountWebsite } from '../__tests__/mount-website';
import TemplatePicker from './TemplatePicker.vue';

async function picker(props: Record<string, unknown> = {}) {
  const { wrapper } = await mountWebsite(TemplatePicker, {
    props: { modelValue: 'classic', primary: '#112233', accent: '#445566', ...props },
  });
  return wrapper;
}

describe('TemplatePicker', () => {
  it('offers the four designs with their name and what they look like, the chosen one checked', async () => {
    const wrapper = await picker({ modelValue: 'modern' });
    const cards = wrapper.findAll('[role="radio"]');
    expect(cards.map((card) => card.attributes('data-testid'))).toEqual([
      'website-template-classic',
      'website-template-modern',
      'website-template-minimal',
      'website-template-bold',
    ]);
    expect(cards.map((card) => card.attributes('aria-checked'))).toEqual(['false', 'true', 'false', 'false']);
    expect(cards[0].text()).toContain('Classic');
    expect(cards[0].text()).toContain('Centred and timeless');
    expect(wrapper.find('[role="radiogroup"]').attributes('aria-label')).toBe('Design');
  });

  it('draws each thumbnail in the page colours, without images', async () => {
    const wrapper = await picker();
    const thumb = wrapper.get('[data-testid="website-template-bold"] .wt-thumb');
    expect(thumb.attributes('style')).toContain('--wt-primary: #112233');
    expect(thumb.attributes('style')).toContain('--wt-accent: #445566');
    expect(wrapper.findAll('img')).toHaveLength(0);
  });

  it('picking another design emits it; the chosen one or a disabled picker emits nothing', async () => {
    const wrapper = await picker();
    await wrapper.get('[data-testid="website-template-bold"]').trigger('click');
    await wrapper.get('[data-testid="website-template-classic"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['bold']]);
    const locked = await picker({ disabled: true });
    await locked.get('[data-testid="website-template-minimal"]').trigger('click');
    expect(locked.emitted('update:modelValue')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountWebsite(TemplatePicker, { props: { modelValue: 'classic', primary: '#000000', accent: '#ffffff' }, locale: 'es' });
    expect(wrapper.get('[data-testid="website-template-bold"]').text()).toContain('Llamativa');
  });
});
