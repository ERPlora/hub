// @vitest-environment happy-dom
// Contrato de renombrar/borrar en `/files` (ADR-0166): la pantalla obedece la política que le
// manda el runtime y distingue borrar un fichero de borrar una carpeta (que se lleva su contenido
// y deja al usuario sin carpeta donde está).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchMedia = vi.fn();
const deleteMedia = vi.fn();
const renameMedia = vi.fn();
vi.mock('../lib/media', () => ({
  fetchMedia: (...a: unknown[]) => fetchMedia(...a),
  deleteMedia: (...a: unknown[]) => deleteMedia(...a),
  renameMedia: (...a: unknown[]) => renameMedia(...a),
  uploadMedia: vi.fn(),
  createMediaFolder: vi.fn(),
  fetchMediaBytes: vi.fn(),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

// Los diálogos de Ionic se sustituyen por un doble que confirma y devuelve el nombre tecleado.
const dialog = { role: 'confirm', data: { values: { name: 'nuevo' } } };
vi.mock('@ionic/vue', async (original) => {
  const actual = (await original()) as Record<string, unknown>;
  return {
    ...actual,
    alertController: {
      create: () =>
        Promise.resolve({ present: () => Promise.resolve(), onDidDismiss: () => Promise.resolve(dialog) }),
    },
  };
});

import FilesPage from './FilesPage.vue';

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } });

const FILE = { id: 'facturas/a.pdf', name: 'a.pdf', ext: 'pdf', url: '/api/media/raw?path=facturas/a.pdf' };

async function mountPage(policy?: Record<string, boolean>): Promise<VueWrapper> {
  fetchMedia.mockResolvedValue({ folders: [], files: [FILE], path: [], policy });
  const wrapper = mount(FilesPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
  await flushPromises();
  return wrapper;
}

function manager(wrapper: VueWrapper): HTMLElement & { policy?: unknown } {
  return wrapper.find('ok-file-manager').element as HTMLElement & { policy?: unknown };
}

function emitFromManager(wrapper: VueWrapper, name: string, detail: unknown): void {
  manager(wrapper).dispatchEvent(new CustomEvent(name, { detail }));
}

beforeEach(() => {
  fetchMedia.mockReset();
  deleteMedia.mockReset().mockResolvedValue(true);
  renameMedia.mockReset().mockResolvedValue(true);
  dialog.role = 'confirm';
  dialog.data = { values: { name: 'nuevo' } };
});

describe('/files · política del runtime', () => {
  it('traslada al gestor lo que el runtime dice que se puede hacer aquí', async () => {
    const wrapper = await mountPage({ upload: false, rename: false, delete: false });
    expect(manager(wrapper).policy).toEqual({ upload: false, rename: false, delete: false });
  });

  it('sin política en la respuesta no inventa restricciones', async () => {
    const wrapper = await mountPage(undefined);
    expect(manager(wrapper).policy).toBeUndefined();
  });
});

describe('/files · renombrar', () => {
  it('renombra un fichero con el nombre que teclea el usuario', async () => {
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-rename', { id: FILE.id, name: 'a.pdf', kind: 'file' });
    await flushPromises();
    expect(renameMedia).toHaveBeenCalledWith(FILE.id, 'nuevo');
  });

  it('cancelar el diálogo no renombra nada', async () => {
    dialog.role = 'cancel';
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-rename', { id: FILE.id, name: 'a.pdf', kind: 'file' });
    await flushPromises();
    expect(renameMedia).not.toHaveBeenCalled();
  });

  it('un nombre vacío no llega al runtime', async () => {
    dialog.data = { values: { name: '   ' } };
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-rename', { id: FILE.id, name: 'a.pdf', kind: 'file' });
    await flushPromises();
    expect(renameMedia).not.toHaveBeenCalled();
  });

  it('tras renombrar una carpeta navega a su nuevo nombre, no a una ruta que ya no existe', async () => {
    // El gestor solo deja renombrar la carpeta en la que estás, así que primero se entra en ella.
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-navigate', { id: 'facturas' });
    await flushPromises();
    fetchMedia.mockClear();
    emitFromManager(wrapper, 'ok-rename', { id: 'facturas', name: 'facturas', kind: 'folder' });
    await flushPromises();
    expect(renameMedia).toHaveBeenCalledWith('facturas', 'nuevo');
    expect(fetchMedia).toHaveBeenLastCalledWith('nuevo');
  });
});

describe('/files · borrar', () => {
  it('borra un fichero y se queda donde está', async () => {
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-navigate', { id: 'facturas' });
    await flushPromises();
    fetchMedia.mockClear();

    emitFromManager(wrapper, 'ok-delete', { id: FILE.id, kind: 'file' });
    await flushPromises();

    expect(deleteMedia).toHaveBeenCalledWith(FILE.id);
    expect(fetchMedia).toHaveBeenLastCalledWith('facturas');
  });

  it('al borrar la carpeta actual sube a la de arriba, en vez de quedarse en una que ya no existe', async () => {
    const wrapper = await mountPage();
    emitFromManager(wrapper, 'ok-navigate', { id: 'facturas/2026' });
    await flushPromises();
    fetchMedia.mockClear();

    emitFromManager(wrapper, 'ok-delete', { id: 'facturas/2026', kind: 'folder' });
    await flushPromises();

    expect(deleteMedia).toHaveBeenCalledWith('facturas/2026');
    expect(fetchMedia).toHaveBeenLastCalledWith('facturas');
  });
});
