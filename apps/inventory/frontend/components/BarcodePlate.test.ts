// INVENTORY-F25 (WORKBOOK «Ficha del producto»): the SKU's barcode on a white plate with the SKU under it,
// black on white in every theme so a scanner reads it (inventory#45).
import { describe, expect, it } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import { code128 } from '../lib/barcode';
import BarcodePlate from './BarcodePlate.vue';

async function setup(value: string, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(BarcodePlate, { props: { value }, locale });
  await flush();
  return m;
}

describe('BarcodePlate', () => {
  it('draws one bar per run of the Code 128 and writes the SKU under it', async () => {
    const { wrapper } = await setup('SHA-250');
    const svg = wrapper.find('svg');
    expect(svg.attributes('role')).toBe('img');
    expect(svg.attributes('aria-label')).toBe('Barcode SHA-250');
    expect(wrapper.findAll('svg rect.bar')).toHaveLength(code128('SHA-250')!.bars.length);
    expect(wrapper.find('[data-testid=inventory-barcode-text]').text()).toBe('SHA-250');
  });

  it('is black on a white plate whatever the theme', async () => {
    const { wrapper } = await setup('SHA-250');
    const plate = wrapper.find('[data-testid=inventory-barcode]');
    expect(plate.classes()).toContain('barcode-plate');
    expect(wrapper.find('svg rect.background').attributes('fill')).toBe('#ffffff');
    expect(wrapper.find('svg rect.bar').attributes('fill')).toBe('#000000');
  });

  it('leaves ten modules of white on each side of the bars, the quiet zone a scanner needs to find the code', async () => {
    const { wrapper } = await setup('SHA-250');
    const { modules } = code128('SHA-250')!;
    expect(wrapper.find('svg').attributes('viewBox')).toBe(`0 0 ${modules + 20} 50`);
    const bars = wrapper.findAll('svg rect.bar').map((bar) => [Number(bar.attributes('x')), Number(bar.attributes('width'))]);
    expect(Math.min(...bars.map(([x]) => x))).toBe(10);
    expect(Math.max(...bars.map(([x, width]) => x + width))).toBe(modules + 10);
  });

  it('says so when the SKU cannot be a barcode, in the page language', async () => {
    const { wrapper } = await setup('Ñandú', 'es');
    expect(wrapper.find('svg').exists()).toBe(false);
    expect(wrapper.find('[data-testid=inventory-barcode-invalid]').text()).toBe(
      'Este SKU no se puede pasar a código de barras: usa letras sin tilde, números y signos.',
    );
  });
});
