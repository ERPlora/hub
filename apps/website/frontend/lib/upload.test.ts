// The editor's image upload: the chosen file goes to `website.image.upload` in base64 (the repo's upload contract,
// as verifactu's certificate), and ImageUpload gets back the stored image's id and URL.
import { describe, expect, it, vi } from 'vitest';

import { makeUploader, readAsBase64 } from './upload';

describe('readAsBase64', () => {
  it('encodes the bytes of the file, whatever their size', async () => {
    const bytes = new Uint8Array(70_000).map((_, i) => i % 256);
    const file = new File([bytes], 'big.png', { type: 'image/png' });
    const decoded = Uint8Array.from(atob(await readAsBase64(file)), (char) => char.charCodeAt(0));
    expect(decoded).toEqual(bytes);
  });

  it('encodes an empty file as an empty string', async () => {
    expect(await readAsBase64(new File([], 'x.png'))).toBe('');
  });
});

describe('makeUploader', () => {
  it('sends the name, the type and the base64 of the file, and answers only the id and the URL', async () => {
    const run = vi.fn().mockResolvedValue({ id: 'img-1', url: '/p/media/abc/website/img/1.png', width: 1, height: 1, size: 3, content_type: 'image/png' });
    const upload = makeUploader(run);
    const answer = await upload(new File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' }));
    expect(run).toHaveBeenCalledWith({ filename: 'logo.png', content_type: 'image/png', data_base64: 'AQID' });
    expect(answer).toEqual({ id: 'img-1', url: '/p/media/abc/website/img/1.png' });
  });

  it('lets the server refuse a type it does not take (the picker filters, a phone may not)', async () => {
    const run = vi.fn().mockRejectedValue(new Error('This file is not a PNG image.'));
    await expect(makeUploader(run)(new File(['x'], 'x.gif', { type: 'image/gif' }))).rejects.toThrow('PNG');
    expect(run.mock.calls[0][0].content_type).toBe('image/gif');
  });
});
