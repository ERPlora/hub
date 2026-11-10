// «New ticket» (WORKBOOK «Pantallas · Comandas»; KITCHEN-F23): Type (it starts at the settings' default),
// Destination and Notes (optional) and its dishes — a product of the catalogue, or the dish written by
// hand, its quantity and a note — with «Add dish» and «Remove dish»; «Create ticket» only with a dish.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { ticket } from '../__tests__/kitchen';
import { click, ionValue, mountKitchen, settle } from '../__tests__/mount-kitchen';
import TicketFormModal from './TicketFormModal.vue';

/** A prop of a mounted component, whatever its type (a generic component's props read as `never`). */
const prop = (wrapper: { props: () => unknown }, name: string): unknown => (wrapper.props() as Record<string, unknown>)[name];

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string };

async function form(props: Record<string, unknown> = {}, answers: Record<string, [number, unknown]> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(TicketFormModal, { props: { open: false, defaultType: 'takeaway', ...props }, answers, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`kitchen-ticket-form-${name}`) as Control;
  const combo = (index: number) =>
    m.wrapper.findAllComponents(Combo as unknown as Component).find((c) => prop(c, 'testid') === `kitchen-ticket-form-dish-${index}-product`);
  return { ...m, field, combo, closed: () => prop(m.wrapper, 'open') === false };
}

describe('TicketFormModal', () => {
  it('makes a ticket by hand with a product and a written dish', async () => {
    const made = ticket('t9');
    const f = await form({}, { '/api/kitchen/tickets': [201, made] });
    expect(f.field('type').value).toBe('takeaway');
    expect(f.field('submit').disabled).toBe(true);
    await ionValue(f.field('label'), 'Staff', 'ionInput');
    await ionValue(f.field('notes'), 'Before service', 'ionInput');
    f.combo(0)!.vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
    await settle();
    await ionValue(f.field('dish-0-quantity'), '2', 'ionInput');
    await ionValue(f.field('dish-0-notes'), 'Well done', 'ionInput');
    await click(f.field('add-dish'));
    await ionValue(f.field('dish-1-name'), 'Salad', 'ionInput');
    await click(f.field('submit'));
    expect(f.sent().map((call) => [call.path, call.body])).toEqual([
      [
        '/api/kitchen/tickets',
        {
          order_type: 'takeaway',
          label: 'Staff',
          notes: 'Before service',
          items: [
            { product_id: 'p1', quantity: '2', notes: 'Well done' },
            { name: 'Salad', quantity: '1', notes: '' },
          ],
        },
      ],
    ]);
    expect(f.wrapper.emitted('saved')?.[0]?.[0]).toEqual(made);
    expect(f.closed()).toBe(true);
  });

  it('removes a dish', async () => {
    const f = await form();
    await click(f.field('add-dish'));
    expect(f.field('dish-1-name')).not.toBeNull();
    await click(f.field('dish-1-remove'));
    expect(f.field('dish-1-name')).toBeNull();
  });

  it('a refusal shows in the dialog', async () => {
    const refusal = { error: { code: 'kitchen.product_not_found', message: 'That product does not exist in the catalogue.' } };
    const f = await form({}, { '/api/kitchen/tickets': [404, refusal] });
    await ionValue(f.field('dish-0-name'), 'Soup', 'ionInput');
    await click(f.field('submit'));
    expect(f.inDoc('kitchen-ticket-form-error')?.textContent).toContain('That product does not exist in the catalogue.');
    expect(f.closed()).toBe(false);
  });

  describe('a refusal by fields (hub#833)', () => {
    const NOTICE = 'Check the highlighted details.';
    const ABOVE_ZERO = 'Ensure this value is greater than 0.';
    const refusal = (fields: Record<string, string>) => [422, { error: { code: 'invalid_payload', message: NOTICE, fields } }] as [number, unknown];
    const TICKETS = '/api/kitchen/tickets';
    type Field = Control & { errorText?: unknown };
    const markOf = (el: Element | null) => {
      const field = el as Field;
      return { message: field.errorText || undefined, red: field.classList.contains('ion-invalid') && field.classList.contains('ion-touched') };
    };
    const MARKED = (message: string) => ({ message, red: true });
    const UNMARKED = { message: undefined, red: false };
    /** A keystroke: Ionic's value event, and the native `input` that bubbles up through the field. */
    const type = async (el: Element | null, value: string): Promise<void> => {
      await ionValue(el, value, 'ionInput');
      el?.dispatchEvent(new Event('input', { bubbles: true }));
      await settle();
    };

    /** Two written dishes, «Soup» and «Salad», sent and refused with `fields`. */
    const twoDishes = async (fields: Record<string, string>) => {
      const f = await form({}, { [TICKETS]: refusal(fields) });
      await ionValue(f.field('dish-0-name'), 'Soup', 'ionInput');
      await click(f.field('add-dish'));
      await ionValue(f.field('dish-1-name'), 'Salad', 'ionInput');
      await click(f.field('submit'));
      return f;
    };

    it("a quantity of 0 marks that dish's quantity with the server's reason, not only a notice on top", async () => {
      const f = await form({}, { [TICKETS]: refusal({ 'items.0.quantity': ABOVE_ZERO }) });
      await ionValue(f.field('dish-0-name'), 'Salad', 'ionInput');
      await ionValue(f.field('dish-0-quantity'), '0', 'ionInput');
      await click(f.field('submit'));
      expect(markOf(f.field('dish-0-quantity'))).toEqual(MARKED(ABOVE_ZERO));
      expect(f.inDoc('kitchen-ticket-form-error')?.textContent).toContain(NOTICE);
      expect(f.inDoc('kitchen-ticket-form-error')?.textContent).not.toContain(ABOVE_ZERO);
      expect(f.field('dish-0-name').value).toBe('Salad');
      expect(f.closed()).toBe(false);
    });

    it('the server names a dish by its place in what was sent: an empty row above it is not sent', async () => {
      const f = await form({}, { [TICKETS]: refusal({ 'items.0.quantity': ABOVE_ZERO }) });
      await click(f.field('add-dish'));
      await ionValue(f.field('dish-1-name'), 'Salad', 'ionInput');
      await ionValue(f.field('dish-1-quantity'), '0', 'ionInput');
      await click(f.field('submit'));
      expect(f.sent().at(-1)?.body).toMatchObject({ items: [{ name: 'Salad', quantity: '0' }] });
      expect(markOf(f.field('dish-1-quantity'))).toEqual(MARKED(ABOVE_ZERO));
      expect(markOf(f.field('dish-0-quantity'))).toEqual(UNMARKED);
    });

    it('marks each field of a dish and of the ticket under its own name', async () => {
      const fields = {
        order_type: 'Type refused.',
        label: 'Label refused.',
        notes: 'Notes refused.',
        'items.0.name': 'Name refused.',
        'items.0.quantity': 'Quantity refused.',
        'items.0.notes': 'Note refused.',
      };
      const f = await form({}, { [TICKETS]: refusal(fields) });
      await ionValue(f.field('dish-0-name'), 'Salad', 'ionInput');
      await click(f.field('submit'));
      expect(markOf(f.field('type'))).toEqual(MARKED('Type refused.'));
      expect(markOf(f.field('label'))).toEqual(MARKED('Label refused.'));
      expect(markOf(f.field('notes'))).toEqual(MARKED('Notes refused.'));
      expect(markOf(f.field('dish-0-name'))).toEqual(MARKED('Name refused.'));
      expect(markOf(f.field('dish-0-quantity'))).toEqual(MARKED('Quantity refused.'));
      expect(markOf(f.field('dish-0-notes'))).toEqual(MARKED('Note refused.'));
      expect(f.inDoc('kitchen-ticket-form-error')?.textContent).toContain(NOTICE);
    });

    it("a dish's product passes its refusal to the Combo", async () => {
      const f = await form({}, { [TICKETS]: refusal({ 'items.0.product_id': 'Product refused.' }) });
      f.combo(0)!.vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
      await settle();
      await click(f.field('submit'));
      expect(prop(f.combo(0)!, 'errorText')).toBe('Product refused.');
    });

    it('typing in the marked quantity clears its mark and the notice; the other dish keeps its own', async () => {
      const f = await twoDishes({ 'items.0.quantity': ABOVE_ZERO, 'items.1.quantity': ABOVE_ZERO });
      await type(f.field('dish-0-quantity'), '2');
      expect(markOf(f.field('dish-0-quantity'))).toEqual(UNMARKED);
      expect(markOf(f.field('dish-1-quantity'))).toEqual(MARKED(ABOVE_ZERO));
      expect(f.inDoc('kitchen-ticket-form-error')).toBeNull();
    });

    it('a mark follows its dish when one above it is removed', async () => {
      const f = await twoDishes({ 'items.1.quantity': ABOVE_ZERO });
      await click(f.field('dish-0-remove'));
      expect(f.field('dish-0-name').value).toBe('Salad');
      expect(markOf(f.field('dish-0-quantity'))).toEqual(MARKED(ABOVE_ZERO));
    });

    it('a dish added after the refusal is not taken for the refused one', async () => {
      const f = await form({}, { [TICKETS]: refusal({ 'items.0.quantity': ABOVE_ZERO }) });
      await click(f.field('add-dish'));
      await ionValue(f.field('dish-1-name'), 'Soup', 'ionInput');
      await click(f.field('submit'));
      await click(f.field('add-dish'));
      expect(markOf(f.field('dish-0-quantity'))).toEqual(UNMARKED);
      expect(markOf(f.field('dish-1-quantity'))).toEqual(MARKED(ABOVE_ZERO));
      expect(markOf(f.field('dish-2-quantity'))).toEqual(UNMARKED);
    });

    it('removing the refused dish leaves no promise of marks that are gone', async () => {
      const f = await twoDishes({ 'items.1.quantity': ABOVE_ZERO });
      expect(f.inDoc('kitchen-ticket-form-error')?.textContent).toContain(NOTICE);
      await click(f.field('dish-1-remove'));
      expect(f.inDoc('kitchen-ticket-form-error')).toBeNull();
    });

    it('what no field of this window shows is said on top, by FormModal, with no promise of marks', async () => {
      const f = await form({}, { [TICKETS]: refusal({ items: 'Too many dishes.' }) });
      await ionValue(f.field('dish-0-name'), 'Soup', 'ionInput');
      await click(f.field('submit'));
      expect(f.inDoc('kitchen-ticket-form-error')?.textContent).toContain('Too many dishes.');
      expect(f.inDoc('kitchen-ticket-form-error')?.textContent).not.toContain(NOTICE);
    });

    it('a new opening starts with nothing marked', async () => {
      const f = await form({}, { [TICKETS]: refusal({ 'items.0.quantity': ABOVE_ZERO }) });
      await ionValue(f.field('dish-0-name'), 'Soup', 'ionInput');
      await click(f.field('submit'));
      await f.wrapper.setProps({ open: false });
      await settle();
      await f.wrapper.setProps({ open: true });
      await settle();
      expect(markOf(f.field('dish-0-quantity'))).toEqual(UNMARKED);
      expect(f.inDoc('kitchen-ticket-form-error')).toBeNull();
    });
  });

  it('speaks Spanish', async () => {
    const f = await form({}, {}, 'es');
    expect(f.inDoc('kitchen-ticket-form')?.getAttribute('aria-label')).toBe('Nueva comanda');
    expect(f.field('submit').textContent?.trim()).toBe('Crear comanda');
    expect(f.field('add-dish').textContent?.trim()).toBe('Añadir plato');
  });
});

describe('TicketFormModal: fields refused with the same words (hub#888)', () => {
  // Two dishes with their product (a Combo, named by its place in what was sent) and a label, each refused under its
  // own key.
  const FIELD_OF: Record<string, string> = { 'items.0.product_id': 'dish-0-product', 'items.1.product_id': 'dish-1-product', 'items.1.quantity': 'dish-1-quantity' };
  itTellsTheCorrectedFieldApart(['label', 'items.0.product_id', 'items.1.product_id', 'items.1.quantity'], async (locale, refusal) => {
    const f = await form({}, { '/api/kitchen/tickets': [422, refusal] }, locale);
    f.combo(0)!.vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
    await settle();
    await click(f.field('add-dish'));
    f.combo(1)!.vm.$emit('update:modelValue', { id: 'p2', label: 'Salad' });
    await settle();
    return { field: (key) => f.field(FIELD_OF[key] ?? key), send: () => click(f.field('submit')), settle };
  }, 'items.1.product_id');
});

describe('TicketFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const f = await form();
    const { expectUnsavedFormOnAndroidBack } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormOnAndroidBack({
      overlay: () => f.inDoc('kitchen-ticket-form'),
      change: () => ionValue(f.field('label'), 'Staff', 'ionInput'),
      restore: () => ionValue(f.field('label'), '', 'ionInput'),
    });
  });
});
