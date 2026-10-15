// Handing the browser the CSV the server wrote (ATTENDANCE-F10): a Blob with a BOM, so a spreadsheet
// reads the accents of the names as UTF-8, saved through a temporary link never added to the page.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { saveCsv } from './download';

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

    saveCsv('attendance-2026-10.csv', 'date,user\r\n2026-10-05,Peña\r\n');

    expect(clicks).toEqual([{ href: 'blob:csv', download: 'attendance-2026-10.csv' }]);
    expect(blobs[0].type).toBe('text/csv;charset=utf-8');
    const bytes = new Uint8Array(await blobs[0].arrayBuffer());
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    expect(new TextDecoder().decode(bytes.slice(3))).toBe('date,user\r\n2026-10-05,Peña\r\n');
    expect(revoke).toHaveBeenCalledWith('blob:csv');
  });
});
