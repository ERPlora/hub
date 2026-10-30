// WHATSAPP_INBOX-F29, F30 and F33: the file of a template's photo, video or document header, as the template's sheet and
// «Send a template» show it (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL) — as WhatsApp Manager, WATI
// or respond.io do: the photo's thumbnail, the video's first frame with a play sign, a document's icon; its name and
// size next to it. While the photo or the video loads, a spinner; if it cannot be shown, a notice, and the name stays.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mountInbox, settle } from '../__tests__/mount-inbox';
import type { TemplateSampleOut } from '../operations';
import HeaderFilePreview from './HeaderFilePreview.vue';

const ID = 'preview';
const PHOTO: TemplateSampleOut = {
  id: 's1',
  header_format: 'IMAGE',
  content_type: 'image/jpeg',
  size: 2048,
  name: 'carta.jpg',
  url: '/p/media/0193a5b2c3d47e8f9a0b1c2d3e4f5a6b/whatsapp_inbox/samples/0123456789abcdef.jpg',
};
const VIDEO: TemplateSampleOut = { ...PHOTO, id: 's2', header_format: 'VIDEO', content_type: 'video/mp4', name: 'otono.mp4', url: PHOTO.url.replace('.jpg', '.mp4') };
const DOCUMENT: TemplateSampleOut = { ...PHOTO, id: 's3', header_format: 'DOCUMENT', content_type: 'application/pdf', name: 'carta.pdf', url: PHOTO.url.replace('.jpg', '.pdf') };

async function setup(sample: TemplateSampleOut, locale: 'en' | 'es' = 'en') {
  const m = await mountInbox(HeaderFilePreview, { props: { sample, testid: ID }, locale });
  await settle();
  const part = (name: string) => m.inDoc(`${ID}-${name}`);
  return { ...m, part };
}

describe('HeaderFilePreview: a photo (WHATSAPP_INBOX-F29, F33)', () => {
  it('shows its thumbnail from the address the Hub gives it, named by the file', async () => {
    const s = await setup(PHOTO);
    const image = s.part('image') as HTMLImageElement;
    expect(image.tagName).toBe('IMG');
    expect(image.getAttribute('src')).toBe(PHOTO.url);
    expect(image.getAttribute('alt')).toBe('carta.jpg');
    expect(s.part('video')).toBeNull();
    expect(s.part('document')).toBeNull();
  });

  it('a spinner while it loads, gone once it is shown', async () => {
    const s = await setup(PHOTO);
    expect(s.part('loading')).not.toBeNull();
    expect(s.inDoc(ID)?.querySelector('[aria-busy="true"]')).not.toBeNull();
    s.part('image')!.dispatchEvent(new Event('load'));
    await settle();
    expect(s.part('loading')).toBeNull();
    expect(s.inDoc(ID)?.querySelector('[aria-busy="true"]')).toBeNull();
    expect(s.part('error')).toBeNull();
  });

  it('one that cannot be shown says so, with its kind’s icon in place of the thumbnail', async () => {
    const s = await setup(PHOTO);
    s.part('image')!.dispatchEvent(new Event('error'));
    await settle();
    expect(s.part('image')).toBeNull();
    expect(s.part('loading')).toBeNull();
    expect(s.part('broken')).not.toBeNull();
    expect(s.part('error')?.textContent?.trim()).toBe('The photo could not be shown.');
  });

  it('without an address it says it cannot be shown, and asks nothing', async () => {
    const s = await setup({ ...PHOTO, url: '' });
    expect(s.part('image')).toBeNull();
    expect(s.part('loading')).toBeNull();
    expect(s.part('error')?.textContent?.trim()).toBe('The photo could not be shown.');
  });

  it('another file chosen loads again, without the notice of the one before', async () => {
    const s = await setup(PHOTO);
    s.part('image')!.dispatchEvent(new Event('error'));
    await settle();
    const other = { ...PHOTO, id: 's9', name: 'otono.png', url: PHOTO.url.replace('0123456789abcdef.jpg', 'fedcba9876543210.png') };
    await s.wrapper.setProps({ sample: other });
    await settle();
    expect(s.part('error')).toBeNull();
    expect(s.part('image')?.getAttribute('src')).toBe(other.url);
    expect(s.part('image')?.getAttribute('alt')).toBe('otono.png');
    expect(s.part('loading')).not.toBeNull();
  });
});

