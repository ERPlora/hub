// «New ticket» (WORKBOOK «Pantallas · Comandas»; KITCHEN-F23): Type (it starts at the settings' default),
// Destination and Notes (optional) and its dishes — a product of the catalogue, or the dish written by
// hand, its quantity and a note — with «Add dish» and «Remove dish»; «Create ticket» only with a dish.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

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

  it('speaks Spanish', async () => {
    const f = await form({}, {}, 'es');
    expect(f.inDoc('kitchen-ticket-form')?.getAttribute('aria-label')).toBe('Nueva comanda');
    expect(f.field('submit').textContent?.trim()).toBe('Crear comanda');
    expect(f.field('add-dish').textContent?.trim()).toBe('Añadir plato');
  });
});
