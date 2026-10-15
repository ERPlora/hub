// The thread of a conversation (WHATSAPP_INBOX-F05, F06, F08, F34, F36): oldest first, the customer's
// messages on the left and the business's on the right with their delivery status, the owner's replies
// from the phone marked, attachments opened at erplora.com, internal notes in their own colour with
// «Delete note» for whoever may; «View earlier», «No messages yet.», «Loading…» and the error.
import { describe, expect, it, vi } from 'vitest';

import { click, mountInbox } from '../__tests__/mount-inbox';
import type { MessageOut, NoteOut } from '../operations';
import ThreadView from './ThreadView.vue';

const NOW = new Date('2026-10-15T10:00:00Z');

const message = (over: Partial<MessageOut> = {}): MessageOut => ({
  id: 'm1',
  conversation_id: 'c1',
  direction: 'inbound',
  origin: 'customer',
  source: 'live',
  kind: 'text',
  body: 'Hola, ¿tenéis hora mañana?',
  media_url: '',
  media_mime_type: '',
  media_filename: '',
  media_caption: '',
  template_name: '',
  status: 'received',
  error_code: '',
  error_message: '',
  wa_message_id: 'wamid.1',
  reply_to: '',
  sent_by_name: '',
  sent_at: '2026-10-15T09:00:00Z',
  status_at: null,
  ...over,
});
const note = (over: Partial<NoteOut> = {}): NoteOut => ({
  id: 'n1',
  conversation_id: 'c1',
  text: 'Alérgica al tinte',
  author_id: 1,
  author_name: 'Ana',
  created_at: '2026-10-15T09:30:00Z',
  can_delete: true,
  ...over,
});

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] });
  const m = await mountInbox(ThreadView, { props: { messages: [], notes: [], loading: false, hasMore: false, now: NOW, ...props }, locale });
  vi.useRealTimers();
  const bubbles = () => m.wrapper.findAll('[data-testid="whatsapp-inbox-message"], [data-testid="whatsapp-inbox-note"]');
  return { ...m, bubbles };
}

