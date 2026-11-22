import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, MANAGER, mountInventory, ok, product, refusal, UNITS, type ApiCall } from '../__tests__/mount-inventory';
import ProductFormModal from './ProductFormModal.vue';
import { CATEGORIES, searches, setup } from '../__tests__/product-form';

afterEach(() => {
  document.body.innerHTML = '';
});

// INVENTORY-F30/F31: «Photo» in the form, for who may change products. The image goes once the product is saved: a
// library image or none with `set_image`, a photo of its own with `upload_image` («Uploading photo…»). If the product
// saved and the photo did not, the dialog says so with «Retry» and keeps the photo it had.
describe('ProductFormModal: photo', () => {
  const LATTE = { reference: 'catalog:hospitality/latte', folder: 'hospitality', name: 'latte', title: 'Latte', url: '/p/catalog/hospitality/latte.webp' };
  const WITH_PHOTO = { image: 'catalog:hospitality/americano', image_url: '/p/catalog/hospitality/americano.webp' };
  const IMAGE = '/api/inventory/products/image';
  const UPLOAD = '/api/inventory/products/image/upload';

  /** The API: the library answers its search, every write answers the product (`saved`), the photo steps `photo`. */
  function server(saved: Record<string, unknown>, photo: () => Response | Promise<Response> = () => ok(product(saved))) {
    return (call: ApiCall): Response | Promise<Response> => {
      const path = call.url.split('?')[0];
      if (path === '/api/catalog/images') return ok({ rows: [LATTE], total: 1, limit: 60, offset: 0 });
      if (path === IMAGE || path === UPLOAD) return photo();
      if ((call.init.method ?? 'GET') === 'GET') return searches(CATEGORIES)(call);
      return ok(product(saved), 201);
    };
  }

  async function chooseFile(s: Awaited<ReturnType<typeof setup>>, file: File) {
    const input = s.el('inventory-product-image-file') as unknown as HTMLInputElement;
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    input.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(s.el('inventory-product-image-preview')?.querySelector('img')?.getAttribute('src')).toMatch(/^data:/));
  }

  it('shows «Photo» with what the product has, to who may change products', async () => {
    const s = await setup({ product: product(WITH_PHOTO) });
    expect(s.el('inventory-product-image-label')?.textContent?.trim()).toBe('Photo');
    expect(s.el('inventory-product-image-preview')?.querySelector('img')?.getAttribute('src')).toBe(WITH_PHOTO.image_url);
    expect(s.el('inventory-product-image-remove')?.textContent?.trim()).toBe('Remove photo');
  });

  it('who may create products but not change them does not see «Photo»', async () => {
    const m = await mountInventory(ProductFormModal, {
      props: { open: true, product: null, units: UNITS.rows },
      attach: true,
      session: { ...MANAGER, permissions: MANAGER.permissions.filter((p) => p !== 'inventory.change_product') },
      api: searches(CATEGORIES),
    });
    await m.live();
    expect(document.querySelector('[data-testid="inventory-product-image"]')).toBeNull();
  });

  it('a new product with a library image: the image goes once it is created, on the new product', async () => {
    const s = await setup({}, { api: server({ id: 'p9' }) });
    await s.fillRequired();
    s.el('inventory-product-image-library')!.click();
    await flush();
    const search = s.calls('/api/catalog/images')[0];
    expect(s.query(search).query).toBe('Coffee');
    s.el('inventory-product-image-library-modal-image-hospitality-latte')!.click();
    await flush();
    expect(s.el('inventory-product-image-preview')?.querySelector('img')?.getAttribute('src')).toBe(LATTE.url);
    expect(s.calls(IMAGE)).toHaveLength(0);
    await s.submit();
    expect(s.calls('/api/inventory/products')).toHaveLength(1);
    expect(s.sent(IMAGE)).toEqual({ id: 'p9', image: 'catalog:hospitality/latte' });
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('a photo of its own goes up after the changes, «Uploading photo…» meanwhile', async () => {
    let release: (r: Response) => void = () => undefined;
    const s = await setup({ product: product(WITH_PHOTO) }, { api: server({}, () => new Promise<Response>((resolve) => (release = resolve))) });
    await chooseFile(s, new File(['ABC'], 'mine.png', { type: 'image/png' }));
    await s.submit();
    await vi.waitFor(() => expect(s.calls(UPLOAD)).toHaveLength(1));
    expect(s.sent(UPLOAD)).toEqual({ id: 'p1', data_base64: 'QUJD' });
    expect(s.el('inventory-product-form-submit')?.textContent?.trim()).toBe('Uploading photo…');
    release(ok(product()));
    await flush();
    expect(s.calls(IMAGE)).toHaveLength(0);
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('«Remove photo» clears it on save; an unchanged photo sends nothing', async () => {
    const s = await setup({ product: product(WITH_PHOTO) }, { api: server({}) });
    await s.submit();
    expect(s.calls(IMAGE)).toHaveLength(0);
    expect(s.calls(UPLOAD)).toHaveLength(0);

    const r = await setup({ product: product(WITH_PHOTO) }, { api: server({}) });
    r.el('inventory-product-image-remove')!.click();
    await flush();
    await r.submit();
    expect(r.sent(IMAGE)).toEqual({ id: 'p1', image: '' });
  });

  it('the product saved and the photo not: says why with «Retry», which sends only the photo', async () => {
    let fail = true;
    const s = await setup(
      { product: product(WITH_PHOTO) },
      { api: server({}, () => (fail ? refusal(503, 'base.photo_not_saved', 'The photo could not be saved. Try again.') : ok(product()))) },
    );
    await chooseFile(s, new File(['ABC'], 'mine.png', { type: 'image/png' }));
    await s.submit();
    await vi.waitFor(() => expect(s.el('inventory-product-photo-failed')).not.toBeNull());
    expect(s.el('inventory-product-photo-failed')?.textContent).toContain(
      'The product has been saved, but the photo has not: The photo could not be saved. Try again.',
    );
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(true);
    const updates = s.calls('/api/inventory/products/update').length;
    fail = false;
    s.el('inventory-product-photo-retry')!.click();
    await vi.waitFor(() => expect(s.wrapper.emitted('update:open')).toEqual([[false]]));
    expect(s.calls(UPLOAD)).toHaveLength(2);
    expect(s.calls('/api/inventory/products/update')).toHaveLength(updates);
  });

  it('in Spanish', async () => {
    const s = await setup({ product: product() }, { locale: 'es', api: server({}, () => refusal(422, 'base.photo_too_big', 'La foto pesa más de 2 MB. Elige una más ligera.')) });
    expect(s.el('inventory-product-image-label')?.textContent?.trim()).toBe('Foto');
    await chooseFile(s, new File(['ABC'], 'mine.png', { type: 'image/png' }));
    await s.submit();
    await vi.waitFor(() => expect(s.el('inventory-product-photo-failed')).not.toBeNull());
    expect(s.el('inventory-product-photo-failed')?.textContent).toContain(
      'El producto se ha guardado, pero la foto no: La foto pesa más de 2 MB. Elige una más ligera.',
    );
    expect(s.el('inventory-product-photo-retry')?.textContent?.trim()).toBe('Reintentar');
  });

  it('closing without saving discards the photo chosen; opening another product shows its own', async () => {
    const s = await setup({ product: product(WITH_PHOTO) });
    s.el('inventory-product-image-remove')!.click();
    await flush();
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    await flush();
    expect(s.el('inventory-product-image-preview')?.querySelector('img')?.getAttribute('src')).toBe(WITH_PHOTO.image_url);
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ product: product({ id: 'p2', name: 'Green tea' }), open: true });
    await flush();
    expect(s.el('inventory-product-image-preview')?.querySelector('img')).toBeNull();
    expect(s.el('inventory-product-image-preview')?.textContent?.trim()).toBe('GT');
  });
});
