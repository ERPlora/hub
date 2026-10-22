// The website editor (`/website`): the site live (`website.site.get`), a form per section with «Show» on the
// optional ones, the four designs and the colours, saved by hand or 2 s after the last change, the real preview
// reloaded after each save, publishing (and taking offline) behind a confirmation, and «Share and QR». Loading,
// error, never published, offline and live each say so; a manager only reads; the 422 lands on its field.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import {
  errorFrame,
  flush,
  ionChecked,
  ionValue,
  MANAGER,
  type MountOptions,
  mountWebsite,
  OWNER,
  settle,
  subId,
} from '../__tests__/mount-website';
import PALETTES from '../../palettes.json';
import { SITE } from '../__tests__/site';
import type { SiteOut } from '../operations';
import GalleryEditor from '../components/GalleryEditor.vue';
import ReviewsEditor from '../components/ReviewsEditor.vue';
import WebsitePage from './WebsitePage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn() }));

vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: mocks.toastSuccess,
  toastError: mocks.toastError,
}));

const IonModalStub = defineComponent({
  name: 'IonModal',
  props: { isOpen: Boolean },
  setup(props, { slots }) {
    return () => h('div', { 'data-stub': 'ion-modal' }, props.isOpen ? slots.default?.() : []);
  },
});

type Control = HTMLElement & { errorText?: string; value?: unknown; checked?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountWebsite(WebsitePage, {
    stubs: { IonModal: IonModalStub },
    api: (call) => {
      if (call.url === '/api/website/site') return Response.json(SITE);
      return Response.json({ published_version: 1, published_at: '2026-10-21T10:00:00Z', is_live: true });
    },
    ...options,
  });
  const call = await m.live();
  const show = (site: SiteOut = SITE, rev = 1) => m.result(call, 'website.site.get', site, rev);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const control = (id: string) => m.wrapper.get(`[data-testid="${id}"]`).element as Control;
  const posts = () => m.net.api.filter((api) => api.init.method === 'POST');
  const body = (index = -1) => JSON.parse(posts().at(index)!.init.body as string);
  return { ...m, call, show, testid, control, posts, body };
}

