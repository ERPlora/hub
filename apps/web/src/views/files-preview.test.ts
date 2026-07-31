// @vitest-environment happy-dom
// Contrato del cableado de `/files` con el visor (ADR-0171): «abrir» un fichero previsualiza
// DENTRO del Hub; «descargar» sigue bajando el fichero. Antes ambas cosas hacían lo mismo
// (descargar y lanzar el blob a una pestaña del navegador), que en Hub Local ni siquiera existe.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchMedia = vi.fn();
vi.mock('../lib/media', () => ({
  fetchMedia: (...a: unknown[]) => fetchMedia(...a),
  uploadMedia: vi.fn(),
  deleteMedia: vi.fn(),
  createMediaFolder: vi.fn(),
  fetchMediaBytes: vi.fn(),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
// HubIcon hornea los SVG vía `~icons/…?raw`, que el entorno de test deniega.
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import FilesPage from './FilesPage.vue';
import FilePreviewModal from '../components/FilePreviewModal.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

const FILE = { id: 'facturas/a.pdf', name: 'a.pdf', ext: 'pdf', url: '/api/media/raw?path=a.pdf' };

async function mountPage(): Promise<VueWrapper> {
  fetchMedia.mockResolvedValue({ folders: [], files: [FILE], path: [] });
  const wrapper = mount(FilesPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
  await flushPromises();
  return wrapper;
}

/** Dispara el evento `ok-*` que emite el web component del gestor de ficheros. */
function emitFromManager(wrapper: VueWrapper, name: string, detail: unknown): void {
  wrapper.find('ok-file-manager').element.dispatchEvent(new CustomEvent(name, { detail }));
}

beforeEach(() => {
  fetchMedia.mockReset();
});

describe('/files + visor', () => {
  it('monta el visor en la pantalla', async () => {
    const wrapper = await mountPage();
    expect(wrapper.findComponent(FilePreviewModal).exists()).toBe(true);
  });

  it('arranca con el visor cerrado y sin fichero', async () => {
    const wrapper = await mountPage();
    expect(wrapper.findComponent(FilePreviewModal).props('open')).toBe(false);
    expect(wrapper.findComponent(FilePreviewModal).props('file')).toBeNull();
  });

  it('«abrir» previsualiza dentro del Hub en vez de irse a una pestaña del navegador', async () => {
    const wrapper = await mountPage();
    const openTab = vi.spyOn(window, 'open').mockReturnValue(null);
    emitFromManager(wrapper, 'ok-open', { id: FILE.id });
    await flushPromises();

    const modal = wrapper.findComponent(FilePreviewModal);
    expect(modal.props('open')).toBe(true);
    expect(modal.props('file')).toMatchObject({ id: FILE.id, name: 'a.pdf' });
    expect(openTab).not.toHaveBeenCalled();
  });

  it('cerrar el visor lo cierra de verdad (y suelta el fichero)', async () => {
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-open', { id: FILE.id });
    await flushPromises();
    await wrapper.findComponent(FilePreviewModal).vm.$emit('close');
    await flushPromises();
    expect(wrapper.findComponent(FilePreviewModal).props('open')).toBe(false);
  });

  it('«descargar» NO abre el visor: baja el fichero', async () => {
    const wrapper = await mountPage();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) }));
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();

    emitFromManager(wrapper, 'ok-download', { id: FILE.id });
    await flushPromises();

    expect(wrapper.findComponent(FilePreviewModal).props('open')).toBe(false);
    expect(click).toHaveBeenCalled();
  });

  it('el botón de descarga del propio visor baja el fichero que se está viendo', async () => {
    const wrapper = await mountPage();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) }));
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();

    emitFromManager(wrapper, 'ok-open', { id: FILE.id });
    await flushPromises();
    await wrapper.findComponent(FilePreviewModal).vm.$emit('download');
    await flushPromises();
    expect(click).toHaveBeenCalled();
  });
});
