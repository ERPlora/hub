// The thread of a conversation (WHATSAPP_INBOX-F05, F36): its messages and its internal notes in one
// timeline, oldest first (the server pages them newest first); and a template's text with its variables.
import { describe, expect, it } from 'vitest';

import type { MessageOut, NoteOut } from '../operations';
import { kindLabel, reactionsByMessage, renderTemplate, timeline } from './thread';

const message = (id: string, sent_at: string): MessageOut => ({
  id,
  conversation_id: 'c1',
  direction: 'inbound',
  origin: 'customer',
  source: 'live',
  kind: 'text',
  body: id,
  media_url: '',
  media_mime_type: '',
  media_filename: '',
  media_caption: '',
  template_name: '',
  status: 'received',
  error_code: '',
  error_message: '',
  wa_message_id: `wamid.${id}`,
  reply_to: '',
  reply_id: '',
  sent_by_name: '',
  sent_at,
  status_at: null,
});
const note = (id: string, created_at: string): NoteOut => ({
  id,
  conversation_id: 'c1',
  text: id,
  author_id: '01a16000-0000-7000-8000-0000000000b1',
  author_name: 'Ana',
  created_at,
  can_delete: true,
});

describe('timeline', () => {
  it('interleaves messages and notes by time, oldest first', () => {
    const items = timeline(
      [message('m3', '2026-10-15T10:03:00Z'), message('m1', '2026-10-15T10:01:00Z')],
      [note('n2', '2026-10-15T10:02:00Z')],
    );
    expect(items.map((item) => [item.type, item.id])).toEqual([
      ['message', 'm1'],
      ['note', 'n2'],
      ['message', 'm3'],
    ]);
  });

  it('keeps a stable order for the same instant (by id)', () => {
    const at = '2026-10-15T10:00:00Z';
    expect(timeline([message('b', at), message('a', at)], []).map((item) => item.id)).toEqual(['a', 'b']);
  });

  it('nothing loaded yet is an empty thread', () => {
    expect(timeline(undefined, undefined)).toEqual([]);
  });
});

describe('renderTemplate', () => {
  it('puts each variable in its {{n}} and leaves the empty ones visible', () => {
    expect(renderTemplate('Hola {{1}}, te esperamos el {{2}}.', ['Ana', 'viernes'])).toBe('Hola Ana, te esperamos el viernes.');
    expect(renderTemplate('Hola {{1}}, te esperamos el {{2}}.', ['Ana'])).toBe('Hola Ana, te esperamos el {{2}}.');
    expect(renderTemplate('Hola {{ 1 }}', ['Ana'])).toBe('Hola Ana');
  });
});

describe('reactions', () => {
  it('are not bubbles of the timeline: they sit on the message they answer', () => {
    const reaction = { ...message('r', '2026-10-15T10:05:00Z'), kind: 'reaction', body: '👍', reply_to: 'wamid.m1' };
    const items = timeline([reaction, message('m1', '2026-10-15T10:00:00Z')], []);
    expect(items.map((item) => item.id)).toEqual(['m1']);
    expect(reactionsByMessage([reaction, { ...reaction, id: 'r2', body: '' }])).toEqual(new Map([['wamid.m1', ['👍']]]));
  });
});

describe('kindLabel', () => {
  it('names Meta’s types through the catalogue, and an unknown one by itself', () => {
    const t = (key: string, named?: Record<string, unknown>) => (named ? `${key}:${JSON.stringify(named)}` : key);
    expect(kindLabel('location', t)).toBe('whatsapp_inbox.thread.kinds.location');
    expect(kindLabel('media_placeholder', t)).toBe('whatsapp_inbox.thread.kinds.media_placeholder');
    expect(kindLabel('brand_new', t)).toBe('whatsapp_inbox.thread.kinds.other:{"kind":"brand_new"}');
  });
});
