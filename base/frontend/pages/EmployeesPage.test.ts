// Employees (BASE-G11; the old hub's EmployeesPage): the footer tabbar of its sections, the tab in the hash so a link
// opens it and Back leaves the page — «Staff» (the people), «Roles», «API keys» and «Approvals», in the old hub's
// order. «API keys» and «Approvals» are only for who runs the business: anyone else has no such tab, and their hash
// opens «Staff» (the old hub left a blank page there). Only the open tab's panel is painted, so only it asks the hub.
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, type MountOptions, mountBase } from '../__tests__/mount-base';
import EmployeesPage from './EmployeesPage.vue';

const PANELS = {
  personal: 'people-list-stub',
  roles: 'roles-list-stub',
  apikeys: 'api-keys-panel-stub',
  approvals: 'approvals-list-stub',
};

async function employees(path = '/employees', locale: 'en' | 'es' = 'en', session?: MountOptions['session']) {
  return mountBase(EmployeesPage, {
    path,
    locale,
    session,
    routes: ['/employees'],
    stubs: { PeopleList: true, RolesList: true, ApiKeysPanel: true, ApprovalsList: true },
  });
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('EmployeesPage', () => {
  it('is «Employees» with its four tabs, in the old hub’s order, «Staff» first', async () => {
    const m = await employees('/employees', 'es');
    const page = m.wrapper.getComponent(AppPage);
    expect(page.props('title')).toBe('Empleados');
    expect(page.props('tabs')).toEqual([
      { id: 'personal', label: 'Personal', icon: 'ion:people-outline' },
      { id: 'roles', label: 'Roles', icon: 'ion:shield-checkmark-outline' },
      { id: 'apikeys', label: 'API keys', icon: 'ion:keypad-outline' },
      { id: 'approvals', label: 'Aprobaciones', icon: 'ion:finger-print-outline' },
    ]);
    expect(page.props('tabsLabel')).toBe('Secciones de Empleados');
  });

  it('paints the panel of the tab in the address, and only that one', async () => {
    const hashes = { personal: '', roles: '#roles', apikeys: '#apikeys', approvals: '#approvals' };
    for (const [tab, hash] of Object.entries(hashes)) {
      const m = await employees(`/employees${hash}`);
      for (const [other, stub] of Object.entries(PANELS)) {
        expect(m.wrapper.find(stub).exists(), `${hash} ${other}`).toBe(other === tab);
      }
      m.wrapper.unmount();
    }
  });

  it('an address with a tab it does not have opens «Staff»', async () => {
    const m = await employees('/employees#store');
    expect(m.wrapper.find(PANELS.personal).exists()).toBe(true);
  });

  it('whoever does not run the business has no «API keys» nor «Approvals», and their hash opens «Staff»', async () => {
    for (const hash of ['#apikeys', '#approvals']) {
      const m = await employees(`/employees${hash}`, 'en', EMPLOYEE);
      const tabs = (m.wrapper.getComponent(AppPage).props('tabs') as { id: string }[]).map((tab) => tab.id);
      expect(tabs, hash).toEqual(['personal', 'roles']);
      expect(m.wrapper.find(PANELS.personal).exists(), hash).toBe(true);
      expect(m.wrapper.find(PANELS.apikeys).exists(), hash).toBe(false);
      expect(m.wrapper.find(PANELS.approvals).exists(), hash).toBe(false);
      m.wrapper.unmount();
    }
  });

  it('choosing a tab writes it in the hash, replacing the address (Back leaves the page)', async () => {
    const m = await employees('/employees');
    m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'roles');
    await m.router.isReady();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(m.router.currentRoute.value.hash).toBe('#roles');
    m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'personal');
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(m.router.currentRoute.value.hash).toBe('');
  });
});
