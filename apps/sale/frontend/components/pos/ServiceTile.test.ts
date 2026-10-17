// A service tile of the till's grid (SALE-F38, SERVICE-F09): the initials over the name's colour, the
// name, the duration and the price — «From», «per hour», «Variable» or «Free» when it has no fixed
// price. One without VAT is marked «VAT missing» and still takes the tap, to say why.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { service } from './__tests__/fixtures';
import ServiceTile from './ServiceTile.vue';

describe('ServiceTile', () => {
  it('paints the initials, the name, the duration and the fixed price in the reader’s language', async () => {
    const m = await mountSale(ServiceTile, { props: { service: service() }, locale: 'es' });
    const tile = m.find('pos-service-sv1');
    expect(tile.find('.pos-tile__thumb').text()).toBe('CD');
    expect(tile.find('.pos-tile__name').text()).toBe('Corte de pelo');
    expect(tile.find('.pos-tile__unit').text()).toBe('45 min');
    expect(plain(tile.find('.pos-tile__price').text())).toBe('25,00 €');
    expect(tile.attributes('aria-disabled')).toBeUndefined();
  });

  it.each([
    ['from', 'Desde 65,00 €'],
    ['hourly', '65,00 € / hora'],
    ['variable', 'Variable · 65,00 €'],
    ['free', 'Gratis'],
  ] as const)('a %s service says how it is priced', async (pricing_type, text) => {
    const m = await mountSale(ServiceTile, { props: { service: service({ pricing_type, price: 6500 }) }, locale: 'es' });
    expect(plain(m.find('pos-service-sv1').find('.pos-tile__price').text())).toBe(text);
  });

  it('a service without VAT is marked «VAT missing», looks blocked and still takes the tap', async () => {
    const m = await mountSale(ServiceTile, { props: { service: service({ needs_tax_setup: true }) } });
    const tile = m.find('pos-service-sv1');
    expect(tile.attributes('aria-disabled')).toBe('true');
    expect(tile.find('.pos-tile__badge').text()).toBe('VAT missing');
    await click(tile.element);
    expect(m.wrapper.emitted('pick')).toEqual([[service({ needs_tax_setup: true })]]);
  });

  it('in Ceuta or Melilla the badge names the IPSI, in the reader’s language', async () => {
    const m = await mountSale(ServiceTile, { props: { service: service({ needs_tax_setup: true }) }, locale: 'es' });
    await m.live();
    await m.result('sale.sale.tax_kind', { tax: 'ipsi' });
    expect(m.find('pos-service-sv1').find('.pos-tile__badge').text()).toBe('Falta el IPSI');
  });

  it('a tap hands the service up', async () => {
    const m = await mountSale(ServiceTile, { props: { service: service() } });
    await click(m.find('pos-service-sv1').element);
    expect(m.wrapper.emitted('pick')).toEqual([[service()]]);
  });
});
