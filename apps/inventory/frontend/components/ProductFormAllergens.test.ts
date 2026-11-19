import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, ok, product, refusal } from '../__tests__/mount-inventory';
import { setup } from '../__tests__/product-form';

vi.mock('@ionic/vue', async (importOriginal) => (await import('../../../../base/frontend/__tests__/modal')).mockIonicModal(importOriginal));

afterEach(() => {
  document.body.innerHTML = '';
});

async function mark(id: string, code: string, checked: boolean) {
  const checkbox = document.querySelector<HTMLElement>(`[data-testid="${id}-${code}"] ion-checkbox`)!;
  checkbox.dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
  await flush();
}

describe('ProductFormModal: allergens', () => {
  it('shows the block after Description with the fourteen names in order and none selected on create', async () => {
    const s = await setup();
    const block = s.el('inventory-product-allergens')!;
    const description = s.el('inventory-product-description')!;

    expect(description.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(block.querySelector('legend')?.textContent?.trim()).toBe('Allergens');
    expect(block.querySelector('.allergen-select__helper')?.textContent?.trim()).toBe(
      'Mark the ones it has, also inside a sauce, a batter or a side.',
    );
    const checkboxes = [...block.querySelectorAll('ion-checkbox')];
    expect(checkboxes.map((checkbox) => checkbox.textContent?.trim())).toEqual([
      'Gluten',
      'Crustaceans',
      'Egg',
      'Fish',
      'Peanut',
      'Soy',
      'Milk',
      'Tree nuts',
      'Celery',
      'Mustard',
      'Sesame',
      'Sulphites',
      'Lupin',
      'Molluscs',
    ]);
    expect(checkboxes.every((checkbox) => (checkbox as HTMLElement & { checked: boolean }).checked === false)).toBe(true);
  });

  it('creates the product with the marked allergens in canonical order', async () => {
    const s = await setup();
    await s.fillRequired();
    await mark('inventory-product-allergens', 'milk', true);
    await mark('inventory-product-allergens', 'gluten', true);
    s.net.onApi(() => ok(product(), 201));
    await s.submit();

    expect(s.sent('/api/inventory/products').allergens).toEqual(['gluten', 'milk']);
  });

  it('edits only the changed selection', async () => {
    const s = await setup({ product: product({ allergens: ['milk'] }) });
    await mark('inventory-product-allergens', 'egg', true);
    await mark('inventory-product-allergens', 'milk', false);
    s.net.onApi(() => ok(product({ allergens: ['egg'] })));
    await s.submit();
    expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', allergens: ['egg'] });
  });

  it('shows a field refusal inside the block', async () => {
    const s = await setup({ product: product({ allergens: ['milk'] }) });
    await mark('inventory-product-allergens', 'fish', true);
    s.net.onApi(() => refusal(422, 'invalid_payload', 'Check the fields.', { allergens: 'Choose a valid allergen.' }));
    await s.submit();
    expect(document.querySelector('.allergen-select__error')?.textContent?.trim()).toBe('Choose a valid allergen.');
  });

  it('speaks Spanish, including every allergen name', async () => {
    const s = await setup({}, { locale: 'es' });
    const block = s.el('inventory-product-allergens')!;

    expect(block.querySelector('legend')?.textContent?.trim()).toBe('Alérgenos');
    expect(block.querySelector('.allergen-select__helper')?.textContent?.trim()).toBe(
      'Marca los que lleva, también dentro de una salsa, un rebozado o una guarnición.',
    );
    expect([...block.querySelectorAll('ion-checkbox')].map((checkbox) => checkbox.textContent?.trim())).toEqual([
      'Gluten',
      'Crustáceos',
      'Huevo',
      'Pescado',
      'Cacahuete',
      'Soja',
      'Leche',
      'Frutos de cáscara',
      'Apio',
      'Mostaza',
      'Sésamo',
      'Sulfitos',
      'Altramuces',
      'Moluscos',
    ]);
  });
});
