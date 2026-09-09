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

  it('la baja que falla en mudo dice «no se pudo dar de baja», no «no se pudo guardar» (hub#1190)', () => {
    // Regression test for ERPlora/hub#1190: al pasar la baja por `rejectionMessage` para traducir
    // `invalid_field`, el último recurso de un fallo mudo (red/500 sin código) pasó a ser
    // `employees.saveError` («Changes could not be saved»). Una baja no guarda nada: su frase
    // genérica es `employees.deleteError`, la que tenía antes.
    const deactivate = listSource.slice(
      listSource.indexOf('async function deactivateUser'),
      listSource.indexOf('const staffTable'),
    );
    expect(deactivate).toContain("t('employees.deleteError')");
    expect(deactivate).not.toContain('employees.saveError');
  });

  it('marca el acceso y el estado de cada usuario en la tabla', () => {
    expect(listSource).toContain('has_pin');
    expect(listSource).toContain('is_active');
  });

  // ── hub#988: la placa se da de alta pasándola O acercándola ────────────────────────────────
  //
  // El alta de una tarjeta es «pásala», el gesto que usa el mercado (Square, Toast, Aloha). En una
  // tablet no hay lector USB que pasarla por, y el lector lleva dentro del aparato desde siempre.

  it('el campo de la placa NO se suscribe al NFC: escucha la puerta común', () => {
    // La condición de diseño de la issue. Si esta pantalla llegara a importar el lector NFC para
    // recibir tarjetas, habría dos caminos de placa que mantener —y el diálogo de aprobación y el
    // login tendrían que crecer el suyo—. El toque entra por `onBadgeScan`, como la ráfaga.
    expect(formSource).toContain('onBadgeScan');
    expect(formSource).not.toContain('erplora_nfc_read');
    expect(formSource).not.toContain('installNfcBadgeReader');
  });

  it('solo promete «acércala» donde el aparato sabe leerla', () => {
    // `nfcBadgeReady` se enciende cuando el shell ha atendido una lectura de VERDAD. Ramificar por
    // `isTauri()` prometería el toque en cada instalación de escritorio, y una instrucción que no
    // funciona es peor que no darla.
    expect(formSource).toContain('nfcBadgeReady');
    expect(formSource).toContain('badgeNfcHelp');
    expect(formSource).not.toMatch(/isTauri\(\)[^\n]*badge/i);
  });
});

// ── hub#1697 · el peldaño que faltaba en la escalera ──────────────────────────────────────────
//
// Las guardas de `/api/hub/users` (`hub_users.rs`) rechazan con un código estable —`last_admin`,
// `self_deactivation`, `self_badge_enrollment`, `not_found`— y un `message` escrito DENTRO del
// runtime. `hubUserErrorKey` no cubre esos códigos (va por prefijo), así que caían al último
// recurso y la persona leía la prosa del motor. Ahora tienen frase.
//
// Se comprueba sobre el FUENTE, como el resto de este fichero: lo que puede regresar aquí es el
// ORDEN de la escalera, y estas dos pantallas no tienen banco de montaje. El comportamiento del
// traductor lo prueban `lib/runtime-error-sentence.test.ts` (unidad) y
// `views/RolesPanel.invalid-field.test.ts` (montado de verdad, mismo patrón).
describe('la escalera del rechazo traduce el código ANTES de rendirse (hub#1697)', () => {
  const ladders: ReadonlyArray<readonly [string, string, string]> = [
    ['EmployeesPage', listSource, 'function rejectionMessage'],
    ['EmployeeFormPage', formSource, 'function employeeRejection'],
  ];

  it.each(ladders)('%s traduce por código antes del último recurso', (_name, source, marker) => {
    const start = source.indexOf(marker);
    expect(start, `${marker} no está en el fuente`).toBeGreaterThan(-1);
    const ladder = source.slice(start, source.indexOf('\n}', start));

    const translates = ladder.indexOf('runtimeErrorKey');
    const lastResort = ladder.indexOf('error.message');
    expect(translates, 'la escalera no traduce por código').toBeGreaterThan(-1);
    expect(lastResort, 'el último recurso de la regla 2 de hub#1102 ya no está').toBeGreaterThan(-1);
    // El orden ES el contrato: traducir DESPUÉS de rendirse no traduciría nunca.
    expect(translates).toBeLessThan(lastResort);
  });

  it('el catálogo tiene las cuatro frases que ese peldaño necesita', () => {
    const catalogue = readFileSync(new URL('../i18n/locales/es.ts', import.meta.url), 'utf8');
    for (const code of ['last_admin', 'self_deactivation', 'self_badge_enrollment']) {
      expect(catalogue, `falta la frase de ${code}`).toContain(`${code}: '`);
    }
  });
});
