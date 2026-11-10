// Handing the person the CSV the server wrote (ATTENDANCE-F10): a Blob with a BOM, so a spreadsheet reads the accents
// of the names as UTF-8, saved by the Hub's `saveFile` — a link in a browser, the app's Downloads inside it (hub#1041).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browserDownloads, insideTheAppSaving, keyText, outOfTheApp } from '../../../../base/frontend/__tests__/app-download';
import { saveCsv } from './download';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
});

describe('saveCsv', () => {
  it('saves the text with a BOM, as UTF-8 CSV, under the server’s file name', async () => {
    const saved = browserDownloads();

    await expect(saveCsv('attendance-2026-10.csv', 'date,user\r\n2026-10-05,Peña\r\n', keyText)).resolves.toBe(true);

    expect(saved.map((file) => [file.name, file.blob.type])).toEqual([['attendance-2026-10.csv', 'text/csv;charset=utf-8']]);
    const bytes = new Uint8Array(await saved[0].blob.arrayBuffer());
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    expect(new TextDecoder().decode(bytes.slice(3))).toBe('date,user\r\n2026-10-05,Peña\r\n');
  });

  it('inside the installed app the same bytes go to its Downloads, never a link', async () => {
    const saved = browserDownloads();
    const invoke = insideTheAppSaving({ path: 'Download/attendance-2026-10.csv' });

    await expect(saveCsv('attendance-2026-10.csv', 'date\r\n', keyText)).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledWith('save_download', { name: 'attendance-2026-10.csv', dataBase64: btoa('\xef\xbb\xbfdate\r\n') });
    expect(saved).toEqual([]);
  });
});
