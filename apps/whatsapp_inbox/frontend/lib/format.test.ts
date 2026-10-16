// When a WhatsApp message was said, as a person reads it (ported from the product's
// `ui/lib/message-time.test.ts`): the time if it is from today, «yesterday», or the date if older —
// always on the BUSINESS clock (phase 1: Madrid), never the device's. And the media kind and the
// attachment's file name the thread paints.
import { describe, expect, it } from 'vitest';

import { BUSINESS_ZONE, formatMessageTime, mediaKind, safeMediaUrl } from './format';

// 2026-09-02 12:00 in Madrid (UTC+2 in summer).
const NOW = new Date('2026-09-02T10:00:00Z');
const MADRID = { locale: 'es', now: NOW, yesterday: 'Ayer' };

describe('formatMessageTime — list form (compact)', () => {
  it('phase 1 reads every business on Madrid’s clock', () => {
    expect(BUSINESS_ZONE).toBe('Europe/Madrid');
  });

  it('today shows only the time, on the business clock (UTC 08:00 → 10:00 in Madrid)', () => {
    expect(formatMessageTime('2026-09-02T08:00:00.123456+00:00', MADRID)).toBe('10:00');
  });

  it('the previous business day shows the «yesterday» label', () => {
    expect(formatMessageTime('2026-09-01T08:00:00+00:00', MADRID)).toBe('Ayer');
  });

  it('older than yesterday shows the date in the reader’s language', () => {
    expect(formatMessageTime('2026-03-10T08:00:00+00:00', MADRID)).toBe('10/03/2026');
    expect(formatMessageTime('2026-03-10T08:00:00+00:00', { ...MADRID, locale: 'en' })).toBe('03/10/2026');
  });

  it('«today» is the business day, not the UTC one: 23:30 UTC on the 1st is already the 2nd in Madrid', () => {
    expect(formatMessageTime('2026-09-01T23:30:00+00:00', MADRID)).toBe('01:30');
  });

  it('«now» is read on the business clock too', () => {
    const justAfterMidnight = { ...MADRID, now: new Date('2026-09-01T23:30:00Z') };
    expect(formatMessageTime('2026-09-01T23:00:00+00:00', justAfterMidnight)).toBe('01:00');
    expect(formatMessageTime('2026-09-01T08:00:00+00:00', justAfterMidnight)).toBe('Ayer');
  });
});

describe('formatMessageTime — thread form (withTime)', () => {
  const THREAD = { ...MADRID, withTime: true };

  it('today is just the time; yesterday and older keep it next to the label', () => {
    expect(formatMessageTime('2026-09-02T08:00:00+00:00', THREAD)).toBe('10:00');
    expect(formatMessageTime('2026-09-01T08:05:00+00:00', THREAD)).toBe('Ayer, 10:05');
    expect(formatMessageTime('2026-03-10T08:00:00+00:00', THREAD)).toBe('10/03/2026, 09:00');
  });
});

describe('formatMessageTime — what it does not know', () => {
  it('no value is an empty cell; an unparseable one comes back untouched', () => {
    expect(formatMessageTime(null, MADRID)).toBe('');
    expect(formatMessageTime('', MADRID)).toBe('');
    expect(formatMessageTime('not-a-date', MADRID)).toBe('not-a-date');
  });
});

describe('mediaKind', () => {
  it('names an attachment by Meta’s type, a document also by its MIME type', () => {
    expect(mediaKind({ kind: 'image', media_url: 'https://x/1', media_mime_type: 'image/jpeg' })).toBe('image');
    expect(mediaKind({ kind: 'sticker', media_url: 'https://x/1', media_mime_type: 'image/webp' })).toBe('sticker');
    expect(mediaKind({ kind: 'audio', media_url: 'https://x/1', media_mime_type: 'audio/ogg' })).toBe('audio');
    expect(mediaKind({ kind: 'document', media_url: 'https://x/1', media_mime_type: 'application/pdf' })).toBe('document');
    // A kind Meta did not say, read from the file.
    expect(mediaKind({ kind: 'unknown', media_url: 'https://x/1', media_mime_type: 'video/mp4' })).toBe('video');
    expect(mediaKind({ kind: 'unknown', media_url: 'https://x/1', media_mime_type: 'application/zip' })).toBe('document');
  });

  it('no attachment URL, no attachment', () => {
    expect(mediaKind({ kind: 'image', media_url: '', media_mime_type: '' })).toBeNull();
  });
});

describe('safeMediaUrl', () => {
  it('opens an attachment over https, or the local SaaS in development; anything else is not a link', () => {
    expect(safeMediaUrl('https://erplora.com/whatsapp/media/1')).toBe('https://erplora.com/whatsapp/media/1');
    expect(safeMediaUrl('http://localhost:8001/whatsapp/media/1')).toBe('http://localhost:8001/whatsapp/media/1');
    expect(safeMediaUrl('http://evil.example/x.jpg')).toBeNull();
    expect(safeMediaUrl('javascript:alert(1)')).toBeNull();
    expect(safeMediaUrl('')).toBeNull();
  });
});
