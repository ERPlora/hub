// Files (APP-BASE-8; the old hub's FilesPage, HUB_SHELL-F130…F134): the business's files, live (`base.file.list`).
// The tree of folders on the left (a selector on a narrow screen), the open folder's path, its folders and files in a
// grid or a list, «Space», «Search files…» in the open folder; upload (also by dropping files), «New folder»,
// «Rename», «Move to…» (also by dragging onto a folder), «Delete» with its confirmation, «Open» (the preview) and
// «Download». Who does not run the business only sees and opens. Every refusal reads its own sentence (hub#1776) and
// every notice is a sentence, never a key (hub#2197). A listing that could not be read says why, with «Retry».
import { fetchFile } from '@erplora/ui/sdk';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, OWNER, subId } from '../__tests__/mount-base';
import type { FileItem, FilesListing } from '../operations';
import FilesPage from './FilesPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), saveFile: vi.fn(), syncSearchbarInputName: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
  syncSearchbarInputName: mocks.syncSearchbarInputName,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/sdk')>()),
  fetchFile: vi.fn(),
}));
vi.mock('../lib/data', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/data')>()),
  saveFile: mocks.saveFile,
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub, IonPopover: IonModalStub };
});

const OP = 'base.file.list';
const ADMIN = { ...OWNER, permissions: [...OWNER.permissions, 'base.view_files', 'base.upload_files', 'base.delete_files'] };
const STAFF = { ...EMPLOYEE, permissions: [...EMPLOYEE.permissions, 'base.view_files'] };

function file(path: string, over: Partial<FileItem> = {}): FileItem {
  const name = path.slice(path.lastIndexOf('/') + 1);
  return {
    path,
    name,
    size: 2048,
    modified: '2026-10-24T08:00:00Z',
    content_type: 'application/pdf',
    preview: 'pdf',
    ...over,
  };
}

function listing(over: Partial<FilesListing> = {}): FilesListing {
  return {
    folder: '',
    crumbs: [],
    folders: [
      { path: 'Contratos', name: 'Contratos', children: [] },
      { path: 'Facturas', name: 'Facturas', children: [{ path: 'Facturas/2026', name: '2026', children: [] }] },
    ],
    files: [file('marzo.pdf'), file('foto.png', { content_type: 'image/png', preview: 'image', size: 300 })],
    space: { used_bytes: 1536 * 1024, limit_bytes: null },
    can: { upload: true, delete: true },
    ...over,
  };
}

async function open(options: Parameters<typeof mountBase>[1] = {}, data: FilesListing | null = listing()) {
  const m = await mountBase(FilesPage, {
    path: '/files',
    routes: ['/files'],
    session: ADMIN,
    stubs: { FilePreview: true },
    ...options,
  });
  const call = await m.live();
  if (data) await m.result(call, OP, data);
  return { ...m, call };
}

/** What the fake API answers: the body with its status. */
const reply = (status: number, body: unknown) => Response.json(body, { status });
/** The JSON body of an API call. */
const sent = (call: { init: RequestInit }) => JSON.parse(String(call.init.body)) as Record<string, unknown>;

const inDoc = (selector: string) => document.querySelector<HTMLElement>(selector);
const byTestid = (testid: string) => inDoc(`[data-testid="${testid}"]`);
const posted = (m: Awaited<ReturnType<typeof open>>) =>
  m.net.api.map((c) => [c.url, JSON.parse(String(c.init.body ?? '{}')) as Record<string, unknown>]);
const params = (m: Awaited<ReturnType<typeof open>>) => m.client.stream.subscriptions(OP).map((sub) => sub.params);

async function input(testid: string, value: string) {
  const field = byTestid(testid) as HTMLElement & { value?: string };
  field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
  await flush();
}

async function menu(m: Awaited<ReturnType<typeof open>>, path: string | null, action: string) {
  // `null`: the open folder's own menu, beside its path.
  const button = path === null ? '[data-testid="files-folder-actions"]' : `[data-item="${path}"] [data-testid="files-item-actions"]`;
  await m.wrapper.find(button).trigger('click');
  await flush();
  byTestid(`files-action-${action}`)?.click();
  await flush();
}

