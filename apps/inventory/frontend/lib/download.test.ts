// The export hands the browser the CSV the server wrote (WORKBOOK INVENTORY-F11): a file with the
// server's name and content, saved by the Hub's `saveFile`: a link in a browser, the app's Downloads in it.
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { saveTextFile } from './download';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

const t = (key: string, values?: Record<string, unknown>) => (values ? `${key} ${JSON.stringify(values)}` : key);

afterEach(() => {
  vi.restoreAllMocks();
});

describe('saveTextFile', () => {
  it('saves the content under its name with its media type and releases the URL', async () => {
    const created: Blob[] = [];
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      created.push(blob as Blob);
      return 'blob:csv';
    });
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const clicks: Array<{ href: string; download: string }> = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push({ href: this.getAttribute('href') ?? '', download: this.download });
    });

    await expect(saveTextFile('inventario-productos.csv', '﻿Nombre;SKU\n', 'text/csv', t)).resolves.toBe(true);

    expect(clicks).toEqual([{ href: 'blob:csv', download: 'inventario-productos.csv' }]);
    expect(created).toHaveLength(1);
    expect(created[0].type).toBe('text/csv;charset=utf-8');
    expect(await created[0].text()).toBe('﻿Nombre;SKU\n');
    expect(revoke).toHaveBeenCalledWith('blob:csv');
    expect(document.querySelector('a[download]')).toBeNull();
  });
});

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

describe('saveTextFile inside the installed app (hub#1041)', () => {
  afterEach(() => {
    delete (window as TauriWindow).__TAURI__;
  });

  it('gives the file to the app’s Downloads, never a link, and the app says where', async () => {
    const invoke = vi.fn(async () => ({ path: 'Download/inventario-productos.csv' }));
    (window as TauriWindow).__TAURI__ = { core: { invoke } };
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    await expect(saveTextFile('inventario-productos.csv', 'Nombre;SKU\n', 'text/csv', t)).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledWith('save_download', { name: 'inventario-productos.csv', dataBase64: btoa('Nombre;SKU\n') });
    expect(click).not.toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith('base.download.savedTo {"path":"Download/inventario-productos.csv"}');
  });
});
