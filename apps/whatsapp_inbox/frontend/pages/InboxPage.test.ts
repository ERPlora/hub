// WhatsApp inbox → Inbox (WHATSAPP_INBOX-F03, F05, F09, F10, F13; the WORKBOOK's screens): the live
// `whatsapp_inbox.conversation.list` in a server-side DataTable — Contact, Phone, Status, Assigned to,
// Unread and Last message —, «Filter contact or phone…», filters by status, assignment and unread, 50 a
// page, latest activity first; «Open» (or the row) opens the conversation in a panel above the list
// (also from `?conversation=`); the notices: number not connected (with «Go to erplora.com» for whoever
// configures), reconnect, month spent, number erased; every state of the screen.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountInbox } from '../__tests__/mount-inbox';
import ConversationPanel from '../components/ConversationPanel.vue';
import type { ChannelOut, ConversationOut } from '../operations';
import InboxPage from './InboxPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const LIST = 'whatsapp_inbox.conversation.list';
const CHANNEL = 'whatsapp_inbox.channel.get';

const row = (over: Partial<ConversationOut> = {}): ConversationOut => ({
  id: 'c1',
  phone: '+34600111222',
  contact_name: 'Ana',
  display_name: 'Ana López',
  customer_id: 'k1',
  customer_name: 'Ana López',
  assigned_to_id: null,
  assigned_to_name: '',
  status: 'open',
  unread_count: 2,
  last_message_at: '2026-03-10T08:00:00Z',
  last_message_preview: 'Hola',
  last_message_direction: 'inbound',
  last_message_kind: 'text',
  last_inbound_at: '2026-03-10T08:00:00Z',
  created_at: '2026-03-10T08:00:00Z',
  ...over,
});
const PAGE = {
  rows: [row(), row({ id: 'c2', phone: '+34600999888', contact_name: '', display_name: '+34600999888', customer_id: null, customer_name: '', status: 'pending', unread_count: 0, assigned_to_id: 7, assigned_to_name: 'Marta' })],
  total: 2,
  limit: 50,
  offset: 0,
};
const CONNECTED: ChannelOut = {
  status: 'connected',
  phone_number: '+34910000000',
  display_name: 'Peluquería Ana',
  monthly_limit: 150,
  monthly_usage: 10,
  cap_reached: false,
  synced_at: '2026-10-15T09:00:00Z',
  manage_url: 'http://localhost:8001',
};

async function setup(options: MountOptions = {}, channel: ChannelOut = CONNECTED) {
  const m = await mountInbox(InboxPage, options);
  await m.live();
  await m.result(CHANNEL, channel);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  return { ...m, table, prop };
}