describe('ThreadView', () => {
  it('paints messages and notes oldest first, each on its side', async () => {
    const s = await setup({
      messages: [
        message({ id: 'm2', direction: 'outbound', origin: 'hub', status: 'read', body: 'Sí, a las 10', sent_by_name: 'Luis', sent_at: '2026-10-15T09:45:00Z' }),
        message(),
      ],
      notes: [note()],
    });
    const bubbles = s.bubbles();
    expect(bubbles.map((b) => b.attributes('data-side'))).toEqual(['inbound', 'note', 'outbound']);
    expect(bubbles[0].text()).toContain('Hola, ¿tenéis hora mañana?');
    expect(bubbles[0].text()).toContain('11:00'); // 09:00 UTC on the business clock (Madrid, UTC+2)
    expect(bubbles[1].text()).toContain('Internal note');
    expect(bubbles[1].text()).toContain('Ana');
    expect(bubbles[2].text()).toContain('Read');
    expect(bubbles[2].text()).toContain('Luis');
  });

  it('marks what the owner wrote from the phone, and says why a message was not delivered', async () => {
    const s = await setup({
      messages: [
        message({ id: 'e', direction: 'outbound', origin: 'phone_app', status: 'sent', body: 'Desde el móvil' }),
        message({ id: 'f', direction: 'outbound', origin: 'hub', status: 'failed', error_message: 'Re-engagement message', sent_at: '2026-10-15T09:10:00Z' }),
      ],
    });
    const [echo, failed] = s.bubbles();
    expect(echo.find('[data-testid="whatsapp-inbox-message-from-phone"]').text()).toBe('From the phone');
    expect(failed.find('[data-testid="whatsapp-inbox-message-status"]').text()).toBe('Not delivered');
    expect(failed.text()).toContain("Meta's reason: Re-engagement message");
  });

  it('opens an attachment at erplora.com in a new tab, named by its kind, file and caption', async () => {
    const s = await setup({
      messages: [
        message({ kind: 'document', body: '', media_url: 'https://erplora.com/whatsapp/media/abc', media_mime_type: 'application/pdf', media_filename: 'presupuesto.pdf', media_caption: 'El presupuesto' }),
      ],
    });
    const media = s.find('whatsapp-inbox-message-media');
    expect(media.text()).toContain('Document');
    expect(media.text()).toContain('presupuesto.pdf');
    expect(media.text()).toContain('El presupuesto');
    const link = media.find('a');
    expect(link.attributes()).toMatchObject({ href: 'https://erplora.com/whatsapp/media/abc', target: '_blank', rel: 'noopener noreferrer' });
    expect(link.text()).toBe('Open the attachment');
  });

  it('a message without text nor attachment says its type in the reader’s language; a template says its name', async () => {
    const s = await setup({
      messages: [
        message({ id: 'l', kind: 'location', body: '' }),
        message({ id: 'p', kind: 'media_placeholder', body: '', sent_at: '2026-10-15T09:05:00Z' }),
        message({ id: 'x', kind: 'some_new_type', body: '', sent_at: '2026-10-15T09:06:00Z' }),
        message({ id: 't', kind: 'template', template_name: 'recordatorio', direction: 'outbound', origin: 'hub', status: 'sent', sent_at: '2026-10-15T09:20:00Z' }),
      ],
    });
    const [location, placeholder, unknown, template] = s.bubbles();
    expect(location.find('[data-testid="whatsapp-inbox-message-kind"]').text()).toBe('Location');
    expect(placeholder.find('[data-testid="whatsapp-inbox-message-kind"]').text()).toBe('Attachment on its way');
    expect(unknown.find('[data-testid="whatsapp-inbox-message-kind"]').text()).toBe('Message (some_new_type)');
    expect(template.text()).toContain('Template: recordatorio');
    const es = await setup({ messages: [message({ id: 'c', kind: 'contacts', body: '' })] }, 'es');
    expect(es.find('whatsapp-inbox-message-kind').text()).toBe('Contacto');
  });

  it('a reaction is not a bubble: it sits on the message it answers', async () => {
    const s = await setup({
      messages: [message({ id: 'r', kind: 'reaction', body: '👍', reply_to: 'wamid.1', sent_at: '2026-10-15T09:10:00Z' }), message()],
    });
    expect(s.bubbles()).toHaveLength(1);
    expect(s.find('whatsapp-inbox-message-reaction').text()).toBe('👍');
  });

  it('a message that has not left says «Sending…»; one without a final answer offers «Retry»', async () => {
    const s = await setup({
      messages: [
        message({ id: 'q', direction: 'outbound', origin: 'hub', status: 'queued', wa_message_id: null }),
        message({
          id: 'u',
          direction: 'outbound',
          origin: 'hub',
          status: 'sending',
          wa_message_id: null,
          error_code: 'whatsapp_inbox.saas_unreachable',
          error_message: 'erplora.com did not answer: the message has not left. Try again.',
          sent_at: '2026-10-15T09:10:00Z',
        }),
      ],
    });
    const [queued, stuck] = s.bubbles();
    expect(queued.find('[data-testid="whatsapp-inbox-message-status"]').text()).toBe('Sending…');
    expect(queued.find('[data-testid="whatsapp-inbox-message-retry"]').exists()).toBe(false);
    expect(stuck.find('[data-testid="whatsapp-inbox-message-status"]').text()).toBe('Not sent');
    expect(stuck.text()).toContain('erplora.com did not answer');
    await click(stuck.find('[data-testid="whatsapp-inbox-message-retry"]').element);
    expect(s.wrapper.emitted('retry')).toEqual([[expect.objectContaining({ id: 'u' })]]);
  });

  it('opens only attachments served over https', async () => {
    const s = await setup({
      messages: [message({ kind: 'image', body: '', media_url: 'http://evil.example/x.jpg', media_mime_type: 'image/jpeg' })],
    });
    expect(s.find('whatsapp-inbox-message-media').text()).toContain('Photo');
    expect(s.find('whatsapp-inbox-message-media').find('a').exists()).toBe(false);
  });

  it('offers «Delete note» only on the notes the reader may delete, and asks the page', async () => {
    const s = await setup({ notes: [note(), note({ id: 'n2', can_delete: false, created_at: '2026-10-15T09:40:00Z' })] });
    const buttons = s.wrapper.findAll('[data-testid="whatsapp-inbox-note-delete"]');
    expect(buttons).toHaveLength(1);
    await click(buttons[0].element);
    expect(s.wrapper.emitted('deleteNote')).toEqual([[expect.objectContaining({ id: 'n1' })]]);
  });

  it('«View earlier» asks for the previous page', async () => {
    const s = await setup({ messages: [message()], hasMore: true });
    await click(s.find('whatsapp-inbox-thread-earlier').element);
    expect(s.wrapper.emitted('earlier')).toHaveLength(1);
  });

  it('empty, loading and failed', async () => {
    expect((await setup({})).find('whatsapp-inbox-thread-empty').text()).toBe('No messages yet.');
    expect((await setup({ loading: true })).find('whatsapp-inbox-thread-loading').exists()).toBe(true);
    expect((await setup({ loading: true })).find('whatsapp-inbox-thread-empty').exists()).toBe(false);
    expect((await setup({ error: 'Boom' })).find('whatsapp-inbox-thread-error').text()).toContain('Boom');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ messages: [message({ direction: 'outbound', origin: 'hub', status: 'delivered' })] }, 'es');
    expect(s.find('whatsapp-inbox-message-status').text()).toBe('Entregado');
  });
});
