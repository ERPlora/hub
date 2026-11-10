// Files of the VeriFactu screens: what a person picks travels in base64 inside the JSON body (never in a URL
// that a proxy would log). Saving the model it hands back is the Hub's `saveFile` (`base/frontend/lib/download.test.ts`).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fileToBase64 } from './files';

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
