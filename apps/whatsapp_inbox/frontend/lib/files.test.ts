// The file of a template's header (WHATSAPP_INBOX-F29): what each kind takes — the same rules the Hub applies
// (`samples.py`: JPEG or PNG up to 5 MB, MP4 up to 16 MB, PDF up to 25 MB) — and the file in base64 for its upload.
import { describe, expect, it } from 'vitest';

import { acceptsSample, fileToBase64, formatSize, SAMPLE_RULES } from './files';

const MB = 1024 * 1024;
const file = (name: string, type: string, size = 4) => new File([new Uint8Array(size).fill(0x41)], name, { type });

describe('the header file rules', () => {
  it('are the Hub’s: the types and the largest file of each kind', () => {
    expect(SAMPLE_RULES).toEqual({
      IMAGE: { accept: 'image/jpeg,image/png', maxBytes: 5 * MB },
      VIDEO: { accept: 'video/mp4', maxBytes: 16 * MB },
      DOCUMENT: { accept: 'application/pdf', maxBytes: 25 * MB },
    });
  });

  it('take a file of the kind, by its type or its extension, up to its size', () => {
    expect(acceptsSample(file('carta.jpg', 'image/jpeg'), 'IMAGE')).toBe('ok');
    expect(acceptsSample(file('logo.PNG', ''), 'IMAGE')).toBe('ok');
    expect(acceptsSample(file('visita.mp4', 'video/mp4'), 'VIDEO')).toBe('ok');
    expect(acceptsSample(file('carta.pdf', 'application/pdf'), 'DOCUMENT')).toBe('ok');
    expect(acceptsSample(file('anim.gif', 'image/gif'), 'IMAGE')).toBe('type');
    expect(acceptsSample(file('carta.pdf', 'application/pdf'), 'IMAGE')).toBe('type');
    expect(acceptsSample(file('foto.jpg', 'image/jpeg', 5 * MB + 1), 'IMAGE')).toBe('size');
    expect(acceptsSample(file('foto.jpg', 'image/jpeg', 0), 'IMAGE')).toBe('type');
  });
});

describe('fileToBase64', () => {
  it('is the file’s bytes in base64, whole', async () => {
    expect(await fileToBase64(new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], 'a.jpg'))).toBe('/9j/4A==');
    const big = new Uint8Array(100_000).fill(0x25);
    expect(atob(await fileToBase64(new File([big], 'b.pdf'))).length).toBe(100_000);
  });
});

describe('formatSize', () => {
  it('says a file’s size in the page’s language: kilobytes below a megabyte, one decimal at most', () => {
    expect(formatSize(1536, 'en')).toBe('1.5 KB');
    expect(formatSize(1536, 'es')).toBe('1,5 KB');
    expect(formatSize(5 * MB, 'es')).toBe('5 MB');
    expect(formatSize(300, 'en')).toBe('0.3 KB');
  });
});
