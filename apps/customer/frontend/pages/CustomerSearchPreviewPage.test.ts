// The preview of the till's customer search (dev server only, routes.ts): CustomerSearch as Sales will
// mount it, and what it hands the sale, so it can be driven end to end before Sales exists.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountCustomer } from '../__tests__/mount-customer';
import CustomerSearch from '../components/CustomerSearch.vue';
import CustomerSearchPreviewPage from './CustomerSearchPreviewPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('CustomerSearchPreviewPage', () => {
  it('shows the search and «No customer assigned.» to begin with', async () => {
    const m = await mountCustomer(CustomerSearchPreviewPage, { path: '/customer/preview/customer-search', attachTo: document.body });
    expect(m.wrapper.findComponent(AppPage).props('title')).toBe('Customer search (preview)');
    expect(m.wrapper.findComponent(CustomerSearch).exists()).toBe(true);
    expect(m.wrapper.get('[data-testid="customer-preview-none"]').text()).toBe('No customer assigned.');
  });

  it('paints what the search hands the sale', async () => {
    const m = await mountCustomer(CustomerSearchPreviewPage, { attachTo: document.body });
    m.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', {
      customer_id: 'c1',
      customer_name: 'ACME',
      display_name: 'Ana',
      customer_tax_id: 'X1',
      customer_address: 'Calle 1, 28001 Madrid, Spain',
      customer_country: 'ES',
    });
    await flush();
    const snapshot = m.wrapper.get('[data-testid="customer-preview-snapshot"]');
    expect(snapshot.findAll('dd').map((d) => d.text())).toEqual(['c1', 'ACME', 'Ana', 'X1', 'Calle 1, 28001 Madrid, Spain', 'ES']);
  });
});
