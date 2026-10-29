// How the WhatsApp inbox shows when a message was said and what an attachment is (ported from the
// product's `ui/lib/message-time.ts` and `message-media.ts`). The inbox reads every instant on the
// BUSINESS clock — phase 1 has no settings per business: Madrid's — never the device's: a tablet on
// the wrong zone must not move a customer's message by hours. Pages never format by hand: they call these.

/** The business's IANA zone (phase 1: every business is in Madrid, as the server's `clock.py`). */
export const BUSINESS_ZONE = 'Europe/Madrid';

export interface MessageTimeOptions {
  /** The reader's language (`en`, `es`). */
  locale: string;
  /** Already-translated «yesterday» label. */
  yesterday: string;
  /** Keep the time next to «yesterday» or the date (the thread). The list is compact without it. */
  withTime?: boolean;
  now?: Date;
  timeZone?: string;
}

/** `YYYY-MM-DD` of an instant on the business calendar. */
function businessDay(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(instant);
}

/** The calendar day before `day` (`YYYY-MM-DD`), month and year boundaries included. */
function previousDay(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d - 1)).toISOString().slice(0, 10);
}

/** The time if today, «yesterday» or the date (and, with `withTime`, the time too), on the business clock. */
export function formatMessageTime(value: string | null | undefined, opts: MessageTimeOptions): string {
  const raw = value == null ? '' : String(value);
  if (!raw) return '';
  const instant = new Date(raw);
  if (Number.isNaN(instant.getTime())) return raw;
  const timeZone = opts.timeZone ?? BUSINESS_ZONE;
  const locale = opts.locale || 'en';
  let time: string;
  let date: string;
  try {
    time = instant.toLocaleTimeString(locale, { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    date = instant.toLocaleDateString(locale, { timeZone, day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return raw; // an unknown locale is not a reason to lose the value
  }
  const day = businessDay(instant, timeZone);
  const today = businessDay(opts.now ?? new Date(), timeZone);
  if (day === today) return time;
  const label = day === previousDay(today) ? opts.yesterday : date;
  return opts.withTime ? `${label}, ${time}` : label;
}

export type MediaKind = 'image' | 'sticker' | 'audio' | 'video' | 'document';

const KINDS: readonly MediaKind[] = ['image', 'sticker', 'audio', 'video', 'document'];

/** What an attachment is, by Meta's type or else by its MIME type; `null` without an attachment. */
export function mediaKind(message: { kind: string; media_url: string; media_mime_type: string }): MediaKind | null {
  if (!message.media_url) return null;
  if ((KINDS as readonly string[]).includes(message.kind)) return message.kind as MediaKind;
  const mime = message.media_mime_type.toLowerCase();
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('audio/')) return 'audio';
  if (mime.startsWith('video/')) return 'video';
  return 'document';
}

/** The kind of a template header's file the Hub sent (F33), by its type: kept in the Hub, never linked. */
export function headerFileKind(mimeType: string): 'image' | 'video' | 'document' {
  const mime = mimeType.toLowerCase();
  return mime.startsWith('image/') ? 'image' : mime.startsWith('video/') ? 'video' : 'document';
}

/** The attachment's address when it may be opened: https, or the local SaaS in development. */
export function safeMediaUrl(url: string): string | null {
  return /^https:\/\/[^\s]+$/.test(url) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//.test(url) ? url : null;
}
