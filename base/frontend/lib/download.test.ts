// A file the page holds, saved where the person will find it (hub#1041; the old hub's `save-download.ts`, hub#480):
// in a browser, its downloads through a temporary link; inside the installed app, whose webview does nothing with
// that link (Android's has no download listener at all), the app's `save_download` (ERPlora/app HUB_APP-F30), which
// writes it to Downloads and answers where — said on screen, because inside the app nothing else says the file
// arrived. A refusal is said too, by its reason: a button that does nothing when pressed is the defect.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { saveFile, SAVE_DOWNLOAD_COMMAND } from './download';

const mocks = vi.hoisted(() => ({ toastSuccess: vi.fn(async () => undefined), toastError: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: mocks.toastSuccess,
  toastError: mocks.toastError,
}));

type Invoke = (command: string, args?: unknown) => Promise<unknown>;

const t = (key: string, values?: Record<string, unknown>) => (values ? `${key} ${JSON.stringify(values)}` : key);

function inTheApp(invoke: Invoke): object {
  return { __TAURI__: { core: { invoke } } };
}

function decoded(base64: string): number[] {
  return [...atob(base64)].map((char) => char.charCodeAt(0));
}

let clicked: HTMLAnchorElement[];

beforeEach(() => {
  clicked = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this);
  });
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:hub/1');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.toastSuccess.mockClear();
  mocks.toastError.mockClear();
});

describe('saveFile in a browser', () => {
  it('hands the file to the browser through a temporary link and says nothing itself', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' });

    await expect(saveFile('anexo-i.pdf', blob, t, {})).resolves.toBe(true);

    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe('anexo-i.pdf');
    expect(clicked[0].getAttribute('href')).toBe('blob:hub/1');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:hub/1');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
  });
});

describe('saveFile inside the installed app', () => {
  it('gives the bytes to the app, never the link, and says where the file was saved', async () => {
    const invoke = vi.fn(async () => ({ path: 'Download/anexo-i.pdf' }));
    const blob = new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x00, 0xff])], { type: 'application/pdf' });

    await expect(saveFile('anexo-i.pdf', blob, t, inTheApp(invoke))).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledOnce();
    const [command, args] = invoke.mock.calls[0] as unknown as [string, { name: string; dataBase64: string }];
    expect(command).toBe(SAVE_DOWNLOAD_COMMAND);
    expect(command).toBe('save_download');
    expect(args.name).toBe('anexo-i.pdf');
    expect(decoded(args.dataBase64)).toEqual([0x25, 0x50, 0x44, 0x46, 0x00, 0xff]);
    expect(clicked).toHaveLength(0);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(mocks.toastSuccess).toHaveBeenCalledWith('base.download.savedTo {"path":"Download/anexo-i.pdf"}');
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it('carries a file of several hundred kilobytes whole (the base64 is built in slices)', async () => {
    const bytes = new Uint8Array(300_000).map((_, at) => at % 251);
    const invoke = vi.fn(async () => ({ path: 'Download/copia.blueprint.zip' }));

    await saveFile('copia.blueprint.zip', new Blob([bytes]), t, inTheApp(invoke));

    const [, args] = invoke.mock.calls[0] as unknown as [string, { dataBase64: string }];
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
    const invoke = vi.fn(async () => Promise.reject(answer));

    await expect(saveFile('anexo-i.pdf', new Blob(['x']), t, inTheApp(invoke))).resolves.toBe(false);

    expect(mocks.toastError).toHaveBeenCalledWith(sentence);
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(clicked).toHaveLength(0);
    expect(console.error).toHaveBeenCalled();
  });

  it('takes an answer of the app with no path for a failure, never «saved» without where', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const invoke = vi.fn(async () => ({}));

    await expect(saveFile('anexo-i.pdf', new Blob(['x']), t, inTheApp(invoke))).resolves.toBe(false);

    expect(mocks.toastError).toHaveBeenCalledWith('base.download.refusal.failed');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it('says a failure when the bytes cannot be read', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const invoke = vi.fn(async () => ({ path: 'Download/x' }));
    const unreadable = { arrayBuffer: () => Promise.reject(new Error('gone')) } as unknown as Blob;

    await expect(saveFile('x.pdf', unreadable, t, inTheApp(invoke))).resolves.toBe(false);

    expect(invoke).not.toHaveBeenCalled();
    expect(mocks.toastError).toHaveBeenCalledWith('base.download.refusal.failed');
  });
});
