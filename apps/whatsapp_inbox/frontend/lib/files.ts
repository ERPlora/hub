// The file of a template's header with a photo, a video or a document (WHATSAPP_INBOX-F29): what each kind takes,
// checked here before the upload so a wrong one is said at once — the Hub checks again by the file's bytes
// (`samples.py`) — and the file in base64, as `whatsapp_inbox.template_sample.upload` takes it.
import type { FileHeaderFormat } from '../operations';

const MB = 1024 * 1024;

export interface SampleRule {
  /** The `<input type="file" accept>` list. */
  accept: string;
  maxBytes: number;
}

/** Meta's types and sizes (JPEG or PNG up to 5 MB, MP4 up to 16 MB); a PDF up to the Hub's 25 MB per file. */
export const SAMPLE_RULES: Readonly<Record<FileHeaderFormat, SampleRule>> = {
  IMAGE: { accept: 'image/jpeg,image/png', maxBytes: 5 * MB },
  VIDEO: { accept: 'video/mp4', maxBytes: 16 * MB },
  DOCUMENT: { accept: 'application/pdf', maxBytes: 25 * MB },
};

const EXTENSIONS: Readonly<Record<FileHeaderFormat, readonly string[]>> = {
  IMAGE: ['.jpg', '.jpeg', '.png'],
  VIDEO: ['.mp4'],
  DOCUMENT: ['.pdf'],
};

/** Whether `file` goes as `kind`'s header: `ok`, or what is wrong with it (`type`, `size`). A browser that names
 *  no type is judged by the extension. */
export function acceptsSample(file: File, kind: FileHeaderFormat): 'ok' | 'type' | 'size' {
  const rule = SAMPLE_RULES[kind];
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  const typed = type ? rule.accept.split(',').includes(type) : EXTENSIONS[kind].some((ext) => name.endsWith(ext));
  if (!typed || file.size === 0) return 'type';
  return file.size > rule.maxBytes ? 'size' : 'ok';
}

/** The file's bytes in base64. */
export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}

/** A file's size in words: megabytes from 1 MB, kilobytes below (one decimal at most). */
export function formatSize(bytes: number, locale: string): string {
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  return bytes >= MB ? `${number.format(bytes / MB)} MB` : `${number.format(bytes / 1024)} KB`;
}
