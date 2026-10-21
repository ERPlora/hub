// The box under the thread (WHATSAPP_INBOX-F32, F33, F36): «Reply» writes to the customer within 24
// hours of her last message and «Template» opens the approved ones; «Internal note» writes for the
// team. Out of the window only «Template» is left, with the reason; with the number not connected, the
// month spent or no erplora.com, nothing is offered and the reason is said. A refusal keeps the text,
// and sending it again uses the same key (never twice).
import { formatDateTime } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, flush, ionValue, mountInbox, settle } from '../__tests__/mount-inbox';
import type { ConversationDetailOut } from '../operations';
import MessageComposer from './MessageComposer.vue';
import TemplateSendModal from './TemplateSendModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const NOW = new Date('2026-10-15T10:00:00Z');

const conversation = (over: Partial<ConversationDetailOut> = {}): ConversationDetailOut => ({
  id: 'c1',
  phone: '+34600111222',
  contact_name: 'Ana',
  display_name: 'Ana',
  customer_id: null,
  customer_name: '',
  assigned_to_id: null,
  assigned_to_name: '',
  status: 'open',
  unread_count: 0,
  last_message_at: '2026-10-15T09:50:00Z',
  last_message_preview: 'Hola',
  last_message_direction: 'inbound',
  last_message_kind: 'text',
  last_inbound_at: '2026-10-15T09:50:00Z',
  created_at: '2026-10-15T09:50:00Z',
  window_open: true,
  window_expires_at: '2026-10-16T09:50:00Z',
  can_send: true,
  send_blocked: null,
  ...over,
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string; fill?: string; placeholder?: string };

async function setup(over: Partial<ConversationDetailOut> = {}, locale: 'en' | 'es' = 'en') {
  // The composer subscribes to nothing until «Template» is pressed: no stream to open here.
  const m = await mountInbox(MessageComposer, { props: { conversation: conversation(over), now: NOW }, locale });
  await settle();
  const text = () => m.inDoc('whatsapp-inbox-composer-text') as Control;
  const send = () => m.inDoc('whatsapp-inbox-composer-send') as Control;
  return { ...m, text, send };
}

describe('MessageComposer: reply (WHATSAPP_INBOX-F32)', () => {
  it('writes in an outlined md box; Send waits for a text; the window says until when', async () => {
    const s = await setup();
    expect([s.text().label, s.text().placeholder, s.text().fill, s.text().getAttribute('mode')]).toEqual([
      'Write to the customer',
      'Write a message…',
      'outline',
      'md',
    ]);
    expect(s.send().disabled).toBe(true);
    await ionValue(s.text(), 'Sí, mañana a las 10', 'ionInput');
    expect(s.send().disabled).toBe(false);
    const until = formatDateTime('2026-10-16T09:50:00Z', 'en', { timeZone: 'Europe/Madrid' });
    expect(s.find('whatsapp-inbox-composer-window').text()).toBe(`You can write freely until ${until}.`);
  });

  it('sends through erplora.com and empties the box; the thread shows it by itself', async () => {
    const s = await setup();
    s.answer(201, { id: 'm9', status: 'sent' });
    await ionValue(s.text(), '  Sí, a las 10  ', 'ionInput');
    await click(s.send());
    await flush();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/whatsapp_inbox/messages/send',
        query: {},
        body: { id: 'c1', text: 'Sí, a las 10', client_message_id: expect.any(String) },
      },
    ]);
    expect(s.text().value).toBe('');
  });

  it('a failed send keeps the text and says why; sending again, even retouched, uses the same key', async () => {
    const s = await setup();
    s.answer(503, { error: { code: 'service_unavailable', message: 'The hub did not answer.' } });
    await ionValue(s.text(), 'Hola', 'ionInput');
    await click(s.send());
    await flush();
    expect(s.find('whatsapp-inbox-composer-error').text()).toContain('The hub did not answer.');
    expect(s.text().value).toBe('Hola');
    // The hub may have kept it: a retouched text goes with the same key, so it is never sent twice.
    await ionValue(s.text(), 'Hola, Ana', 'ionInput');
    s.answer(201, { id: 'm9', status: 'queued' });
    await click(s.send());
    await flush();
    const keys = s.sent().map((call) => (call.body as { client_message_id: string }).client_message_id);
    expect(keys[1]).toBe(keys[0]);
    // Once the hub took it, the next message gets a key of its own.
    await ionValue(s.text(), 'Otra cosa', 'ionInput');
    await click(s.send());
    await flush();
    expect(s.sent().map((call) => (call.body as { client_message_id: string }).client_message_id)[2]).not.toBe(keys[0]);
  });

  it('Ctrl+Enter sends', async () => {
    const s = await setup();
    s.answer(201, { id: 'm9' });
    await ionValue(s.text(), 'Hola', 'ionInput');
    s.text().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }));
    await flush();
    expect(s.sent()).toHaveLength(1);
  });

  it('after 24 hours only a template is left, and it says why', async () => {
    const s = await setup({ window_open: false, window_expires_at: '2026-10-14T09:00:00Z' });
    expect(s.find('whatsapp-inbox-composer-closed').text()).toContain('More than 24 hours have passed');
    expect(s.inDoc('whatsapp-inbox-composer-text')).toBeNull();
    expect((s.inDoc('whatsapp-inbox-composer-template') as Control).disabled).toBe(false);
  });

  it('a window that closes while it is on screen closes the box too', async () => {
    const s = await setup({ window_expires_at: '2026-10-15T09:59:00Z' });
    expect(s.find('whatsapp-inbox-composer-closed').exists()).toBe(true);
  });

  it('with the number not connected nothing is offered and the reason is said', async () => {
    const s = await setup({ can_send: false, send_blocked: 'not_connected' });
    expect(s.find('whatsapp-inbox-composer-blocked').text()).toContain('WhatsApp is not connected');
    // It is connected (or reconnected) in the inbox's own Settings (WHATSAPP_INBOX-F01, F02), not in erplora.com.
    expect(s.find('whatsapp-inbox-composer-blocked').text()).toContain('in Settings');
    expect(s.find('whatsapp-inbox-composer-blocked').text()).not.toContain('erplora.com');
    expect(s.find('whatsapp-inbox-composer-blocked').attributes('data-code')).toBe('not_connected');
    expect(s.send().disabled).toBe(true);
    expect((s.inDoc('whatsapp-inbox-composer-template') as Control).disabled).toBe(true);
  });

  it('«Template» opens «Send a template» for this conversation; the templates are read only from then on', async () => {
    const s = await setup();
    // Opening a conversation never reopens the tab's stream a second time just for the templates.
    expect(s.wrapper.findComponent(TemplateSendModal).exists()).toBe(false);
    expect(s.params('whatsapp_inbox.template.list')).toEqual([]);
    await click(s.inDoc('whatsapp-inbox-composer-template'));
    const modal = s.wrapper.findComponent(TemplateSendModal);
    expect(modal.props('conversationId')).toBe('c1');
    expect(modal.props('open')).toBe(true);
    expect(s.params('whatsapp_inbox.template.list')).toEqual([{ sendable: true, limit: 100 }]);
  });
});

