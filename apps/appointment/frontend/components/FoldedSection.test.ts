// What the booking panel keeps folded until it is asked for (the notes, the history): a button with its title and a
// hint that says whether it opens, and what it holds only once opened.
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import FoldedSection from './FoldedSection.vue';

function setup(props: Record<string, unknown> = {}) {
  return mount(FoldedSection, {
    props: { title: 'Internal notes', hint: 'Optional', testid: 'fold', ...props } as { title: string; testid: string },
    slots: { default: '<textarea data-testid="inside"></textarea>' },
    global: { stubs: { HubIcon: true } },
  });
}

describe('FoldedSection', () => {
  it('starts folded: the title and the hint, nothing inside, and the button says it is closed', () => {
    const wrapper = setup();
    const toggle = wrapper.get('[data-testid=fold-toggle]');
    expect([toggle.attributes('type'), toggle.attributes('aria-expanded'), toggle.text()]).toEqual(['button', 'false', 'Internal notesOptional']);
    expect(wrapper.find('[data-testid=inside]').exists()).toBe(false);
  });

  it('opens and folds again with its button, and tells the page', async () => {
    const wrapper = setup({ 'onUpdate:open': (open: boolean) => wrapper.setProps({ open }) });
    const toggle = wrapper.get('[data-testid=fold-toggle]');
    await toggle.trigger('click');
    expect(toggle.attributes('aria-expanded')).toBe('true');
    const body = wrapper.get('[data-testid=inside]').element.parentElement!;
    expect(toggle.attributes('aria-controls')).toBe(body.id);
    await toggle.trigger('click');
    expect(wrapper.find('[data-testid=inside]').exists()).toBe(false);
    expect(wrapper.emitted('update:open')).toEqual([[true], [false]]);
  });

  it('comes open when the page says so', () => {
    expect(setup({ open: true }).find('[data-testid=inside]').exists()).toBe(true);
  });
});
