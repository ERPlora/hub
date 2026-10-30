// The image of a product, a service or a set menu (round 2026-10-30; INVENTORY-F30 to F32, SERVICE-F34/F35,
// COMBO-F14): the initials over the name's colour that stand in for a missing photo, what a form keeps while the person
// chooses (a library image, a photo of their own read on the device, or none), the one step it sends once the record is
// saved, and that step's failure kept for «Retry» (the record saved, the photo not).
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import {
  draftOf,
  imageStep,
  initials,
  MAX_PHOTO_BYTES,
  readPhoto,
  tileGradient,
  useImageSave,
  type ImageDraft,
} from './item-image';

const NONE: ImageDraft = { reference: '', url: '', data: null };

/** A file of `size` bytes and `type`, named `name`. */
function file(size: number, type: string, name = 'photo.png'): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe('initials and tileGradient', () => {
  it('takes the first letter of the first two words, upper-cased', () => {
    expect(initials('café con leche')).toBe('CC');
    expect(initials('  Tostada ')).toBe('T');
    expect(initials('')).toBe('');
  });

  it('gives the same name the same colour and another name another', () => {
    expect(tileGradient('Coffee')).toBe(tileGradient('Coffee'));
    expect(tileGradient('Coffee')).toMatch(/^linear-gradient\(135deg, hsl\(\d+ 42% 38%\), hsl\(\d+ 44% 26%\)\)$/);
    expect(tileGradient('Coffee')).not.toBe(tileGradient('Tea'));
  });
});

describe('draftOf', () => {
  it('starts from what the record has: its reference and where it is served', () => {
    expect(draftOf({ image: 'catalog:hospitality/americano', image_url: '/p/catalog/hospitality/americano.webp' })).toEqual({
      reference: 'catalog:hospitality/americano',
      url: '/p/catalog/hospitality/americano.webp',
      data: null,
    });
  });

  it('a new record, or one from before the photos, has none', () => {
    expect(draftOf(null)).toEqual(NONE);
    expect(draftOf({})).toEqual(NONE);
  });
});

describe('imageStep', () => {
  it('sends nothing when the image did not change (its own photo included)', () => {
    expect(imageStep('', NONE)).toEqual({ kind: 'none' });
    expect(imageStep('file:inventory/products/a.webp', { reference: 'file:inventory/products/a.webp', url: '/p/media/a', data: null })).toEqual({
      kind: 'none',
    });
  });

  it('sets the library image chosen, or clears the one it had', () => {
    expect(imageStep('', { reference: 'catalog:hospitality/americano', url: '/x', data: null })).toEqual({
      kind: 'set',
      image: 'catalog:hospitality/americano',
    });
    expect(imageStep('catalog:hospitality/americano', NONE)).toEqual({ kind: 'set', image: '' });
  });

  it('uploads a photo of its own chosen on the device, whatever it had', () => {
    expect(imageStep('catalog:hospitality/americano', { reference: '', url: 'data:image/png;base64,QUJD', data: 'QUJD' })).toEqual({
      kind: 'upload',
      data: 'QUJD',
    });
  });
});

describe('readPhoto', () => {
  it('reads a JPG, PNG or WebP of up to 2 MB: the preview and its base64', async () => {
    const read = await readPhoto(new File(['ABC'], 'a.png', { type: 'image/png' }));
    expect(read).toEqual({ ok: true, url: 'data:image/png;base64,QUJD', data: 'QUJD' });
    expect((await readPhoto(file(MAX_PHOTO_BYTES, 'image/webp'))).ok).toBe(true);
    expect((await readPhoto(file(10, 'image/jpeg'))).ok).toBe(true);
  });

  it('refuses a photo past 2 MB without reading it', async () => {
    expect(MAX_PHOTO_BYTES).toBe(2 * 1024 * 1024);
    expect(await readPhoto(file(MAX_PHOTO_BYTES + 1, 'image/png'))).toEqual({ ok: false, reason: 'too_big' });
  });

  it('refuses what is not a JPG, PNG or WebP; a file with no type goes by its extension', async () => {
    expect(await readPhoto(file(10, 'application/pdf', 'menu.pdf'))).toEqual({ ok: false, reason: 'not_a_photo' });
    expect(await readPhoto(file(10, 'image/gif', 'a.gif'))).toEqual({ ok: false, reason: 'not_a_photo' });
    expect(await readPhoto(file(10, '', 'notes.txt'))).toEqual({ ok: false, reason: 'not_a_photo' });
    expect((await readPhoto(file(10, '', 'IMG_0001.JPG'))).ok).toBe(true);
  });
});

describe('useImageSave', () => {
  const steps = () => ({ set: vi.fn(async () => ({})), upload: vi.fn(async () => ({})) });

  it('does nothing when the image did not change', async () => {
    const s = steps();
    const photo = useImageSave(s);
    expect(await photo.save('p1', '', NONE)).toBe(true);
    expect(s.set).not.toHaveBeenCalled();
    expect(s.upload).not.toHaveBeenCalled();
  });

  it('sets or uploads for the saved record, saying «uploading» only while a photo goes up', async () => {
    const s = steps();
    let release: () => void = () => undefined;
    s.upload.mockImplementation(() => new Promise((resolve) => (release = () => resolve({}))));
    const photo = useImageSave(s);
    const going = photo.save('p1', '', { reference: '', url: 'data:,', data: 'QUJD' });
    expect([photo.pending.value, photo.uploading.value]).toEqual([true, true]);
    release();
    expect(await going).toBe(true);
    expect(s.upload).toHaveBeenCalledWith('p1', 'QUJD');
    expect([photo.pending.value, photo.uploading.value]).toEqual([false, false]);

    expect(await photo.save('p2', 'catalog:a/b', NONE)).toBe(true);
    expect(s.set).toHaveBeenCalledWith('p2', '');
  });

  it('keeps a refusal with its record and its message, and a new try clears it', async () => {
    const s = steps();
    s.upload.mockRejectedValueOnce(new ApiError(503, 'base.photo_not_saved', 'The photo could not be saved. Try again.'));
    const photo = useImageSave(s);
    const draft = { reference: '', url: 'data:,', data: 'QUJD' };
    expect(await photo.save('p1', '', draft)).toBe(false);
    expect(photo.failure.value).toEqual({ id: 'p1', reason: 'The photo could not be saved. Try again.' });
    expect(photo.pending.value).toBe(false);
    expect(await photo.save('p1', '', draft)).toBe(true);
    expect(photo.failure.value).toBeNull();
  });

  it('a failure with no message keeps an empty reason (the form says its own)', async () => {
    const s = steps();
    s.set.mockRejectedValueOnce('offline');
    const photo = useImageSave(s);
    expect(await photo.save('p1', '', { reference: 'catalog:a/b', url: '/x', data: null })).toBe(false);
    expect(photo.failure.value).toEqual({ id: 'p1', reason: '' });
    photo.reset();
    expect(photo.failure.value).toBeNull();
  });
});
