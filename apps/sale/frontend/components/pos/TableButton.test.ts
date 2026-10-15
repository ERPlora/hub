// The table button of the check's bar (SALE-F19), before the customer's: an icon-only grid that opens
// «Choose table». With a table on the check it turns the primary colour and names the table.
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import TableButton from './TableButton.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(TableButton, { props: { tableNumber: null, ...props }, locale });
}

describe('TableButton', () => {
  it('without a table it offers to assign one, and a tap opens the picker', async () => {
    const m = await setup({}, 'es');
    const trigger = m.find('pos-table-trigger');
    expect(trigger.attributes('aria-label')).toBe('Asignar mesa');
    expect(trigger.attributes('title')).toBe('Asignar mesa');
    expect(trigger.classes()).not.toContain('pos-table-trigger--assigned');
    expect(trigger.findComponent(HubIcon).props('name')).toBe('ion:grid-outline');
    await click(trigger.element);
    expect(m.wrapper.emitted('open')).toHaveLength(1);
  });

  it('with a table it is the primary colour and names it', async () => {
    const m = await setup({ tableNumber: '4' });
    const trigger = m.find('pos-table-trigger');
    expect(trigger.attributes('aria-label')).toBe('Assign table: Table 4');
    expect(trigger.attributes('title')).toBe('Assign table: Table 4');
    expect(trigger.classes()).toContain('pos-table-trigger--assigned');
  });
});
