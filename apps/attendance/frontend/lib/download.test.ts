// Handing the browser the CSV the server wrote (ATTENDANCE-F10): a Blob with a BOM, so a spreadsheet
// reads the accents of the names as UTF-8, saved by the Hub's `saveFile`: a link in a browser, the app's Downloads in it.
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { saveCsv } from './download';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

const t = (key: string, values?: Record<string, unknown>) => (values ? `${key} ${JSON.stringify(values)}` : key);

afterEach(() => vi.restoreAllMocks());

describe('saveCsv', () => {
  it('saves the text with a BOM under the server’s file name and releases the URL', async () => {
    const blobs: Blob[] = [];
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      blobs.push(blob as Blob);
      return 'blob:csv';
    });
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const clicks: Array<{ href: string; download: string }> = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push({ href: this.getAttribute('href') ?? '', download: this.download });
    });

    await expect(saveCsv('attendance-2026-10.csv', 'date,user\r\n2026-10-05,Peña\r\n', t)).resolves.toBe(true);

    expect(clicks).toEqual([{ href: 'blob:csv', download: 'attendance-2026-10.csv' }]);
    expect(blobs[0].type).toBe('text/csv;charset=utf-8');
    const bytes = new Uint8Array(await blobs[0].arrayBuffer());
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    expect(new TextDecoder().decode(bytes.slice(3))).toBe('date,user\r\n2026-10-05,Peña\r\n');
    expect(revoke).toHaveBeenCalledWith('blob:csv');
  });
});

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

describe('saveCsv inside the installed app (hub#1041)', () => {
  afterEach(() => {
    delete (window as TauriWindow).__TAURI__;
  });

  it('gives the file to the app’s Downloads, never a link, and the app says where', async () => {
    const invoke = vi.fn(async () => ({ path: 'Download/attendance-2026-10.csv' }));
    (window as TauriWindow).__TAURI__ = { core: { invoke } };
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    await expect(saveCsv('attendance-2026-10.csv', 'date\r\n', t)).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledWith('save_download', { name: 'attendance-2026-10.csv', dataBase64: btoa('\xef\xbb\xbfdate\r\n') });
    expect(click).not.toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith('base.download.savedTo {"path":"Download/attendance-2026-10.csv"}');
  });
});
