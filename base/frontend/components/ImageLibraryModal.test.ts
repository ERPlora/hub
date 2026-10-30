// «Image library» (INVENTORY-F30, SERVICE-F34, COMBO-F14): the window a product's, a service's or a set menu's «Photo»
// opens. The search box comes written with the item's name and searches the shared library (`base.catalog_image.search`)
// by title and synonyms in Spanish or English; the sector tabs narrow it (a service's put «Hair» and «Beauty» first);
// 60 at a time with «Load more»; each image with its title under it. Loading, empty («No image matches your search…»)
// and error («The image library could not be loaded.» with «Retry») states. A tap on an image hands it up and closes;
// «Upload photo» asks the field for the device's picker and closes too.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CatalogImage, CatalogImagePage } from '../operations';
import { flush, mountBase } from '../__tests__/mount-base';
import ImageLibraryModal from './ImageLibraryModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

const PATH = '/api/catalog/images';
const TID = 'lib';

function image(name: string, title: string, folder = 'hospitality'): CatalogImage {
  return { reference: `catalog:${folder}/${name}`, folder, name, title, url: `/p/catalog/${folder}/${name}.webp` };
}

function answer(rows: CatalogImage[], total = rows.length, offset = 0): CatalogImagePage {
  return { rows, total, limit: 60, offset };
}

type Answer = Response | Promise<Response>;

