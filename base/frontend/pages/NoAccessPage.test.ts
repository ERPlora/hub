import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import NoAccessPage from './NoAccessPage.vue';

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(NoAccessPage, { path: '/tax/rules', session: EMPLOYEE, ...options });
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('NoAccessPage', () => {
  it('says the screen does not open for this role, and looks for who can give it', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.access.grantors')).toHaveLength(1);
    expect(m.wrapper.text()).toContain('No access');
    expect(m.wrapper.find('[data-testid="no-access"]').text()).toContain('You do not have access to this screen');
    expect(m.wrapper.find('[data-testid="no-access-checking"]').exists()).toBe(true);
  });

  it('names who can give it, each with their avatar, and nothing else of them', async () => {
    const m = await open();
    await m.result(m.call, 'base.access.grantors', { grantors: [{ name: 'Olga Ruiz' }, { name: 'Adam' }] });
    expect(m.wrapper.find('[data-testid="no-access-checking"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="no-access-ask"]').text()).toContain('Ask one of these people to give you access');
    const people = m.wrapper.findAll('[data-testid="no-access-grantor"]');
    expect(people.map((row) => row.text())).toEqual([expect.stringContaining('Olga Ruiz'), expect.stringContaining('Adam')]);
    expect(people[0].findComponent({ name: 'UserAvatar' }).props('name')).toBe('Olga Ruiz');
  });

  it('with nobody to name, it says to ask whoever runs the business', async () => {
    const m = await open();
    await m.result(m.call, 'base.access.grantors', { grantors: [] });
    expect(m.wrapper.find('[data-testid="no-access-nobody"]').text()).toContain('Ask whoever runs the business');
    expect(m.wrapper.find('[data-testid="no-access-grantors"]').exists()).toBe(false);
  });

  it('a failed look says so, still says the screen is closed, and tries again', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.access.grantors'), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="no-access-error"]').text()).toContain('We could not find out who can give you access');
    expect(m.wrapper.find('[data-testid="no-access"]').text()).toContain('You do not have access to this screen');
    await m.wrapper.find('[data-testid="no-access-retry"]').trigger('click');
    await flush();
    expect(m.client.stream.subscriptions('base.access.grantors').length).toBeGreaterThan(0);
  });

  it('leads back to the Home', async () => {
    const m = await open();
    await m.result(m.call, 'base.access.grantors', { grantors: [{ name: 'Olga' }] });
    await m.wrapper.find('[data-testid="no-access-home"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/');
  });

  it('in Spanish', async () => {
    const m = await open({ locale: 'es' });
    expect(m.wrapper.text()).toContain('Sin acceso');
    expect(m.wrapper.find('[data-testid="no-access"]').text()).toContain('No tienes acceso a esta pantalla');
    await m.result(m.call, 'base.access.grantors', { grantors: [{ name: 'Olga' }] });
    expect(m.wrapper.find('[data-testid="no-access-ask"]').text()).toContain('Pide acceso a una de estas personas');
    expect(m.wrapper.find('[data-testid="no-access-home"]').text()).toBe('Ir al Inicio');
  });
});
