// «CSV tax categories» (WORKBOOK INVENTORY-F09, step 2): one block per fiscal text Taxes did not
// recognise (or «Rows with no tax category»), each with «Pick» (a tax category of Taxes), «Create»
// (Key and Name) or «Skip», and «Confirm & import»; «Cancel» imports nothing.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountInventory, TAX_CATEGORIES } from '../__tests__/mount-inventory';
import ImportTaxModal from './ImportTaxModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; label?: string };

const choice = (mode: 'pick' | 'create' | 'skip', text: string) => ({ mode, key: '', newKey: '', newName: text });

async function setup(unresolved: unknown[], locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(ImportTaxModal, { props: { open: true, unresolved }, locale, attach: true });
  // Only «Pick» follows the tax categories: without it there is no stream to open.
  if (m.client.stream.subscriptions('tax.category.list').length > 0) {
    const call = await m.live();
    await m.result(call, 'tax.category.list', TAX_CATEGORIES);
  }
  await flush();
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<Control>(`[data-testid="${id}"]`)];
  return { ...m, el, all };
}

describe('ImportTaxModal', () => {
  it('one block per text, the rows without one named as such, «Pick» first', async () => {
    const s = await setup([
      { text: 'Vino', choice: choice('pick', 'Vino') },
      { text: '', choice: choice('pick', '') },
    ]);
    expect(s.el('inventory-import-tax')?.getAttribute('aria-label')).toBe('CSV tax categories');
    expect(s.all('inventory-import-tax-text').map((el) => el.textContent?.trim())).toEqual(['«Vino»', 'Rows with no tax category']);
    expect(s.all('inventory-import-tax-mode').map((el) => el.value)).toEqual(['pick', 'pick']);
    expect(s.all('inventory-import-tax-pick')).toHaveLength(2);
    expect(s.el('inventory-import-tax-submit')?.textContent?.trim()).toBe('Confirm & import');
  });

  it('switching to «Create» asks for Key and Name; every change goes to the importer', async () => {
    const s = await setup([{ text: 'Vino', choice: choice('create', 'Vino') }]);
    expect([s.el('inventory-import-tax-new-key')?.label, s.el('inventory-import-tax-new-name')?.label, s.el('inventory-import-tax-new-name')?.value]).toEqual([
      'Key',
      'Name',
      'Vino',
    ]);
    const key = s.el('inventory-import-tax-new-key')!;
    key.value = 'drinks.wine';
    key.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'drinks.wine' } }));
    await flush();
    const mode = s.el('inventory-import-tax-mode')!;
    mode.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'skip' } }));
    await flush();
    expect(s.wrapper.emitted('setChoice')).toEqual([
      ['Vino', { newKey: 'drinks.wine' }],
      ['Vino', { mode: 'skip' }],
    ]);
  });

  it('«Confirm & import» is off while a block is incomplete («Pick» without a category, «Create» without a key) or the import runs', async () => {
    const submit = (s: Awaited<ReturnType<typeof setup>>) => (s.el('inventory-import-tax-submit') as Control & { disabled?: boolean }).disabled;
    expect(submit(await setup([{ text: 'Vino', choice: choice('pick', 'Vino') }]))).toBe(true);
    document.body.innerHTML = '';
    expect(submit(await setup([{ text: 'Vino', choice: { ...choice('pick', 'Vino'), key: 'product.generic' } }]))).toBe(false);
    document.body.innerHTML = '';
    expect(submit(await setup([{ text: 'Vino', choice: choice('create', 'Vino') }]))).toBe(true);
    document.body.innerHTML = '';
    expect(submit(await setup([{ text: 'Vino', choice: { ...choice('create', 'Vino'), newKey: 'drinks.wine' } }]))).toBe(false);
    document.body.innerHTML = '';
    expect(submit(await setup([{ text: 'Vino', choice: choice('skip', 'Vino') }]))).toBe(false);
    document.body.innerHTML = '';
    const running = await mountInventory(ImportTaxModal, {
      props: { open: true, pending: true, unresolved: [{ text: 'Vino', choice: choice('skip', 'Vino') }] },
      attach: true,
    });
    await flush();
    expect((running.wrapper.find('[data-testid="inventory-import-tax-submit"]').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });

  it('«Confirm & import» and «Cancel» go to the importer', async () => {
    const s = await setup([{ text: 'Vino', choice: choice('skip', 'Vino') }]);
    s.el('inventory-import-tax-submit')!.click();
    await flush();
    expect(s.wrapper.emitted('confirm')).toHaveLength(1);
    s.el('inventory-import-tax-cancel')!.click();
    await flush();
    expect(s.wrapper.emitted('cancel')).toHaveLength(1);
  });

  it('speaks Spanish', async () => {
    const s = await setup([{ text: '', choice: choice('pick', '') }], 'es');
    expect(s.el('inventory-import-tax')?.getAttribute('aria-label')).toBe('Categorías fiscales del CSV');
    expect(s.el('inventory-import-tax-text')?.textContent?.trim()).toBe('Filas sin categoría fiscal');
  });
});
