// Contrato de la pantalla de **Personal**: es CORE, no una vista del módulo `staff`.
//
// Antes leía `staff.members.list`/`staff.roles.list`. El módulo `staff` es otra cosa (profesional
// reservable, comisiones, horarios) y trae su propia navegación; en un hub sin él la pantalla salía
// con «No se pudo cargar el personal» y el owner/administrador —que entra por Cloud y no tiene
// PIN— no aparecía por ningún lado. La fuente es `hub_user` vía `lib/hub-users.ts`.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const listSource = readFileSync(new URL('./EmployeesPage.vue', import.meta.url), 'utf8');
const formSource = readFileSync(new URL('./EmployeeFormPage.vue', import.meta.url), 'utf8');

describe('Personal (core)', () => {
  it('no le pide nada al módulo staff', () => {
    for (const source of [listSource, formSource]) {
      expect(source).not.toMatch(/['"]staff\.[\w.]+['"]/);
    }
  });

  it('lista y gestiona los usuarios del hub con el cliente core', () => {
    expect(listSource).toContain('listHubUsers');
    expect(listSource).toContain('createHubUser');
    expect(listSource).toContain('deactivateHubUser');
    expect(listSource).toContain('listHubRoles');
    expect(formSource).toContain('updateHubUser');
  });

  it('oculta la baja cuando el servidor la rechazaría (uno mismo / último admin)', () => {
    expect(listSource).toContain('canDeactivate');
  });

  it('ya no duplica una pestaña de usuarios: el personal ES la lista de usuarios', () => {
    // `pinUsers` solo trae los que tienen PIN — era la razón de que faltase el owner.
    expect(listSource).not.toContain('pinUsers');
    expect(listSource).not.toContain("value=\"users\"");
  });

  it('marca el acceso y el estado de cada usuario en la tabla', () => {
    expect(listSource).toContain('has_pin');
    expect(listSource).toContain('is_active');
  });
});
