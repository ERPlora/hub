// WhatsApp inbox → Settings («Ajustes del canal»; WHATSAPP_INBOX-F01, F02, F13, F27, F28), owner and admin
// only: «Your number» (connected with the number and the name, not connected, or to reconnect) and
// «Manage in erplora.com»; «This month» (messages sent against the plan's, or no limit); «Meta templates»
// — Name, Language, Category, Status in Meta and Text, «Search template…», Meta's reason on a rejected
// one, «No templates.» with where they are made. Whoever may not configure reads «You do not have permission».
import { DataTable, EmptyState, UsageMeter } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { errorFrame, flush, MANAGER, type MountOptions, mountInbox } from '../__tests__/mount-inbox';
import type { ChannelOut, TemplateOut } from '../operations';
import SettingsPage from './SettingsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const CHANNEL = 'whatsapp_inbox.channel.get';
const TEMPLATES = 'whatsapp_inbox.template.list';

const CONNECTED: ChannelOut = {
  status: 'connected',
  phone_number: '+34910000000',
  display_name: 'Peluquería Ana',
  monthly_limit: 150,
  monthly_usage: 12,
  cap_reached: false,
  synced_at: '2026-10-15T09:00:00Z',
  manage_url: 'http://localhost:8001',
};
const template = (over: Partial<TemplateOut> = {}): TemplateOut => ({
  id: 't1',
  name: 'recordatorio',
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header: '',
  body: 'Hola {{1}}, te esperamos el {{2}}.',
  footer: '',
  variables: 2,
  rejected_reason: '',
  synced_at: null,
  header_format: '',
  body_examples: [],
  buttons: [],
  meta_id: 'm1',
  draft: null,
  submit_state: '',
  submit_error_code: '',
  submit_error: '',
  editable: true,
  sendable: true,
  deleting: false,
  ...over,
});
const PAGE = { rows: [template(), template({ id: 't2', name: 'promo', category: 'MARKETING', status: 'REJECTED', rejected_reason: 'INVALID_FORMAT' })], total: 2, limit: 50, offset: 0 };

async function setup(options: MountOptions = {}, channel: ChannelOut = CONNECTED) {
  const m = await mountInbox(SettingsPage, { path: '/whatsapp_inbox/settings', ...options });
  // Whoever may not configure subscribes to nothing: there is no stream to open.
  if (m.params(CHANNEL).length) {
    await m.live();
    await m.result(CHANNEL, channel);
  }
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  return { ...m, table, prop };
}

describe('SettingsPage: the number and the month', () => {
  it('is «Channel settings»: the number connected, its name and «Manage in erplora.com»', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Channel settings');
    expect(s.find('whatsapp-inbox-settings-number').text()).toContain('Connected');
    expect(s.find('whatsapp-inbox-settings-number').text()).toContain('+34910000000');
    expect(s.find('whatsapp-inbox-settings-number').text()).toContain('Peluquería Ana');
    expect(s.find('whatsapp-inbox-settings-manage').attributes()).toMatchObject({ href: 'http://localhost:8001', target: '_blank' });
  });

  it('not connected, or to reconnect, says what to do', async () => {
    expect((await setup({}, { ...CONNECTED, status: 'not_connected', phone_number: '' })).find('whatsapp-inbox-settings-number').text()).toContain(
      'Connect the business',
    );
    expect((await setup({}, { ...CONNECTED, status: 'reconnect_needed' })).find('whatsapp-inbox-settings-number').text()).toContain(
      'WhatsApp withdrew the permission',
    );
  });

  it('the month: messages sent against the plan’s, the cap said when it is reached, or no limit', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(UsageMeter).props()).toMatchObject({ value: 12, max: 150, label: 'This month' });
    expect(s.find('whatsapp-inbox-settings-month').text()).toContain('12 of 150 messages sent');
    const spent = await setup({}, { ...CONNECTED, monthly_usage: 150, cap_reached: true });
    expect(spent.find('whatsapp-inbox-settings-month').text()).toContain('You have used all the messages of your plan this month.');
    const free = await setup({}, { ...CONNECTED, monthly_limit: 0, monthly_usage: 40 });
    expect(free.wrapper.findComponent(UsageMeter).exists()).toBe(false);
    expect(free.find('whatsapp-inbox-settings-month').text()).toContain('No limit: 40 messages sent');
  });
});

describe('SettingsPage: Meta templates (WHATSAPP_INBOX-F27, F28)', () => {
  it('lists every template by name with its state at Meta and its reason', async () => {
    const s = await setup();
    expect(s.params(TEMPLATES)).toEqual([{ limit: 50, offset: 0 }]);
    await s.result(TEMPLATES, PAGE);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'whatsapp-inbox-templates', total: 2 });
    expect(s.prop('searchPlaceholder')).toBe('Search template…');
    const columns = s.prop<{ key: string; label: string; format?: (v: unknown, r: TemplateOut) => string }[]>('columns');
    expect(columns.map((c) => c.label)).toEqual(['Name', 'Language', 'Category', 'Status in Meta', 'Text']);
    const category = columns.find((c) => c.key === 'category')!;
    expect(category.format!('MARKETING', PAGE.rows[1])).toBe('Marketing');
    const status = columns.find((c) => c.key === 'status')!;
    expect(status.format!('REJECTED', PAGE.rows[1])).toBe("Rejected · Meta's reason: INVALID_FORMAT");
    expect(status.format!('APPROVED', PAGE.rows[0])).toBe('Approved');
  });

  it('a search goes to the server; empty says where templates are made', async () => {
    const s = await setup();
    s.table().vm.$emit('update:search', 'record');
    await flush();
    await s.reopen();
    expect(s.params(TEMPLATES)).toEqual([{ search: 'record', limit: 50, offset: 0 }]);
    const empty = await setup();
    await empty.result(TEMPLATES, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(empty.wrapper.findComponent(EmptyState).props()).toMatchObject({
      heading: 'No templates.',
      message: 'Create one with «Add template»: Meta reviews it. The ones made in WhatsApp Manager appear here too.',
    });
  });

  it('a list that cannot be loaded offers Retry', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(TEMPLATES), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('Could not load the templates.');
  });
});

