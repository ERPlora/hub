import { afterEach, describe, expect, it } from 'vitest';

import { unsavedChangesIn } from '../../../../base/frontend/lib/system-back';
import { ionModalStubOf } from '../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub';
import { flush, ok, product } from '../__tests__/mount-inventory';
import { CATEGORIES, JAPANESE, searches, setup } from '../__tests__/product-form';

afterEach(() => {
  document.body.innerHTML = '';
});

// hub#1015 (INVENTORY-F01, F02; BASE-F05): on the installed app Android's Back closed «New product» and threw away what
// had been typed, without a word. The window signs up with the system Back (`useUnsavedChanges`): while something typed
// is not saved, Back on it asks «Discard changes?» («Keep editing» / «Discard changes») instead of closing it; as it
// opened (nothing typed, or put back as it was), Back closes it as before. What Back does with that is pinned in
// base/frontend/lib/system-back.test.ts and on the real app in tests/e2e/inventory-unsaved-changes.spec.ts.
describe('ProductFormModal: Back with something typed asks first (hub#1015)', () => {
  /** The window that holds Back in this dialog, if any: what the system Back asks before closing it. */
  const holding = (s: { el: (id: string) => HTMLElement | null }) => unsavedChangesIn(s.el('inventory-product-form')!);

  it('a new product as it opened holds nothing: Back closes it as before', async () => {
    const s = await setup();
    expect(holding(s)).toBeUndefined();
  });

  it.each([
    ['inventory-product-name', 'Coffee'],
    ['inventory-product-sku', 'CAF-1'],
    ['inventory-product-price', '2,20'],
    ['inventory-product-cost', '0,80'],
    ['inventory-product-initial-stock', '5'],
    ['inventory-product-threshold', '3'],
    ['inventory-product-ean13', '4006381333931'],
    ['inventory-product-description', 'Hot'],
  ])('something typed in %s holds Back', async (id, value) => {
    const s = await setup();
    await s.type(id, value);
    expect(holding(s)).toBeDefined();
  });

  it.each<[string, (s: Awaited<ReturnType<typeof setup>>) => Promise<void>]>([
    ['the type', (s) => s.pick('inventory-product-type', 'service')],
    ['the unit', (s) => s.pick('inventory-product-unit', 'kg')],
    ['the tax category', (s) => s.choose('inventory-product-tax', 'product.generic')],
    ['a category', (s) => s.choose('inventory-product-categories', 'c2')],
    ['«Track stock for this item»', (s) => s.check('inventory-product-track-stock', !s.el('inventory-product-track-stock')!.checked)],
  ])('%s chosen holds Back', async (_what, change) => {
    const s = await setup();
    await change(s);
    expect(holding(s)).toBeDefined();
  });

  it('typed and put back as it was holds nothing', async () => {
    const s = await setup();
    await s.type('inventory-product-name', 'Coffee');
    await s.type('inventory-product-name', '');
    expect(holding(s)).toBeUndefined();
  });

  it('editing: as saved it holds nothing, also once the business answers and the price is rewritten in its currency', async () => {
    const s = await setup({ product: product({ price: 220, cost: 80 }) }, { business: null });
    expect(holding(s)).toBeUndefined();
    await s.answer(JAPANESE);
    expect(s.el('inventory-product-price')?.value).toBe('220');
    expect(holding(s)).toBeUndefined();
    await s.type('inventory-product-name', 'Cola');
    expect(holding(s)).toBeDefined();
  });

  it('editing: the photo removed holds Back', async () => {
    const s = await setup({ product: product({ image: 'catalog:hospitality/americano', image_url: '/p/catalog/hospitality/americano.webp' }) });
    expect(holding(s)).toBeUndefined();
    s.el('inventory-product-image-remove')!.click();
    await flush();
    expect(holding(s)).toBeDefined();
  });

  it('asks «Discard changes?» with «Keep editing» and «Discard changes», in the window’s language', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.type('inventory-product-name', 'Café');
    const answer = holding(s)!.confirmDiscard();
    await flush();
    const asked = document.querySelector<HTMLElement>('[data-stub="ion-modal"][aria-label="¿Descartar los cambios?"]');
    expect(asked?.querySelector('.ep-form-modal__cancel')?.textContent?.trim()).toBe('Seguir editando');
    expect(asked?.querySelector('.ep-form-modal__submit')?.textContent?.trim()).toBe('Descartar cambios');
    asked!.querySelector<HTMLElement>('.ep-form-modal__cancel')!.click();
    await expect(answer).resolves.toBe(false);
    expect(s.el('inventory-product-name')?.value).toBe('Café');
  });

  it('saved and closed, it holds nothing; opened again, nothing either', async () => {
    const s = await setup({}, { api: (call) => ((call.init.method ?? 'GET') === 'GET' ? searches(CATEGORIES)(call) : ok(product(), 201)) });
    await s.fillRequired();
    await s.submit();
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    await s.wrapper.setProps({ open: false });
    expect(holding(s)).toBeUndefined();
    await s.wrapper.setProps({ open: true });
    await flush();
    expect(holding(s)).toBeUndefined();
  });
});

