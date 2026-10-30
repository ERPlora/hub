// The photo of a product, a service or a set menu (INVENTORY-F32): the photo when it has one, covering its box, loaded
// lazily and named by the item; its initials over its colour when it has none or the photo does not load, never a gap
// nor a broken image. The box's size is its parent's (a till tile, a list's 40 px thumbnail, the form's preview).
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import ItemImage from './ItemImage.vue';

const URL = '/p/catalog/hospitality/americano.webp';

describe('ItemImage', () => {
  it('shows the photo, lazily, named by the item, and no initials over it', () => {
    const w = mount(ItemImage, { props: { src: URL, name: 'Café con leche' } });
    const img = w.get('img');
    expect(img.attributes('src')).toBe(URL);
    expect(img.attributes('alt')).toBe('Café con leche');
    expect(img.attributes('loading')).toBe('lazy');
    expect(w.attributes('data-image')).toBe('photo');
    expect(w.find('.item-image__initials').exists()).toBe(false);
  });

  it('covers its box by default; a wide box (a till tile) may show the whole photo instead', () => {
    const cover = mount(ItemImage, { props: { src: URL, name: 'Té' } });
    expect(cover.get('img').classes()).not.toContain('item-image__photo--contain');
    const contain = mount(ItemImage, { props: { src: URL, name: 'Té', fit: 'contain' } });
    expect(contain.get('img').classes()).toContain('item-image__photo--contain');
  });

  it('without a photo shows the initials over the name’s colour', () => {
    for (const src of ['', null, undefined]) {
      const w = mount(ItemImage, { props: { src, name: 'Café con leche' } });
      expect(w.find('img').exists()).toBe(false);
      expect(w.get('.item-image__initials').text()).toBe('CC');
      expect(w.attributes('style')).toMatch(/linear-gradient/);
      expect(w.attributes('data-image')).toBe('initials');
    }
  });

  it('a photo that does not load leaves the initials; another photo is tried again', async () => {
    const w = mount(ItemImage, { props: { src: URL, name: 'Té' } });
    await w.get('img').trigger('error');
    expect(w.find('img').exists()).toBe(false);
    expect(w.get('.item-image__initials').text()).toBe('T');
    await w.setProps({ src: '/p/catalog/hospitality/te.webp' });
    expect(w.get('img').attributes('src')).toBe('/p/catalog/hospitality/te.webp');
  });

  it('keeps what its parent lays over it (a till tile’s warning)', () => {
    const w = mount(ItemImage, { props: { src: URL, name: 'Té' }, slots: { default: '<span class="warn">!</span>' } });
    expect(w.find('.warn').exists()).toBe(true);
  });

  it('the initials are not read aloud: the item is named by its photo or by the row', () => {
    const w = mount(ItemImage, { props: { src: '', name: 'Té' } });
    expect(w.get('.item-image__initials').attributes('aria-hidden')).toBe('true');
  });
});
