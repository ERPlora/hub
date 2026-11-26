// The address of an image a public page draws: only one the business's own Hub serves (a path of its own, or an
// absolute address of the page's own origin); anything else is no image, so a page never loads one from elsewhere.
import { describe, expect, it } from 'vitest';

import { ownImageUrl } from './own-image';

const ORIGIN = 'https://tenant-a.erplora.com';

describe('ownImageUrl', () => {
  it.each([
    ['/p/media/hub-1/inventory/products/cro.webp', '/p/media/hub-1/inventory/products/cro.webp'],
    ['  /p/catalog/hospitality/menu_dia.webp ', '/p/catalog/hospitality/menu_dia.webp'],
    [`${ORIGIN}/p/media/hub-1/logo.png`, `${ORIGIN}/p/media/hub-1/logo.png`],
  ])('keeps %s, which the Hub serves itself', (given, kept) => {
    expect(ownImageUrl(given, ORIGIN)).toBe(kept);
  });

  it.each([
    '',
    '//evil.example/x.webp',
    '/\\evil.example/x.webp',
    'https://evil.example/x.webp',
    'http://tenant-a.erplora.com.evil.example/x.webp',
    'javascript:alert(1)',
    'data:image/svg+xml,<svg/>',
    'p/media/relative.webp',
  ])('draws nothing for %s', (given) => {
    expect(ownImageUrl(given, ORIGIN)).toBe('');
  });

  it('reads the page’s own origin when none is given', () => {
    expect(ownImageUrl(`${window.location.origin}/p/media/a.webp`)).toBe(`${window.location.origin}/p/media/a.webp`);
  });
});
