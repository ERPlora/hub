// GalleryEditor: the gallery's photos, up to twelve, in the order the page shows them; each one replaced or removed
// through its own ImageUpload, moved up or down, and one more added at the end while there is room.
import { ImageUpload } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { mountWebsite, settle } from '../__tests__/mount-website';
import type { ImageRef } from '../operations';
import GalleryEditor from './GalleryEditor.vue';

const photo = (id: string): ImageRef => ({ id, url: `/p/media/hub/website/img/${id}.jpg` });
const A = photo('a');
const B = photo('b');
const C = photo('c');

async function editor(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const upload = vi.fn();
  const { wrapper } = await mountWebsite(GalleryEditor, { props: { modelValue: [A, B, C], upload, ...props }, locale });
  const last = (): ImageRef[] => (wrapper.emitted('update:modelValue') ?? []).at(-1)?.[0] as ImageRef[];
  const uploader = (testid: string) => {
    const found = wrapper.findAllComponents(ImageUpload).find((component) => component.props('testid') === testid);
    if (!found) throw new Error(`no ImageUpload ${testid}`);
    return found;
  };
  const button = (testid: string) => wrapper.get(`[data-testid="${testid}"]`);
  return { wrapper, upload, last, uploader, button };
}

describe('GalleryEditor', () => {
  it('lists the photos in their order, each with its own upload, and offers one more', async () => {
    const { wrapper, uploader, upload } = await editor();
    const photos = wrapper.findAll('[data-testid^="website-gallery-photo-"][data-testid$="-row"]');
    expect(photos.map((row) => row.attributes('data-testid'))).toEqual([
      'website-gallery-photo-0-row',
      'website-gallery-photo-1-row',
      'website-gallery-photo-2-row',
    ]);
    expect(uploader('website-gallery-photo-1').props('modelValue')).toEqual(B);
    expect(uploader('website-gallery-photo-1').props('label')).toBe('Photo 2');
    expect(uploader('website-gallery-photo-1').props('upload')).toBe(upload);
    expect(uploader('website-gallery-add').props('modelValue')).toBeNull();
    expect(wrapper.get('[data-testid="website-gallery-count"]').element.textContent).toContain('3 of 12 photos');
  });

  it('an empty gallery says so and offers the first photo', async () => {
    const { wrapper, uploader } = await editor({ modelValue: [] });
    expect(wrapper.find('[data-testid="website-gallery-empty"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="website-gallery-empty"]').element.textContent).toContain('No photos yet');
    expect(uploader('website-gallery-add').exists()).toBe(true);
  });

  it('a photo added goes at the end', async () => {
    const { uploader, last } = await editor();
    const added = photo('d');
    uploader('website-gallery-add').vm.$emit('update:modelValue', added);
    await settle();
    expect(last()).toEqual([A, B, C, added]);
  });

  it('removing a photo takes it out and keeps the others in their order', async () => {
    const { uploader, last } = await editor();
    uploader('website-gallery-photo-1').vm.$emit('update:modelValue', null);
    await settle();
    expect(last()).toEqual([A, C]);
  });

  it('replacing a photo keeps its place', async () => {
    const { uploader, last } = await editor();
    const other = photo('z');
    uploader('website-gallery-photo-0').vm.$emit('update:modelValue', other);
    await settle();
    expect(last()).toEqual([other, B, C]);
  });

  it('moves a photo up or down; the first cannot go up and the last cannot go down', async () => {
    const { button, last, wrapper } = await editor();
    await button('website-gallery-photo-1-up').trigger('click');
    expect(last()).toEqual([B, A, C]);
    await button('website-gallery-photo-1-down').trigger('click');
    expect(last()).toEqual([A, C, B]);
    const disabled = (testid: string) => (wrapper.get(`[data-testid="${testid}"]`).element as HTMLElement & { disabled?: boolean }).disabled;
    expect(disabled('website-gallery-photo-0-up')).toBe(true);
    expect(disabled('website-gallery-photo-0-down')).toBe(false);
    expect(disabled('website-gallery-photo-2-up')).toBe(false);
    expect(disabled('website-gallery-photo-2-down')).toBe(true);
    // A disabled arrow changes nothing even if its click arrives.
    const before = (wrapper.emitted('update:modelValue') ?? []).length;
    await button('website-gallery-photo-0-up').trigger('click');
    await button('website-gallery-photo-2-down').trigger('click');
    expect((wrapper.emitted('update:modelValue') ?? []).length).toBe(before);
  });

  it('with twelve photos there is no room for another', async () => {
    const twelve = Array.from({ length: 12 }, (_value, index) => photo(`p${index}`));
    const { wrapper } = await editor({ modelValue: twelve });
    expect(wrapper.findAllComponents(ImageUpload).some((component) => component.props('testid') === 'website-gallery-add')).toBe(false);
    expect(wrapper.get('[data-testid="website-gallery-count"]').element.textContent).toContain('12 of 12 photos');
    expect(wrapper.get('[data-testid="website-gallery-full"]').element.textContent).toContain('The gallery is full');
  });

  it('shows the server’s refusal', async () => {
    const message = 'This image was not uploaded to this business’s website: upload it again.';
    const { wrapper } = await editor({ error: message });
    expect(wrapper.get('[data-testid="website-gallery-error"]').element.textContent).toContain(message);
  });

  it('a disabled gallery shows the photos and changes nothing', async () => {
    const { wrapper, uploader, button } = await editor({ disabled: true });
    expect(wrapper.findAllComponents(ImageUpload).some((component) => component.props('testid') === 'website-gallery-add')).toBe(false);
    expect(uploader('website-gallery-photo-0').props('disabled')).toBe(true);
    await button('website-gallery-photo-1-up').trigger('click');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const { wrapper, uploader } = await editor({}, 'es');
    expect(uploader('website-gallery-photo-0').props('label')).toBe('Foto 1');
    expect(uploader('website-gallery-add').props('label')).toBe('Añadir una foto');
    expect(wrapper.get('[data-testid="website-gallery-count"]').element.textContent).toContain('3 de 12 fotos');
  });
});
