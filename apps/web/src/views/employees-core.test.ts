import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const listSource = readFileSync(new URL('./EmployeesPage.vue', import.meta.url), 'utf8');
const formSource = readFileSync(new URL('./EmployeeFormPage.vue', import.meta.url), 'utf8');

describe('Employees core contracts', () => {
  it('uses the current staff module operation names', () => {
    expect(listSource).toContain("'staff.members.list'");
    expect(listSource).toContain("'staff.roles.list'");
    expect(listSource).not.toContain("'staff.members_list'");
    expect(listSource).not.toContain("'staff.roles_list'");
  });

  it('does not expose inert create, edit, or delete actions', () => {
    expect(listSource).toContain("'staff.members.create'");
    expect(listSource).toContain("'staff.roles.create'");
    expect(listSource).toContain("'staff.members.delete'");
    expect(listSource).not.toContain("console.info('roles.new')");
    expect(formSource).toContain("'staff.members.get'");
    expect(formSource).toContain("'staff.members.update'");
    expect(formSource).not.toContain('María García');
  });

  it('shows real Hub users instead of a future placeholder', () => {
    expect(listSource).toContain('pinUsers');
    expect(listSource).not.toContain('usersPlaceholder');
  });
});
