import { afterEach, describe, expect, it } from 'vitest';

import { ok, product } from '../__tests__/mount-inventory';
import { setup } from '../__tests__/product-form';

afterEach(() => {
  document.body.innerHTML = '';
});

const BOX = 'inventory-product-show-on-website';
const NOTE = 'inventory-product-show-on-website-note';

describe('ProductFormModal: show on website (INVENTORY-F36)', () => {
  it('offers it on for a new product and says what turning it off does', async () => {
    const s = await setup();

    expect(s.el(BOX)?.checked).toBe(true);
    expect(s.el(BOX)?.textContent?.trim()).toBe('Show on website');
    expect(s.el(NOTE)).toBeNull();
    await s.check(BOX, false);
    expect(s.el(NOTE)?.textContent?.trim()).toBe('Your website’s catalog leaves it out; the till still sells it.');
  });

  it('creates a product hidden from the website when it is turned off', async () => {
    const s = await setup();
    await s.fillRequired();
    await s.check(BOX, false);
    s.net.onApi(() => ok(product({ show_on_website: false }), 201));
    await s.submit();

    expect(s.sent('/api/inventory/products').show_on_website).toBe(false);
  });

  it('creates it shown on the website when left as it is', async () => {
    const s = await setup();
    await s.fillRequired();
    s.net.onApi(() => ok(product(), 201));
    await s.submit();

    expect(s.sent('/api/inventory/products').show_on_website).toBe(true);
  });

  it('opens a hidden product with it off and sends only that change', async () => {
    const s = await setup({ product: product({ show_on_website: false }) });
    expect(s.el(BOX)?.checked).toBe(false);

    await s.check(BOX, true);
    s.net.onApi(() => ok(product()));
    await s.submit();
    expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', show_on_website: true });
  });

  it('leaves it out of an edit that does not touch it', async () => {
    const s = await setup({ product: product() });
    await s.type('inventory-product-name', 'Coffee to go');
    s.net.onApi(() => ok(product({ name: 'Coffee to go' })));
    await s.submit();

    expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', name: 'Coffee to go' });
  });

  it('reads in Spanish', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.check(BOX, false);

    expect(s.el(BOX)?.textContent?.trim()).toBe('Mostrar en la página web');
    expect(s.el(NOTE)?.textContent?.trim()).toBe('El catálogo de tu página web no lo enseña; el TPV lo sigue vendiendo.');
  });
});
