// ShareDialog: the website's address to copy, its QR to download (PNG to print, SVG to scale) and, honestly, why
// the address opens the app on the owner's own device.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountWebsite, settle } from '../__tests__/mount-website';
import ShareDialog from './ShareDialog.vue';

const toasts = vi.hoisted(() => ({ success: vi.fn() }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: toasts.success,
}));

/** Ionic's modal presents itself only in a real browser: the stub renders its content while open. */
const IonModalStub = defineComponent({
  name: 'IonModal',
  props: { isOpen: Boolean },
  emits: ['didDismiss'],
  setup(props, { slots, emit }) {
    return () => h('div', { 'data-stub': 'ion-modal', onClose: () => emit('didDismiss') }, props.isOpen ? slots.default?.() : []);
  },
});

const URL = 'https://pepe.erplora.com/';

async function dialog(props: Record<string, unknown> = {}) {
  return mountWebsite(ShareDialog, { props: { open: true, url: URL, isLive: true, ...props }, stubs: { IonModal: IonModalStub } });
}

afterEach(() => {
  vi.restoreAllMocks();
  toasts.success.mockReset();
});

describe('ShareDialog', () => {
  it('shows the address, the QR and its two downloads', async () => {
    const { wrapper } = await dialog();
    expect(wrapper.get('[data-testid="website-share-url"]').text()).toBe(URL);
    const qr = wrapper.get('[data-testid="website-share-qr"]');
    expect(qr.attributes('src')).toBe('/api/website/qr?format=svg');
    expect(qr.attributes('alt')).toBe('QR code of your website');
    // ion-button takes href and download as properties (it renders the <a> in its shadow root).
    const link = (testid: string) => wrapper.get(`[data-testid="${testid}"]`).element as HTMLElement & { href?: string; download?: string };
    expect([link('website-share-png').href, link('website-share-png').download]).toEqual(['/api/website/qr?format=png', 'website-qr.png']);
    expect([link('website-share-svg').href, link('website-share-svg').download]).toEqual(['/api/website/qr?format=svg', 'website-qr.svg']);
    expect(wrapper.get('[data-testid="website-share-signed-in"]').text()).toContain('private window');
    expect(wrapper.find('[data-testid="website-share-not-live"]').exists()).toBe(false);
  });

  it('warns that the address opens the sign-in while the site is not online', async () => {
    const { wrapper } = await dialog({ isLive: false });
    expect(wrapper.get('[data-testid="website-share-not-live"]').text()).toContain('sign-in page');
  });

  it('copies the address and says so; when the browser refuses, says how to do it by hand', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const { wrapper } = await dialog();
    await wrapper.get('[data-testid="website-share-copy"]').trigger('click');
    await settle();
    expect(writeText).toHaveBeenCalledWith(URL);
    expect(toasts.success).toHaveBeenCalledWith('Link copied');
    writeText.mockRejectedValueOnce(new Error('denied'));
    await wrapper.get('[data-testid="website-share-copy"]').trigger('click');
    await settle();
    expect(wrapper.get('[data-testid="website-share-copy-error"]').text()).toContain('copy it by hand');
  });

  it('closing it tells the page', async () => {
    const { wrapper } = await dialog();
    await wrapper.get('[data-testid="website-share-close"]').trigger('click');
    expect(wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('closed, it shows nothing', async () => {
    const { wrapper } = await dialog({ open: false });
    expect(wrapper.find('[data-testid="website-share-url"]').exists()).toBe(false);
  });
});
