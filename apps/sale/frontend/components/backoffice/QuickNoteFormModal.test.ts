// SALE-F36 (prepare the quick notes): the «+» of Quick notes opens «New quick note» — Note (up to 80
// characters) and Position — with «Add»; a row's «Edit» opens «Edit quick note» from that note, with
// «Save», and sends only what changed. The dialog closes once the server saved it (the live list paints
// it). A refusal keeps it open with what was typed: a 422 under its field, a note another device deleted
// with the server's words on top, a failure without words as «The quick note could not be saved.».
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountSale, settle } from '../../__tests__/mount-sale';
import type { QuickNoteOut } from '../../operations';
import QuickNoteFormModal from './QuickNoteFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & {
  label?: string;
  value?: unknown;
  fill?: string;
  type?: string;
  min?: string;
  step?: string;
  maxlength?: number;
  labelPlacement?: string;
  errorText?: string;
  disabled?: boolean;
};

const NO_SALT: QuickNoteOut = { id: 'n1', text: 'no salt', sort_order: 2 };
const GONE = 'That quick note is no longer in this business. Reload the list and try again.';

async function setup(note: QuickNoteOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(QuickNoteFormModal, { props: { open: true, note }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const field = (name: string) => m.inDoc(`sale-quick-note-form-${name}`) as Control;
  const submit = () => m.inDoc('sale-quick-note-form-submit') as Control;
  const title = () => m.inDoc('sale-quick-note-form')?.getAttribute('aria-label');
  const type = (name: string, value: string) => ionValue(field(name), value, 'ionInput');
  const closed = () => m.wrapper.emitted('update:open')?.at(-1)?.[0] === false;
  return { ...m, field, submit, title, type, closed };
}

describe('QuickNoteFormModal: «New quick note»', () => {
  it('asks the Note (80 characters at most) and the Position in outlined md boxes, with «Add»', async () => {
    const s = await setup();
    expect(s.title()).toBe('New quick note');
    const text = s.field('text');
    expect([text.label, text.fill, text.getAttribute('mode'), text.labelPlacement, text.maxlength, text.value]).toEqual(['Note', 'outline', 'md', 'floating', 80, '']);
    const order = s.field('order');
    expect([order.label, order.fill, order.getAttribute('mode'), order.type, String(order.min), String(order.step), order.value]).toEqual([
      'Position',
      'outline',
      'md',
      'number',
      '0',
      '1',
      '0',
    ]);
    expect(s.submit().textContent?.trim()).toBe('Add');
  });

  it('«Add» waits for a note', async () => {
    const s = await setup();
    expect(s.submit().disabled).toBe(true);
    await s.type('text', '   ');
    expect(s.submit().disabled).toBe(true);
    await s.type('text', 'no ice');
    expect(s.submit().disabled).toBe(false);
  });

  it('sends sale.quick_note.create with the note trimmed and its position, then closes and starts blank again', async () => {
    const s = await setup();
    s.answer(201, { id: 'n9', text: 'no ice', sort_order: 3 });
    await s.type('text', '  no ice ');
    await s.type('order', '3');
    await click(s.submit());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/sale/quick_notes', query: {}, body: { text: 'no ice', sort_order: 3 } }]);
    expect(s.closed()).toBe(true);
    await s.wrapper.setProps({ open: true });
    await settle();
    expect([s.field('text').value, s.field('order').value]).toEqual(['', '0']);
  });

  it('a Position left blank goes as 0, the server’s first place', async () => {
    const s = await setup();
    s.answer(201, { id: 'n9', text: 'no ice', sort_order: 0 });
    await s.type('text', 'no ice');
    await s.type('order', '');
    await click(s.submit());
    expect(s.sent()[0].body).toEqual({ text: 'no ice', sort_order: 0 });
  });
});

describe('QuickNoteFormModal: «Edit quick note»', () => {
  it('starts from the note, with «Save»', async () => {
    const s = await setup(NO_SALT);
    expect(s.title()).toBe('Edit quick note');
    expect([s.field('text').value, s.field('order').value]).toEqual(['no salt', '2']);
    expect(s.submit().textContent?.trim()).toBe('Save');
  });

  it('sends sale.quick_note.update with its id and only what changed', async () => {
    const s = await setup(NO_SALT);
    s.answer(200, { ...NO_SALT, sort_order: 5 });
    await s.type('order', '5');
    await click(s.submit());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/sale/quick_notes/update', query: {}, body: { id: 'n1', sort_order: 5 } }]);
    expect(s.closed()).toBe(true);
  });

  it('nothing changed: closes without asking the server', async () => {
    const s = await setup(NO_SALT);
    await s.type('text', ' no salt ');
    await click(s.submit());
    expect(s.sent()).toEqual([]);
    expect(s.closed()).toBe(true);
  });

  it('opened again for another note, shows that one', async () => {
    const s = await setup(NO_SALT);
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ note: { id: 'n2', text: 'medium rare', sort_order: 7 }, open: true });
    await settle();
    expect([s.field('text').value, s.field('order').value]).toEqual(['medium rare', '7']);
  });
});

describe('QuickNoteFormModal: refusals keep it open with what was typed', () => {
  it('a note another device deleted: the server’s words on top', async () => {
    const s = await setup(NO_SALT);
    s.answer(404, { error: { code: 'sale.quick_note_not_found', message: GONE } });
    await s.type('text', 'no salt please');
    await click(s.submit());
    expect(s.inDoc('sale-quick-note-form-error')?.textContent).toContain(GONE);
    expect(s.closed()).toBe(false);
    expect(s.field('text').value).toBe('no salt please');
  });

  it('a 422 is said under its field', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { sort_order: 'Input should be less than or equal to 100000' } } });
    await s.type('text', 'no ice');
    await s.type('order', '200000');
    await click(s.submit());
    expect(s.field('order').errorText).toBe('Input should be less than or equal to 100000');
    expect(s.field('order').classList.contains('ion-invalid')).toBe(true);
    expect(s.field('text').classList.contains('ion-invalid')).toBe(false);
  });

  it('a failure without words says «The quick note could not be saved.»', async () => {
    const s = await setup();
    s.net.onApi(() => new Response('<html>502</html>', { status: 502 }));
    await s.type('text', 'no ice');
    await click(s.submit());
    expect(s.inDoc('sale-quick-note-form-error')?.textContent).toContain('The quick note could not be saved.');
  });
});

describe('QuickNoteFormModal: Spanish', () => {
  it('speaks the old screen’s words', async () => {
    const s = await setup(null, 'es');
    expect(s.title()).toBe('Nueva nota rápida');
    expect([s.field('text').label, s.field('order').label, s.submit().textContent?.trim()]).toEqual(['Nota', 'Posición', 'Añadir']);
    const e = await setup(NO_SALT, 'es');
    expect([e.title(), e.submit().textContent?.trim()]).toEqual(['Editar nota rápida', 'Guardar']);
  });
});
