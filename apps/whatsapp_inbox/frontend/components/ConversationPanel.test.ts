// The open conversation, in a panel above the inbox (WHATSAPP_INBOX-F05, F07, F10, F35, F37): who it is
// and their number, the status and «Close»; the customer card (View card, Unlink) or «Link to a card» /
// «Create card»; «Assigned to» (the team for whoever may assign, «Assign to me» for everyone); the
// status buttons; the live thread with its notes and «View earlier»; the composer; «Erase this number's
// data» for owner and admin, asked first. Opening it leaves it read.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { click, EMPLOYEE, errorFrame, flush, ionValue, MANAGER, type MountOptions, mountInbox, settle } from '../__tests__/mount-inbox';
import type { ChannelOut, ConversationDetailOut, MessageOut, NoteOut } from '../operations';
import MessageComposer from './MessageComposer.vue';
import ConversationPanel from './ConversationPanel.vue';
import ThreadView from './ThreadView.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => mocks.confirm.mockReset());

const DETAIL = 'whatsapp_inbox.conversation.detail';
const MESSAGES = 'whatsapp_inbox.message.list';
const NOTES = 'whatsapp_inbox.note.list';

const detail = (over: Partial<ConversationDetailOut> = {}): ConversationDetailOut => ({
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
  window_expires_at: '2099-10-16T09:50:00Z',
  can_send: true,
  send_blocked: null,
  ...over,
});
const message = (id: string, sent_at: string): MessageOut => ({
  id,
  conversation_id: 'c1',
  direction: 'inbound',
  origin: 'customer',
  source: 'live',
  kind: 'text',
  body: `texto ${id}`,
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
const NOTE: NoteOut = { id: 'n1', conversation_id: 'c1', text: 'Llamar', author_id: 1, author_name: 'Ana', created_at: '2026-10-15T09:55:00Z', can_delete: true };
const page = <T>(rows: T[], total = rows.length) => ({ rows, total, limit: 50, offset: 0 });

/** CustomerSearch of the Customers app, stood in for by a button that picks Marta's card. */
const CustomerSearchStub = defineComponent({
  emits: ['update:modelValue'],
  setup(_, { emit }) {
    return () =>
      h('button', { 'data-testid': 'customer-search-stub', onClick: () => emit('update:modelValue', { customer_id: 'k9', customer_name: 'Marta' }) }, 'pick');
  },
});

async function setup(over: Partial<ConversationDetailOut> = {}, options: MountOptions = {}) {
  const m = await mountInbox(ConversationPanel, { props: { conversationId: 'c1' }, stubs: { CustomerSearch: CustomerSearchStub }, ...options });
  await m.live();
  await m.result(DETAIL, detail(over));
  await m.result(MESSAGES, page([message('m1', '2026-10-15T09:50:00Z')]));
  await m.result(NOTES, page([NOTE]));
  await settle();
  return m;
}

describe('ConversationPanel: what it shows', () => {
  it('follows the conversation, its last 50 messages and its notes', async () => {
    const s = await setup();
    expect(s.params(DETAIL)).toEqual([{ id: 'c1' }]);
    expect(s.params(MESSAGES)).toEqual([{ id: 'c1', limit: 50, offset: 0 }]);
    expect(s.params(NOTES)).toEqual([{ id: 'c1', limit: 100 }]);
    expect(s.find('whatsapp-inbox-detail-name').text()).toBe('Ana');
    expect(s.find('whatsapp-inbox-detail-phone').text()).toBe('+34600111222');
    expect(s.find('whatsapp-inbox-detail-status').text()).toContain('Open');
    const thread = s.wrapper.findComponent(ThreadView);
    expect(thread.props('messages')).toHaveLength(1);
    expect(thread.props('notes')).toEqual([NOTE]);
    expect(s.wrapper.findComponent(MessageComposer).props('conversation')).toMatchObject({ id: 'c1' });
    expect(s.wrapper.findComponent(MessageComposer).props('channel')).toBeNull();
  });

  it('hands the business’s channel to the box, which says why nothing can be sent (WHATSAPP_INBOX-F13)', async () => {
    const channel: ChannelOut = {
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
    const s = await setup({ can_send: false, send_blocked: 'cap_reached' }, { props: { conversationId: 'c1', channel } });
    expect(s.wrapper.findComponent(MessageComposer).props('channel')).toEqual(channel);
    expect(s.find('whatsapp-inbox-composer-blocked').text()).toContain('Your plan does not include WhatsApp messages');
  });

  it('«View earlier» follows one more page of 50', async () => {
    const s = await setup();
    await s.result(MESSAGES, page([message('m1', '2026-10-15T09:50:00Z')], 120));
    s.wrapper.findComponent(ThreadView).vm.$emit('earlier');
    await flush();
    expect(s.params(MESSAGES)).toEqual([
      { id: 'c1', limit: 50, offset: 0 },
      { id: 'c1', limit: 50, offset: 50 },
    ]);
  });

  it('opening a conversation with unread messages leaves it read', async () => {
    const s = await setup({ unread_count: 3 });
    expect(s.sent()).toContainEqual({ method: 'POST', path: '/api/whatsapp_inbox/conversations/mark_read', query: {}, body: { id: 'c1' } });
  });

  it('«Close» goes back to the list', async () => {
    const s = await setup();
    await click(s.inDoc('whatsapp-inbox-detail-close'));
    expect(s.wrapper.emitted('close')).toHaveLength(1);
  });
});

describe('ConversationPanel: the card (WHATSAPP_INBOX-F37)', () => {
  it('without a card: link one from Customers’ search or create it', async () => {
    const s = await setup();
    s.answer(200, detail({ customer_id: 'k9', customer_name: 'Marta' }));
    await click(s.inDoc('customer-search-stub'));
    await click(s.inDoc('whatsapp-inbox-detail-create-card'));
    expect(s.sent().filter((c) => c.path.endsWith('/link_customer')).map((c) => c.body)).toEqual([
      { id: 'c1', customer_id: 'k9' },
      { id: 'c1', create: true },
    ]);
  });

  it('with a card: its name, «View card» and «Unlink»', async () => {
    const s = await setup({ customer_id: 'k9', customer_name: 'Marta Ruiz' });
    expect(s.find('whatsapp-inbox-detail-customer').text()).toContain('Marta Ruiz');
    expect(s.inDoc('whatsapp-inbox-detail-view-card')?.getAttribute('href')).toBe('/customer/customers/k9');
    s.answer(200, detail());
    await click(s.inDoc('whatsapp-inbox-detail-unlink'));
    expect(s.sent().at(-1)?.body).toEqual({ id: 'c1', unlink: true });
  });
});

describe('ConversationPanel: assignment and status (WHATSAPP_INBOX-F07, F35)', () => {
  it('«Assign to me» never takes it from somebody else', async () => {
    const s = await setup({}, { session: EMPLOYEE });
    s.answer(200, detail({ assigned_to_id: 2, assigned_to_name: 'Luis' }));
    await click(s.inDoc('whatsapp-inbox-detail-assign-me'));
    expect(s.sent().at(-1)?.body).toEqual({ id: 'c1', assignee: 'me', only_if_unassigned: true });
    // An employee does not choose somebody else.
    expect(s.inDoc('whatsapp-inbox-detail-assignee')).toBeNull();
  });

  it('a manager chooses anybody of the team and can remove the assignment', async () => {
    const s = await setup({ assigned_to_id: 7, assigned_to_name: 'Marta' }, { session: MANAGER });
    expect(s.inDoc('whatsapp-inbox-detail-assignee')).not.toBeNull();
    s.answer(200, detail());
    await click(s.inDoc('whatsapp-inbox-detail-unassign'));
    expect(s.sent().at(-1)?.body).toEqual({ id: 'c1', unassign: true });
  });

  it('who has it is said; an employee may only take it off themselves', async () => {
    const mine = await setup({ assigned_to_id: 2, assigned_to_name: 'Luis' }, { session: EMPLOYEE });
    expect(mine.find('whatsapp-inbox-detail-assigned').text()).toContain('Luis');
    expect(mine.inDoc('whatsapp-inbox-detail-unassign')).not.toBeNull();
    expect(mine.inDoc('whatsapp-inbox-detail-assign-me')).toBeNull();
    const theirs = await setup({ assigned_to_id: 7, assigned_to_name: 'Marta' }, { session: EMPLOYEE });
    expect(theirs.inDoc('whatsapp-inbox-detail-unassign')).toBeNull();
  });

  it('the status buttons set open, pending or closed', async () => {
    const s = await setup();
    s.answer(200, detail({ status: 'pending' }));
    await ionValue(s.inDoc('whatsapp-inbox-detail-status-choice'), 'pending');
    expect(s.sent().at(-1)).toEqual({ method: 'POST', path: '/api/whatsapp_inbox/conversations/set_status', query: {}, body: { id: 'c1', status: 'pending' } });
  });

  it('a refused change says why', async () => {
    const s = await setup({}, { session: EMPLOYEE });
    s.answer(409, { error: { code: 'whatsapp_inbox.already_assigned', message: 'This conversation is already with Marta.' } });
    await click(s.inDoc('whatsapp-inbox-detail-assign-me'));
    await flush();
    expect(s.find('whatsapp-inbox-action-error').text()).toContain('This conversation is already with Marta.');
  });
});

describe('ConversationPanel: erasing and notes (WHATSAPP_INBOX-F10, F36)', () => {
  it('only owner and admin see «Erase this number’s data»; it asks first, naming the number', async () => {
    expect((await setup({}, { session: MANAGER })).inDoc('whatsapp-inbox-detail-erase')).toBeNull();
    const s = await setup();
    mocks.confirm.mockResolvedValue(false);
    await click(s.inDoc('whatsapp-inbox-detail-erase'));
    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Erase this number's data?",
        message: 'Every message, attachment and note of +34600111222 will be erased. This cannot be undone.',
        tone: 'danger',
        confirmLabel: 'Erase data',
      }),
    );
    expect(s.sent().some((c) => c.path.endsWith('/erase'))).toBe(false);
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, { id: 'c1' });
    await click(s.inDoc('whatsapp-inbox-detail-erase'));
    await flush();
    expect(s.sent().at(-1)?.path).toBe('/api/whatsapp_inbox/conversations/erase');
    expect(s.wrapper.emitted('erased')).toHaveLength(1);
  });

  it('«Retry» on a message that did not leave hands it to erplora.com again', async () => {
    const s = await setup();
    s.answer(200, { ...message('m9', '2026-10-15T09:58:00Z'), status: 'sending' });
    s.wrapper.findComponent(ThreadView).vm.$emit('retry', message('m9', '2026-10-15T09:58:00Z'));
    await flush();
    expect(s.sent().at(-1)).toEqual({ method: 'POST', path: '/api/whatsapp_inbox/messages/retry', query: {}, body: { id: 'm9' } });
  });

  it('deleting a note asks first', async () => {
    const s = await setup();
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, { id: 'n1' });
    s.wrapper.findComponent(ThreadView).vm.$emit('deleteNote', NOTE);
    await flush();
    await flush();
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Delete this note?', tone: 'danger' }));
    expect(s.sent().at(-1)).toEqual({ method: 'POST', path: '/api/whatsapp_inbox/notes/delete', query: {}, body: { id: 'n1' } });
  });

  it('a conversation that cannot be loaded says why', async () => {
    const m = await mountInbox(ConversationPanel, { props: { conversationId: 'c1' }, stubs: { CustomerSearch: CustomerSearchStub } });
    await m.live();
    m.net.lastStream().push(errorFrame(m.subId(DETAIL), 'whatsapp_inbox.conversation_not_found'));
    await flush();
    expect(m.find('whatsapp-inbox-detail-error').text()).toContain('msg whatsapp_inbox.conversation_not_found');
  });
});