describe('SettingsPage: making, changing and deleting templates (WHATSAPP_INBOX-F29…F31)', () => {
  it('«Add template» opens the empty form; a row it can change opens it filled', async () => {
    const s = await setup();
    await s.result(TEMPLATES, PAGE);
    expect(s.table().props()).toMatchObject({ addable: true, rowClickable: true });
    expect(s.prop<{ add: string }>('labels').add).toBe('Add template');
    s.table().vm.$emit('add');
    await flush();
    expect(s.inDoc('whatsapp-inbox-template-editor')?.getAttribute('aria-label')).toBe('New template');
  });

  it('Edit only on what the Hub can change; Delete on every template; Retry on what did not reach Meta', async () => {
    const s = await setup();
    await s.result(TEMPLATES, PAGE);
    type Action = { id: string; label: string; hidden?: (row: TemplateOut) => boolean };
    const actions = s.prop<Action[]>('actions');
    const shown = (row: TemplateOut) => actions.filter((a) => !a.hidden?.(row)).map((a) => a.label);
    expect(shown(template())).toEqual(['Edit', 'Delete']);
    expect(shown(template({ editable: false }))).toEqual(['Delete']);
    expect(shown(template({ submit_state: 'failed', submit_error: 'Bad body' }))).toEqual(['Edit', 'Send to Meta again', 'Delete']);
    expect(shown(template({ submit_state: 'sending', submit_error_code: 'whatsapp_inbox.saas_unreachable' }))).toEqual([
      'Edit',
      'Send to Meta again',
      'Delete',
    ]);
    expect(shown(template({ deleting: true, submit_error: 'Meta did not answer.' }))).toEqual(['Send to Meta again']);
    expect(shown(template({ deleting: true }))).toEqual([]);
  });

  it('says where each one is on its way to Meta, and why it did not get there', async () => {
    const s = await setup();
    await s.result(TEMPLATES, PAGE);
    const columns = s.prop<{ key: string; format?: (v: unknown, r: TemplateOut) => string }[]>('columns');
    const status = columns.find((c) => c.key === 'status')!;
    expect(status.format!('DRAFT', template({ status: 'DRAFT', submit_state: 'queued' }))).toBe('Not sent to Meta · Sending to Meta…');
    expect(status.format!('DRAFT', template({ status: 'DRAFT', submit_state: 'failed', submit_error: 'Bad body' }))).toBe(
      'Not sent to Meta · Not accepted: Bad body',
    );
    expect(
      status.format!('APPROVED', template({ submit_state: 'sending', submit_error_code: 'x', submit_error: 'erplora.com did not answer.' })),
    ).toBe('Approved · Changes not sent: erplora.com did not answer.');
    expect(status.format!('APPROVED', template({ deleting: true }))).toBe('Being deleted at Meta');
    expect(status.format!('APPROVED', template({ deleting: true, submit_error: 'Meta did not answer.' }))).toBe(
      'Being deleted at Meta · Meta did not answer.',
    );
  });

  it('Delete asks first, naming the template and that Meta deletes it too, then deletes it', async () => {
    const s = await setup();
    await s.result(TEMPLATES, PAGE);
    s.answer(200, template({ deleting: true }));
    s.table().vm.$emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    await flush();
    const dialog = s.inDoc('whatsapp-inbox-template-delete');
    expect(dialog?.getAttribute('aria-label')).toBe('Delete this template?');
    expect(dialog?.textContent).toContain('recordatorio (es)');
    expect(dialog?.textContent).toContain('Meta deletes it too');
    expect(s.sent()).toEqual([]);
    (s.inDoc('whatsapp-inbox-template-delete-submit') as HTMLElement).click();
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/whatsapp_inbox/templates/delete', query: {}, body: { id: 't1' } }]);
  });

  it('«Send to Meta again» hands it over again', async () => {
    const s = await setup();
    await s.result(TEMPLATES, PAGE);
    s.answer(200, template({ submit_state: 'queued' }));
    s.table().vm.$emit('action', { actionId: 'retry', row: template({ submit_state: 'failed' }) });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/whatsapp_inbox/templates/retry', query: {}, body: { id: 't1' } }]);
  });
});

describe('SettingsPage: who sees it', () => {
  it('whoever may not configure reads «You do not have permission» and nothing is asked', async () => {
    const s = await setup({ session: MANAGER });
    expect(s.find('whatsapp-inbox-settings-forbidden').text()).toContain('You do not have permission');
    expect(s.params(CHANNEL)).toEqual([]);
    expect(s.params(TEMPLATES)).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Ajustes del canal');
    expect(s.find('whatsapp-inbox-settings-month').text()).toContain('12 de 150 mensajes enviados');
  });
});
