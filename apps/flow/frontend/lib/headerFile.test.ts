// The file of a WhatsApp template's header in a «Send a message» step (WORKBOOK FLOW-F32): what each kind takes,
// checked before the upload so a wrong one is said at once (the inbox checks again by the file's bytes).
import { describe, expect, it } from 'vitest';

import { formatFileSize, HEADER_FILE_RULES, headerFileKind, judgeHeaderFile } from './headerFile';

const file = (name: string, type: string, size = 4) => new File([new Uint8Array(size)], name, { type });
const MB = 1024 * 1024;

describe('headerFile', () => {
  it('a photo, a video or a document header asks for a file; text or none does not', () => {
    expect(headerFileKind('IMAGE')).toBe('IMAGE');
    expect(headerFileKind('VIDEO')).toBe('VIDEO');
    expect(headerFileKind('DOCUMENT')).toBe('DOCUMENT');
    expect(headerFileKind('TEXT')).toBeNull();
    expect(headerFileKind('')).toBeNull();
    expect(headerFileKind(undefined)).toBeNull();
  });

  it('takes what WhatsApp takes for each kind: JPEG or PNG up to 5 MB, MP4 up to 16 MB, PDF up to 25 MB', () => {
    expect(HEADER_FILE_RULES.IMAGE).toEqual({ accept: 'image/jpeg,image/png', maxBytes: 5 * MB });
    expect(HEADER_FILE_RULES.VIDEO).toEqual({ accept: 'video/mp4', maxBytes: 16 * MB });
    expect(HEADER_FILE_RULES.DOCUMENT).toEqual({ accept: 'application/pdf', maxBytes: 25 * MB });
    expect(judgeHeaderFile(file('carta.png', 'image/png'), 'IMAGE')).toBe('ok');
    expect(judgeHeaderFile(file('promo.mp4', 'video/mp4'), 'VIDEO')).toBe('ok');
    expect(judgeHeaderFile(file('carta.pdf', 'application/pdf'), 'DOCUMENT')).toBe('ok');
  });

  it('a file of another kind, an empty one or a heavier one is refused', () => {
    expect(judgeHeaderFile(file('carta.pdf', 'application/pdf'), 'IMAGE')).toBe('type');
    expect(judgeHeaderFile(file('carta.png', 'image/png', 0), 'IMAGE')).toBe('type');
    expect(judgeHeaderFile(file('big.png', 'image/png', 5 * MB + 1), 'IMAGE')).toBe('size');
  });

  it('a browser that names no type is judged by the extension', () => {
    expect(judgeHeaderFile(file('carta.JPG', ''), 'IMAGE')).toBe('ok');
    expect(judgeHeaderFile(file('carta.txt', ''), 'IMAGE')).toBe('type');
  });

  it('says a size as people read it: kilobytes below a megabyte, megabytes from it, one decimal at most', () => {
    expect(formatFileSize(6349, 'en')).toBe('6.2 KB');
    expect(formatFileSize(2 * MB, 'en')).toBe('2 MB');
    expect(formatFileSize(1.25 * MB, 'es')).toBe('1,3 MB');
  });
});
