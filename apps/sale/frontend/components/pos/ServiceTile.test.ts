// A service tile of the till's grid (SALE-F38, SERVICE-F09): the initials over the name's colour, the
// name, the duration and the price — «From», «per hour», «Variable» or «Free» when it has no fixed
// price. One without VAT is marked «VAT missing» and still takes the tap, to say why.
import { describe, expect, it } from 'vitest';

import { click, mountSale, taxSettings } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { service } from './__tests__/fixtures';
import ServiceTile from './ServiceTile.vue';

describe('ServiceTile', () => {
  it('paints the initials, the name, the duration and the fixed price in the reader’s language', async () => {
    const m = await mountSale(ServiceTile, { props: { service: service() }, locale: 'es' });
    await m.live();
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
    await m.live();
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
    await m.result('tax.settings.get', taxSettings('ipsi'));
    expect(m.find('pos-service-sv1').find('.pos-tile__badge').text()).toBe('Falta el IPSI');
  });

  it('a tap hands the service up', async () => {
    const m = await mountSale(ServiceTile, { props: { service: service() } });
    await click(m.find('pos-service-sv1').element);
    expect(m.wrapper.emitted('pick')).toEqual([[service()]]);
  });

  // SERVICE-F34: the service's photo on its tile, as a product's (INVENTORY-F32).
  it('shows the service’s photo where the initials go, and the initials when it does not load', async () => {
    const url = '/p/catalog/beauty_hair/corte_mujer.webp';
    const m = await mountSale(ServiceTile, { props: { service: service({ image: 'catalog:beauty_hair/corte_mujer', image_url: url }) } });
    const thumb = m.find('pos-service-sv1').find('.pos-tile__thumb');
    expect([thumb.get('img').attributes('src'), thumb.get('img').attributes('alt'), thumb.get('img').attributes('loading')]).toEqual([
      url,
      service().name,
      'lazy',
    ]);
    await thumb.get('img').trigger('error');
    expect(thumb.find('img').exists()).toBe(false);
    expect(thumb.text()).toBe('CD');
  });
});
