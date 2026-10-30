// The box under the thread (WHATSAPP_INBOX-F32, F33, F36): «Reply» writes to the customer within 24
// hours of her last message and «Template» opens the approved ones; «Internal note» writes for the
// team. Out of the window only «Template» is left, with the reason; with the number not connected, the
// month spent or no erplora.com, nothing is offered and the reason is said. A refusal keeps the text,
// and sending it again uses the same key (never twice).
import { formatDateTime } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, flush, ionValue, mountInbox, settle } from '../__tests__/mount-inbox';
import type { ChannelOut, ConversationDetailOut } from '../operations';
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
  flagged: false,
  created_at: '2026-10-15T09:50:00Z',
  window_open: true,
  window_expires_at: '2026-10-16T09:50:00Z',
  can_send: true,
  send_blocked: null,
  ...over,
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string; fill?: string; placeholder?: string };

async function setup(
  over: Partial<ConversationDetailOut> = {},
  locale: 'en' | 'es' = 'en',
  extra: { channel?: ChannelOut | null; session?: typeof EMPLOYEE } = {},
) {
  // The composer subscribes to nothing until «Template» is pressed: no stream to open here.
  const props = { conversation: conversation(over), now: NOW, ...(extra.channel !== undefined ? { channel: extra.channel } : {}) };
  const m = await mountInbox(MessageComposer, { props, locale, session: extra.session });
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
    expect(s.params('whatsapp_inbox.template.list')).toEqual([{ fillable: true, limit: 100 }]);
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

describe('MessageComposer: the plan’s messages (WHATSAPP_INBOX-F13)', () => {
  const CHANNEL: ChannelOut = {
    status: 'connected',
    phone_number: '+34910000000',
    display_name: 'Peluquería Ana',
    monthly_limit: 0,
    monthly_usage: 0,
    cap_reached: true,
    synced_at: '2026-10-15T09:00:00Z',
    manage_url: 'http://localhost:8001',
    plans_url: 'http://localhost:8001/store/plans',
  };
  const BLOCKED = { can_send: false, send_blocked: 'cap_reached' as const };

  it('a plan without WhatsApp messages: «Send» says so instead of sending, «Upgrade plan» for whoever configures', async () => {
    const s = await setup(BLOCKED, 'en', { channel: CHANNEL });
    const blocked = s.find('whatsapp-inbox-composer-blocked');
    expect(blocked.attributes('data-code')).toBe('cap_reached');
    expect(blocked.text()).toContain('Your plan does not include WhatsApp messages: nothing can be sent.');
    expect(blocked.text()).not.toContain('next month');
    expect(s.send().disabled).toBe(true);
    expect((s.inDoc('whatsapp-inbox-composer-template') as Control).disabled).toBe(true);
    expect(s.find('whatsapp-inbox-composer-upgrade').attributes()).toMatchObject({
      href: 'http://localhost:8001/store/plans',
      target: '_blank',
      rel: 'noopener',
    });
    const employee = await setup(BLOCKED, 'en', { channel: CHANNEL, session: EMPLOYEE });
    expect(employee.find('whatsapp-inbox-composer-blocked').text()).toContain('Your plan does not include WhatsApp messages');
    expect(employee.find('whatsapp-inbox-composer-upgrade').exists()).toBe(false);
  });

  it('the month spent keeps its own words, with «Upgrade plan»; without the channel, only the words', async () => {
    const spent = await setup(BLOCKED, 'en', { channel: { ...CHANNEL, monthly_limit: 150, monthly_usage: 150 } });
    expect(spent.find('whatsapp-inbox-composer-blocked').text()).toContain("This month's WhatsApp messages of your plan are spent");
    expect(spent.find('whatsapp-inbox-composer-upgrade').text()).toBe('Upgrade plan');
    const unknown = await setup(BLOCKED);
    expect(unknown.find('whatsapp-inbox-composer-blocked').text()).toContain("This month's WhatsApp messages of your plan are spent");
    expect(unknown.find('whatsapp-inbox-composer-upgrade').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup(BLOCKED, 'es', { channel: CHANNEL });
    expect(s.find('whatsapp-inbox-composer-blocked').text()).toContain('Tu plan no incluye mensajes de WhatsApp: no se puede enviar nada.');
    expect(s.find('whatsapp-inbox-composer-upgrade').text()).toBe('Mejorar el plan');
  });

  it('while the number needs reconnecting, «Send» says so as «Your number» does, never «not connected» (WHATSAPP_INBOX-F02)', async () => {
    const reconnect = { ...CHANNEL, status: 'reconnect_needed' as const, monthly_limit: 150, monthly_usage: 3, cap_reached: false };
    const off = { can_send: false, send_blocked: 'not_connected' as const };
    for (const [locale, said] of [
      ['en', 'The number needs reconnecting in Settings to send.'],
      ['es', 'Hay que reconectar el número en Ajustes para enviar.'],
    ] as const) {
      const s = await setup(off, locale, { channel: reconnect });
      const blocked = s.find('whatsapp-inbox-composer-blocked');
      expect(blocked.text(), locale).toBe(said);
      expect(blocked.text(), locale).not.toMatch(/not connected|no está conectado/);
      expect(s.send().disabled, locale).toBe(true);
    }
    // Disconnected for good, it is still «not connected».
    const gone = await setup(off, 'en', { channel: { ...reconnect, status: 'not_connected' } });
    expect(gone.find('whatsapp-inbox-composer-blocked').text()).toContain('WhatsApp is not connected');
  });
});
