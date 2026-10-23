// Sales & POS → Settings (SALE-F34; WORKBOOK «Pantallas · Ajustes»): the till settings form under «Sales &
// POS» with its tabbar, in the reading width of a settings page. Whoever may change the till settings
// (`sale.manage_settings`) edits them (`sale.settings.get`); anyone else — an employee, who opens it from
// the menu — sees the business's values blocked (`sale.pos_settings.get`) with «You do not have permission
// to change these settings…», never a 403 nor the factory values.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { EMPLOYEE, type MountOptions, mountSale } from '../__tests__/mount-sale';
import SettingsForm from '../components/backoffice/SettingsForm.vue';
import SettingsPage from './SettingsPage.vue';

const SETTINGS = {
  allow_cash: true,
  allow_card: true,
  allow_transfer: false,
  show_products: true,
  show_services: true,
  require_customer: false,
  allow_discounts: true,
  max_discount_percent: 100,
  enable_parked_tickets: true,
  default_tax_included: true,
  auto_invoice_with_tax_id: false,
  default_document_type: 'ticket',
  receipt_header: '',
  receipt_footer: '',
  receipt_footer_image: '',
  receipt_marketing_url: '',
  receipt_marketing_text: '',
  updated_at: null,
};

async function setup(options: MountOptions = {}) {
  const m = await mountSale(SettingsPage, { path: '/sale/settings', ...options });
  await m.live();
  return m;
}

describe('SettingsPage', () => {
  it('sits under «Sales & POS» with its tabbar, in the reading width of a settings page', async () => {
    const m = await setup();
    const page = m.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('tabsLabel'), page.props('contentLayout')]).toEqual(['Sales & POS', 'Sales & POS sections', 'detail']);
    expect((page.props('tabs') as Array<{ id: string; to: string }>).find((tab) => tab.id === 'settings')?.to).toBe('/sale/settings');
  });

  it('whoever may change the till settings edits them', async () => {
    const m = await setup();
    expect(m.wrapper.findComponent(SettingsForm).props('editable')).toBe(true);
    expect(m.params('sale.settings.get')).toEqual([{}]);
    await m.result('sale.settings.get', SETTINGS);
    expect(m.find('sale-settings-save').exists()).toBe(true);
  });

  it('an employee sees the business’s values blocked and why, without asking what would be refused', async () => {
    const m = await setup({ session: EMPLOYEE });
    expect(m.wrapper.findComponent(SettingsForm).props('editable')).toBe(false);
    expect(m.params('sale.settings.get')).toEqual([]);
    await m.result('sale.pos_settings.get', SETTINGS);
    expect(m.find('sale-settings-read-only').text()).toBe('You do not have permission to change these settings. Ask an administrator if you need to.');
    expect(m.find('sale-settings-save').exists()).toBe(false);
  });
});