describe('HeaderFilePreview: a video (WHATSAPP_INBOX-F29, F33)', () => {
  it('shows its first frame, muted and without playing, with a play sign', async () => {
    const s = await setup(VIDEO);
    const video = s.part('video') as HTMLVideoElement;
    expect(video.tagName).toBe('VIDEO');
    expect(video.getAttribute('src')).toBe(`${VIDEO.url}#t=0.1`);
    expect(video.getAttribute('preload')).toBe('metadata');
    expect(video.muted).toBe(true);
    expect(video.hasAttribute('autoplay')).toBe(false);
    expect(video.getAttribute('aria-label')).toBe('otono.mp4');
    expect(s.part('image')).toBeNull();
    // The spinner holds the play sign's place until the frame is there.
    expect(s.part('loading')).not.toBeNull();
    expect(s.part('play')).toBeNull();
    video.dispatchEvent(new Event('loadeddata'));
    await settle();
    expect(s.part('loading')).toBeNull();
    expect(s.part('play')).not.toBeNull();
  });

  it('one that cannot be shown says so', async () => {
    const s = await setup(VIDEO);
    s.part('video')!.dispatchEvent(new Event('error'));
    await settle();
    expect(s.part('video')).toBeNull();
    expect(s.part('broken')).not.toBeNull();
    expect(s.part('error')?.textContent?.trim()).toBe('The video could not be shown.');
  });
});

// Safari (WebKit, the iPad the Hub runs on) loads no frame of a `preload="metadata"` video until the person taps it, so
// `loadeddata` may never come: the spinner must never turn for ever.
describe('HeaderFilePreview: a video Safari loads no frame of', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('with its metadata alone, the spinner gives way to the play sign', async () => {
    const s = await setup(VIDEO);
    s.part('video')!.dispatchEvent(new Event('loadedmetadata'));
    await settle();
    expect(s.part('loading')).toBeNull();
    expect(s.part('play')).not.toBeNull();
    expect(s.part('video')).not.toBeNull();
    expect(s.part('error')).toBeNull();
  });

  it('saying nothing at all, after a few seconds it is the video with its play sign, never an endless spinner', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const s = await setup(VIDEO);
    expect(s.part('loading')).not.toBeNull();
    await vi.advanceTimersByTimeAsync(5_000);
    await settle();
    expect(s.part('loading')).toBeNull();
    expect(s.part('play')).not.toBeNull();
    expect(s.part('video')).not.toBeNull();
    expect(s.part('error')).toBeNull();
  });
});

describe('HeaderFilePreview: a document (WHATSAPP_INBOX-F29, F33)', () => {
  it('is its icon: no thumbnail, nothing to load, nothing to fail', async () => {
    const s = await setup(DOCUMENT);
    expect(s.part('document')).not.toBeNull();
    expect(s.inDoc(ID)?.querySelector('img, video')).toBeNull();
    expect(s.part('loading')).toBeNull();
    expect(s.part('error')).toBeNull();
  });
});

describe('HeaderFilePreview: in Spanish', () => {
  it('says that the photo or the video could not be shown', async () => {
    const photo = await setup(PHOTO, 'es');
    photo.part('image')!.dispatchEvent(new Event('error'));
    await settle();
    expect(photo.part('error')?.textContent?.trim()).toBe('No se ha podido mostrar la foto.');
    const video = await setup(VIDEO, 'es');
    video.part('video')!.dispatchEvent(new Event('error'));
    await settle();
    expect(video.part('error')?.textContent?.trim()).toBe('No se ha podido mostrar el vídeo.');
  });
});
