// PalettePicker: the website's palettes as swatch cards, the eight curated ones; each shows its main and second colour
// on the light page and on the dark one, and its name. One is chosen; picking another emits it and drops the owner's
// colours. Under the cards, the two colours on show (the owner's, or the chosen palette's own) to change: a change is
// the owner's pair over the palette, and «Reset colours», shown only then, gives the palette's own back.
import { describe, expect, it } from 'vitest';

import RAW from '../../palettes.json';
import { ionValue, mountWebsite } from '../__tests__/mount-website';
import PalettePicker from './PalettePicker.vue';

type Control = HTMLElement & { value?: unknown };

async function picker(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const { wrapper } = await mountWebsite(PalettePicker, { props: { modelValue: 'ocean', ...props }, locale });
  return wrapper;
}

describe('PalettePicker', () => {
  it('offers the curated palettes, by name, the chosen one checked', async () => {
    const wrapper = await picker({ modelValue: 'forest' });
    const cards = wrapper.findAll('[role="radio"]');
    expect(cards.map((card) => card.attributes('data-testid'))).toEqual(
      ['ocean', 'forest', 'terracotta', 'slate', 'rose', 'sand', 'midnight', 'olive'].map((id) => `website-palette-${id}`),
    );
    expect(cards.map((card) => card.attributes('aria-checked'))).toEqual([
      'false', 'true', 'false', 'false', 'false', 'false', 'false', 'false',
    ]);
    expect(cards.map((card) => card.text())).toEqual(['Ocean', 'Forest', 'Terracotta', 'Slate', 'Rose', 'Sand', 'Midnight', 'Olive']);
    expect(wrapper.get('[data-testid="website-palette-forest"]').classes()).toContain('wp-card--chosen');
    expect(wrapper.find('[role="radiogroup"]').attributes('aria-label')).toBe('Palette');
  });

  it('shows each palette’s colours, light and dark, from the server’s own file', async () => {
    const wrapper = await picker();
    const style = wrapper.get('[data-testid="website-palette-terracotta"] .wp-swatch').attributes('style');
    expect(style).toContain(`--wp-primary: ${RAW.terracotta.light.primary}`);
    expect(style).toContain(`--wp-accent: ${RAW.terracotta.accent}`);
    expect(style).toContain(`--wp-bg: ${RAW.terracotta.light.bg}`);
    expect(style).toContain(`--wp-dark-bg: ${RAW.terracotta.dark.bg}`);
    expect(style).toContain(`--wp-dark-primary: ${RAW.terracotta.dark.primary}`);
  });

  it('picking another palette emits it; the chosen one or a disabled picker emits nothing', async () => {
    const wrapper = await picker();
    await wrapper.get('[data-testid="website-palette-midnight"]').trigger('click');
    await wrapper.get('[data-testid="website-palette-ocean"]').trigger('click');
    await wrapper.get('[data-testid="website-palette-sand"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['midnight'], ['sand']]);
    const locked = await picker({ disabled: true });
    await locked.get('[data-testid="website-palette-rose"]').trigger('click');
    expect(locked.emitted('update:modelValue')).toBeUndefined();
  });

  it('shows the chosen palette’s own two colours to change, and no «Reset colours» while they are its own', async () => {
    const wrapper = await picker({ modelValue: 'rose', custom: null });
    expect((wrapper.get('[data-testid="website-colour-primary"]').element as Control).value).toBe(RAW.rose.light.primary);
    expect((wrapper.get('[data-testid="website-colour-accent"]').element as Control).value).toBe(RAW.rose.accent);
    expect(wrapper.find('[data-testid="website-colours-reset"]').exists()).toBe(false);
  });

  it('changing a colour emits the owner’s pair over the palette, keeping the other colour', async () => {
    const wrapper = await picker({ modelValue: 'forest', custom: null });
    await ionValue(wrapper.get('[data-testid="website-colour-primary"]').element, '#112233', 'ionInput');
    expect(wrapper.emitted('update:custom')).toEqual([[{ primary: '#112233', accent: RAW.forest.accent }]]);
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });

  it('with the owner’s colours: they are on show, «Reset colours» gives the palette’s own back', async () => {
    const wrapper = await picker({ modelValue: 'forest', custom: { primary: '#112233', accent: '#445566' } });
    expect((wrapper.get('[data-testid="website-colour-primary"]').element as Control).value).toBe('#112233');
    expect((wrapper.get('[data-testid="website-colour-accent"]').element as Control).value).toBe('#445566');
    const reset = wrapper.get('[data-testid="website-colours-reset"]');
    expect(reset.text()).toBe('Reset colours');
    await reset.trigger('click');
    expect(wrapper.emitted('update:custom')).toEqual([[null]]);
  });

  it('another palette drops the owner’s colours: its own are on show', async () => {
    const wrapper = await picker({ modelValue: 'forest', custom: { primary: '#112233', accent: '#445566' } });
    await wrapper.get('[data-testid="website-palette-sand"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['sand']]);
    expect(wrapper.emitted('update:custom')).toEqual([[null]]);
    const untouched = await picker({ modelValue: 'forest', custom: null });
    await untouched.get('[data-testid="website-palette-sand"]').trigger('click');
    expect(untouched.emitted('update:custom')).toBeUndefined();
  });

  it('a disabled picker shows the colours but changes nothing', async () => {
    const wrapper = await picker({ modelValue: 'forest', custom: { primary: '#112233', accent: '#445566' }, disabled: true });
    expect(wrapper.find('[data-testid="website-colours-reset"]').exists()).toBe(false);
    await ionValue(wrapper.get('[data-testid="website-colour-accent"]').element, '#000000', 'ionInput');
    expect(wrapper.emitted('update:custom')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const wrapper = await picker({ custom: { primary: '#112233', accent: '#445566' } }, 'es');
    expect(wrapper.get('[data-testid="website-palette-ocean"]').text()).toBe('Océano');
    expect(wrapper.get('[data-testid="website-palette-terracotta"]').text()).toBe('Terracota');
    expect(wrapper.find('[role="radiogroup"]').attributes('aria-label')).toBe('Paleta');
    expect(wrapper.get('[data-testid="website-colours-reset"]').text()).toBe('Restablecer colores');
  });
});
