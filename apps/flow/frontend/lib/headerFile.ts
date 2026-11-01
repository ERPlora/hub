// The file of a WhatsApp template's header in a «Send a message» step (WORKBOOK FLOW-F32; the old hub's HUB-F112):
// what each kind takes, checked here before the upload so a wrong one is said at once. The WhatsApp inbox checks it
// again by the file's bytes when it keeps it (`whatsapp_inbox.template_sample.upload`): these are Meta's limits, the
// same the inbox's own form says.

export type HeaderFileKind = 'IMAGE' | 'VIDEO' | 'DOCUMENT';

const MB = 1024 * 1024;

export interface HeaderFileRule {
  /** The `<input type="file" accept>` list. */
  accept: string;
  maxBytes: number;
}

/** JPEG or PNG up to 5 MB, MP4 up to 16 MB, PDF up to 25 MB. */
export const HEADER_FILE_RULES: Readonly<Record<HeaderFileKind, HeaderFileRule>> = {
  IMAGE: { accept: 'image/jpeg,image/png', maxBytes: 5 * MB },
  VIDEO: { accept: 'video/mp4', maxBytes: 16 * MB },
  DOCUMENT: { accept: 'application/pdf', maxBytes: 25 * MB },
};

const EXTENSIONS: Readonly<Record<HeaderFileKind, readonly string[]>> = {
  IMAGE: ['.jpg', '.jpeg', '.png'],
  VIDEO: ['.mp4'],
  DOCUMENT: ['.pdf'],
};

/** The kind of file a template's header asks for; `null` for a text header or none. */
export function headerFileKind(format: string | null | undefined): HeaderFileKind | null {
  return format === 'IMAGE' || format === 'VIDEO' || format === 'DOCUMENT' ? format : null;
}

/** Whether `file` goes as `kind`'s header: `ok`, or what is wrong with it (`type`, `size`). A browser that names
 *  no type is judged by the extension. */
export function judgeHeaderFile(file: File, kind: HeaderFileKind): 'ok' | 'type' | 'size' {
  const rule = HEADER_FILE_RULES[kind];
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  const typed = type ? rule.accept.split(',').includes(type) : EXTENSIONS[kind].some((ext) => name.endsWith(ext));
  if (!typed || file.size === 0) return 'type';
  return file.size > rule.maxBytes ? 'size' : 'ok';
}

/** A file's size in words: megabytes from 1 MB, kilobytes below (one decimal at most). */
export function formatFileSize(bytes: number, locale: string): string {
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  return bytes >= MB ? `${number.format(bytes / MB)} MB` : `${number.format(bytes / 1024)} KB`;
}