/** Mounts the window open; `replies` answers each search in turn (the last one repeats). */
async function setup(props: Record<string, unknown> = {}, replies: Array<() => Answer> = [], locale: 'en' | 'es' = 'es') {
  let n = 0;
  const m = await mountBase(ImageLibraryModal, {
    locale,
    props: { open: true, query: 'Café con leche', testid: TID, ...props },
    onApi: () => {
      const reply = replies[Math.min(n++, replies.length - 1)];
      return reply ? reply() : Response.json(answer([]));
    },
  });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement & { value?: unknown }>(`[data-testid="${TID}-${id}"]`);
  const searches = () =>
    m.net.api
      .filter((call) => call.url.split('?')[0] === PATH)
      .map((call) => Object.fromEntries(new URL(call.url, 'http://a.localhost').searchParams));
  async function type(value: string) {
    const box = el('search')!;
    box.value = value;
    box.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function tab(value: string) {
    const segment = el('folders')!;
    segment.value = value;
    segment.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  return { ...m, el, searches, type, tab };
}

const ok = (data: unknown) => () => Response.json(data);

describe('ImageLibraryModal', () => {
  it('opens searching the item’s name, with the box written, and shows each image with its title under it', async () => {
    const s = await setup({}, [ok(answer([image('cafe_con_leche', 'Café con leche'), image('latte', 'Latte')]))]);
    expect(s.searches()).toEqual([{ query: 'Café con leche', limit: '60', offset: '0' }]);
    expect(s.el('search')!.value).toBe('Café con leche');
    expect((s.el('search') as HTMLElement & { placeholder?: string }).placeholder).toBe('Buscar imagen…');
    expect(document.querySelector('[data-testid="lib"]')!.textContent).toContain('Librería de imágenes');
    const tile = s.el('image-hospitality-cafe_con_leche')!;
    const img = tile.querySelector('img')!;
    expect([img.getAttribute('src'), img.getAttribute('alt'), img.getAttribute('loading')]).toEqual([
      '/p/catalog/hospitality/cafe_con_leche.webp',
      'Café con leche',
      'lazy',
    ]);
    expect(tile.textContent!.trim()).toBe('Café con leche');
    expect(s.el('image-hospitality-latte')).not.toBeNull();
  });

  it('shows placeholders while the library answers', async () => {
    let release: (r: Response) => void = () => undefined;
    const s = await setup({}, [() => new Promise<Response>((resolve) => (release = resolve))]);
    expect(s.el('loading')).not.toBeNull();
    expect(s.el('loading')!.getAttribute('aria-label')).toBe('Cargando imágenes…');
    release(Response.json(answer([image('te', 'Té')])));
    await flush();
    expect(s.el('loading')).toBeNull();
    expect(s.el('image-hospitality-te')).not.toBeNull();
  });

  it('searches what the person types; under two letters, the whole library', async () => {
    const s = await setup({}, [ok(answer([]))]);
    await s.type('champú');
    await s.type('c');
    expect(s.searches().map((q) => q.query)).toEqual(['Café con leche', 'champú', '']);
  });

  it('the sector tabs narrow the search, in their order; a service’s put Hair and Beauty first', async () => {
    const s = await setup({}, [ok(answer([]))]);
    const labels = () => [...document.querySelectorAll(`[data-testid^="${TID}-folder-"]`)].map((b) => b.textContent!.trim());
    expect(labels()).toEqual(['Todas', 'Hostelería', 'Peluquería', 'Estética', 'Comercio', 'Deporte', 'Spa y bienestar']);
    await s.tab('beauty_hair');
    await s.tab('all');
    expect(s.searches().map((q) => q.folder)).toEqual([undefined, 'beauty_hair', undefined]);
    s.wrapper.unmount();

    const service = await setup({ folders: ['beauty_hair', 'beauty_body'] }, [ok(answer([]))]);
    expect(labels()).toEqual(['Todas', 'Peluquería', 'Estética', 'Hostelería', 'Comercio', 'Deporte', 'Spa y bienestar']);
    service.wrapper.unmount();
  });

  it('says the tabs in English to an English reader', async () => {
    await setup({}, [ok(answer([]))], 'en');
    const labels = [...document.querySelectorAll(`[data-testid^="${TID}-folder-"]`)].map((b) => b.textContent!.trim());
    expect(labels).toEqual(['All', 'Hospitality', 'Hair', 'Beauty', 'Retail', 'Fitness', 'Spa and wellness']);
  });

  it('brings 60 at a time with «Load more» until all are shown', async () => {
    const first = Array.from({ length: 60 }, (_, i) => image(`i${i}`, `Imagen ${i}`));
    const s = await setup({}, [ok(answer(first, 61)), ok(answer([image('i60', 'Imagen 60')], 61, 60))]);
    expect(s.el('count')!.textContent!.trim()).toBe('Mostrando 60 de 61');
    s.el('more')!.click();
    await flush();
    expect(s.searches()[1]).toEqual({ query: 'Café con leche', limit: '60', offset: '60' });
    expect(document.querySelectorAll(`[data-testid^="${TID}-image-"]`)).toHaveLength(61);
    expect(s.el('more')).toBeNull();
  });

  it('says so when nothing matches, and offers to upload a photo', async () => {
    const s = await setup({}, [ok(answer([]))]);
    expect(s.el('empty')!.textContent).toContain('Ninguna imagen coincide con tu búsqueda. Prueba con otra palabra o sube una foto.');
    expect(s.el('upload')!.textContent!.trim()).toBe('Subir foto');
  });

  it('a library that cannot be read says so with «Retry», which searches again', async () => {
    const unavailable = () =>
      Response.json({ error: { code: 'base.image_library_unavailable', message: 'x' } }, { status: 503 });
    const s = await setup({}, [unavailable, ok(answer([image('te', 'Té')]))]);
    expect(s.el('error')!.textContent).toContain('No se pudo cargar la librería de imágenes.');
    expect(s.el('retry')!.textContent!.trim()).toBe('Reintentar');
    s.el('retry')!.click();
    await flush();
    expect(s.el('error')).toBeNull();
    expect(s.el('image-hospitality-te')).not.toBeNull();
  });

  it('an older answer that arrives late never covers the newer search', async () => {
    let late: (r: Response) => void = () => undefined;
    const s = await setup({}, [() => new Promise<Response>((resolve) => (late = resolve)), ok(answer([image('latte', 'Latte')]))]);
    await s.type('latte');
    late(Response.json(answer([image('cafe', 'Café')])));
    await flush();
    expect(s.el('image-hospitality-latte')).not.toBeNull();
    expect(s.el('image-hospitality-cafe')).toBeNull();
  });

  it('a tap on an image hands it up and closes the window', async () => {
    const latte = image('latte', 'Latte');
    const s = await setup({}, [ok(answer([latte]))]);
    s.el('image-hospitality-latte')!.click();
    await flush();
    expect(s.wrapper.emitted('pick')).toEqual([[latte]]);
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('«Upload photo» asks for the device’s picker and closes the window', async () => {
    const s = await setup({}, [ok(answer([]))]);
    s.el('upload')!.click();
    await flush();
    expect(s.wrapper.emitted('upload')).toHaveLength(1);
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('opening it again starts over from the item’s name and all the sectors', async () => {
    const s = await setup({}, [ok(answer([]))]);
    await s.type('champú');
    await s.tab('retail');
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true, query: 'Tostada' });
    await flush();
    expect(s.searches().at(-1)).toEqual({ query: 'Tostada', limit: '60', offset: '0' });
    expect(s.el('search')!.value).toBe('Tostada');
  });
});
