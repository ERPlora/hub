// The thread of a conversation (WHATSAPP_INBOX-F05, F36): its messages and its internal notes in one
// timeline, oldest first, the way a thread is read downwards (the server pages both newest first); and a
// template's text with its variables in place, as the server renders it when it sends one.
import type { MessageOut, NoteOut } from '../operations';

export type ThreadItem =
  | { type: 'message'; id: string; at: string; message: MessageOut }
  | { type: 'note'; id: string; at: string; note: NoteOut };

export function timeline(messages: readonly MessageOut[] | undefined, notes: readonly NoteOut[] | undefined): ThreadItem[] {
  const items: ThreadItem[] = [
    // A reaction is not news: it sits on the message it answers (`reactionsByMessage`).
    ...(messages ?? [])
      .filter((message) => message.kind !== 'reaction')
      .map((message) => ({ type: 'message' as const, id: message.id, at: message.sent_at, message })),
    ...(notes ?? []).map((note) => ({ type: 'note' as const, id: note.id, at: note.created_at, note })),
  ];
  return items.sort((a, b) => {
    const delta = new Date(a.at).getTime() - new Date(b.at).getTime();
    return delta !== 0 ? delta : a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

/** `body` with each `{{n}}` replaced by `variables[n - 1]`; a variable not given stays visible. */
export function renderTemplate(body: string, variables: readonly string[]): string {
  return body.replace(/\{\{\s*(\d+)\s*\}\}/g, (whole, index: string) => {
    const value = variables[Number(index) - 1];
    return value ? value : whole;
  });
}

/** The reactions (👍) of the thread by the WhatsApp id of the message they answer; an empty one (a
 *  reaction taken back) adds nothing. */
export function reactionsByMessage(messages: readonly MessageOut[] | undefined): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const message of messages ?? []) {
    if (message.kind !== 'reaction' || !message.reply_to || !message.body) continue;
    out.set(message.reply_to, [...(out.get(message.reply_to) ?? []), message.body]);
  }
  return out;
}

/** Meta's message types the catalogue names (`whatsapp_inbox.thread.kinds.*`). */
const KNOWN_KINDS = new Set([
  'text',
  'image',
  'sticker',
  'audio',
  'video',
  'document',
  'location',
  'contacts',
  'interactive',
  'button',
  'reaction',
  'unsupported',
  'media_placeholder',
  'template',
]);

/** A message's type in the reader's language; one Meta adds tomorrow is named as it came. */
export function kindLabel(kind: string, t: (key: string, named?: Record<string, unknown>) => string): string {
  return KNOWN_KINDS.has(kind) ? t(`whatsapp_inbox.thread.kinds.${kind}`) : t('whatsapp_inbox.thread.kinds.other', { kind });
}
