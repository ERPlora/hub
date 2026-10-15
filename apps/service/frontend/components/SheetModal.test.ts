// The sheet a voucher's lists open over the packages table (Sold vouchers, Movements, Vouchers with no
// customer): its title and what it shows, its rows, «Close», and «Load more» with «Showing {shown} of
// {total}» while there are more.
import { describe, expect, it, vi } from 'vitest';

import { click, mountService, settle } from '../__tests__/mount-service';
import SheetModal from './SheetModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountService(SheetModal, {
    props: { open: true, title: 'Sold vouchers — Bono', hint: 'Every customer', testid: 'sheet', shown: 2, total: 2, ...props },
    locale,
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  return m;
}

describe('SheetModal', () => {
  it('shows its title, its hint and its content, and closes', async () => {
    const m = await mountService(SheetModal, {
      props: { open: true, title: 'Sold vouchers — Bono', hint: 'Every customer', testid: 'sheet', shown: 0, total: 0 },
    });
    await settle();
    expect(m.inDoc('sheet-title')?.textContent).toContain('Sold vouchers — Bono');
    expect(m.inDoc('sheet-hint')?.textContent).toContain('Every customer');
    await click(m.inDoc('sheet-close'));
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('offers «Load more» with the count while there are more', async () => {
    const m = await setup({ shown: 20, total: 45 });
    expect(m.inDoc('sheet-count')?.textContent).toContain('Showing 20 of 45');
    await click(m.inDoc('sheet-more'));
    expect(m.wrapper.emitted('more')).toHaveLength(1);
    const all = await setup({ shown: 2, total: 2 });
    expect(all.inDoc('sheet-more')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const m = await setup({ shown: 20, total: 45 }, 'es');
    expect(m.inDoc('sheet-count')?.textContent).toContain('Se muestran 20 de 45');
    expect(m.inDoc('sheet-more')?.textContent).toContain('Cargar más');
    expect(m.inDoc('sheet-close')?.textContent).toContain('Cerrar');
  });
});
