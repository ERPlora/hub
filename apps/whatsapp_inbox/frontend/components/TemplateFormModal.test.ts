// WHATSAPP_INBOX-F29 (create a template and send it for review) and F30 (edit it): Settings → «Add template»
// opens «New template» — Name (lowercase, numbers and underscores), Language, Category (Utility or Marketing),
// Header, Text with an «Example» box per variable it uses, Footer and up to 10 buttons (quick replies, links,
// a call) —; «Send to Meta for review» waits for what Meta needs and sends it. A row opens «Edit template —
// {name}» with what Meta has (or the changes still on their way), its verdict and its reason; name and
// language never change, and the category only while Meta has not approved it. A refusal stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { click, flush, ionValue, mountInbox, settle } from '../__tests__/mount-inbox';
import type { TemplateOut } from '../operations';
import TemplateFormModal from './TemplateFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const ID = 'whatsapp-inbox-template-editor';

const approved = (over: Partial<TemplateOut> = {}): TemplateOut => ({
  id: 't1',
  name: 'recordatorio',
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header_format: 'TEXT',
  header: 'Tu cita',
  body: 'Hola {{1}}, te esperamos el {{2}}.',
  body_examples: ['Ana', 'viernes'],
  footer: 'Peluquería Ana',
  buttons: [{ type: 'QUICK_REPLY', text: 'Confirmar', url: '', phone_number: '' }],
  variables: 2,
  rejected_reason: '',
  meta_id: 'm1',
  synced_at: null,
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

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string; fill?: string; errorText?: string };

async function setup(template: TemplateOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountInbox(TemplateFormModal, { props: { open: true, template }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const field = (name: string) => m.inDoc(`${ID}-${name}`) as Control;
  const submit = () => field('submit');
  async function type(name: string, value: string) {
    await ionValue(field(name), value, 'ionInput');
  }
  async function choose(name: string, value: string) {
    await ionValue(field(name), value, 'ionChange');
  }
  return { ...m, field, submit, type, choose };
}

describe('TemplateFormModal: a new template (WHATSAPP_INBOX-F29)', () => {
  it('is «New template» with outlined boxes and «Send to Meta for review»', async () => {
    const s = await setup();
    expect(s.inDoc(ID)?.getAttribute('aria-label')).toBe('New template');
    for (const name of ['name', 'header', 'body', 'footer']) {
      expect([s.field(name).fill, s.field(name).getAttribute('mode')]).toEqual(['outline', 'md']);
    }
    expect(s.field('name').label).toBe('Name');
    expect(s.field('language').value).toBe('es');
    expect(s.field('category').value).toBe('UTILITY');
    expect(s.submit().textContent).toContain('Send to Meta for review');
  });

  it('asks for an example of each variable the text uses; sending waits for all of them', async () => {
    const s = await setup();
    await s.type('name', 'recordatorio_cita');
    await s.type('body', 'Hola {{1}}, te esperamos el {{2}}.');
    expect(s.field('example-1').label).toBe('Example for variable 1');
    expect(s.field('example-2')).toBeTruthy();
    expect(s.submit().disabled).toBe(true);
    await s.type('example-1', 'Ana');
    expect(s.submit().disabled).toBe(true);
    await s.type('example-2', 'viernes');
    expect(s.submit().disabled).toBe(false);
    await s.type('body', 'Hola {{1}}.');
    expect(s.field('example-2')).toBeNull();
    expect(s.submit().disabled).toBe(false);
  });

  it('a name Meta would refuse says so under it before anything is sent', async () => {
    const s = await setup();
    await s.type('name', 'Recordatorio Cita');
    await s.type('body', 'Hola');
    expect(s.submit().disabled).toBe(true);
    expect(s.inDoc(ID)?.textContent).toContain('Use lowercase letters, numbers and underscores only.');
  });

  it('buttons: quick replies, a link that needs its https:// address, a call that needs its number; at most 10', async () => {
    const s = await setup();
    await s.type('name', 'promo_otono');
    await s.choose('category', 'MARKETING');
    await s.type('body', '¡Oferta de otoño!');
    await click(s.field('button-add'));
    await s.type('button-0-text', 'Me interesa');
    await click(s.field('button-add'));
    await s.choose('button-1-type', 'URL');
    await s.type('button-1-text', 'Ver la oferta');
    expect(s.submit().disabled).toBe(true); // the link has no address yet
    await s.type('button-1-url', 'https://peluqueria.test/otono');
    await click(s.field('button-add'));
    await s.choose('button-2-type', 'PHONE_NUMBER');
    await s.type('button-2-text', 'Llamar');
    await s.type('button-2-phone_number', '+34910000000');
    expect(s.submit().disabled).toBe(false);
    s.answer(201, approved({ id: 't9', name: 'promo_otono', status: 'DRAFT', submit_state: 'queued' }));
    await click(s.submit());
    await flush();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/whatsapp_inbox/templates',
        query: {},
        body: {
          name: 'promo_otono',
          language: 'es',
          category: 'MARKETING',
          header: '',
          body: '¡Oferta de otoño!',
          body_examples: [],
          footer: '',
          buttons: [
            { type: 'QUICK_REPLY', text: 'Me interesa' },
            { type: 'URL', text: 'Ver la oferta', url: 'https://peluqueria.test/otono' },
            { type: 'PHONE_NUMBER', text: 'Llamar', phone_number: '+34910000000' },
          ],
          submit_key: expect.any(String),
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a button is removed with its ✕, and there is no 11th', async () => {
    const s = await setup();
    for (let n = 0; n < 10; n += 1) await click(s.field('button-add'));
    expect(s.field('button-add').disabled).toBe(true);
    await click(s.field('button-9-remove'));
    expect(s.field('button-9-text')).toBeNull();
    expect(s.field('button-add').disabled).toBe(false);
  });

  it('a refusal stays in the dialog: a field under it, the rest on top; what was typed stays', async () => {
    const s = await setup();
    await s.type('name', 'recordatorio');
    await s.type('body', 'Hola');
    const message = 'There is already a template “recordatorio” in that language.';
    s.answer(409, { error: { code: 'whatsapp_inbox.template_exists', message } });
    await click(s.submit());
    await flush();
    expect(s.inDoc(`${ID}-error`)?.textContent).toContain(message);
    expect(s.field('name').value).toBe('recordatorio');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});

describe('TemplateFormModal: a refusal under a field (WHATSAPP_INBOX-F29, F30)', () => {
  it('goes away as soon as that field is changed; the others stay until theirs is', async () => {
    const s = await setup();
    await s.type('name', 'recordatorio');
    await s.type('body', 'Hola {{nombre}}');
    const fields = { body: 'Number the variables 1, 2, 3… in order, without skipping any.', footer: 'The header and the footer cannot have variables.' };
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields } });
    await click(s.submit());
    await flush();
    expect(s.field('body').errorText).toBe(fields.body);
    expect(s.field('footer').errorText).toBe(fields.footer);
    await s.type('body', 'Hola {{1}}');
    await flush();
    expect(s.field('body').errorText ?? '').toBe('');
    expect(s.field('footer').errorText).toBe(fields.footer);
  });
});

describe('TemplateFormModal: editing a template (WHATSAPP_INBOX-F30)', () => {
  it('is «Edit template — {name}» with what Meta has; name and language do not change', async () => {
    const s = await setup(approved());
    expect(s.inDoc(ID)?.getAttribute('aria-label')).toBe('Edit template — recordatorio');
    expect(s.field('name')).toBeNull();
    expect(s.field('language')).toBeNull();
    expect(s.field('identity').textContent).toContain('recordatorio');
    expect(s.field('body').value).toBe('Hola {{1}}, te esperamos el {{2}}.');
    expect(s.field('example-2').value).toBe('viernes');
    expect(s.field('button-0-text').value).toBe('Confirmar');
    // Meta approved it: its category stays.
    expect(s.field('category').disabled).toBe(true);
    expect(s.field('state').textContent).toContain('Approved');
    expect(s.field('state').textContent).toContain('the approved one keeps being sent');
  });

  it('with changes still on their way it shows them, and why they did not get there', async () => {
    const s = await setup(
      approved({
        draft: {
          category: 'UTILITY',
          header: '',
          body: 'Hola {{1}}, nueva hora el {{2}}.',
          body_examples: ['Ana', 'lunes'],
          footer: '',
          buttons: [],
        },
        submit_state: 'failed',
        submit_error_code: 'whatsapp_inbox.template_refused',
        submit_error: 'Template body has too many variables',
      }),
    );
    expect(s.field('body').value).toBe('Hola {{1}}, nueva hora el {{2}}.');
    expect(s.field('state').textContent).toContain('Template body has too many variables');
  });

  it('a rejected one says Meta’s reason and its category can change', async () => {
    const s = await setup(approved({ status: 'REJECTED', rejected_reason: 'INVALID_FORMAT' }));
    expect(s.field('state').textContent).toContain("Meta's reason: INVALID_FORMAT");
    expect(s.field('category').disabled).toBe(false);
  });

  it('«Save and send to Meta» sends the changes without the name or the language', async () => {
    const s = await setup(approved());
    await s.type('footer', 'Peluquería Ana · Centro');
    s.answer(200, approved({ submit_state: 'queued' }));
    expect(s.submit().textContent).toContain('Save and send to Meta');
    await click(s.submit());
    await flush();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/whatsapp_inbox/templates/update',
        query: {},
        body: {
          id: 't1',
          category: 'UTILITY',
          header: 'Tu cita',
          body: 'Hola {{1}}, te esperamos el {{2}}.',
          body_examples: ['Ana', 'viernes'],
          footer: 'Peluquería Ana · Centro',
          buttons: [{ type: 'QUICK_REPLY', text: 'Confirmar' }],
          submit_key: expect.any(String),
        },
      },
    ]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(null, 'es');
    expect(s.inDoc(ID)?.getAttribute('aria-label')).toBe('Nueva plantilla');
    expect(s.field('name').label).toBe('Nombre');
    expect(s.submit().textContent).toContain('Enviar a revisión de Meta');
  });
});
