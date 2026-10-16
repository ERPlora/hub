// Printing → Settings (PRINTING-F06): the ticket settings and each role's printer, in the reading width of
// a settings page, under the app's tabs. Whoever lacks `printing.manage_settings` sees them blocked.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { EMPLOYEE, MANAGER, mountPrinting } from '../__tests__/mount-printing';
import SettingsCard from '../components/SettingsCard.vue';
import SettingsPage from './SettingsPage.vue';

describe('SettingsPage', () => {
  it('is Printing’s settings page, with its tabs and the settings', async () => {
    const m = await mountPrinting(SettingsPage, { path: '/printing/settings' });
    const page = m.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Printing');
    expect(page.props('contentLayout')).toBe('detail');
    expect((page.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['printers', 'jobs', 'settings']);
    expect(m.wrapper.findComponent(SettingsCard).props('editable')).toBe(true);
  });

  it('the manager changes them; the employee reads them blocked', async () => {
    const manager = await mountPrinting(SettingsPage, { path: '/printing/settings', session: MANAGER });
    expect(manager.wrapper.findComponent(SettingsCard).props('editable')).toBe(true);
    const employee = await mountPrinting(SettingsPage, { path: '/printing/settings', session: EMPLOYEE });
    expect(employee.wrapper.findComponent(SettingsCard).props('editable')).toBe(false);
  });
});