beforeEach(() => {
  mocks.confirm.mockReset().mockResolvedValue(true);
  mocks.toastSuccess.mockReset();
  mocks.toastError.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('WebsitePage', () => {
  it('follows the site live, with a spinner until the first result', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('website.site.get')).toEqual([{ id: expect.any(String), params: {} }]);
    expect(s.testid('website-loading').exists()).toBe(true);
    await s.show();
    expect(s.testid('website-loading').exists()).toBe(false);
    expect(s.control('website-field-hero-title').value).toBe('Fresh food');
    expect(s.control('website-field-topbar-name').value).toBe('Pepe');
  });

  it('a failed load says so instead of an empty form', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'website.site.get'), 'internal_error'));
    await flush();
    expect(s.testid('website-load-error').exists()).toBe(true);
    expect(s.testid('website-editor').exists()).toBe(false);
  });

  it('without the website’s permission, nothing but the reason', async () => {
    const s = await setup({ session: { ...OWNER, permissions: [] } });
    expect(s.testid('website-forbidden').exists()).toBe(true);
    expect(s.testid('website-loading').exists()).toBe(false);
    expect(s.testid('website-editor').exists()).toBe(false);
  });

  it('never published: invites to publish', async () => {
    const s = await setup();
    await s.show();
    expect(s.testid('website-status-never').exists()).toBe(true);
    expect(s.testid('website-unpublish').exists()).toBe(false);
  });

  it('online: says where, and that the draft has unpublished changes; offline: says so', async () => {
    const s = await setup();
    await s.show({ ...SITE, published_version: 2, is_live: true, has_changes: true });
    expect(s.testid('website-status-live').html()).toContain('https://a.erplora.com/');
    expect(s.testid('website-status-changes').exists()).toBe(true);
    expect(s.testid('website-unpublish').exists()).toBe(true);
    await s.show({ ...SITE, published_version: 2, is_live: false }, 2);
    expect(s.testid('website-status-offline').exists()).toBe(true);
  });

  it('saves the draft by hand and reloads the preview', async () => {
    const s = await setup();
    await s.show();
    const frame = () => s.wrapper.get('[data-testid="website-preview-frame"]').attributes('src');
    const before = frame();
    await ionValue(s.wrapper.get('[data-testid="website-field-hero-title"]').element, 'Brand new', 'ionInput');
    expect(s.testid('website-save-state').text()).toBe('Unsaved changes');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.posts().map((post) => post.url)).toEqual(['/api/website/site']);
    expect(s.body().content.hero.title).toBe('Brand new');
    expect(s.body().content.location.address_lines).toEqual([]);
    expect(s.testid('website-save-state').text()).toBe('All changes saved');
    expect(frame()).not.toBe(before);
  });

  it('saves on its own two seconds after the last change', async () => {
    const s = await setup();
    await s.show();
    // Fake timers only from here: the harness's flush() waits on real ones.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const type = (value: string) => {
      const field = s.wrapper.get('[data-testid="website-field-hero-tagline"]').element as Control;
      field.value = value;
      field.dispatchEvent(new CustomEvent('ionInput', { detail: { value }, bubbles: true }));
    };
    type('Since 1998');
    await vi.advanceTimersByTimeAsync(1500);
    type('Since 1999');
    await vi.advanceTimersByTimeAsync(1500);
    expect(s.posts()).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    await settle();
    expect(s.posts()).toHaveLength(1);
    expect(s.body().content.hero.tagline).toBe('Since 1999');
  });

  it('its own save coming back live never rewrites what is being typed', async () => {
    const s = await setup();
    await s.show();
    await ionValue(s.wrapper.get('[data-testid="website-field-topbar-name"]').element, 'Pepe ', 'ionInput');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    // The server keeps «Pepe» (it trims) and the site comes back live with it: the field keeps the space being typed.
    await s.show({ ...SITE, content: { ...SITE.content, topbar: { name: 'Pepe', logo: null } } }, 2);
    expect(s.control('website-field-topbar-name').value).toBe('Pepe ');
    expect(s.testid('website-save-state').text()).toBe('All changes saved');
    // Someone else's change does come in when nothing is pending here.
    await s.show({ ...SITE, content: { ...SITE.content, hero: { ...SITE.content.hero, title: 'Theirs' } } }, 3);
    expect(s.control('website-field-hero-title').value).toBe('Theirs');
  });

  it('a section opened by hand stays open, with its field and what is typed, while typing and when the save comes back', async () => {
    // Regression (Ioan, 2026-10-22): every keystroke re-rendered the form, Vue set the accordion group's `value` back
    // to the sections open at first, and the one being typed in folded: the field lost the focus and the page jumped.
    const s = await setup();
    await s.show();
    const group = s.wrapper.get('[data-testid="website-sections"]').element as Control;
    expect(group.value).toEqual(['topbar', 'hero']);
    // The owner opens «About us», as Ionic does: the group's value changes and it says so.
    group.value = ['topbar', 'hero', 'about'];
    group.dispatchEvent(new CustomEvent('ionChange', { detail: { value: group.value }, bubbles: true }));
    await settle();
    const field = s.control('website-field-about-title');
    for (const typed of ['W', 'We', 'We c', 'We cook']) {
      await ionValue(field, typed, 'ionInput');
      expect(group.value).toEqual(['topbar', 'hero', 'about']);
    }
    // A change of another control inside the group (its ionChange bubbles) never closes the sections.
    await ionChecked(s.wrapper.get('[data-testid="website-show-contact"]').element, false);
    expect(group.value).toEqual(['topbar', 'hero', 'about']);
    // The save comes back live with the same text: the same field, still holding it, the section still open.
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    await s.show({ ...SITE, content: { ...SITE.content, about: { ...SITE.content.about, title: 'We cook' } } }, 2);
    expect(s.control('website-field-about-title')).toBe(field);
    expect(field.value).toBe('We cook');
    expect(group.value).toEqual(['topbar', 'hero', 'about']);
  });

  it('changing the design keeps every text', async () => {
    const s = await setup();
    await s.show();
    await s.wrapper.get('[data-testid="website-template-bold"]').trigger('click');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().template).toBe('bold');
    expect(s.body().content.hero.title).toBe('Fresh food');
    expect(s.body().content.topbar.name).toBe('Pepe');
  });

  it('hides an optional section with its «Show» switch; the fixed ones have none', async () => {
    const s = await setup();
    await s.show();
    expect(s.testid('website-show-topbar').exists()).toBe(false);
    expect(s.testid('website-show-hero').exists()).toBe(false);
    expect(s.testid('website-show-footer').exists()).toBe(false);
    await ionChecked(s.wrapper.get('[data-testid="website-show-about"]').element, false);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().content.about.hidden).toBe(true);
  });

  it('a palette and the page’s mode go with the draft, «Auto» by default and said what it does', async () => {
    const s = await setup();
    await s.show();
    expect(s.control('website-mode').value).toBe('auto');
    expect(s.testid('website-mode-auto-hint').text()).toContain('device');
    expect(s.wrapper.get('[data-testid="website-palette-ocean"]').attributes('aria-checked')).toBe('true');
    // The palette's own two colours are on show, ready to change.
    expect(s.control('website-colour-primary').value).toBe(PALETTES.ocean.light.primary);
    await s.wrapper.get('[data-testid="website-palette-forest"]').trigger('click');
    await ionValue(s.wrapper.get('[data-testid="website-mode"]').element, 'dark', 'ionChange');
    expect(s.testid('website-mode-auto-hint').exists()).toBe(false);
    // The designs are drawn in the chosen palette.
    expect(s.wrapper.get('[data-testid="website-template-bold"] .wt-thumb').attributes('style')).toContain(
      `--wt-primary: ${PALETTES.forest.light.primary}`,
    );
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().theme).toEqual({ palette: 'forest', custom: null, mode: 'dark' });
    await ionValue(s.wrapper.get('[data-testid="website-mode"]').element, 'auto', 'ionChange');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().theme.mode).toBe('auto');
  });

  it('any palette’s two colours can be changed over it, and «Reset colours» gives its own back', async () => {
    const s = await setup();
    await s.show();
    expect(s.control('website-colour-accent').value).toBe(PALETTES.ocean.accent);
    expect(s.testid('website-colours-reset').exists()).toBe(false);
    await ionValue(s.wrapper.get('[data-testid="website-colour-primary"]').element, '#112233', 'ionInput');
    // The designs are drawn in the owner's colours.
    expect(s.wrapper.get('[data-testid="website-template-bold"] .wt-thumb').attributes('style')).toContain('--wt-primary: #112233');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().theme).toEqual({ palette: 'ocean', custom: { primary: '#112233', accent: PALETTES.ocean.accent }, mode: 'auto' });
    // «Reset colours»: the palette's own pair again, stored as none.
    await s.wrapper.get('[data-testid="website-colours-reset"]').trigger('click');
    expect(s.control('website-colour-primary').value).toBe(PALETTES.ocean.light.primary);
    expect(s.testid('website-colours-reset').exists()).toBe(false);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().theme).toEqual({ palette: 'ocean', custom: null, mode: 'auto' });
    // Another palette after a change: its own colours, not the owner's of the one before.
    await ionValue(s.wrapper.get('[data-testid="website-colour-accent"]').element, '#445566', 'ionInput');
    await s.wrapper.get('[data-testid="website-palette-sand"]').trigger('click');
    expect(s.control('website-colour-primary').value).toBe(PALETTES.sand.light.primary);
    expect(s.control('website-colour-accent').value).toBe(PALETTES.sand.accent);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().theme).toEqual({ palette: 'sand', custom: null, mode: 'auto' });
  });

  it('a site with the owner’s colours opens with them on show and «Reset colours»', async () => {
    const s = await setup();
    await s.show({ ...SITE, theme: { palette: 'rose', custom: { primary: '#112233', accent: '#445566' }, mode: 'light' } });
    expect(s.wrapper.get('[data-testid="website-palette-rose"]').attributes('aria-checked')).toBe('true');
    expect(s.control('website-colour-primary').value).toBe('#112233');
    expect(s.control('website-colour-accent').value).toBe('#445566');
    expect(s.testid('website-colours-reset').exists()).toBe(true);
  });

  it('offers as the catalog only the sources this business has on', async () => {
    const s = await setup();
    await s.show();
    const options = s.wrapper.findAll('[data-testid="website-catalog-source"] ion-select-option');
    expect(options.map((option) => (option.element as Control).value)).toEqual(['', 'service']);
  });

  // flow: WEBSITE-F05 — a catalog saved from an app that is now off says so, and asks that app nothing.
  it('a catalog saved from an app that is off says the page shows no catalog, and asks it for no categories', async () => {
    const s = await setup();
    await s.show({ ...SITE, content: { ...SITE.content, catalog: { ...SITE.content.catalog, source: 'inventory' } } });
    const options = s.wrapper.findAll('[data-testid="website-catalog-source"] ion-select-option');
    expect(options.map((option) => (option.element as Control).value)).toEqual(['', 'service', 'inventory']);
    expect((options.at(-1)!.element as Control & { disabled?: boolean }).disabled).toBe(true);
    expect(s.testid('website-catalog-source-off').text()).toBe(
      'Inventory is not on in this business: your page shows no catalog until you turn it on or choose another source.',
    );
    expect(s.wrapper.findComponent({ name: 'CategoryPicker' }).exists()).toBe(false);
    expect(s.net.api.some((api) => api.url.startsWith('/api/website/catalog/categories'))).toBe(false);
  });

  it('turning the opening hours on starts from a usual week', async () => {
    const s = await setup();
    await s.show();
    await ionChecked(s.wrapper.get('[data-testid="website-show-hours"]').element, true);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().content.contact.hours).toHaveLength(7);
  });

  it('a refused save leaves its message on the field and keeps what was typed', async () => {
    const s = await setup({
      api: () =>
        Response.json(
          { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { 'content.location.map_url': 'Enter a link that starts with https://.' } } },
          { status: 422 },
        ),
    });
    await s.show();
    await ionValue(s.wrapper.get('[data-testid="website-field-location-map_url"]').element, 'http://x', 'ionInput');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.control('website-field-location-map_url').errorText).toBe('Enter a link that starts with https://.');
    expect(s.testid('website-save-error').exists()).toBe(true);
    expect(s.control('website-field-location-map_url').value).toBe('http://x');
  });

  it('the gallery takes its photos through the uploads, in their order, and can hide', async () => {
    const s = await setup();
    await s.show();
    expect(s.testid('website-section-gallery').exists()).toBe(true);
    const gallery = s.wrapper.findComponent(GalleryEditor);
    expect(gallery.props('modelValue')).toEqual([]);
    const photos = [
      { id: 'p2', url: '/p/media/a/website/img/p2.jpg' },
      { id: 'p1', url: '/p/media/a/website/img/p1.jpg' },
    ];
    gallery.vm.$emit('update:modelValue', photos);
    await ionChecked(s.wrapper.get('[data-testid="website-show-gallery"]').element, false);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().content.gallery).toEqual({ hidden: true, title: '', images: photos });
  });

  it('a photo of the gallery the server refuses says so under the gallery', async () => {
    const message = 'This image was not uploaded to this business’s website: upload it again.';
    const s = await setup({
      api: () =>
        Response.json(
          { error: { code: 'invalid_payload', message, fields: { 'content.gallery.images.1': message } } },
          { status: 422 },
        ),
    });
    await s.show();
    const photos = [
      { id: 'p1', url: '/p/media/a/website/img/p1.jpg' },
      { id: 'x9', url: '/p/media/b/website/img/x9.jpg' },
    ];
    s.wrapper.findComponent(GalleryEditor).vm.$emit('update:modelValue', photos);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.wrapper.findComponent(GalleryEditor).props('error')).toBe(message);
    expect(s.wrapper.findComponent(GalleryEditor).props('modelValue')).toEqual(photos);
  });

  it('the Google reviews take the business’s link on Google Maps and say whether its reviews are there', async () => {
    const s = await setup();
    const ready = { state: 'ready' as const, rating: 4.7, count: 128, fetched_at: '2026-10-22T09:00:00Z' };
    await s.show({ ...SITE, reviews: ready });
    expect(s.testid('website-section-reviews').exists()).toBe(true);
    const reviews = s.wrapper.findComponent(ReviewsEditor);
    expect(reviews.props('status')).toEqual(ready);
    expect(reviews.props('changed')).toBe(false);
    const link = 'https://maps.app.goo.gl/AbCdEf123';
    await ionValue(s.wrapper.get('[data-testid="website-field-reviews-place_ref"]').element, link, 'ionInput');
    // Not saved yet: Google is asked once it is.
    expect(s.wrapper.findComponent(ReviewsEditor).props('changed')).toBe(true);
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.body().content.reviews).toEqual({ hidden: false, title: '', place_ref: link });
    expect(s.wrapper.findComponent(ReviewsEditor).props('changed')).toBe(false);
  });

  it('a link the server refuses says why on the field', async () => {
    const message = 'Paste the link of your business on Google Maps, or its Place ID.';
    const s = await setup({
      api: () =>
        Response.json(
          { error: { code: 'invalid_payload', message, fields: { 'content.reviews.place_ref': message } } },
          { status: 422 },
        ),
    });
    await s.show();
    await ionValue(s.wrapper.get('[data-testid="website-field-reviews-place_ref"]').element, 'Peluquería Manoli', 'ionInput');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    expect(s.wrapper.findComponent(ReviewsEditor).props('error')).toBe(message);
  });

  it('publishes after a confirmation, saving first what is unsaved', async () => {
    const s = await setup();
    await s.show();
    await ionValue(s.wrapper.get('[data-testid="website-field-hero-title"]').element, 'Opening day', 'ionInput');
    await s.wrapper.get('[data-testid="website-publish"]').trigger('click');
    await settle();
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Publish your website?' }));
    expect(s.posts().map((post) => post.url)).toEqual(['/api/website/site', '/api/website/site/publish']);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Your website is online');
  });

  it('nothing is published when the confirmation is declined', async () => {
    mocks.confirm.mockResolvedValue(false);
    const s = await setup();
    await s.show();
    await s.wrapper.get('[data-testid="website-publish"]').trigger('click');
    await settle();
    expect(s.posts()).toHaveLength(0);
  });

  it('takes the site offline after a confirmation', async () => {
    const s = await setup();
    await s.show({ ...SITE, published_version: 1, is_live: true });
    await s.wrapper.get('[data-testid="website-unpublish"]').trigger('click');
    await settle();
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Take your website offline?', tone: 'warning' }));
    expect(s.posts().map((post) => post.url)).toEqual(['/api/website/site/unpublish']);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Your website is offline');
  });

  it('a failed publication says why', async () => {
    const s = await setup({ api: () => Response.json({ error: { code: 'internal_error', message: 'Internal error' } }, { status: 500 }) });
    await s.show();
    await s.wrapper.get('[data-testid="website-publish"]').trigger('click');
    await settle();
    expect(mocks.toastError).toHaveBeenCalledWith('The website could not be published');
  });

  // flow: WEBSITE-F09
  it('opens «Share and QR» with the public address', async () => {
    const s = await setup();
    await s.show();
    // One hook per control: the button and its dialog are told apart (the e2e clicks the button by it).
    expect(s.wrapper.findAll('[data-testid="website-share"]')).toHaveLength(1);
    await s.wrapper.get('[data-testid="website-share"]').trigger('click');
    await settle();
    expect(s.testid('website-share-url').text()).toBe('https://a.erplora.com/');
  });

  it('switches between editing and the preview on a phone or a tablet', async () => {
    const s = await setup();
    await s.show();
    expect(s.wrapper.get('.we-grid').classes()).toContain('we-grid--edit');
    await ionValue(s.wrapper.get('[data-testid="website-view"]').element, 'preview', 'ionChange');
    expect(s.wrapper.get('.we-grid').classes()).toContain('we-grid--preview');
  });

  it('a manager sees the status and can share, but changes nothing', async () => {
    const s = await setup({ session: MANAGER });
    await s.show({ ...SITE, published_version: 1, is_live: true });
    expect(s.testid('website-status-live').exists()).toBe(true);
    expect(s.testid('website-read-only').exists()).toBe(true);
    expect(s.testid('website-editor').exists()).toBe(false);
    expect(s.testid('website-publish').exists()).toBe(false);
    expect(s.testid('website-share').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show();
    expect(s.testid('website-status-never').html()).toContain('Publícala');
    expect(s.wrapper.get('[data-testid="website-publish"]').text()).toContain('Publicar');
  });
});
