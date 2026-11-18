import { describe, expect, it } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import HelpSummary from './HelpSummary.vue';

const TEXT = 'The first paragraph explains the screen.\n\nThe second paragraph and its details stay folded.';

async function setup(text = TEXT) {
  const m = await mountBase(HelpSummary, { props: { text, name: 'purpose' } });
  const content = () => m.wrapper.get('[data-testid="help-summary-purpose-content"]');
  const toggle = () => m.wrapper.get('[data-testid="help-summary-purpose-toggle"]');
  return { ...m, content, toggle };
}

describe('HelpSummary', () => {
  it('shows only the first paragraph until Ver más expands the full markdown', async () => {
    const s = await setup();
    expect(s.content().text()).toContain('The first paragraph');
    expect(s.content().text()).not.toContain('The second paragraph');
    expect(s.toggle().text()).toBe('Show more');
    expect(s.toggle().attributes('aria-expanded')).toBe('false');

    await s.toggle().trigger('click');
    await flush();
    expect(s.content().text()).toContain('The second paragraph');
    expect(s.toggle().text()).toBe('Show less');
    expect(s.toggle().attributes('aria-expanded')).toBe('true');
  });

  it('has no toggle for a short single paragraph', async () => {
    const s = await setup('A short explanation.');
    expect(s.content().text()).toContain('A short explanation.');
    expect(s.wrapper.find('[data-testid="help-summary-purpose-toggle"]').exists()).toBe(false);
  });

  it('line-clamps a long first paragraph and removes the clamp when expanded', async () => {
    const s = await setup(`A long paragraph. ${'Enough words to need more than four lines. '.repeat(12)}`);
    expect(s.content().classes()).toContain('help-summary__content--clamped');
    await s.toggle().trigger('click');
    expect(s.content().classes()).not.toContain('help-summary__content--clamped');
  });
});
