// The editor's image upload: the chosen file goes to `website.image.upload` in base64 (the repo's upload contract,
// as verifactu's certificate), and ImageUpload gets back the stored image's id and URL.
import { describe, expect, it, vi } from 'vitest';

import { makeUploader } from './upload';

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
