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
  header_sample: null,
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
          header_format: '',
          header: '',
          header_sample: null,
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

// ── A header with a photo, a video or a document (WHATSAPP_INBOX-F29) ───────────────────────────────────────────────

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);
const photo = (name = 'carta.jpg', bytes: BlobPart = JPEG, type = 'image/jpeg') => new File([bytes], name, { type });
const MEDIA = '/p/media/0193a5b2c3d47e8f9a0b1c2d3e4f5a6b/whatsapp_inbox/samples';
const SAMPLE = { id: 's1', header_format: 'IMAGE', content_type: 'image/jpeg', size: 6, name: 'carta.jpg', url: `${MEDIA}/0123456789abcdef.jpg` } as const;
const VIDEO = { id: 's2', header_format: 'VIDEO', content_type: 'video/mp4', size: 6, name: 'otono.mp4', url: `${MEDIA}/fedcba9876543210.mp4` } as const;

type Setup = Awaited<ReturnType<typeof setup>>;

/** Picks `file` in the header's file input, as the browser's picker does. */
async function pick(s: Setup, file: File): Promise<void> {
  const input = s.field('header-file-input') as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new Event('change'));
  await flush();
  await settle();
}

describe('TemplateFormModal: a header with a file (WHATSAPP_INBOX-F29)', () => {
  it('«Photo» asks for its file, keeps it in the business’s files and sends the template with it', async () => {
    const s = await setup();
    expect(s.field('header-format').value).toBe('TEXT');
    await s.choose('header-format', 'IMAGE');
    expect(s.field('header')).toBeNull();
    expect(s.field('header-file-rules').textContent).toContain('JPEG or PNG, up to 5 MB');
    expect(s.field('header-file-input').getAttribute('accept')).toBe('image/jpeg,image/png');
    await s.type('name', 'promo_otono');
    await s.type('body', '¡Oferta de otoño!');
    expect(s.submit().disabled).toBe(true); // no file yet
    s.answer(201, SAMPLE);
    await pick(s, photo());
    expect(s.field('header-file-name').textContent).toContain('carta.jpg');
    expect(s.submit().disabled).toBe(false);
    s.answer(201, approved({ id: 't9', name: 'promo_otono', status: 'DRAFT', header_format: 'IMAGE', header: '', header_sample: SAMPLE }));
    await click(s.submit());
    await flush();
    const [upload, creation] = s.sent();
    expect(upload).toEqual({
      method: 'POST',
      path: '/api/whatsapp_inbox/templates/samples',
      query: {},
      body: { header_format: 'IMAGE', name: 'carta.jpg', content_base64: '/9j/4AAQ' },
    });
    expect(creation.path).toBe('/api/whatsapp_inbox/templates');
    expect(creation.body).toMatchObject({ header_format: 'IMAGE', header: '', header_sample: 's1' });
  });

  it('a video or a document asks for its own type', async () => {
    const s = await setup();
    await s.choose('header-format', 'VIDEO');
    expect(s.field('header-file-rules').textContent).toContain('MP4, up to 16 MB');
    await s.choose('header-format', 'DOCUMENT');
    expect(s.field('header-file-rules').textContent).toContain('PDF, up to 25 MB');
    expect(s.field('header-file-input').getAttribute('accept')).toBe('application/pdf');
  });

  it('a file of another type, or too heavy, is said under the field and never uploaded', async () => {
    const s = await setup();
    await s.choose('header-format', 'IMAGE');
    await pick(s, photo('anim.gif', new Uint8Array([0x47, 0x49, 0x46]), 'image/gif'));
    expect(s.field('header-file-error').textContent).toContain('Choose a JPEG or PNG photo.');
    await pick(s, photo('enorme.jpg', new Uint8Array(5 * 1024 * 1024 + 1)));
    expect(s.field('header-file-error').textContent).toContain('This file weighs more than 5 MB: choose a lighter one.');
    expect(s.sent()).toEqual([]);
    expect(s.field('header-file-name')).toBeNull();
  });

  it('the Hub refusing the file says its reason under the field', async () => {
    const s = await setup();
    await s.choose('header-format', 'IMAGE');
    const message = 'Choose a JPEG or PNG photo.';
    s.answer(422, { error: { code: 'invalid_payload', message, fields: { content_base64: message } } });
    await pick(s, photo());
    expect(s.field('header-file-error').textContent).toContain(message);
    expect(s.field('header-file-name')).toBeNull();
  });

  it('no space left in the plan for files is said under the field, as Files says it', async () => {
    const s = await setup(null, 'es');
    await s.choose('header-format', 'IMAGE');
    const message = 'No queda espacio para ese archivo: tu plan incluye 1 GB.';
    s.answer(409, { error: { code: 'base.file_no_space', message } });
    await pick(s, photo());
    expect(s.field('header-file-error').textContent).toContain(message);
    expect(s.field('header-file-name')).toBeNull();
  });

  it('a refusal of the template’s file on saving is said under it', async () => {
    const s = await setup();
    await s.choose('header-format', 'IMAGE');
    await s.type('name', 'promo_otono');
    await s.type('body', 'Hola');
    s.answer(201, SAMPLE);
    await pick(s, photo());
    const message = "Choose the header's file: Meta reviews the template with it.";
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { header_sample: message } } });
    await click(s.submit());
    await flush();
    await settle();
    expect(s.field('header-file-error').textContent).toContain(message);
  });

  it('the photo just kept shows its thumbnail next to its name (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL)', async () => {
    const s = await setup();
    await s.choose('header-format', 'IMAGE');
    expect(s.field('header-file-preview')).toBeNull();
    s.answer(201, SAMPLE);
    await pick(s, photo());
    const thumbnail = s.field('header-file-preview-image');
    expect([thumbnail?.tagName, thumbnail?.getAttribute('src'), thumbnail?.getAttribute('alt')]).toEqual(['IMG', SAMPLE.url, 'carta.jpg']);
    expect(s.field('header-file-preview').contains(s.field('header-file-name'))).toBe(true);
    expect(s.field('header-file-preview-loading')).not.toBeNull();
    thumbnail.dispatchEvent(new Event('load'));
    await settle();
    expect(s.field('header-file-preview-loading')).toBeNull();
    expect(s.field('header-file-preview-error')).toBeNull();
  });

  it('a video shows its first frame; one that cannot be shown says so and keeps its name', async () => {
    const s = await setup();
    await s.choose('header-format', 'VIDEO');
    s.answer(201, VIDEO);
    await pick(s, new File([new Uint8Array([0, 0, 0, 0x18, 0x66, 0x74, 0x79, 0x70])], 'otono.mp4', { type: 'video/mp4' }));
    const video = s.field('header-file-preview-video') as HTMLVideoElement;
    expect([video.tagName, video.getAttribute('src'), video.getAttribute('preload')]).toEqual(['VIDEO', `${VIDEO.url}#t=0.1`, 'metadata']);
    video.dispatchEvent(new Event('error'));
    await settle();
    expect(s.field('header-file-preview-error').textContent).toContain('The video could not be shown.');
    expect(s.field('header-file-name').textContent).toContain('otono.mp4');
  });

  it('editing a template with a photo shows its file and keeps it without uploading it again', async () => {
    const s = await setup(approved({ header_format: 'IMAGE', header: '', header_sample: SAMPLE, supported: false, sendable: false }));
    expect(s.field('header-format').value).toBe('IMAGE');
    expect(s.field('header-file-name').textContent).toContain('carta.jpg');
    expect(s.field('header-file-preview-image').getAttribute('src')).toBe(SAMPLE.url);
    expect(s.field('header-file-choose').textContent).toContain('Change file');
    s.answer(200, approved());
    await click(s.submit());
    await flush();
    const [update] = s.sent();
    expect(update.path).toBe('/api/whatsapp_inbox/templates/update');
    expect(update.body).toMatchObject({ id: 't1', header_format: 'IMAGE', header: '', header_sample: 's1' });
  });

  it('a text header sends what it always sent', async () => {
    const s = await setup(approved());
    s.answer(200, approved());
    await click(s.submit());
    await flush();
    const [update] = s.sent();
    expect(update.body).not.toHaveProperty('header_format');
    expect(update.body).not.toHaveProperty('header_sample');
    expect(update.body).toMatchObject({ header: 'Tu cita' });
  });

  it('speaks Spanish', async () => {
    const s = await setup(null, 'es');
    await s.choose('header-format', 'IMAGE');
    s.answer(201, SAMPLE);
    await pick(s, photo());
    s.field('header-file-preview-image').dispatchEvent(new Event('error'));
    await settle();
    expect(s.field('header-file-preview-error').textContent).toContain('No se ha podido mostrar la foto.');
    await s.choose('header-format', 'DOCUMENT');
    expect(s.field('header-format').label).toBe('Tipo de cabecera');
    expect(s.field('header-file-rules').textContent).toContain('PDF, hasta 25 MB');
    expect(s.field('header-file-choose').textContent).toContain('Elegir archivo');
    expect(s.field('header-file-empty').textContent).toContain('Ningún archivo elegido');
  });
});
