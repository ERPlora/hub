// WhatsApp inbox → Settings («Ajustes del canal»; WHATSAPP_INBOX-F01, F02, F13, F27, F28), owner and admin
// only: «Your number» (connected with the number and the name, not connected, or to reconnect), connected,
// reconnected and disconnected here (components/NumberConnection.vue); «This month» (messages sent against the plan's, or that the plan includes none, with «Upgrade plan»); «Meta templates»
// — Name, Language, Category, Status in Meta and Text, «Search template…», Meta's reason on a rejected
// one, «No templates.» with where they are made. Whoever may not configure reads «You do not have permission».
import { DataTable, EmptyState, UsageMeter } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { ADMIN, errorFrame, flush, MANAGER, type MountOptions, mountInbox } from '../__tests__/mount-inbox';
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
  plans_url: 'http://localhost:8001/store/plans',
};
const template = (over: Partial<TemplateOut> = {}): TemplateOut => ({
  id: 't1',
  name: 'recordatorio',
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header: '',
  header_sample: null,
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
  supported: true,
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
  it('is «Channel settings»: the number connected, its name and «Disconnect», here and not in erplora.com', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Channel settings');
    expect(s.find('whatsapp-inbox-settings-number').text()).toContain('Connected');
    expect(s.find('whatsapp-inbox-settings-number').text()).toContain('+34910000000');
    expect(s.find('whatsapp-inbox-settings-number').text()).toContain('Peluquería Ana');
    expect(s.find('whatsapp-inbox-number-disconnect').exists()).toBe(true);
    // erplora.com has no WhatsApp screen: nothing leads there any more.
    expect(s.find('whatsapp-inbox-settings-manage').exists()).toBe(false);
  });

  it('not connected, or to reconnect, says what to do', async () => {
    expect((await setup({}, { ...CONNECTED, status: 'not_connected', phone_number: '' })).find('whatsapp-inbox-settings-number').text()).toContain(
      'Connect the business',
    );
    expect((await setup({}, { ...CONNECTED, status: 'reconnect_needed' })).find('whatsapp-inbox-settings-number').text()).toContain(
      'WhatsApp withdrew the permission',
    );
  });

  it('the month: messages sent against the plan’s, and the cap said with «Upgrade plan» when it is reached', async () => {
    const s = await setup();
    // The block is titled «This month» once: the meter's own label says what it counts (hub#118 review).
    expect(s.wrapper.findComponent(UsageMeter).props()).toMatchObject({ value: 12, max: 150, label: 'Messages sent' });
    expect(s.find('whatsapp-inbox-settings-month').text()).toContain('12 of 150 messages sent');
    expect(s.find('whatsapp-inbox-settings-upgrade').exists()).toBe(false);
    const spent = await setup({}, { ...CONNECTED, monthly_usage: 150, cap_reached: true });
    expect(spent.find('whatsapp-inbox-settings-month').text()).toContain('You have used all the messages of your plan this month.');
    expect(spent.find('whatsapp-inbox-settings-upgrade').attributes()).toMatchObject({
      href: 'http://localhost:8001/store/plans',
      target: '_blank',
      rel: 'noopener',
    });
    expect(spent.find('whatsapp-inbox-settings-upgrade').text()).toBe('Upgrade plan');
  });

  it('from 80 % of the month\'s messages, the month says how many are left, with «Upgrade plan»', async () => {
    const near = await setup({}, { ...CONNECTED, monthly_usage: 120 });
    const month = near.find('whatsapp-inbox-settings-month');
    expect(month.text()).toContain('120 of 150 messages sent');
    expect(month.find('[data-testid=whatsapp-inbox-settings-near-cap]').text()).toBe('You have 30 of 150 messages of your plan left this month.');
    expect(near.find('whatsapp-inbox-settings-upgrade').attributes('href')).toBe('http://localhost:8001/store/plans');
    const below = await setup({}, { ...CONNECTED, monthly_usage: 119 });
    expect(below.find('whatsapp-inbox-settings-near-cap').exists()).toBe(false);
    expect(below.find('whatsapp-inbox-settings-upgrade').exists()).toBe(false);
    const spent = await setup({}, { ...CONNECTED, monthly_usage: 150, cap_reached: true });
    expect(spent.find('whatsapp-inbox-settings-near-cap').exists()).toBe(false);
  });

  it('a plan without WhatsApp messages says so, never «No limit» (WHATSAPP_INBOX-F13, ADR-0474: 0 = none)', async () => {
    const none = await setup({}, { ...CONNECTED, monthly_limit: 0, monthly_usage: 0, cap_reached: true });
    expect(none.wrapper.findComponent(UsageMeter).exists()).toBe(false);
    const month = none.find('whatsapp-inbox-settings-month');
    expect(month.text()).toContain('Your plan does not include WhatsApp messages.');
    expect(month.text()).not.toContain('No limit');
    expect(none.find('whatsapp-inbox-settings-upgrade').attributes('href')).toBe('http://localhost:8001/store/plans');
    // A server not linked to erplora.com has nowhere to send the owner.
    const unlinked = await setup({}, { ...CONNECTED, monthly_limit: 0, monthly_usage: 0, cap_reached: true, plans_url: '' });
    expect(unlinked.find('whatsapp-inbox-settings-upgrade').exists()).toBe(false);
  });

  it('before erplora.com speaks, the month says it is not known yet (no figure, no cap)', async () => {
    const unknown = await setup({}, { ...CONNECTED, status: 'not_connected', phone_number: '', monthly_limit: 0, monthly_usage: 0, synced_at: null });
    expect(unknown.wrapper.findComponent(UsageMeter).exists()).toBe(false);
    expect(unknown.find('whatsapp-inbox-settings-month').text()).toContain('erplora.com has not reported this month’s messages yet.');
    expect(unknown.find('whatsapp-inbox-settings-upgrade').exists()).toBe(false);
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

  it('says of one made in WhatsApp Manager the Hub cannot fill that it is not sent nor edited here, whatever Meta says of it', async () => {
    const manager = template({
      id: 't3',
      name: 'bienvenida_foto',
      category: 'MARKETING',
      header_format: 'IMAGE',
      body: 'Hola {{nombre}}, te damos la bienvenida.',
      variables: 0,
      editable: false,
      sendable: false,
      supported: false,
    });
    const inReview = template({ id: 't4', status: 'PENDING', editable: false, sendable: false });
    for (const [locale, approved, review, rejected] of [
      ['en', "Approved · Can't be sent or edited here: it is managed in WhatsApp Manager.", 'In review', "Rejected · Meta's reason: INVALID_FORMAT · Can't be sent or edited here: it is managed in WhatsApp Manager."],
      ['es', 'Aprobada · No se puede enviar ni editar aquí: se gestiona en WhatsApp Manager.', 'En revisión', 'Rechazada · Motivo de Meta: INVALID_FORMAT · No se puede enviar ni editar aquí: se gestiona en WhatsApp Manager.'],
    ] as const) {
      const s = await setup({ locale });
      await s.result(TEMPLATES, { ...PAGE, rows: [manager, inReview], total: 2 });
      const status = s.prop<{ key: string; format?: (v: unknown, r: TemplateOut) => string }[]>('columns').find((c) => c.key === 'status')!;
      expect(status.format!('APPROVED', manager), locale).toBe(approved);
      // In review the Hub cannot send nor change it either, yet it fills it: nothing said of WhatsApp Manager.
      expect(status.format!('PENDING', inReview), locale).toBe(review);
      expect(status.format!('REJECTED', { ...manager, status: 'REJECTED', rejected_reason: 'INVALID_FORMAT' }), locale).toBe(rejected);
    }
  });

  it('one with a photo made here names its file and is sent from the inbox; one from WhatsApp Manager is edited there (F29, F33, F28)', async () => {
    const photo = template({
      id: 't5',
      name: 'promo_otono',
      header_format: 'IMAGE',
      header_sample: { id: 's1', header_format: 'IMAGE', content_type: 'image/jpeg', size: 120_000, name: 'carta.jpg' },
      body: '¡Oferta de otoño!',
      editable: true,
      sendable: true,
      supported: true,
    });
    const fromManager = template({ id: 't6', name: 'promo_foto', header_format: 'IMAGE', header_sample: null, editable: false, sendable: false, supported: true });
    for (const [locale, said, text, manager] of [
      ['en', 'Approved', 'Photo: carta.jpg · ¡Oferta de otoño!', 'Approved · Edited in WhatsApp Manager.'],
      ['es', 'Aprobada', 'Foto: carta.jpg · ¡Oferta de otoño!', 'Aprobada · Se edita en WhatsApp Manager.'],
    ] as const) {
      const s = await setup({ locale });
      await s.result(TEMPLATES, { ...PAGE, rows: [photo, fromManager], total: 2 });
      const columns = s.prop<{ key: string; format?: (v: unknown, r: TemplateOut) => string }[]>('columns');
      expect(columns.find((c) => c.key === 'status')!.format!('APPROVED', photo), locale).toBe(said);
      expect(columns.find((c) => c.key === 'body')!.format!(photo.body, photo), locale).toBe(text);
      expect(columns.find((c) => c.key === 'status')!.format!('APPROVED', fromManager), locale).toBe(manager);
      // A text one keeps its text alone.
      expect(columns.find((c) => c.key === 'body')!.format!('Hola', template()), locale).toBe('Hola');
    }
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

describe('SettingsPage: «What do you use it for?» (WHATSAPP_INBOX-F15)', () => {
  it('offers the automatic answer between the month and the templates when Reservas is on', async () => {
    const session = { ...ADMIN, apps: [{ label: 'flow', state: 'on' as const }, { label: 'reservation', state: 'on' as const }] };
    const s = await setup({ session });
    const blocks = s.wrapper.findAll('.wa-settings__block').map((block) => block.attributes('data-testid'));
    expect(blocks.indexOf('whatsapp-inbox-autoreply')).toBe(blocks.indexOf('whatsapp-inbox-settings-month') + 1);
    expect(s.params('flow.recipe.list')).toEqual([{}]);
  });

  it('a business without Reservas sees no such block and asks nothing of Automatizaciones, Citas on or not', async () => {
    const session = { ...ADMIN, apps: [{ label: 'flow', state: 'on' as const }, { label: 'appointment', state: 'on' as const }] };
    const s = await setup({ session });
    expect(s.find('whatsapp-inbox-autoreply').exists()).toBe(false);
    expect(s.params('flow.recipe.list')).toEqual([]);
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
    const none = await setup({ locale: 'es' }, { ...CONNECTED, monthly_limit: 0, monthly_usage: 0, cap_reached: true });
    expect(none.find('whatsapp-inbox-settings-month').text()).toContain('Tu plan no incluye mensajes de WhatsApp.');
    expect(none.find('whatsapp-inbox-settings-upgrade').text()).toBe('Mejorar el plan');
    const near = await setup({ locale: 'es' }, { ...CONNECTED, monthly_usage: 120 });
    expect(near.find('whatsapp-inbox-settings-near-cap').text()).toBe('Te quedan 30 de 150 mensajes de tu plan este mes.');
  });
});
