import { describe, expect, it } from 'vitest';

import { ionChecked, ionValue, mountBase } from '../__tests__/mount-base';
import type { RolePermission } from '../operations/people';
import RolePermissionRow from './RolePermissionRow.vue';

function permission(fields: Partial<RolePermission> = {}): RolePermission {
  return { permission: 'sale.take_payment', phrase: 'Cobrar', state: 'on', approvable: false, to_review: false, ...fields };
}

async function open(line: RolePermission, state = line.state) {
  return mountBase(RolePermissionRow, { locale: 'es', props: { line, state } });
}

describe('RolePermissionRow', () => {
  it('a permission nobody approves is a switch named by its phrase', async () => {
    const m = await open(permission());
    const toggle = m.wrapper.get('[data-testid="role-switch-sale.take_payment"]');
    expect(toggle.text()).toBe('Cobrar');
    expect((toggle.element as unknown as { checked: boolean }).checked).toBe(true);
    expect(m.wrapper.find('ion-segment').exists()).toBe(false);
  });

  it('switching it says what it becomes', async () => {
    const m = await open(permission());
    const toggle = m.wrapper.get('[data-testid="role-switch-sale.take_payment"]').element;
    await ionChecked(toggle, false);
    await ionChecked(toggle, true);
    expect(m.wrapper.emitted('change')).toEqual([['off'], ['on']]);
  });

  it('what a manager can approve has the three states, named by its phrase', async () => {
    const m = await open(permission({ permission: 'sale.void_sale', phrase: 'Anular una venta', state: 'approval', approvable: true }));
    const segment = m.wrapper.get('[data-testid="role-states-sale.void_sale"]');
    expect(segment.attributes('aria-label')).toBe('Anular una venta');
    expect(segment.html().match(/Permitido|Con aprobación|\bNo\b/g)).toEqual(['Permitido', 'Con aprobación', 'No']);
    expect(segment.findAll('ion-segment-button')).toHaveLength(3);
    expect((segment.element as unknown as { value: string }).value).toBe('approval');
    expect(m.wrapper.find('ion-toggle').exists()).toBe(false);
    await ionValue(segment.element, 'off');
    expect(m.wrapper.emitted('change')).toEqual([['off']]);
  });

  it('it paints the state the form holds, not the saved one', async () => {
    const m = await open(permission({ state: 'on' }), 'off');
    expect((m.wrapper.get('ion-toggle').element as unknown as { checked: boolean }).checked).toBe(false);
    const approvable = await open(permission({ approvable: true, state: 'approval' }), 'on');
    expect((approvable.wrapper.get('ion-segment').element as unknown as { value: string }).value).toBe('on');
  });

  it('one left to review is marked, of either kind; the others are not', async () => {
    expect((await open(permission())).wrapper.find('[data-testid="role-to-review"]').exists()).toBe(false);
    const marked = await open(permission({ to_review: true }));
    expect(marked.wrapper.get('[data-testid="role-to-review"]').text()).toBe('Por revisar');
    const approvable = await open(permission({ to_review: true, approvable: true }));
    expect(approvable.wrapper.get('[data-testid="role-to-review"]').text()).toBe('Por revisar');
  });
});
