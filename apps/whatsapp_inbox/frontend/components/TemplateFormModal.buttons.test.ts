// The template editor's buttons whose icon says them alone are that icon, named and titled by their label: the file of
// a photo, video or document header (its cloud), «Add button» (its «+») and each button's «Remove button» (its ✕).
import { DOMWrapper } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import { iconOnly, iconOnlyNamed } from '../../../../base/frontend/__tests__/icon-only';
import { mountInbox, settle } from '../__tests__/mount-inbox';
import type { TemplateOut } from '../operations';
import TemplateFormModal from './TemplateFormModal.vue';

const ID = 'whatsapp-inbox-template-editor';

const WITH_PHOTO: TemplateOut = {
  id: 't1',
  name: 'recordatorio',
  language: 'es',
  category: 'UTILITY',
  status: 'APPROVED',
  header_format: 'IMAGE',
  header: '',
  header_sample: { id: 's1', header_format: 'IMAGE', content_type: 'image/jpeg', size: 6, name: 'carta.jpg', url: '/p/media/carta.jpg' },
  body: 'Hola {{1}}.',
  body_examples: ['Ana'],
  footer: '',
  buttons: [{ type: 'QUICK_REPLY', text: 'Confirmar', url: '', phone_number: '' }],
  variables: 1,
  rejected_reason: '',
  meta_id: 'm1',
  synced_at: null,
  draft: null,
  submit_state: '',
  submit_error_code: '',
  submit_error: '',
  editable: true,
  sendable: false,
  supported: false,
  deleting: false,
};

async function editor(locale: 'en' | 'es' = 'en') {
  const m = await mountInbox(TemplateFormModal, { props: { open: true, template: WITH_PHOTO }, locale });
  await settle();
  return (name: string) => iconOnly(new DOMWrapper(m.inDoc(`${ID}-${name}`)!));
}

describe('TemplateFormModal: its action buttons', () => {
  it('are their icons alone, named and titled by their labels', async () => {
    const button = await editor();
    expect([button('header-file-choose'), button('button-add'), button('button-0-remove')]).toEqual([
      iconOnlyNamed('Change file'),
      iconOnlyNamed('Add button'),
      iconOnlyNamed('Remove button'),
    ]);
  });

  it('speak Spanish', async () => {
    const button = await editor('es');
    expect([button('header-file-choose'), button('button-add'), button('button-0-remove')]).toEqual([
      iconOnlyNamed('Cambiar archivo'),
      iconOnlyNamed('Añadir botón'),
      iconOnlyNamed('Quitar botón'),
    ]);
  });
});
