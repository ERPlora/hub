// «Import CSV» of the customer list's toolbar (CUSTOMER-F08): it picks a CSV file and hands it up.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mountCustomer } from '../__tests__/mount-customer';
import CustomerImportButton from './CustomerImportButton.vue';

afterEach(() => vi.restoreAllMocks());

describe('CustomerImportButton', () => {
  it('«Import CSV» opens the file picker for CSV files and hands up the file chosen', async () => {
    const m = await mountCustomer(CustomerImportButton, { props: { busy: false } });
    const input = m.wrapper.get('input[type="file"]');
    expect(input.attributes('accept')).toBe('.csv,text/csv');
    const opened = vi.spyOn(input.element as HTMLInputElement, 'click');
    const button = m.wrapper.get('[data-testid="customer-import"]');
    expect(button.text()).toBe('Import CSV');
    await button.trigger('click');
    expect(opened).toHaveBeenCalledOnce();
    const file = new File(['name\nAna'], 'c.csv', { type: 'text/csv' });
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
    await input.trigger('change');
    expect(m.wrapper.emitted('pick')).toEqual([[file]]);
  });

  it('is off while an import is running', async () => {
    const m = await mountCustomer(CustomerImportButton, { props: { busy: true } });
    expect((m.wrapper.get('[data-testid="customer-import"]').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });
});
