import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import PosItemTile from './PosItemTile.vue';

describe('PosItemTile', () => {
  it('uses an Ionic button and keeps a blocked tile tappable so the catalogue can explain why', async () => {
    const m = await mountSale(PosItemTile, {
      props: { testid: 'pos-item', name: 'Café con leche', price: '1,50 €', blocked: true, label: 'Café con leche · No disponible' },
    });
    const tile = m.find('pos-item');
    expect(tile.element.tagName.toLowerCase()).toBe('ion-button');
    expect(tile.attributes('aria-disabled')).toBe('true');
    expect(tile.attributes('disabled')).toBeUndefined();
    expect(tile.classes()).toContain('pos-tile--blocked');
    await click(tile.element);
    expect(m.wrapper.emitted('pick')).toHaveLength(1);
  });

  it('paints the shared name, price, metadata and badge', async () => {
    const m = await mountSale(PosItemTile, {
      props: { testid: 'pos-item', name: 'Corte de pelo', price: '25,00 €', meta: '45 min', badge: 'Servicio' },
    });
    const tile = m.find('pos-item');
    expect(tile.find('.pos-tile__name').text()).toBe('Corte de pelo');
    expect(tile.find('.pos-tile__price').text()).toBe('25,00 €');
    expect(tile.find('.pos-tile__unit').text()).toBe('45 min');
    expect(tile.find('.pos-tile__badge').text()).toBe('Servicio');
  });

  it('keeps its native button announcing the change when it sells out or goes back on sale with the till open', async () => {
    const m = await mountSale(PosItemTile, { props: { testid: 'pos-item', name: 'Croquetas', price: '6,50 €' } });
    const tile = m.find('pos-item');
    // Ionic copies the host's aria-* to its native button only when it loads (INVENTORY-F29, SALE-F07; hub#1337).
    tile.element.shadowRoot!.innerHTML = '<button type="button"></button>';
    const native = () => tile.element.shadowRoot!.querySelector('button')!;
    expect(tile.attributes('data-aria-disabled')).toBe('false');

    await m.wrapper.setProps({ soldOut: true });
    expect(tile.attributes('data-aria-disabled')).toBe('true');
    expect(native().getAttribute('aria-disabled')).toBe('true');

    await m.wrapper.setProps({ soldOut: false });
    expect(tile.attributes('data-aria-disabled')).toBe('false');
    expect(native().hasAttribute('aria-disabled')).toBe(false);

    await m.wrapper.setProps({ blocked: true });
    expect(native().getAttribute('aria-disabled')).toBe('true');
  });
});
