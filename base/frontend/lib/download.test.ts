// A file the page holds, saved where the person will find it (hub#1041; the old hub's `save-download.ts`):
// in a browser, its downloads through a temporary link; inside the installed app, whose webview does nothing with
// that link (Android's has no download listener at all), the app's `save_download` (ERPlora/app HUB_APP-F30), which
// writes it to Downloads and answers where — said on screen, because inside the app nothing else says the file
// arrived. A refusal is said too, by its reason: a button that does nothing when pressed is the defect.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browserDownloads, insideTheAppSaving, keyText as t, outOfTheApp } from '../__tests__/app-download';
import { saveFile, SAVE_DOWNLOAD_COMMAND } from './download';

const mocks = vi.hoisted(() => ({ toastSuccess: vi.fn(async () => undefined), toastError: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: mocks.toastSuccess,
  toastError: mocks.toastError,
}));

function decoded(base64: string): number[] {
  return [...atob(base64)].map((char) => char.charCodeAt(0));
}

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
  mocks.toastSuccess.mockClear();
  mocks.toastError.mockClear();
});

describe('saveFile in a browser', () => {
  it('hands the file to the browser through a temporary link and says nothing itself', async () => {
    const saved = browserDownloads();
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' });

    await expect(saveFile('anexo-i.pdf', blob, t)).resolves.toBe(true);

    expect(saved).toEqual([{ name: 'anexo-i.pdf', href: 'blob:test/1', blob }]);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test/1');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
  });
});

describe('saveFile inside the installed app', () => {
  it('gives the bytes to the app, never the link, and says where the file was saved', async () => {
    const saved = browserDownloads();
    const invoke = insideTheAppSaving({ path: 'Download/anexo-i.pdf' });
    const blob = new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x00, 0xff])], { type: 'application/pdf' });

    await expect(saveFile('anexo-i.pdf', blob, t)).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledOnce();
    const [command, args] = invoke.mock.calls[0] as [string, { name: string; dataBase64: string }];
    expect(command).toBe(SAVE_DOWNLOAD_COMMAND);
    expect(command).toBe('save_download');
    expect(args.name).toBe('anexo-i.pdf');
    expect(decoded(args.dataBase64)).toEqual([0x25, 0x50, 0x44, 0x46, 0x00, 0xff]);
    expect(saved).toEqual([]);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(mocks.toastSuccess).toHaveBeenCalledWith('base.download.savedTo {"path":"Download/anexo-i.pdf"}');
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it('carries a file of several hundred kilobytes whole (the base64 is built in slices)', async () => {
    const bytes = new Uint8Array(300_000).map((_, at) => at % 251);
    const invoke = insideTheAppSaving({ path: 'Download/copia.blueprint.zip' });

    await saveFile('copia.blueprint.zip', new Blob([bytes]), t);

    const [, args] = invoke.mock.calls[0] as [string, { dataBase64: string }];
    expect(decoded(args.dataBase64)).toEqual([...bytes]);
  });

  it.each([
    ['downloads_unreachable', 'base.download.refusal.unreachable'],
    ['not_the_linked_hub', 'base.download.refusal.unlinked'],
    ['Command save_download not found', 'base.download.refusal.outdated'],
    ['save_download not allowed. Permissions associated with this command: allow-save-download', 'base.download.refusal.outdated'],
    ['download_refused', 'base.download.refusal.failed'],
    ['io error: No space left on device', 'base.download.refusal.failed'],
  ])('says why the app did not save it (%s) and resolves false', async (answer, sentence) => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const saved = browserDownloads();
    insideTheAppSaving(answer);

    await expect(saveFile('anexo-i.pdf', new Blob(['x']), t)).resolves.toBe(false);

    expect(mocks.toastError).toHaveBeenCalledWith(sentence);
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(saved).toEqual([]);
    expect(console.error).toHaveBeenCalled();
  });

  it('takes an answer of the app with no path for a failure, never «saved» without where', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    insideTheAppSaving({});

    await expect(saveFile('anexo-i.pdf', new Blob(['x']), t)).resolves.toBe(false);

    expect(mocks.toastError).toHaveBeenCalledWith('base.download.refusal.failed');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it('says a failure when the bytes cannot be read', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const invoke = insideTheAppSaving({ path: 'Download/x' });
    const unreadable = { arrayBuffer: () => Promise.reject(new Error('gone')) } as unknown as Blob;

    await expect(saveFile('x.pdf', unreadable, t)).resolves.toBe(false);

    expect(invoke).not.toHaveBeenCalled();
    expect(mocks.toastError).toHaveBeenCalledWith('base.download.refusal.failed');
  });

  it('asks the bridge of the window it is given', async () => {
    const invoke = vi.fn(async () => ({ path: 'Download/x.pdf' }));

    await saveFile('x.pdf', new Blob(['x']), t, { __TAURI__: { core: { invoke } } });

    expect(invoke).toHaveBeenCalledWith('save_download', expect.objectContaining({ name: 'x.pdf' }));
  });
});
