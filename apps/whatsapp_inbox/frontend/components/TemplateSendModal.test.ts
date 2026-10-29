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
  header_sample: null,
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
    // What the inbox can send now: approved, not being deleted; a file header asks for its file (WHATSAPP_INBOX-F33).
    expect(s.params(OP)).toEqual([{ fillable: true, limit: 100 }]);
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

// ── A header with a photo, a video or a document (WHATSAPP_INBOX-F33) ───────────────────────────────────────────────

const SAMPLE = { id: 's1', header_format: 'IMAGE', content_type: 'image/jpeg', size: 2048, name: 'carta.jpg' } as const;
const OTHER = { id: 's2', header_format: 'IMAGE', content_type: 'image/png', size: 4096, name: 'otono.png' } as const;
const photo = (name = 'otono.png', type = 'image/png') => new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type });
const PHOTO_TEMPLATES = {
  rows: [
    template({ id: 't3', name: 'oferta_foto', header_format: 'IMAGE', header_sample: SAMPLE, body: '¡Hola {{1}}!', variables: 1 }),
    template({ id: 't4', name: 'promo_foto', header_format: 'IMAGE', header_sample: null, body: 'Oferta', variables: 0, editable: false, sendable: false }),
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

async function choose(s: Awaited<ReturnType<typeof setup>>, file: File): Promise<void> {
  const input = s.inDoc('whatsapp-inbox-template-file-input') as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new Event('change'));
  await flush();
  await settle();
}

describe('TemplateSendModal: a header with a file (WHATSAPP_INBOX-F33)', () => {
  it('a template made here comes with its own photo, and goes with it', async () => {
    const s = await setup();
    await s.result(OP, PHOTO_TEMPLATES);
    await s.pick('t3');
    expect(s.inDoc('whatsapp-inbox-template-file-name')?.textContent).toContain('carta.jpg');
    expect(s.inDoc('whatsapp-inbox-template-file-rules')?.textContent).toContain('JPEG or PNG, up to 5 MB.');
    await ionValue(s.variable(1), 'Ana', 'ionInput');
    s.answer(201, { id: 'm9', status: 'queued' });
    await click(s.send());
    await flush();
    expect(s.sent().at(-1)?.body).toEqual({
      id: 'c1',
      template: { name: 'oferta_foto', language: 'es', variables: ['Ana'], header_sample: 's1' },
      client_message_id: expect.any(String),
    });
  });

  it('one made in WhatsApp Manager asks for the file: kept at once in the business’s files, then sent with it', async () => {
    const s = await setup();
    await s.result(OP, PHOTO_TEMPLATES);
    await s.pick('t4');
    expect(s.inDoc('whatsapp-inbox-template-file-empty')?.textContent).toContain('No file chosen');
    expect(s.send().disabled).toBe(true);
    expect(s.inDoc('whatsapp-inbox-template-file-input')?.getAttribute('accept')).toBe('image/jpeg,image/png');
    s.answer(201, OTHER);
    await choose(s, photo());
    expect(s.sent().at(-1)).toMatchObject({
      path: '/api/whatsapp_inbox/templates/samples',
      body: { header_format: 'IMAGE', name: 'otono.png', content_base64: expect.any(String) },
    });
    expect(s.inDoc('whatsapp-inbox-template-file-name')?.textContent).toContain('otono.png');
    expect(s.send().disabled).toBe(false);
    s.answer(201, { id: 'm9', status: 'queued' });
    await click(s.send());
    await flush();
    expect(s.sent().at(-1)?.body).toMatchObject({ template: { name: 'promo_foto', header_sample: 's2' } });
  });

  it('a file of another type is said under the field and never uploaded', async () => {
    const s = await setup('es');
    await s.result(OP, PHOTO_TEMPLATES);
    await s.pick('t4');
    const before = s.sent().length;
    await choose(s, photo('carta.pdf', 'application/pdf'));
    expect(s.inDoc('whatsapp-inbox-template-file-error')?.textContent).toContain('Elige una foto JPEG o PNG.');
    expect(s.sent()).toHaveLength(before);
    expect(s.send().disabled).toBe(true);
  });
});

