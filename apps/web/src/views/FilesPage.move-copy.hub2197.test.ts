// @vitest-environment happy-dom
// hub#2197 — moving a file showed the raw key «files.moveSuccess» in the toast: the screen asked for
// two keys (`moveSuccess`, `moveError`) that no catalogue declared. The screen also handed the
// file manager only part of its labels, so «Move to…», «Rename», «Rename folder», «Delete folder»
// and «No limit» stayed in the component's built-in Spanish for a hub in English. Mounted against
// the REAL catalogues, so a missing key reads as the key path and fails here.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const fetchMedia = vi.fn();
const moveMedia = vi.fn();
vi.mock('../lib/media', async () => ({
  isMediaFailure: (await vi.importActual<typeof import('../lib/media')>('../lib/media')).isMediaFailure,
  mediaFailureSentence: (await vi.importActual<typeof import('../lib/media')>('../lib/media')).mediaFailureSentence,
  fetchMedia: (...a: unknown[]) => fetchMedia(...a),
  moveMedia: (...a: unknown[]) => moveMedia(...a),
  deleteMedia: vi.fn(),
  renameMedia: vi.fn(),
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

import FilesPage from './FilesPage.vue';

// Every label `ok-file-manager` renders (its DEFAULT_LABELS, all in Spanish): each one the screen
// leaves out is shown in Spanish whatever the hub's language.
const MANAGER_LABELS = [
  'upload',
  'import',
  'search',
  'folders',
  'space',
  'empty',
  'download',
  'delete',
  'open',
  'move',
  'newFolder',
  'rename',
  'renameFolder',
  'deleteFolder',
  'noLimit',
];

const FILE = { id: 'facturas/a.pdf', name: 'a.pdf', ext: 'pdf', url: '/api/media/raw?path=facturas/a.pdf' };

async function mountPage(locale: 'en' | 'es'): Promise<VueWrapper> {
  const i18n = createI18n({ legacy: false, locale, messages: { en, es } });
  fetchMedia.mockResolvedValue({ folders: [], files: [FILE], path: [] });
  const wrapper = mount(FilesPage, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
  await flushPromises();
  return wrapper;
}

type Manager = HTMLElement & { labels: Record<string, string> };
const manager = (w: VueWrapper): Manager => w.find('ok-file-manager').element as Manager;
const toastMessage = (w: VueWrapper): string => String(w.findComponent({ name: 'IonToast' }).props('message'));

async function move(w: VueWrapper, to: string): Promise<void> {
  manager(w).dispatchEvent(new CustomEvent('ok-move', { detail: { from: FILE.id, to } }));
  await flushPromises();
}

beforeEach(() => {
  fetchMedia.mockReset();
  moveMedia.mockReset().mockResolvedValue({ ok: true });
});

describe('/files · move toast (hub#2197)', () => {
  it('says where the file went, in English', async () => {
    const w = await mountPage('en');
    await move(w, 'clientes/2026');
    expect(moveMedia).toHaveBeenCalledWith(FILE.id, 'clientes/2026');
    expect(toastMessage(w)).toBe('Moved to “2026”.');
  });

  it('says where the file went, in Spanish', async () => {
    const w = await mountPage('es');
    await move(w, 'clientes');
    expect(toastMessage(w)).toBe('Movido a «clientes».');
  });

  it('names the top level as Files when the file goes back to it', async () => {
    const w = await mountPage('es');
    await move(w, '');
    expect(toastMessage(w)).toBe(`Movido a «${es.files.title}».`);
  });

  it('a refused move reads a sentence, never the key path', async () => {
    moveMedia.mockResolvedValue({ ok: false, status: 0 });
    const w = await mountPage('es');
    await move(w, 'clientes');
    expect(toastMessage(w)).not.toMatch(/files\./);
    expect(toastMessage(w)).toBe(es.files.moveError);
  });
});

describe('/files · file manager labels follow the hub language (hub#2197)', () => {
  it.each(['en', 'es'] as const)('hands the manager every label it renders, in %s', async (locale) => {
    const w = await mountPage(locale);
    const labels = manager(w).labels;
    expect(Object.keys(labels).sort()).toEqual([...MANAGER_LABELS].sort());
    for (const key of MANAGER_LABELS) expect(labels[key], key).not.toMatch(/^files\./);
  });

  it('the English labels are English, not the component defaults', async () => {
    const w = await mountPage('en');
    expect(manager(w).labels.move).toBe('Move to…');
    expect(manager(w).labels.noLimit).toBe('No limit');
  });
});
