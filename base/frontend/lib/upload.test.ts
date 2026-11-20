import { describe, expect, it } from 'vitest';

import { readAsBase64 } from './upload';

describe('readAsBase64', () => {
  it('encodes every byte, including files larger than one chunk', async () => {
    const bytes = new Uint8Array(70_000).map((_, index) => index % 256);
    const encoded = await readAsBase64(new File([bytes], 'big.png', { type: 'image/png' }));
    expect(Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0))).toEqual(bytes);
  });

  it('encodes an empty file as an empty string', async () => {
    expect(await readAsBase64(new File([], 'empty.png'))).toBe('');
  });
});
