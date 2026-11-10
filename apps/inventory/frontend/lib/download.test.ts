// The export hands the person the CSV the server wrote (WORKBOOK INVENTORY-F11): the server's name, content and media
// type, saved by the Hub's `saveFile` — a link in a browser, the app's Downloads inside it (hub#1041).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browserDownloads, insideTheAppSaving, keyText, outOfTheApp } from '../../../../base/frontend/__tests__/app-download';
import { saveTextFile } from './download';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
});

describe('saveTextFile', () => {
  it('saves the content under its name with its media type in UTF-8, never left in the page', async () => {
    const saved = browserDownloads();

    await expect(saveTextFile('inventario-productos.csv', '﻿Nombre;SKU\n', 'text/csv', keyText)).resolves.toBe(true);

    expect(saved.map((file) => [file.name, file.blob.type])).toEqual([['inventario-productos.csv', 'text/csv;charset=utf-8']]);
    expect(await saved[0].blob.text()).toBe('﻿Nombre;SKU\n');
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it('inside the installed app the same bytes go to its Downloads, never a link', async () => {
    const saved = browserDownloads();
    const invoke = insideTheAppSaving({ path: 'Download/inventario-productos.csv' });

    await expect(saveTextFile('inventario-productos.csv', 'Nombre;SKU\n', 'text/csv', keyText)).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledWith('save_download', { name: 'inventario-productos.csv', dataBase64: btoa('Nombre;SKU\n') });
    expect(saved).toEqual([]);
  });
});
