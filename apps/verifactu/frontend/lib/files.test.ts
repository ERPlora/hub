// Files of the VeriFactu screens: what a person picks travels in base64 inside the JSON body (never in a URL
// that a proxy would log), and a file the server hands back in base64 (the blank model of the representation
// authorisation) is saved through a temporary link, its object URL released afterwards.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fileToBase64, saveBase64File } from './files';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('fileToBase64', () => {
  it('reads a picked file into base64', async () => {
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], 'model.pdf', { type: 'application/pdf' });
    expect(await fileToBase64(file)).toBe('JVBERg==');
  });

  it('reads a file larger than one chunk whole', async () => {
    const bytes = new Uint8Array(0x8000 * 2 + 3).map((_, i) => i % 251);
    const decoded = atob(await fileToBase64(new File([bytes], 'big.pdf')));
    expect(decoded.length).toBe(bytes.length);
    expect(decoded.charCodeAt(0x8000 + 1)).toBe(bytes[0x8000 + 1]);
  });
});

describe('saveBase64File', () => {
  it('hands the browser the decoded file under its name and releases its URL', async () => {
    const created: Blob[] = [];
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      created.push(blob as Blob);
      return 'blob:model';
    });
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const clicked: { href: string; download: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.getAttribute('href') ?? '', download: this.download });
    });

    saveBase64File('anexo-i.pdf', 'application/pdf', 'JVBERi0xLjQ=');

    expect(clicked).toEqual([{ href: 'blob:model', download: 'anexo-i.pdf' }]);
    expect(created[0].type).toBe('application/pdf');
    expect(new Uint8Array(await created[0].arrayBuffer())).toEqual(new TextEncoder().encode('%PDF-1.4'));
    expect(revoke).toHaveBeenCalledWith('blob:model');
  });
});
