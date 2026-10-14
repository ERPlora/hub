// The export hands the browser the CSV the server wrote (WORKBOOK INVENTORY-F11): a file with the
// server's name and content, saved through a link, the object URL released afterwards.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { saveTextFile } from './download';

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

    saveTextFile('inventario-productos.csv', '﻿Nombre;SKU\n', 'text/csv');

    expect(clicks).toEqual([{ href: 'blob:csv', download: 'inventario-productos.csv' }]);
    expect(created).toHaveLength(1);
    expect(created[0].type).toBe('text/csv;charset=utf-8');
    expect(await created[0].text()).toBe('﻿Nombre;SKU\n');
    expect(revoke).toHaveBeenCalledWith('blob:csv');
    expect(document.querySelector('a[download]')).toBeNull();
  });
});
