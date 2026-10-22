// PalettePicker: the website's palettes as swatch cards, the eight curated ones and «Your colours»; each shows its
// main and second colour on the light page and on the dark one, and its name. One is chosen; picking another emits it.
import { describe, expect, it } from 'vitest';

import RAW from '../../palettes.json';
import { mountWebsite } from '../__tests__/mount-website';
import PalettePicker from './PalettePicker.vue';

async function picker(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const { wrapper } = await mountWebsite(PalettePicker, { props: { modelValue: 'ocean', custom: null, ...props }, locale });
  return wrapper;
}

describe('PalettePicker', () => {
  it('offers the curated palettes and «Your colours», by name, the chosen one checked', async () => {
    const wrapper = await picker({ modelValue: 'forest' });
    const cards = wrapper.findAll('[role="radio"]');
    expect(cards.map((card) => card.attributes('data-testid'))).toEqual(
      ['ocean', 'forest', 'terracotta', 'slate', 'rose', 'sand', 'midnight', 'olive', 'custom'].map((id) => `website-palette-${id}`),
    );
    expect(cards.map((card) => card.attributes('aria-checked'))).toEqual([
      'false', 'true', 'false', 'false', 'false', 'false', 'false', 'false', 'false',
    ]);
    expect(cards.map((card) => card.text())).toEqual([
      'Ocean', 'Forest', 'Terracotta', 'Slate', 'Rose', 'Sand', 'Midnight', 'Olive', 'Your colours',
    ]);
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

  it('«Your colours» shows the owner’s two colours once chosen', async () => {
    const wrapper = await picker({ modelValue: 'custom', custom: { primary: '#112233', accent: '#445566' } });
    const style = wrapper.get('[data-testid="website-palette-custom"] .wp-swatch').attributes('style');
    expect(style).toContain('--wp-primary: #112233');
    expect(style).toContain('--wp-accent: #445566');
  });

  it('picking another palette emits it; the chosen one or a disabled picker emits nothing', async () => {
    const wrapper = await picker();
    await wrapper.get('[data-testid="website-palette-midnight"]').trigger('click');
    await wrapper.get('[data-testid="website-palette-ocean"]').trigger('click');
    await wrapper.get('[data-testid="website-palette-custom"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['midnight'], ['custom']]);
    const locked = await picker({ disabled: true });
    await locked.get('[data-testid="website-palette-rose"]').trigger('click');
    expect(locked.emitted('update:modelValue')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const wrapper = await picker({}, 'es');
    expect(wrapper.get('[data-testid="website-palette-ocean"]').text()).toBe('Océano');
    expect(wrapper.get('[data-testid="website-palette-custom"]').text()).toBe('Tus colores');
    expect(wrapper.find('[role="radiogroup"]').attributes('aria-label')).toBe('Paleta');
  });
});
