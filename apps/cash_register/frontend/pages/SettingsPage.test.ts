// Cash register → Settings (CASH_REGISTER-F01, F02): the drawer settings and the drawers, in the reading
// width of a settings page, under the app's tabs. Whoever lacks `cash_register.manage_settings` sees them
// blocked.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, mountCash } from '../__tests__/mount-cash-register';
import RegistersCard from '../components/RegistersCard.vue';
import SettingsCard from '../components/SettingsCard.vue';
import SettingsPage from './SettingsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

describe('SettingsPage', () => {
  it('is Cash register’s settings page, with its tabs, the settings and the drawers', async () => {
    const m = await mountCash(SettingsPage, { path: '/cash_register/settings' });
    const page = m.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Cash register');
    expect(page.props('contentLayout')).toBe('detail');
    expect((page.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['sessions', 'settings']);
    expect(m.wrapper.findComponent(SettingsCard).props('editable')).toBe(true);
    expect(m.wrapper.findComponent(RegistersCard).props('editable')).toBe(true);
  });

  it('the employee reads them blocked', async () => {
    const m = await mountCash(SettingsPage, { path: '/cash_register/settings', session: EMPLOYEE });
    expect(m.wrapper.findComponent(SettingsCard).props('editable')).toBe(false);
    expect(m.wrapper.findComponent(RegistersCard).props('editable')).toBe(false);
  });
});
