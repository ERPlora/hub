// «Export CSV» of the customer list's toolbar (CUSTOMER-F09): downloads `customers.csv` with EVERY
// card matching the search and filters, not just the page shown; the server builds the file and
// checks the permission.
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import CustomerExportButton from './CustomerExportButton.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastError: vi.fn(() => Promise.resolve()),
}));

beforeEach(() => vi.mocked(toastError).mockClear());
afterEach(() => vi.restoreAllMocks());

describe('CustomerExportButton', () => {
  it('asks the server for the file with the search and filters and downloads it', async () => {
    const m = await mountCustomer(CustomerExportButton, { props: { filters: { search: 'ana', lifecycle_stage: 'vip' } } });
    m.net.onApi(() => json({ filename: 'customers.csv', content_type: 'text/csv', rows: 1, csv: 'name\nAna\n' }));
    const created = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    const revoked = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect([this.download, this.href]).toEqual(['customers.csv', 'blob:x']);
    });
    const button = m.wrapper.get('[data-testid="customer-export"]');
    expect(button.text()).toBe('Export CSV');
    await button.trigger('click');
    await flush();
    const call = sent(m.net.api[0]);
    expect([m.net.api[0].init.method, call.path, call.query]).toEqual([
      'GET',
      '/api/customer/customers/export',
      { search: 'ana', lifecycle_stage: 'vip' },
    ]);
    expect(clicked).toHaveBeenCalledOnce();
    const blob = created.mock.calls[0][0] as Blob;
    expect(await blob.text()).toBe('﻿name\nAna\n');
    expect(revoked).toHaveBeenCalledWith('blob:x');
  });

  it('a refusal (no permission to export) is told in a toast', async () => {
    const m = await mountCustomer(CustomerExportButton, { props: { filters: {} } });
    m.net.onApi(() => refusal(403, 'permission_denied', 'You do not have permission to do that.'));
    await m.wrapper.get('[data-testid="customer-export"]').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('The customers could not be exported: You do not have permission to do that.');
  });

  it('speaks Spanish', async () => {
    const m = await mountCustomer(CustomerExportButton, { props: { filters: {} }, locale: 'es' });
    expect(m.wrapper.get('[data-testid="customer-export"]').text()).toBe('Exportar CSV');
  });
});
