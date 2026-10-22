// WHATSAPP_INBOX-F33 (send a template): «Template» in the composer opens «Send a template» with the
// templates Meta approved (name, language, category, text); choosing one asks for its variables and
// shows the text as it will go out; «Send» waits until everything is filled in, sends it through
// erplora.com and closes. A refusal (no marketing consent, the window, erplora.com down) stays on top
// of the dialog with what was typed.
import { describe, expect, it, vi } from 'vitest';

import { click, flush, ionValue, mountInbox, settle } from '../__tests__/mount-inbox';
import type { TemplateOut } from '../operations';
import TemplateSendModal from './TemplateSendModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'whatsapp_inbox.template.list';

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
  supported: true,
  deleting: false,
  ...over,
});
const PAGE = { rows: [template(), template({ id: 't2', name: 'promo', category: 'MARKETING', body: '¡Oferta de otoño!', variables: 0 })], total: 2, limit: 100, offset: 0 };

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string; fill?: string };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountInbox(TemplateSendModal, { props: { open: true, conversationId: 'c1' }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.live();
  await settle();
  const send = () => m.inDoc('whatsapp-inbox-template-form-submit') as Control;
  const variable = (n: number) => m.inDoc(`whatsapp-inbox-template-variable-${n}`) as Control;
  async function pick(id: string) {
    await ionValue(m.inDoc('whatsapp-inbox-template-pick'), id);
  }
  return { ...m, send, variable, pick };
}

describe('TemplateSendModal (WHATSAPP_INBOX-F33)', () => {
  it('offers the approved templates with their language, category and text', async () => {
    const s = await setup();
    // Only what the Hub can send now: approved, not being deleted, no file header (WHATSAPP_INBOX-F33).
    expect(s.params(OP)).toEqual([{ sendable: true, limit: 100 }]);
    await s.result(OP, PAGE);
    expect(s.inDoc('whatsapp-inbox-template-form')?.getAttribute('aria-label')).toBe('Send a template');
    const first = s.inDoc('whatsapp-inbox-template-option-t1');
    expect(first?.textContent).toContain('recordatorio');
    expect(first?.textContent).toContain('es');
    expect(first?.textContent).toContain('Utility');
    expect(first?.textContent).toContain('Hola {{1}}, te esperamos el {{2}}.');
    expect(s.inDoc('whatsapp-inbox-template-option-t2')?.textContent).toContain('Marketing');
  });

  it('asks for each variable in an outlined box and shows the text as it will go out; Send waits for all', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    expect(s.send().disabled).toBe(true);
    await s.pick('t1');
    expect([s.variable(1).label, s.variable(1).fill, s.variable(1).getAttribute('mode')]).toEqual(['Variable 1', 'outline', 'md']);
    expect(s.send().disabled).toBe(true);
    await ionValue(s.variable(1), 'Ana', 'ionInput');
    expect(s.inDoc('whatsapp-inbox-template-preview')?.textContent).toContain('Hola Ana, te esperamos el {{2}}.');
    expect(s.send().disabled).toBe(true);
    await ionValue(s.variable(2), 'viernes', 'ionInput');
    expect(s.inDoc('whatsapp-inbox-template-preview')?.textContent).toContain('Hola Ana, te esperamos el viernes.');
    expect(s.send().disabled).toBe(false);
  });

  it('sends it through erplora.com and closes; a template without variables sends at once', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    s.answer(201, { id: 'm9', status: 'sent' });
    await s.pick('t2');
    expect(s.send().disabled).toBe(false);
    await click(s.send());
    await flush();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/whatsapp_inbox/messages/send',
        query: {},
        body: { id: 'c1', template: { name: 'promo', language: 'es', variables: [] }, client_message_id: expect.any(String) },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal stays on top of the dialog, which keeps what was chosen', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    const message = 'This customer has not agreed to receive marketing by WhatsApp.';
    s.answer(409, { error: { code: 'whatsapp_inbox.marketing_consent_missing', message } });
    await s.pick('t2');
    await click(s.send());
    await flush();
    expect(s.inDoc('whatsapp-inbox-template-form-error')?.textContent).toContain(message);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('without approved templates it says where they are made', async () => {
    const s = await setup('es');
    await s.result(OP, { rows: [], total: 0, limit: 100, offset: 0 });
    expect(s.inDoc('whatsapp-inbox-template-none')?.textContent).toContain('No hay plantillas aprobadas');
  });
});
