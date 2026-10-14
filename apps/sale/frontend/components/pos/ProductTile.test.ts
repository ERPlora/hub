// A product tile of the till's grid (WORKBOOK «Vender»: articles with their initials, their unit and
// their price; SALE-F07: one without VAT is marked «Falta el IVA» and still takes the tap, to say why).
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { product } from './__tests__/fixtures';
import ProductTile from './ProductTile.vue';

describe('ProductTile', () => {
  it('paints the initials over the name’s colour, the name and the price in the reader’s language; never the SKU', async () => {
    const m = await mountSale(ProductTile, { props: { product: product() }, locale: 'es' });
    const tile = m.find('pos-product-p1');
    expect(tile.find('.pos-tile__thumb').text()).toBe('CC');
    expect(tile.find('.pos-tile__thumb').attributes('style')).toMatch(/linear-gradient/);
    expect(tile.find('.pos-tile__name').text()).toBe('Café con leche');
    expect(plain(tile.find('.pos-tile__price').text())).toBe('1,50 €');
    expect(tile.find('.pos-tile__unit').exists()).toBe(false);
    expect(tile.text()).not.toContain('CAF-1');
    expect(tile.attributes('aria-disabled')).toBeUndefined();
  });

  it('shows the unit of a product sold by weight or volume', async () => {
    const m = await mountSale(ProductTile, { props: { product: product({ unit: 'kg', pricing_unit: 'kg' }) } });
    expect(m.find('pos-product-p1').find('.pos-tile__unit').text()).toBe('kg');
  });

  it('a product without VAT is marked «VAT missing», looks blocked, says why and still takes the tap', async () => {
    const m = await mountSale(ProductTile, { props: { product: product({ needs_tax_setup: true }) } });
    const tile = m.find('pos-product-p1');
    expect(tile.attributes('aria-disabled')).toBe('true');
    expect(tile.find('.pos-tile__badge').text()).toBe('VAT missing');
    expect(tile.attributes('aria-label')).toBe('Café con leche · Cannot be sold: no tax category. VAT needs to be set up.');
    expect(tile.find('.pos-tile__warn').exists()).toBe(true);
    await click(tile.element);
    expect(m.wrapper.emitted('pick')).toEqual([[product({ needs_tax_setup: true })]]);
  });

  it('a tap hands the product up', async () => {
    const m = await mountSale(ProductTile, { props: { product: product() } });
    await click(m.find('pos-product-p1').element);
    expect(m.wrapper.emitted('pick')).toEqual([[product()]]);
  });
});