beforeEach(() => {
  mocks.confirm.mockReset();
  mocks.saveFile.mockReset();
  vi.mocked(fetchFile).mockReset();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('FilesPage · see (BASE-G82)', () => {
  it('follows the root live, loading meanwhile', async () => {
    const m = await open({}, null);
    expect(params(m)).toEqual([{ folder: '' }]);
    expect(m.wrapper.find('[data-testid="files-loading"]').text()).toContain('Loading files');
  });

  it('paints the tree, the open folder’s folders and files, and the space used', async () => {
    const m = await open();
    expect(m.wrapper.findAll('[data-testid="files-tree"] [data-folder]').map((n) => n.text())).toEqual([
      'Contratos',
      'Facturas',
      '2026',
    ]);
    expect(m.wrapper.findAll('[data-item]').map((n) => n.attributes('data-item'))).toEqual([
      'Contratos',
      'Facturas',
      'marzo.pdf',
      'foto.png',
    ]);
    expect(m.wrapper.find('[data-testid="files-space"]').text()).toBe('Space: 1.5 MB used · No limit');
  });

  it('with the plan’s space, how much of it is used: one line and a bar at the exact share', async () => {
    // 600 KB of 1 MB: a bar in rounded GB would read «0 GB of 0 GB · 0 %».
    const m = await open({}, listing({ space: { used_bytes: 600 * 1024, limit_bytes: 1024 ** 2 } }));
    const space = m.wrapper.find('[data-testid="files-space"]');
    expect(space.find('.usage-meter__label').text()).toBe('Space: 600 KB of 1 MB');
    expect(space.find('.usage-meter__value').exists()).toBe(false);
    expect(space.find('.usage-meter__percent').text()).toBe('59%');
    expect(space.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('59');
    expect(m.wrapper.text()).not.toContain('GB');
  });

  it('opens a folder from the tree, the list or the path, and the address says which', async () => {
    const m = await open();
    await m.wrapper.find('[data-testid="files-tree"] [data-folder="Facturas/2026"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.query.folder).toBe('Facturas/2026');
    expect(params(m)).toEqual([{ folder: 'Facturas/2026' }]);
    await m.result(m.call, OP, listing({ folder: 'Facturas/2026', crumbs: [
      { path: 'Facturas', name: 'Facturas' },
      { path: 'Facturas/2026', name: '2026' },
    ], files: [] }));
    expect(m.wrapper.findAll('[data-crumb]').map((c) => c.text())).toEqual(['Files', 'Facturas', '2026']);
    await m.wrapper.find('[data-crumb=""]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.query.folder).toBeUndefined();
  });

  it('while another folder loads, «Loading files…» shows: never the files of the folder before', async () => {
    const m = await open();
    expect(m.wrapper.find('[data-item="marzo.pdf"]').exists()).toBe(true);
    await m.wrapper.find('[data-testid="files-tree"] [data-folder="Contratos"]').trigger('click');
    await flush();
    expect(m.wrapper.find('[data-testid="files-loading"]').text()).toContain('Loading files');
    expect(m.wrapper.find('[data-item="marzo.pdf"]').exists()).toBe(false);
    await m.result(m.call, OP, listing({ folder: 'Contratos', crumbs: [{ path: 'Contratos', name: 'Contratos' }], files: [file('Contratos/nda.pdf')] }));
    expect(m.wrapper.find('[data-testid="files-loading"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-item="Contratos/nda.pdf"]').exists()).toBe(true);
  });

  it('a folder in the list opens with a tap', async () => {
    const m = await open();
    await m.wrapper.find('[data-item="Facturas"] [data-testid="files-item-main"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.query.folder).toBe('Facturas');
  });

  it('on a narrow screen the tree folds into a selector with every folder', async () => {
    const m = await open();
    const options = m.wrapper.findAll('[data-testid="files-folder-select"] ion-select-option');
    expect(options.map((o) => (o.element as HTMLElement & { value: string }).value)).toEqual([
      '',
      'Contratos',
      'Facturas',
      'Facturas/2026',
    ]);
  });

  it('the selector shows the open folder by its name, never with the indentation of the tree', async () => {
    const m = await open(
      { path: '/files?folder=Facturas%2F2026' },
      listing({ folder: 'Facturas/2026', crumbs: [{ path: 'Facturas', name: 'Facturas' }, { path: 'Facturas/2026', name: '2026' }] }),
    );
    const select = m.wrapper.find('[data-testid="files-folder-select"] ion-select').element as HTMLElement & {
      selectedText?: string;
    };
    expect(select.selectedText ?? select.getAttribute('selected-text')).toBe('2026');
  });

  it('searches only the open folder, and says when nothing matches', async () => {
    const m = await open();
    await input('files-search', 'MARZ');
    expect(m.wrapper.findAll('[data-item]').map((n) => n.attributes('data-item'))).toEqual(['marzo.pdf']);
    await input('files-search', 'abril');
    expect(m.wrapper.find('[data-testid="files-no-match"]').text()).toContain('No file in this folder matches “abril”');
  });

  it('switches between grid and list, the list with each file’s size and date', async () => {
    const m = await open();
    expect(m.wrapper.find('[data-testid="files-items"]').classes()).toContain('files-grid');
    await m.wrapper.find('[data-testid="files-view-list"]').trigger('click');
    expect(m.wrapper.find('[data-testid="files-items"]').classes()).toContain('files-list');
    expect(m.wrapper.find('[data-item="marzo.pdf"]').text()).toContain('2 KB');
    expect(m.wrapper.find('[data-testid="files-view-list"]').attributes('aria-pressed')).toBe('true');
  });

  it('a name is cut in what it says, never in its extension; the whole name is its title', async () => {
    const long = 'supplier price list for the second quarter.csv';
    const m = await open({}, listing({ files: [file(long, { content_type: 'text/plain', preview: 'table' })] }));
    await m.wrapper.find('[data-testid="files-view-list"]').trigger('click');
    const name = m.wrapper.find(`[data-item="${long}"] .files-item-name`);
    expect(name.attributes('title')).toBe(long);
    expect(name.find('.files-item-stem').text()).toBe('supplier price list for the second quarter');
    expect(name.find('.files-item-ext').text()).toBe('.csv');
    expect(name.text()).toBe(long);
    // The size and the date go with the name in one block: beside it on a wide screen, under it on a phone.
    expect(m.wrapper.find(`[data-item="${long}"] .files-item-text .files-item-meta`).exists()).toBe(true);
    const folder = m.wrapper.find('[data-item="Facturas"] .files-item-name');
    expect(folder.find('.files-item-ext').exists()).toBe(false);
    expect(folder.text()).toBe('Facturas');
  });

  it('an empty folder says «No files», and who runs the business is told how to add some', async () => {
    const m = await open({}, listing({ folders: [], files: [] }));
    expect(m.wrapper.find('[data-testid="files-empty"]').text()).toContain('No files');
    expect(m.wrapper.find('[data-testid="files-empty"]').text()).toContain('Upload a file or drag it here.');
  });

  it('a listing that could not be read says why, never «check the connection» for all (hub#1776), with «Retry»', async () => {
    const m = await open({}, null);
    m.call.push(errorFrame(subId(m.client, OP), 'base.file_store_unavailable'));
    await flush();
    const error = m.wrapper.find('[data-testid="files-error"]');
    expect(error.text()).toContain('The files could not be loaded');
    expect(error.text()).toContain('The file store did not answer. Try again in a moment.');
    expect(m.wrapper.find('[data-testid="files-retry"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-item]').exists()).toBe(false);
  });

  it('a folder that is not there any more says so', async () => {
    const m = await open({ path: '/files?folder=Nadie' }, null);
    m.call.push(errorFrame(subId(m.client, OP), 'base.file_folder_missing'));
    await flush();
    expect(m.wrapper.find('[data-testid="files-error"]').text()).toContain('That folder no longer exists.');
  });

  it('in Spanish', async () => {
    const m = await open({ locale: 'es' });
    expect(m.wrapper.find('[data-testid="files-space"]').text()).toBe('Espacio: 1,5 MB usados · Sin límite');
    expect(m.wrapper.find('[data-testid="files-folders-label"]').text()).toBe('Carpetas');
  });

  it('the search box is named by its hint in the person’s language, never Ionic’s English «search text» (BASE-G152)', async () => {
    mocks.syncSearchbarInputName.mockClear();
    await open({ locale: 'es' });
    const search = byTestid('files-search');
    const calls = mocks.syncSearchbarInputName.mock.calls as unknown as [ParentNode, () => string][];
    // The shared helper names the first ion-searchbar under the root it gets: that one has to be Files' box.
    expect(calls.map(([root, name]) => [root.querySelector('ion-searchbar'), name()])).toContainEqual([search, 'Buscar archivos…']);
  });
});

describe('FilesPage · upload and new folder (BASE-G83)', () => {
  function choose(m: Awaited<ReturnType<typeof open>>, files: File[]) {
    const element = m.wrapper.find('[data-testid="files-upload-input"]').element as HTMLInputElement;
    Object.defineProperty(element, 'files', { value: files, configurable: true });
    element.dispatchEvent(new Event('change'));
  }

  it('uploads each chosen file into the open folder, in base64, and says so', async () => {
    const m = await open({
      onApi: (call) => reply(200, { path: 'x', name: sent(call).name, size: 3 }),
    });
    choose(m, [new File(['abc'], 'a.txt'), new File(['xyz'], 'b.txt')]);
    await flush();
    await flush();
    expect(posted(m)).toEqual([
      ['/api/files/upload', { folder: '', name: 'a.txt', content_base64: 'YWJj' }],
      ['/api/files/upload', { folder: '', name: 'b.txt', content_base64: 'eHl6' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Files uploaded.');
  });

  it('says when a file went up under another name', async () => {
    const m = await open({ onApi: () => reply(200, { path: 'a (1).txt', name: 'a (1).txt', size: 3 }) });
    choose(m, [new File(['abc'], 'a.txt')]);
    await flush();
    await flush();
    expect(toastSuccess).toHaveBeenCalledWith('Uploaded as “a (1).txt”: there was already one with that name.');
  });

  it('a file past 25 MB is refused here, before sending it', async () => {
    const m = await open();
    const big = new File(['x'], 'grande.mp4');
    Object.defineProperty(big, 'size', { value: 25 * 1024 * 1024 + 1 });
    choose(m, [big]);
    await flush();
    expect(posted(m)).toEqual([]);
    expect(toastError).toHaveBeenCalledWith(
      'Could not upload “grande.mp4”: That file weighs more than 25 MB, the most Files takes.',
    );
  });

  it('a batch with files kept and files refused says both in one notice: a second would close the first', async () => {
    const m = await open({
      onApi: (call) =>
        sent(call).name === 'virus.exe'
          ? reply(422, { error: { code: 'base.file_type_refused', message: 'x' } })
          : reply(200, { path: 'b.pdf', name: 'b.pdf', size: 1 }),
    });
    choose(m, [new File(['MZ'], 'virus.exe'), new File(['x'], 'b.pdf')]);
    await flush();
    await flush();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledTimes(1);
    // One line of sentences (a notice paints a line break as a space), what was kept first.
    expect(vi.mocked(toastError).mock.calls[0][0]).toBe(
      'Files uploaded. Could not upload “virus.exe”: Programs (.exe) can\'t be kept in Files: they could harm whoever opens them.',
    );
  });

  it('a refusal of the server reads its own sentence: a program, the plan’s space', async () => {
    const m = await open(
      {
        onApi: (call) =>
          sent(call).name === 'virus.exe'
            ? reply(422, { error: { code: 'base.file_type_refused', message: 'x' } })
            : reply(409, { error: { code: 'base.file_no_space', message: 'x' } }),
      },
      listing({ space: { used_bytes: 10, limit_bytes: 1024 ** 3 } }),
    );
    choose(m, [new File(['MZ'], 'virus.exe'), new File(['x'], 'b.pdf')]);
    await flush();
    await flush();
    const said = String(vi.mocked(toastError).mock.calls[0][0]);
    expect(said).toContain('Could not upload “virus.exe”: Programs (.exe) can\'t be kept in Files');
    expect(said).toContain('Could not upload “b.pdf”: There is no space left for that file: your plan includes 1 GB.');
    // Each refusal its own sentence, one after the other on one line.
    expect(said).not.toMatch(/\n/);
    expect(said).toMatch(/opens them\. Could not upload “b\.pdf”/);
  });

  it('dropping files on the manager uploads them', async () => {
    const m = await open({ onApi: () => reply(200, { path: 'a.txt', name: 'a.txt', size: 3 }) });
    const drop = new Event('drop', { bubbles: true, cancelable: true }) as DragEvent;
    Object.defineProperty(drop, 'dataTransfer', { value: { types: ['Files'], files: [new File(['abc'], 'a.txt')] } });
    m.wrapper.find('[data-testid="files-manager"]').element.dispatchEvent(drop);
    await flush();
    await flush();
    expect(posted(m)).toEqual([['/api/files/upload', { folder: '', name: 'a.txt', content_base64: 'YWJj' }]]);
  });

  it('makes a new folder in the open one', async () => {
    const m = await open(
      { path: '/files?folder=Facturas', onApi: () => reply(200, { path: 'Facturas/2027', name: '2027' }) },
      listing({ folder: 'Facturas', crumbs: [{ path: 'Facturas', name: 'Facturas' }] }),
    );
    await m.wrapper.find('[data-testid="files-new-folder"]').trigger('click');
    await flush();
    await input('files-new-folder-name', '2027');
    byTestid('files-new-folder-dialog-submit')?.click();
    await flush();
    expect(posted(m)).toEqual([['/api/files/folder', { parent: 'Facturas', name: '2027' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Folder created.');
  });

  it('who does not run the business has no upload nor new folder, and no changes in the menu', async () => {
    const m = await open({ session: STAFF }, listing({ can: { upload: false, delete: false } }));
    expect(m.wrapper.find('[data-testid="files-upload"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="files-new-folder"]').exists()).toBe(false);
    await menu(m, 'marzo.pdf', 'open');
    await m.wrapper.find('[data-item="marzo.pdf"] [data-testid="files-item-actions"]').trigger('click');
    await flush();
    expect(byTestid('files-action-download')).not.toBeNull();
    for (const action of ['rename', 'move', 'delete']) expect(byTestid(`files-action-${action}`)).toBeNull();
  });
});

describe('FilesPage · open and download (BASE-G84)', () => {
  it('«Open» shows the file in the preview', async () => {
    const m = await open();
    await menu(m, 'marzo.pdf', 'open');
    const preview = m.wrapper.findComponent({ name: 'FilePreview' });
    expect(preview.props('open')).toBe(true);
    expect((preview.props('file') as FileItem).path).toBe('marzo.pdf');
  });

  it('a tap on a file opens it too', async () => {
    const m = await open();
    await m.wrapper.find('[data-item="foto.png"] [data-testid="files-item-main"]').trigger('click');
    expect((m.wrapper.findComponent({ name: 'FilePreview' }).props('file') as FileItem).path).toBe('foto.png');
  });

  it('«Download» asks the hub for the file and saves it with its name', async () => {
    const blob = new Blob(['%PDF']);
    vi.mocked(fetchFile).mockResolvedValue({ blob, name: 'marzo.pdf' });
    const m = await open();
    await menu(m, 'marzo.pdf', 'download');
    await flush();
    expect(fetchFile).toHaveBeenCalledWith('/api/files/raw?path=marzo.pdf', 'application/pdf');
    expect(mocks.saveFile).toHaveBeenCalledWith('marzo.pdf', blob);
  });

  it('a download that fails says so, with why', async () => {
    vi.mocked(fetchFile).mockRejectedValue(Object.assign(new Error('x'), { code: 'base.file_missing' }));
    const m = await open();
    await menu(m, 'marzo.pdf', 'download');
    await flush();
    expect(toastError).toHaveBeenCalledWith(
      'Could not download “marzo.pdf”: That file or folder no longer exists. Refresh the list.',
    );
  });
});

describe('FilesPage · rename and move (BASE-G85)', () => {
  it('renames with the current name written in, and says so', async () => {
    const m = await open({ onApi: () => reply(200, { path: 'abril.pdf', name: 'abril.pdf' }) });
    await menu(m, 'marzo.pdf', 'rename');
    expect((byTestid('files-rename-name') as HTMLElement & { value: string }).value).toBe('marzo.pdf');
    await input('files-rename-name', 'abril.pdf');
    byTestid('files-rename-dialog-submit')?.click();
    await flush();
    expect(posted(m)).toEqual([['/api/files/rename', { path: 'marzo.pdf', name: 'abril.pdf' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Renamed.');
  });

  it('a refused rename keeps the dialog with the sentence of why', async () => {
    const m = await open({
      onApi: () => reply(409, { error: { code: 'base.file_exists', message: 'There is already…' } }),
    });
    await menu(m, 'marzo.pdf', 'rename');
    await input('files-rename-name', 'foto.png');
    byTestid('files-rename-dialog-submit')?.click();
    await flush();
    expect(byTestid('files-rename-dialog-error')?.textContent).toContain(
      'There is already a file or folder with that name here.',
    );
    expect(byTestid('files-rename-name')).not.toBeNull();
  });

  it('the open folder has its own menu beside its path; renamed, the screen follows it', async () => {
    const m = await open(
      {
        path: '/files?folder=Facturas%2F2026',
        onApi: () => reply(200, { path: 'Facturas/Año 2026', name: 'Año 2026' }),
      },
      listing({ folder: 'Facturas/2026' }),
    );
    await menu(m, null, 'rename');
    expect((byTestid('files-rename-name') as HTMLElement & { value: string }).value).toBe('2026');
    await input('files-rename-name', 'Año 2026');
    byTestid('files-rename-dialog-submit')?.click();
    await flush();
    expect(posted(m)).toEqual([['/api/files/rename', { path: 'Facturas/2026', name: 'Año 2026' }]]);
    expect(m.router.currentRoute.value.query.folder).toBe('Facturas/Año 2026');
  });

  it('the top has no menu of its own', async () => {
    const m = await open();
    expect(m.wrapper.find('[data-testid="files-folder-actions"]').exists()).toBe(false);
  });

  it('moves to the folder chosen and says where it went (hub#2197), the top named «Files»', async () => {
    const m = await open({ onApi: () => reply(200, { path: 'Facturas/2026/marzo.pdf', name: 'marzo.pdf' }) });
    await menu(m, 'marzo.pdf', 'move');
    const options = [...document.querySelectorAll<HTMLElement>('[data-testid="files-move-option"]')];
    expect(options.map((o) => o.dataset.to)).toEqual(['', 'Contratos', 'Facturas', 'Facturas/2026']);
    options.find((o) => o.dataset.to === 'Facturas/2026')?.click();
    await flush();
    byTestid('files-move-dialog-submit')?.click();
    await flush();
    expect(posted(m)).toEqual([['/api/files/move', { path: 'marzo.pdf', to: 'Facturas/2026' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Moved to “2026”.');
  });

  it('a folder is never offered to move inside itself', async () => {
    const m = await open();
    await menu(m, 'Facturas', 'move');
    const options = [...document.querySelectorAll<HTMLElement>('[data-testid="files-move-option"]')];
    expect(options.map((o) => o.dataset.to)).toEqual(['', 'Contratos']);
  });

  it('a refused move reads a sentence, never the key (hub#2197)', async () => {
    const m = await open({
      onApi: () => reply(409, { error: { code: 'base.file_already_there', message: 'x' } }),
    });
    await menu(m, 'marzo.pdf', 'move');
    byTestid('files-move-dialog-submit')?.click();
    await flush();
    expect(byTestid('files-move-dialog-error')?.textContent).toContain('It is already in that folder.');
    expect(byTestid('files-move-dialog-error')?.textContent).not.toContain('base.files');
  });

  it('dragging a file onto a folder of the tree moves it there', async () => {
    const m = await open({ onApi: () => reply(200, { path: 'Contratos/marzo.pdf', name: 'marzo.pdf' }) });
    await m.wrapper.find('[data-item="marzo.pdf"]').trigger('dragstart', { dataTransfer: { setData: vi.fn(), effectAllowed: '' } });
    await m.wrapper.find('[data-testid="files-tree"] [data-folder="Contratos"]').trigger('drop');
    await flush();
    expect(posted(m)).toEqual([['/api/files/move', { path: 'marzo.pdf', to: 'Contratos' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Moved to “Contratos”.');
  });

  it('«Files» of the tree takes what comes from a folder, never what is already at the top', async () => {
    const over = () => {
      const event = new Event('dragover', { bubbles: true, cancelable: true });
      m.wrapper.find('[data-testid="files-root"]').element.dispatchEvent(event);
      return event.defaultPrevented;
    };
    const m = await open(
      { path: '/files?folder=Facturas', onApi: () => reply(200, { path: 'nota.pdf', name: 'nota.pdf' }) },
      listing({ folder: 'Facturas', crumbs: [{ path: 'Facturas', name: 'Facturas' }], files: [file('Facturas/nota.pdf')] }),
    );
    await m.wrapper.find('[data-item="Facturas/nota.pdf"]').trigger('dragstart', { dataTransfer: { setData: vi.fn(), effectAllowed: '' } });
    expect(over()).toBe(true);
    await m.wrapper.find('[data-testid="files-root"]').trigger('drop');
    await flush();
    expect(posted(m)).toEqual([['/api/files/move', { path: 'Facturas/nota.pdf', to: '' }]]);

    const top = await open();
    await top.wrapper.find('[data-item="marzo.pdf"]').trigger('dragstart', { dataTransfer: { setData: vi.fn(), effectAllowed: '' } });
    const event = new Event('dragover', { bubbles: true, cancelable: true });
    top.wrapper.find('[data-testid="files-root"]').element.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});

describe('FilesPage · delete (BASE-G86)', () => {
  it('asks first, deletes and says so', async () => {
    mocks.confirm.mockResolvedValue(true);
    const m = await open({ onApi: () => reply(200, { path: 'marzo.pdf', folder: false }) });
    await menu(m, 'marzo.pdf', 'delete');
    await flush();
    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Delete file',
        message: 'You are about to delete “marzo.pdf”. This cannot be undone.',
        tone: 'danger',
      }),
    );
    expect(posted(m)).toEqual([['/api/files/delete', { path: 'marzo.pdf' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('File deleted.');
  });

  it('a folder says everything in it goes too; deleting the open one goes up', async () => {
    mocks.confirm.mockResolvedValue(true);
    const m = await open(
      { path: '/files?folder=Facturas%2F2026', onApi: () => reply(200, { path: 'Facturas/2026', folder: true }) },
      listing({ folder: 'Facturas/2026' }),
    );
    await menu(m, null, 'delete');
    await flush();
    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Delete folder',
        message: 'You are about to delete “2026” and everything in it. This cannot be undone.',
      }),
    );
    expect(toastSuccess).toHaveBeenCalledWith('Folder deleted.');
    expect(m.router.currentRoute.value.query.folder).toBe('Facturas');
  });

  it('«Cancel» deletes nothing', async () => {
    mocks.confirm.mockResolvedValue(false);
    const m = await open();
    await menu(m, 'marzo.pdf', 'delete');
    await flush();
    expect(posted(m)).toEqual([]);
  });

  it('a session that ended reads as that', async () => {
    mocks.confirm.mockResolvedValue(true);
    const m = await open({ onApi: () => reply(401, { error: { code: 'unauthorized', message: 'x' } }) });
    await menu(m, 'marzo.pdf', 'delete');
    await flush();
    expect(toastError).toHaveBeenCalledWith(
      'Could not delete: Your session has expired. Sign in again and try once more.',
    );
  });
});