// hub#1023 (INVENTORY-F01, F02): «Cancel» («Cancel editing»), the window's «×», Escape and a tap outside closed «New product»
// and «Editing product» and threw away what had been typed, without a word, though Android's Back on it already asked
// (hub#1015). Now every way out asks the same «Discard changes?» (`useUnsavedChanges` gives its FormModal the question as
// `canDismiss`): «Keep editing» leaves the window as it was, «Discard changes» closes it; as it opened, they close it at
// once. On the real app: tests/e2e/inventory-unsaved-changes.spec.ts.
describe('ProductFormModal: Cancel, ×, Escape and a tap outside ask first with something typed (hub#1023)', () => {
  const QUESTION = '[data-stub="ion-modal"][aria-label="Discard changes?"]';
  const asked = () => document.querySelector<HTMLElement>(QUESTION);
  const answer = async (part: 'cancel' | 'submit') => {
    asked()!.querySelector<HTMLElement>(`.ep-form-modal__${part}`)!.click();
    await flush();
  };
  const form = () => document.querySelector<HTMLElement>('[data-stub="ion-modal"][data-testid="inventory-product-form"]')!;
  type Setup = Awaited<ReturnType<typeof setup>>;
  const ways: [string, (s: Setup) => Promise<void>][] = [
    ['«Cancel»', async (s) => {
      s.el('inventory-product-form-cancel')!.click();
      await flush();
    }],
    ['the «×»', async (s) => {
      s.el('inventory-product-form-close')!.click();
      await flush();
    }],
    ['Escape', async (s) => {
      s.el('inventory-product-name')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
      await flush();
    }],
    // Not awaited: with a question up, the tap settles only once it is answered.
    ['a tap outside', async () => {
      void ionModalStubOf(form()).tapBackdrop();
      await flush();
    }],
  ];

  it.each(ways)('%s on «New product» as it opened closes it at once, without asking', async (_way, leave) => {
    const s = await setup();
    await leave(s);
    expect(asked()).toBeNull();
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it.each(ways)('%s with something typed asks «Discard changes?»; «Keep editing» keeps the window and what was typed', async (_way, leave) => {
    const s = await setup();
    await s.type('inventory-product-name', 'Coffee');
    await leave(s);
    expect(asked()).not.toBeNull();
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    await answer('cancel');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(s.el('inventory-product-name')?.value).toBe('Coffee');
  });

  it.each(ways)('%s with something typed, then «Discard changes», closes it and saves nothing', async (_way, leave) => {
    const s = await setup();
    await s.type('inventory-product-name', 'Coffee');
    await leave(s);
    await answer('submit');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(s.calls('/api/inventory/products').filter((c) => (c.init.method ?? 'GET') !== 'GET')).toHaveLength(0);
  });

  it('«Cancel editing» on «Editing product»: as saved it closes at once; with a change it asks, in Spanish too', async () => {
    const s = await setup({ product: product({ price: 220 }) }, { locale: 'es' });
    s.el('inventory-product-form-cancel')!.click();
    await flush();
    expect(document.querySelector('[data-stub="ion-modal"][aria-label="¿Descartar los cambios?"]')).toBeNull();
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);

    const t = await setup({ product: product({ price: 220 }) }, { locale: 'es' });
    await t.type('inventory-product-name', 'Cola');
    t.el('inventory-product-form-cancel')!.click();
    await flush();
    const question = [...document.querySelectorAll<HTMLElement>('[data-stub="ion-modal"][aria-label="¿Descartar los cambios?"]')].at(-1);
    expect(question?.querySelector('.ep-form-modal__cancel')?.textContent?.trim()).toBe('Seguir editando');
    expect(question?.querySelector('.ep-form-modal__submit')?.textContent?.trim()).toBe('Descartar cambios');
    expect(t.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('the photo chosen and not saved asks too', async () => {
    const s = await setup({ product: product({ image: 'catalog:hospitality/americano', image_url: '/p/catalog/hospitality/americano.webp' }) });
    s.el('inventory-product-image-remove')!.click();
    await flush();
    s.el('inventory-product-form-cancel')!.click();
    await flush();
    expect(asked()).not.toBeNull();
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('saved, it closes without asking', async () => {
    const s = await setup({}, { api: (call) => ((call.init.method ?? 'GET') === 'GET' ? searches(CATEGORIES)(call) : ok(product(), 201)) });
    await s.fillRequired();
    await s.submit();
    expect(asked()).toBeNull();
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });
});
