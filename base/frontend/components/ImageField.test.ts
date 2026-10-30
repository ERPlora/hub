// «Photo» of a product's, a service's or a set menu's form (INVENTORY-F30/F31, SERVICE-F34/F35, COMBO-F14): the photo
// (or the initials, «No photo: its initials are shown»), «Choose from the library» and «Upload photo» while it has none,
// «Change» and «Remove photo» once it has one. The library hands back an image of it; «Upload photo» opens the device's
// picker and a JPG, PNG or WebP of up to 2 MB shows at once, read on the device (nothing is sent until the form saves).
// A bigger file or one that is not a photo says why next to «Photo» and changes nothing.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ImageDraft } from '../lib/item-image';
import { flush, mountBase } from '../__tests__/mount-base';
import ImageField from './ImageField.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

const NONE: ImageDraft = { reference: '', url: '', data: null };
const AMERICANO: ImageDraft = {
  reference: 'catalog:hospitality/americano',
  url: '/p/catalog/hospitality/americano.webp',
  data: null,
};
const LATTE = {
  reference: 'catalog:hospitality/latte',
  folder: 'hospitality',
  name: 'latte',
  title: 'Latte',
  url: '/p/catalog/hospitality/latte.webp',
};

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountBase(ImageField, {
    locale: 'es',
    props: { modelValue: NONE, name: 'Café con leche', testid: 'f', ...props },
    onApi: () => Response.json({ rows: [LATTE], total: 1, limit: 60, offset: 0 }),
  });
  // A form keeps what the field hands up.
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: ImageDraft) => m.wrapper.setProps({ modelValue: value }) });
  const el = (id: string) => document.querySelector<HTMLElement & { disabled?: boolean }>(`[data-testid="f-${id}"]`);
  const drafts = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value as ImageDraft);
  async function choose(file: File) {
    const input = el('file') as HTMLInputElement;
    const before = drafts().length;
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    input.dispatchEvent(new Event('change'));
    // Read on the device: done once it hands a photo up or says why not.
    await vi.waitFor(() => expect(drafts().length > before || !!el('error')).toBe(true));
    await flush();
  }
  return { ...m, el, drafts, choose };
}

describe('ImageField', () => {
  it('without a photo shows the initials and offers the library and an upload', async () => {
    const s = await setup();
    expect(s.el('label')!.textContent!.trim()).toBe('Foto');
    expect(s.el('preview')!.textContent!.trim()).toBe('CC');
    expect(s.el('none')!.textContent!.trim()).toBe('Sin foto: se ven sus iniciales');
    expect(s.el('library')!.textContent!.trim()).toBe('Elegir de la librería');
    expect(s.el('upload')!.textContent!.trim()).toBe('Subir foto');
    expect(s.el('rules')!.textContent!.trim()).toBe('JPG, PNG o WebP de hasta 2 MB');
    expect(s.el('change')).toBeNull();
    expect(s.el('remove')).toBeNull();
  });

  it('with a photo shows it and offers «Change» and «Remove photo»', async () => {
    const s = await setup({ modelValue: AMERICANO });
    expect(s.el('preview')!.querySelector('img')!.getAttribute('src')).toBe(AMERICANO.url);
    expect(s.el('change')!.textContent!.trim()).toBe('Cambiar');
    expect(s.el('remove')!.textContent!.trim()).toBe('Quitar foto');
    expect(s.el('library')).toBeNull();
    expect(s.el('none')).toBeNull();
  });

  it('the library opens searching the item’s name; the image tapped is the photo at once', async () => {
    const s = await setup();
    s.el('library')!.click();
    await flush();
    const search = s.net.api.find((call) => call.url.startsWith('/api/catalog/images'))!;
    expect(new URL(search.url, 'http://a.localhost').searchParams.get('query')).toBe('Café con leche');
    s.el('library-modal-image-hospitality-latte')!.click();
    await flush();
    expect(s.drafts()).toEqual([{ reference: LATTE.reference, url: LATTE.url, data: null }]);
    expect(s.el('preview')!.querySelector('img')!.getAttribute('src')).toBe(LATTE.url);
  });

  it('«Change» opens the library too, with a service’s sectors first', async () => {
    const s = await setup({ modelValue: AMERICANO, folders: ['beauty_hair', 'beauty_body'] });
    s.el('change')!.click();
    await flush();
    const tabs = [...document.querySelectorAll('[data-testid^="f-library-modal-folder-"]')].map((b) => b.getAttribute('data-testid'));
    expect(tabs.slice(0, 3)).toEqual(['f-library-modal-folder-all', 'f-library-modal-folder-beauty_hair', 'f-library-modal-folder-beauty_body']);
  });

  it('«Remove photo» leaves it with its initials', async () => {
    const s = await setup({ modelValue: AMERICANO });
    s.el('remove')!.click();
    await flush();
    expect(s.drafts()).toEqual([NONE]);
    expect(s.el('preview')!.textContent!.trim()).toBe('CC');
  });

  it('«Upload photo» opens the device’s picker, for photos', async () => {
    const s = await setup();
    const input = s.el('file') as HTMLInputElement;
    expect(input.getAttribute('accept')).toBe('image/*');
    const click = vi.spyOn(input, 'click');
    s.el('upload')!.click();
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('the library’s «Upload photo» opens the device’s picker as well', async () => {
    const s = await setup();
    const click = vi.spyOn(s.el('file') as HTMLInputElement, 'click');
    s.el('library')!.click();
    await flush();
    s.el('library-modal-upload')!.click();
    await flush();
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('a photo chosen on the device shows at once and waits for «Save»', async () => {
    const s = await setup({ modelValue: AMERICANO });
    await s.choose(new File(['ABC'], 'mine.png', { type: 'image/png' }));
    expect(s.drafts()).toEqual([{ reference: '', url: 'data:image/png;base64,QUJD', data: 'QUJD' }]);
    expect(s.el('preview')!.querySelector('img')!.getAttribute('src')).toBe('data:image/png;base64,QUJD');
    expect(s.net.api.filter((call) => call.init.method === 'POST')).toEqual([]);
  });

  it('a photo past 2 MB says so and changes nothing', async () => {
    const s = await setup({ modelValue: AMERICANO });
    await s.choose(new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'big.jpg', { type: 'image/jpeg' }));
    expect(s.el('error')!.textContent!.trim()).toBe('La foto pesa más de 2 MB. Elige una más ligera.');
    expect(s.drafts()).toEqual([]);
  });

  it('a file that is not a photo says so; a good one afterwards clears it', async () => {
    const s = await setup();
    await s.choose(new File(['%PDF'], 'carta.pdf', { type: 'application/pdf' }));
    expect(s.el('error')!.textContent!.trim()).toBe('Ese archivo no es una foto. Sube una imagen JPG, PNG o WebP.');
    await s.choose(new File(['ABC'], 'mine.webp', { type: 'image/webp' }));
    expect(s.el('error')).toBeNull();
  });

  it('while the form saves, nothing can be changed', async () => {
    const s = await setup({ modelValue: AMERICANO, disabled: true });
    expect(s.el('change')!.disabled).toBe(true);
    expect(s.el('remove')!.disabled).toBe(true);
  });
});
