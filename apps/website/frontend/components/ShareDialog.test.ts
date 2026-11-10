// ShareDialog: the website's address to copy, its QR to download (PNG to print, SVG to scale) and, honestly, why
// the address opens the app on the owner's own device.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountWebsite, settle } from '../__tests__/mount-website';
import ShareDialog from './ShareDialog.vue';

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: toasts.success,
  toastError: toasts.error,
}));

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

/** The hub's answer to the QR's address, as `website.qr.get` serves it: the image, as an attachment with its name. */
function servesTheQr(): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(async (url: string) => {
    const format = new globalThis.URL(url, 'https://pepe.erplora.com').searchParams.get('format');
    const type = format === 'png' ? 'image/png' : 'image/svg+xml';
    return new Response(format === 'png' ? new Uint8Array([0x89, 0x50]) : '<svg/>', {
      headers: { 'Content-Type': type, 'Content-Disposition': `attachment; filename="website-qr-pepe.${format}"` },
    });
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

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

async function dialog(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountWebsite(ShareDialog, { props: { open: true, url: URL, isLive: true, ...props }, locale, stubs: { IonModal: IonModalStub } });
}

afterEach(() => {
  delete (window as TauriWindow).__TAURI__;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  toasts.success.mockReset();
  toasts.error.mockReset();
});

describe('ShareDialog', () => {
  it('shows the address, the QR and its two downloads', async () => {
    const { wrapper } = await dialog();
    expect(wrapper.get('[data-testid="website-share-url"]').text()).toBe(URL);
    const qr = wrapper.get('[data-testid="website-share-qr"]');
    expect(qr.attributes('src')).toBe('/api/website/qr?format=svg');
    expect(qr.attributes('alt')).toBe('QR code of your website');
    expect(wrapper.get('[data-testid="website-share-png"]').text()).toBe('Download PNG');
    expect(wrapper.get('[data-testid="website-share-svg"]').text()).toBe('Download SVG');
    expect(wrapper.get('[data-testid="website-share-signed-in"]').text()).toContain('private window');
    expect(wrapper.find('[data-testid="website-share-not-live"]').exists()).toBe(false);
  });

  it('each download brings the QR with the session and hands it to the browser under its name', async () => {
    const fetch = servesTheQr();
    const saved: { name: string; type: string }[] = [];
    const blobs: Blob[] = [];
    vi.spyOn(globalThis.URL, 'createObjectURL').mockImplementation((blob) => {
      blobs.push(blob as Blob);
      return `blob:qr/${blobs.length}`;
    });
    vi.spyOn(globalThis.URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      saved.push({ name: this.download, type: blobs[blobs.length - 1].type });
    });
    const { wrapper } = await dialog();
    await wrapper.get('[data-testid="website-share-png"]').trigger('click');
    await settle();
    await wrapper.get('[data-testid="website-share-svg"]').trigger('click');
    await settle();
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/website/qr?format=png', '/api/website/qr?format=svg']);
    expect(saved).toEqual([
      { name: 'website-qr-pepe.png', type: 'image/png' },
      { name: 'website-qr-pepe.svg', type: 'image/svg+xml' },
    ]);
    expect(toasts.error).not.toHaveBeenCalled();
  });

  it('inside the installed app the QR goes to the app’s Downloads, which says where (hub#1041)', async () => {
    servesTheQr();
    const invoke = vi.fn(async () => ({ path: 'Download/website-qr-pepe.png' }));
    (window as TauriWindow).__TAURI__ = { core: { invoke } };
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const { wrapper } = await dialog();
    await wrapper.get('[data-testid="website-share-png"]').trigger('click');
    await settle();
    expect(invoke).toHaveBeenCalledWith('save_download', { name: 'website-qr-pepe.png', dataBase64: btoa('\x89\x50') });
    expect(click).not.toHaveBeenCalled();
    expect(toasts.success).toHaveBeenCalledWith('Saved to Download/website-qr-pepe.png');
  });

  it('a QR that does not come is said, never a press that does nothing', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    const { wrapper } = await dialog({}, 'es');
    await wrapper.get('[data-testid="website-share-svg"]').trigger('click');
    await settle();
    expect(toasts.error).toHaveBeenCalledWith('No se ha podido descargar el archivo.');
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
