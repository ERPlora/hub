// «Park check» (SALE-F17 step 2): the title comes with the time (in the reader's language) and can be
// changed («e.g. Ana — terrace»); Enter or «Park this check» confirms, «Cancel» does not. A refusal is
// read in the sheet.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import ParkSheet from './ParkSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 14, 13, 7));
});
afterEach(() => vi.useRealTimers());

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const m = await mountSale(
    { setup: () => () => h(ParkSheet, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), pending: false, error: null, ...props }) },
    { locale },
  );
  await settle();
  const field = () => m.find('pos-park-name').element as HTMLInputElement;
  return { ...m, open, field, sheet: () => m.wrapper.findComponent(ParkSheet) };
}

describe('ParkSheet', () => {
  it('is «Park check», with its hint and the time as the title', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-park-title').text()).toBe('Aparcar cuenta');
    expect(m.find('pos-park-hint').text()).toBe('El título es opcional y solo sirve para reconocer la cuenta cuando quieras retomarla.');
    expect(m.field().value).toBe('13:07');
    expect(m.field().placeholder).toBe('p. ej. Ana — terraza');
    expect(m.field().getAttribute('aria-label')).toBe('Título opcional');
    expect(m.find('pos-park-confirm').text()).toBe('Aparcar esta cuenta');
  });

  it('parks under the title typed, trimmed; with Enter too', async () => {
    const m = await setup();
    m.field().value = '  Ana — terrace ';
    m.field().dispatchEvent(new Event('input'));
    await click(m.find('pos-park-confirm').element);
    m.field().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(m.sheet().emitted('park')).toEqual([['Ana — terrace'], ['Ana — terrace']]);
  });

  it('«Cancel» closes it without parking', async () => {
    const m = await setup();
    await click(m.find('pos-park-cancel').element);
    expect(m.open.value).toBe(false);
    expect(m.sheet().emitted('park')).toBeUndefined();
  });

  it('a refusal is read in the sheet; the button waits while parking', async () => {
    const m = await setup({ error: 'The check could not be parked. It is still on screen.', pending: true });
    expect(m.find('pos-park-error').text()).toBe('The check could not be parked. It is still on screen.');
    expect((m.find('pos-park-confirm').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });
});
