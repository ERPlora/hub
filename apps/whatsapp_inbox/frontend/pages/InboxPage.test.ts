// WhatsApp inbox → Inbox (WHATSAPP_INBOX-F03, F05, F09, F10, F13; the WORKBOOK's screens): the live
// `whatsapp_inbox.conversation.list` in a server-side DataTable — Contact, Phone, Status, Assigned to,
// Unread and Last message —, «Filter contact or phone…», filters by status, assignment and unread, 50 a
// page, latest activity first; «Open» (or the row) opens the conversation in a panel above the list
// (also from `?conversation=`); the notices: number not connected or to reconnect (with «Go to Settings», where it
// is connected, for whoever configures), month spent, number erased; every state of the screen.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage, applySurface } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { click, EMPLOYEE, errorFrame, flush, type MountOptions, mountInbox } from '../__tests__/mount-inbox';
import ConversationPanel from '../components/ConversationPanel.vue';
import type { ChannelOut, ConversationOut } from '../operations';
import InboxPage from './InboxPage.vue';
import source from './InboxPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

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
  flagged: false,
  created_at: '2026-03-10T08:00:00Z',
  ...over,
});
const PAGE = {
  rows: [row(), row({ id: 'c2', phone: '+34600999888', contact_name: '', display_name: '+34600999888', customer_id: null, customer_name: '', status: 'pending', unread_count: 0, assigned_to_id: '01a16000-0000-7000-8000-0000000000b7', assigned_to_name: 'Marta' })],
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
  plans_url: 'http://localhost:8001/store/plans',
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
  it('while the list loads, the table says it is loading, never «0 conversations» (gh:pm#611)', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    await s.result(LIST, PAGE);
    expect(s.prop('loading')).toBe(false);
  });

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

  it('a conversation an automatic answer could not answer says «Needs attention» next to its name (WHATSAPP_INBOX-F20)', async () => {
    const s = await setup();
    await s.result(LIST, { ...PAGE, rows: [row({ flagged: true }), row({ id: 'c2' })], total: 2 });
    expect(s.wrapper.findAll('[data-testid="whatsapp-inbox-flagged"]').map((chip) => chip.text())).toEqual(['Needs attention']);
  });

  it('a long name ends in «…» in a box of its own, with «Needs attention» beside it, never cut short', async () => {
    const s = await setup();
    await s.result(LIST, { ...PAGE, rows: [row({ flagged: true, display_name: 'Lucía Fernández de la Peña' })], total: 1 });
    const name = s.find('whatsapp-inbox-name');
    expect(name.text()).toBe('Lucía Fernández de la Peña');
    expect(name.element.nextElementSibling?.getAttribute('data-testid')).toBe('whatsapp-inbox-flagged');
    // The table's cell only gives «…» to its own span; inside the row with the mark, the name needs its own.
    expect(source).toMatch(/\.wa-inbox__display \{[^}]*min-width: 0;[^}]*overflow: hidden;[^}]*text-overflow: ellipsis;[^}]*white-space: nowrap;/);
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
  it('a number not connected: the notice, and «Go to Settings» (where it is connected) for whoever configures', async () => {
    const s = await setup({}, { ...CONNECTED, status: 'not_connected', phone_number: '' });
    expect(s.find('whatsapp-inbox-not-connected').text()).toContain('Connect the business’s number in Settings');
    expect(s.find('whatsapp-inbox-go-to-settings').text()).toBe('Go to Settings');
    await click(s.find('whatsapp-inbox-go-to-settings').element);
    expect(s.router.currentRoute.value.path).toBe('/whatsapp_inbox/settings');
    const employee = await setup({ session: EMPLOYEE }, { ...CONNECTED, status: 'not_connected' });
    expect(employee.find('whatsapp-inbox-not-connected').exists()).toBe(true);
    expect(employee.find('whatsapp-inbox-go-to-settings').exists()).toBe(false);
  });

  it('a number to reconnect, and the month spent', async () => {
    const reconnect = await setup({}, { ...CONNECTED, status: 'reconnect_needed' });
    expect(reconnect.find('whatsapp-inbox-reconnect').text()).toContain('reconnect the number in Settings');
    expect(reconnect.find('whatsapp-inbox-go-to-settings').exists()).toBe(true);
    const spent = await setup({}, { ...CONNECTED, cap_reached: true, monthly_usage: 150 });
    expect(spent.find('whatsapp-inbox-cap-reached').text()).toContain('You have used all the WhatsApp messages of your plan this month.');
    expect(spent.find('whatsapp-inbox-upgrade').attributes()).toMatchObject({
      href: 'http://localhost:8001/store/plans',
      target: '_blank',
      rel: 'noopener',
    });
    expect(spent.find('whatsapp-inbox-upgrade').text()).toBe('Upgrade plan');
    expect((await setup()).find('whatsapp-inbox-cap-reached').exists()).toBe(false);
  });

  // «Upgrade plan» sells, and everything that sells is web only (surface.ts): in the installed app the link opened
  // nothing (gh:hub#439), so there the inbox says it without the link.
  it('«Upgrade plan» sells: never on the app surfaces, where the inbox still says the month is spent', async () => {
    applySurface('mobile');
    try {
      const spent = await setup({}, { ...CONNECTED, cap_reached: true, monthly_usage: 150 });
      expect(spent.find('whatsapp-inbox-cap-reached').text()).toContain('You have used all the WhatsApp messages of your plan this month.');
      expect(spent.find('whatsapp-inbox-upgrade').exists()).toBe(false);
    } finally {
      applySurface('web');
    }
  });

  it('from 80 % of the month\'s messages the inbox says how many are left, «Upgrade plan» for whoever configures (as the assistant, BASE-F104)', async () => {
    const near = await setup({}, { ...CONNECTED, monthly_usage: 120 });
    expect(near.find('whatsapp-inbox-near-cap').text()).toContain('You have 30 of 150 WhatsApp messages of your plan left this month.');
    expect(near.find('whatsapp-inbox-near-cap').attributes('data-tone')).toBe('warning');
    expect(near.find('whatsapp-inbox-cap-reached').exists()).toBe(false);
    expect(near.find('whatsapp-inbox-upgrade').attributes()).toMatchObject({
      href: 'http://localhost:8001/store/plans',
      target: '_blank',
      rel: 'noopener',
    });
    const employee = await setup({ session: EMPLOYEE }, { ...CONNECTED, monthly_usage: 120 });
    expect(employee.find('whatsapp-inbox-near-cap').text()).toContain('You have 30 of 150 WhatsApp messages of your plan left this month.');
    expect(employee.find('whatsapp-inbox-upgrade').exists()).toBe(false);
    // Below 80 %, nothing; once spent, the cap says it instead.
    expect((await setup({}, { ...CONNECTED, monthly_usage: 119 })).find('whatsapp-inbox-near-cap').exists()).toBe(false);
    const spent = await setup({}, { ...CONNECTED, monthly_usage: 150, cap_reached: true });
    expect(spent.find('whatsapp-inbox-near-cap').exists()).toBe(false);
    expect(spent.find('whatsapp-inbox-cap-reached').exists()).toBe(true);
    // A new month (or a bigger plan) takes it away by itself, without reloading.
    await near.result(CHANNEL, CONNECTED);
    expect(near.find('whatsapp-inbox-near-cap').exists()).toBe(false);
  });

  it('a plan without WhatsApp messages says so above the list, «Upgrade plan» for whoever configures (ADR-0474: 0 = none)', async () => {
    const none = { ...CONNECTED, monthly_limit: 0, monthly_usage: 0, cap_reached: true };
    const s = await setup({}, none);
    const notice = s.find('whatsapp-inbox-cap-reached');
    expect(notice.text()).toContain('Your plan does not include WhatsApp messages.');
    expect(notice.text()).not.toContain('next month');
    expect(s.find('whatsapp-inbox-upgrade').attributes('href')).toBe('http://localhost:8001/store/plans');
    // The open conversation knows it too: its «Send» says why instead of sending.
    await s.result(LIST, PAGE);
    s.table().vm.$emit('rowClick', PAGE.rows[0]);
    await flush();
    expect(s.wrapper.findComponent(ConversationPanel).props('channel')).toEqual(none);
    const employee = await setup({ session: EMPLOYEE }, none);
    expect(employee.find('whatsapp-inbox-cap-reached').text()).toContain('Your plan does not include WhatsApp messages.');
    expect(employee.find('whatsapp-inbox-upgrade').exists()).toBe(false);
    const unlinked = await setup({}, { ...none, plans_url: '' });
    expect(unlinked.find('whatsapp-inbox-upgrade').exists()).toBe(false);
  });

  it('a number reconnected (or a new month) takes its notice away by itself, without reloading (gh:hub#2064)', async () => {
    const s = await setup({}, { ...CONNECTED, status: 'reconnect_needed', cap_reached: true });
    expect(s.find('whatsapp-inbox-reconnect').exists()).toBe(true);
    expect(s.find('whatsapp-inbox-cap-reached').exists()).toBe(true);
    await s.result(CHANNEL, CONNECTED);
    expect(s.find('whatsapp-inbox-reconnect').exists()).toBe(false);
    expect(s.find('whatsapp-inbox-cap-reached').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' }, { ...CONNECTED, status: 'not_connected' });
    expect(s.find('whatsapp-inbox-not-connected').text()).toContain('WhatsApp no está conectado.');
    const none = await setup({ locale: 'es' }, { ...CONNECTED, monthly_limit: 0, monthly_usage: 0, cap_reached: true });
    expect(none.find('whatsapp-inbox-cap-reached').text()).toContain(
      'Tu plan no incluye mensajes de WhatsApp. Los mensajes siguen llegando aquí, pero no se puede enviar nada hasta que mejores el plan.',
    );
    expect(none.find('whatsapp-inbox-upgrade').text()).toBe('Mejorar el plan');
    const near = await setup({ locale: 'es' }, { ...CONNECTED, monthly_usage: 120 });
    expect(near.find('whatsapp-inbox-near-cap').text()).toContain('Te quedan 30 de 150 mensajes de WhatsApp de tu plan este mes.');
    await s.result(LIST, PAGE);
    expect(s.prop('searchPlaceholder')).toBe('Filtrar contacto o teléfono…');
  });
});

describe('InboxPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });

  it('on a phone «No conversations.» stays in sight: the list hangs from AppPage’s stack itself, never from a nested one under the notices, and its filters sit behind «Filters» (the old hub’s funnel)', async () => {
    const s = await setup({}, { ...CONNECTED, status: 'not_connected', phone_number: '' });
    expect(s.find('whatsapp-inbox-not-connected').exists()).toBe(true);
    expect(s.prop('filterable')).toBe(true);
    const stack = s.table().element.parentElement;
    expect(stack?.parentElement?.classList.contains('hub-detail-shell--fill')).toBe(true);
    expect(stack?.contains(s.find('whatsapp-inbox-not-connected').element)).toBe(true);
  });
});