describe('InboxPage: the live list', () => {
  it('follows the conversations, 50 by the latest activity, and paints the old columns', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ sort: 'last_message_at', dir: 'desc', limit: 50, offset: 0 }]);
    await s.result(LIST, PAGE);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('WhatsApp inbox');
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'whatsapp-inbox', pageSize: 50, total: 2, rowClickable: true });
    expect(s.prop('searchPlaceholder')).toBe('Filter contact or phone…');
    const columns = s.prop<{ key: string; label: string; format?: (v: unknown, r: ConversationOut) => string }[]>('columns');
    expect(columns.map((c) => c.label)).toEqual(['Contact', 'Phone', 'Status', 'Assigned to', 'Unread', 'Last message']);
    const cell = (key: string, r: ConversationOut) => {
      const column = columns.find((c) => c.key === key)!;
      return column.format ? column.format((r as unknown as Record<string, unknown>)[key], r) : String((r as unknown as Record<string, unknown>)[key]);
    };
    expect(cell('status', PAGE.rows[1])).toBe('Pending');
    expect(cell('unread_count', PAGE.rows[0])).toBe('2');
    expect(cell('unread_count', PAGE.rows[1])).toBe('—');
    expect(cell('assigned_to_name', PAGE.rows[0])).toBe('—');
    // On a pinned clock: no test reads the real time.
    vi.useFakeTimers({ now: new Date('2026-10-15T10:00:00Z'), toFake: ['Date'] });
    try {
      expect(cell('last_message_at', PAGE.rows[0])).toBe('03/10/2026');
      expect(cell('last_message_at', row({ last_message_at: '2026-10-15T08:30:00Z' }))).toBe('10:30');
      expect(cell('last_message_at', row({ last_message_at: '2026-10-14T08:30:00Z' }))).toBe('Yesterday');
    } finally {
      vi.useRealTimers();
    }
  });

  it('«Unread» has a cell of its own: the count, or «—» when it is all read', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    expect(s.wrapper.findAll('[data-testid="whatsapp-inbox-unread"]').map((cell) => cell.text())).toEqual(['2', '—']);
  });

  it('a last message without text is named by its type, in the reader’s language', async () => {
    const s = await setup();
    await s.result(LIST, { ...PAGE, rows: [row({ last_message_preview: '', last_message_kind: 'location' })], total: 1 });
    expect(s.find('whatsapp-inbox-preview').text()).toBe('Location');
    await s.result(LIST, { ...PAGE, rows: [row({ last_message_preview: 'presupuesto.pdf', last_message_kind: 'document' })], total: 1 }, {}, 2);
    expect(s.find('whatsapp-inbox-preview').text()).toBe('Document · presupuesto.pdf');
  });

  it('its filters go to the server: status, assigned to me or nobody, unread', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { status: 'pending', assigned: 'me', unread: 'true' });
    await flush();
    await s.reopen();
    expect(s.params(LIST)).toEqual([{ status: 'pending', assigned: 'me', unread: true, sort: 'last_message_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('a search goes to the server from the first page', async () => {
    const s = await setup();
    s.table().vm.$emit('update:search', '600 111');
    await flush();
    await s.reopen();
    expect(s.params(LIST)).toEqual([{ search: '600 111', sort: 'last_message_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('empty, no results and a failure with Retry', async () => {
    const s = await setup();
    await s.result(LIST, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No conversations.');
    s.net.lastStream().push(errorFrame(s.subId(LIST), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('Could not load the conversations.');
  });

  it('an app that is off here shows the notice instead of the list', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(LIST), 'app_inactive'));
    await flush();
    expect(s.find('whatsapp-inbox-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
  });
});

describe('InboxPage: the conversation above the list', () => {
  it('«Open» or the row opens it above the list and in the address; «Close» closes both', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    expect(s.prop<{ id: string; label: string }[]>('actions').map((a) => [a.id, a.label])).toEqual([['open', 'Open']]);
    s.table().vm.$emit('rowClick', PAGE.rows[0]);
    await flush();
    expect(s.wrapper.findComponent(ConversationPanel).props('conversationId')).toBe('c1');
    expect(s.router.currentRoute.value.query).toEqual({ conversation: 'c1' });
    s.table().vm.$emit('action', { actionId: 'open', row: PAGE.rows[1] });
    await flush();
    expect(s.wrapper.findComponent(ConversationPanel).props('conversationId')).toBe('c2');
    s.wrapper.findComponent(ConversationPanel).vm.$emit('close');
    await flush();
    expect(s.wrapper.findComponent(ConversationPanel).exists()).toBe(false);
    expect(s.router.currentRoute.value.query).toEqual({});
  });

  it('an address with ?conversation= opens it', async () => {
    const s = await setup({ path: '/whatsapp_inbox/inbox?conversation=c2' });
    expect(s.wrapper.findComponent(ConversationPanel).props('conversationId')).toBe('c2');
  });

  it('after erasing a number the panel closes and the page says so', async () => {
    const s = await setup({ path: '/whatsapp_inbox/inbox?conversation=c1' });
    s.wrapper.findComponent(ConversationPanel).vm.$emit('erased');
    await flush();
    expect(s.wrapper.findComponent(ConversationPanel).exists()).toBe(false);
    expect(s.find('whatsapp-inbox-erased').text()).toContain('The data of this number has been erased.');
  });
});

describe('InboxPage: the channel notices (WHATSAPP_INBOX-F01, F02, F13)', () => {
  it('a number not connected: the notice, and «Go to erplora.com» for whoever configures', async () => {
    const s = await setup({}, { ...CONNECTED, status: 'not_connected', phone_number: '' });
    expect(s.find('whatsapp-inbox-not-connected').text()).toContain('WhatsApp is not connected.');
    expect(s.find('whatsapp-inbox-go-to-saas').attributes('href')).toBe('http://localhost:8001');
    const employee = await setup({ session: EMPLOYEE }, { ...CONNECTED, status: 'not_connected' });
    expect(employee.find('whatsapp-inbox-not-connected').exists()).toBe(true);
    expect(employee.find('whatsapp-inbox-go-to-saas').exists()).toBe(false);
  });

  it('a number to reconnect, and the month spent', async () => {
    expect((await setup({}, { ...CONNECTED, status: 'reconnect_needed' })).find('whatsapp-inbox-reconnect').text()).toContain('reconnect');
    const spent = await setup({}, { ...CONNECTED, cap_reached: true, monthly_usage: 150 });
    expect(spent.find('whatsapp-inbox-cap-reached').text()).toContain('You have used all the WhatsApp messages of your plan this month.');
    expect((await setup()).find('whatsapp-inbox-cap-reached').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' }, { ...CONNECTED, status: 'not_connected' });
    expect(s.find('whatsapp-inbox-not-connected').text()).toContain('WhatsApp no está conectado.');
    await s.result(LIST, PAGE);
    expect(s.prop('searchPlaceholder')).toBe('Filtrar contacto o teléfono…');
  });
});