describe('MessageComposer: internal note (WHATSAPP_INBOX-F36)', () => {
  it('names each tab with a hook of its own (Ionic keeps `value` as a property, not an attribute)', async () => {
    const s = await setup();
    expect(s.inDoc('whatsapp-inbox-composer-mode-reply')?.textContent?.trim()).toBe('Reply');
    expect(s.inDoc('whatsapp-inbox-composer-mode-note')?.textContent?.trim()).toBe('Internal note');
  });


  it('writes a note for the team, also when nothing can be sent', async () => {
    const s = await setup({ can_send: false, send_blocked: 'cap_reached', window_open: false });
    await ionValue(s.inDoc('whatsapp-inbox-composer-mode'), 'note');
    const note = s.inDoc('whatsapp-inbox-composer-note') as Control;
    expect(note.placeholder).toBe('Write a note only the team sees…');
    const add = s.inDoc('whatsapp-inbox-composer-add-note') as Control;
    expect(add.disabled).toBe(true);
    s.answer(201, { id: 'n1' });
    await ionValue(note, 'Llamar mañana', 'ionInput');
    await click(add);
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/whatsapp_inbox/notes', query: {}, body: { id: 'c1', text: 'Llamar mañana' } }]);
    expect((s.inDoc('whatsapp-inbox-composer-note') as Control).value).toBe('');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    const until = formatDateTime('2026-10-16T09:50:00Z', 'es', { timeZone: 'Europe/Madrid' });
    expect(s.find('whatsapp-inbox-composer-window').text()).toBe(`Puedes escribir libremente hasta el ${until}.`);
    expect(s.send().textContent?.trim()).toBe('Enviar');
  });
});
