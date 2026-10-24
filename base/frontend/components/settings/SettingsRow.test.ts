// One row of a Settings card (the old hub's): its icon, its name, the line that says what it is for and, at the end,
// either its value (read-only) or a chevron that opens another screen. The two Settings tabs of APP-BASE-6 use it.
import { HubIcon } from '@erplora/ui/shell';
import { IonItem } from '@ionic/vue';
import { afterEach, describe, expect, it } from 'vitest';

import { flush, mountBase } from '../../__tests__/mount-base';
import SettingsRow from './SettingsRow.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SettingsRow', () => {
  it('a value: icon, name, what it is for and the value at the end, nothing to press', async () => {
    const m = await mountBase(SettingsRow, {
      props: { icon: 'ion:globe-outline', title: 'Country', hint: 'The one of its taxes', value: 'Spain' },
    });
    expect(m.wrapper.getComponent(HubIcon).props('name')).toBe('ion:globe-outline');
    expect(m.wrapper.get('[data-testid="settings-row-title"]').text()).toBe('Country');
    expect(m.wrapper.get('[data-testid="settings-row-hint"]').text()).toBe('The one of its taxes');
    expect(m.wrapper.get('[data-testid="settings-row-value"]').text()).toBe('Spain');
    const item = m.wrapper.getComponent(IonItem);
    expect(item.props('button')).not.toBe(true);
    expect(item.props('detail')).not.toBe(true);
  });

  it('a link: a chevron instead of a value, and pressing it opens its screen', async () => {
    const m = await mountBase(SettingsRow, {
      props: { icon: 'ion:receipt-outline', title: 'Fiscal data', hint: 'What invoices use', to: '/invoice/issuer' },
      routes: ['/invoice/issuer'],
    });
    expect(m.wrapper.find('[data-testid="settings-row-value"]').exists()).toBe(false);
    const item = m.wrapper.getComponent(IonItem);
    expect(item.props('detail')).toBe(true);
    expect(item.props('button')).toBe(true);
    await item.trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/invoice/issuer');
  });
});
