// The heading of the check (WORKBOOK «Vender»): the editable title («New check») and the chips of the
// customer, «Served by …» and «Customer required» (SALE-F05, F16).
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import CartHeading from './CartHeading.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(CartHeading, {
    props: { label: '', customerName: null, staffId: null, staffName: null, needsCustomer: false, ...props },
    locale,
  });
}

const title = (m: Awaited<ReturnType<typeof setup>>) => m.find('pos-check-title').element as HTMLInputElement;

describe('CartHeading: the title', () => {
  it('is an input with «New check» as placeholder and the check’s title as value', async () => {
    const m = await setup({ label: 'Ana — terrace' }, 'es');
    expect(title(m).value).toBe('Ana — terrace');
    expect(title(m).placeholder).toBe('Cuenta nueva');
    expect(title(m).getAttribute('aria-label')).toBe('Título de la cuenta');
    expect(m.find('pos-check-title-edit').attributes('aria-label')).toBe('Editar título de la cuenta');
  });

  it('a changed title goes up trimmed, once, when the field is left', async () => {
    const m = await setup({ label: 'Old' });
    title(m).value = '  Table 4 ';
    title(m).dispatchEvent(new Event('change'));
    expect(m.wrapper.emitted('rename')).toEqual([['Table 4']]);
    await m.wrapper.setProps({ label: 'Table 4' });
    title(m).dispatchEvent(new Event('change'));
    expect(m.wrapper.emitted('rename')).toHaveLength(1);
  });

  it('follows the title the server keeps', async () => {
    const m = await setup({ label: 'One' });
    await m.wrapper.setProps({ label: 'Two' });
    expect(title(m).value).toBe('Two');
  });
});

describe('CartHeading: the chips', () => {
  it('with nobody chosen it is served by «me» and has no table nor customer', async () => {
    const m = await setup({}, 'es');
    const staff = m.find('pos-staff-chip');
    expect(staff.text()).toBe('Atiende yo');
    expect(staff.attributes('title')).toBe('Quién atiende esta cuenta');
    expect(m.find('pos-check-context-empty').text()).toBe('Cuenta sin mesa ni cliente');
  });

  it('names the chosen professional, or «the assigned professional» while the name is unknown', async () => {
    expect((await setup({ staffId: 's1', staffName: 'Marta' })).find('pos-staff-chip').text()).toBe('Served by Marta');
    expect((await setup({ staffId: 's1' })).find('pos-staff-chip').text()).toBe('Served by the assigned professional');
  });

  it('the staff chip opens the picker', async () => {
    const m = await setup();
    await click(m.find('pos-staff-chip').element);
    expect(m.wrapper.emitted('staff')).toHaveLength(1);
  });

  it('shows the customer', async () => {
    const m = await setup({ customerName: 'Lucía' });
    expect(m.find('pos-customer-chip').text()).toBe('Lucía');
    expect(m.find('pos-check-context-empty').exists()).toBe(false);
  });

  it('a business that requires a customer shows «Customer required», which asks for one', async () => {
    const m = await setup({ needsCustomer: true }, 'es');
    const chip = m.find('pos-needs-customer');
    expect(chip.text()).toBe('Falta el cliente');
    expect(chip.attributes('title')).toBe('Este negocio exige un cliente en cada venta. Elige uno para seguir con el cobro.');
    await click(chip.element);
    expect(m.wrapper.emitted('askCustomer')).toHaveLength(1);
    expect(m.find('pos-check-context-empty').exists()).toBe(false);
  });
});
